using StardewModdingAPI;
using StardewModdingAPI.Events;
using Microsoft.Xna.Framework;
using StardewValley;
using StardewValley.Menus;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

/// <summary>
/// 观察原版 DialogueBox 和 AI 聊天菜单的生命周期，允许同一天连续续聊。
/// </summary>
public sealed class FaceToFaceConversationCoordinator
{
    private readonly StoryStateStore storyStateStore;
    private readonly Action<StardewNpc?>? runtimeDialogueObserver;
    private readonly ShareFriendshipLedger shareFriendshipLedger;
    private readonly NpcKissAnimationController kissAnimationController = new();
    private ConversationService? conversationService;
    private StardewNpc? npc;
    private FaceToFaceConversationState state =
        new(FaceToFaceState.Idle, null);
    private StardewNpc? lastChatNpc;
    private int? lastChatDay;
    private StardewNpc? kissNpc;
    private int? kissDay;
    private bool disposed;

    public FaceToFaceConversationCoordinator(
        ConversationService? conversationService,
        StoryStateStore storyStateStore,
        Action<StardewNpc?>? runtimeDialogueObserver = null,
        ShareFriendshipLedger? shareFriendshipLedger = null)
    {
        this.conversationService = conversationService;
        this.storyStateStore = storyStateStore ??
            throw new ArgumentNullException(nameof(storyStateStore));
        this.runtimeDialogueObserver = runtimeDialogueObserver;
        this.shareFriendshipLedger = shareFriendshipLedger ?? new ShareFriendshipLedger();
    }

    public FaceToFaceConversationState State => state;

    public void ResetRepeatTarget()
    {
        lastChatNpc = null;
        lastChatDay = null;
        kissAnimationController.Reset();
        kissNpc = null;
        kissDay = null;
        if (state.State is FaceToFaceState.AwaitingKiss or FaceToFaceState.Kissing)
        {
            state = new FaceToFaceConversationState(FaceToFaceState.Idle, null);
            npc = null;
        }
    }

    public bool TryOpenChat(StardewNpc target)
    {
        ArgumentNullException.ThrowIfNull(target);
        if (disposed || conversationService is null ||
            kissNpc is not null || state.State == FaceToFaceState.Kissing)
        {
            return false;
        }

        npc = target;
        state = new FaceToFaceConversationState(
            FaceToFaceState.Composing,
            target.Name);
        OpenChatMenu(target);
        return true;
    }

    /// <summary>
    /// 从私聊名单里选了一位**不在同一地点**的角色：走线上频道（B26）。
    ///
    /// <c>channel=remote</c> 与 F9 群聊是同一条语义：只表达当前想法或提出待确认的安排、
    /// 不写成已经见面；不传送 NPC、不改日程。Bridge 侧对这条频道有独立的越界判定，
    /// 以及「线上留下的约定等见面再兑现」的 open loop 规则，所以这里不需要额外处理。
    ///
    /// 刻意**不**进入面对面的状态机：续聊提问与吻别的前提都是人就在旁边。
    /// 关闭后不记续聊目标、不武装亲吻，直接回到世界（名单随时可以再开）。
    ///
    /// 「不进状态机」是在**两端**都落实的（<see cref="EndRemoteChatSession"/>）：
    /// 打开前先把可能残留的面对面中间态收干净，关闭后再收一次。只靠在关闭回调里
    /// 清 npc 是不够的——那条回调只在 <c>ChatInputMenu.Close()</c> 里触发，
    /// 走 <c>exitThisMenu</c> 一类路径退出时不会执行，残留的
    /// <c>AwaitingContinuationChoice</c>＋上一位面对面角色就会把续聊提问弹出来
    /// （用户实测反馈）。
    /// </summary>
    public bool TryOpenRemoteChat(StardewNpc target)
    {
        ArgumentNullException.ThrowIfNull(target);
        if (disposed || conversationService is null ||
            kissNpc is not null || state.State == FaceToFaceState.Kissing)
        {
            return false;
        }

        EndRemoteChatSession();

        Game1.activeClickableMenu = new ChatInputMenu(
            target,
            conversationService,
            storyStateStore,
            OnRemoteChatClosed,
            initialMessages: conversationService.RecentMessages(target.Name),
            conversationChannel: ConversationChannel.Remote,
            shareFriendshipLedger: shareFriendshipLedger);
        return true;
    }

    private void OnRemoteChatClosed(bool valuableRelationshipRepair)
    {
        _ = valuableRelationshipRepair;
        EndRemoteChatSession();
    }

    /// <summary>
    /// 线上会话的收尾（打开前与关闭后共用同一处实现）：丢掉面对面会话目标，
    /// 并把状态机收敛回空闲。这样线上既不继承上一次面对面的中间态，
    /// 也不给下一次留下能弹续聊提问的残留。
    /// </summary>
    private void EndRemoteChatSession()
    {
        npc = null;
        state = FaceToFaceStateRules.EndFaceToFaceSessionForRemote(state);
    }

    public bool TryConsumePendingKiss(Vector2 interactionTile)
    {
        if (state.State == FaceToFaceState.Kissing)
        {
            return true;
        }

        var candidate = kissNpc;
        if (candidate is null ||
            !FaceToFaceStateRules.InteractionTargetsRememberedNpc(
                candidate.GetBoundingBox(),
                interactionTile,
                Game1.tileSize))
        {
            return false;
        }

        // A pending kiss has priority over repeat chat. Keep it armed when
        // the original action cannot run yet, so a later right-click can
        // retry after the player is nearby and free to act.
        if (!CanTriggerPendingKiss(candidate))
        {
            return true;
        }

        if (!kissAnimationController.TryStart(candidate, OnKissCompleted))
        {
            return true;
        }

        kissNpc = null;
        kissDay = null;
        state = FaceToFaceStateRules.BeginKiss(state);
        return true;
    }

    public bool TryOpenRepeatChat(Vector2 interactionTile)
    {
        if (kissNpc is not null || state.State == FaceToFaceState.Kissing)
        {
            return false;
        }

        var candidate = lastChatNpc;
        var sameLocation = candidate is not null &&
            ReferenceEquals(candidate.currentLocation, Game1.currentLocation);
        var npcNearby = candidate is not null && IsNearby(candidate);
        var npcTargeted = candidate is not null &&
            FaceToFaceStateRules.InteractionTargetsRememberedNpc(
                candidate.GetBoundingBox(),
                interactionTile,
                Game1.tileSize);
        if (!FaceToFaceStateRules.CanStartRepeatChat(
                CaptureGate(lastChatDay, sameLocation, npcNearby)) ||
            !npcTargeted ||
            conversationService is null)
        {
            return false;
        }

        npc = candidate;
        state = new FaceToFaceConversationState(
            FaceToFaceState.Composing,
            candidate!.Name);
        OpenChatMenu(candidate);
        return true;
    }

    public void OnUpdateTicked(object? sender, UpdateTickedEventArgs e)
    {
        _ = sender;
        _ = e;
        if (disposed || state.State != FaceToFaceState.Kissing)
        {
            return;
        }

        kissAnimationController.Update(Game1.currentGameTime);
    }

    public void UpdateService(ConversationService? service)
    {
        if (disposed)
        {
            return;
        }

        conversationService = service;
        if (service is null)
        {
            Reset();
        }
    }

    public void OnMenuChanged(object? sender, MenuChangedEventArgs e)
    {
        if (disposed || conversationService is null || !Context.IsWorldReady)
        {
            return;
        }

        if (e.NewMenu is DialogueBox &&
            FaceToFaceStateRules.ShouldObserveDialogueOpened(state))
        {
            ObserveDialogueOpened();
            return;
        }

        // 线上会话退出：一律不进面对面状态机——不弹续聊提问、不武装亲吻，
        // 并把会话状态收敛回空闲。
        //
        // 判据是**刚关掉的那个窗口自己的频道**，不是「关闭回调有没有被调用」：
        // ChatInputMenu 的 onClosed 只在 Close()（Esc／「结束」按钮）里触发，
        // 走 exitThisMenu 一类路径退出时不会执行（ModEntry 里就有两处这样退菜单），
        // 那时 npc 会留着上一位面对面角色，下面那条续聊分支就会拿他弹窗。
        if (e.NewMenu is null &&
            e.OldMenu is ChatInputMenu closedChat &&
            FaceToFaceStateRules.IsRemoteChannel(closedChat.ChatChannel))
        {
            EndRemoteChatSession();
            return;
        }

        // 面对面会话退出：照旧问一句要不要继续。
        if (e.NewMenu is null &&
            e.OldMenu is ChatInputMenu &&
            FaceToFaceStateRules.ShouldOfferContinuationAfterChatClosed(
                state,
                remoteChannelClosed: false,
                hasSpeaker: npc is not null))
        {
            OfferContinuationChoice(npc!);
            return;
        }

        if (e.OldMenu is DialogueBox && e.NewMenu is null &&
            state.State == FaceToFaceState.AwaitingContinuationChoice)
        {
            // The continuation question itself is a DialogueBox. If it closes
            // without an answer callback (Esc/right-click), end only this
            // prompt instead of immediately opening it again.
            var repeatTarget = npc;
            state = FaceToFaceStateRules.DismissContinuationChoice(state);
            if (repeatTarget is not null)
            {
                RememberRepeatTarget(repeatTarget);
            }
            npc = null;
            return;
        }

        if (e.OldMenu is DialogueBox && e.NewMenu is null)
        {
            ObserveDialogueClosed();
        }
    }

    public void Reset()
    {
        kissAnimationController.Reset();
        state = new FaceToFaceConversationState(FaceToFaceState.Idle, null);
        npc = null;
        lastChatNpc = null;
        lastChatDay = null;
        kissNpc = null;
        kissDay = null;
    }

    public void Dispose()
    {
        disposed = true;
        conversationService = null;
        Reset();
    }

    private void ObserveDialogueOpened()
    {
        var currentSpeaker = Game1.currentSpeaker;
        runtimeDialogueObserver?.Invoke(currentSpeaker);
        npc = currentSpeaker;
        state = FaceToFaceStateRules.StartForNpc(
            currentSpeaker?.Name,
            eventUp: Game1.eventUp,
            festival: Game1.isFestival());
        state = FaceToFaceStateRules.ObserveDialogueOpened(state);
    }

    private void ObserveDialogueClosed()
    {
        state = FaceToFaceStateRules.ObserveDialogueClosed(state);
        if (state.State == FaceToFaceState.AwaitingContinuationChoice && npc is not null)
        {
            OfferContinuationChoice(npc);
        }
        else if (state.State == FaceToFaceState.Idle)
        {
            npc = null;
        }
    }

    private void OfferContinuationChoice(StardewNpc speaker)
    {
        if (Game1.currentLocation is null || Game1.activeClickableMenu is not null)
        {
            return;
        }

        var responses = new[]
        {
            new Response("continue", "继续聊聊"),
            new Response("leave", "先告辞"),
        };
        Game1.currentLocation.createQuestionDialogue(
            "要继续聊聊吗？",
            responses,
            (farmer, answer) => HandleContinuationChoice(answer, speaker),
            speaker);
    }

    private void HandleContinuationChoice(string answer, StardewNpc speaker)
    {
        if (disposed || conversationService is null)
        {
            Reset();
            return;
        }

        state = FaceToFaceStateRules.ChooseContinuation(
            state,
            continueChat: string.Equals(answer, "continue", StringComparison.Ordinal));
        if (state.State != FaceToFaceState.Composing)
        {
            // “先告辞”只结束当前菜单，不结束当天与该 NPC 的互动对象。
            // 这样再次按交互键时仍能打开新的聊天，而不会退化为只能聊一次。
            RememberRepeatTarget(speaker);
            npc = null;
            return;
        }

        npc = speaker;
        Game1.activeClickableMenu = new ChatInputMenu(
            speaker,
            conversationService,
            storyStateStore,
            OnChatClosed,
            initialMessages: conversationService.RecentMessages(speaker.Name),
            conversationChannel: ConversationChannel.FaceToFace,
            shareFriendshipLedger: shareFriendshipLedger);
    }

    private void OnChatClosed(bool valuableRelationshipRepair)
    {
        if (valuableRelationshipRepair && npc is not null && CanArmKiss(npc))
        {
            state = FaceToFaceStateRules.ArmKissAfterReply(state);
            kissNpc = npc;
            kissDay = Game1.Date.TotalDays;
            return;
        }

        state = FaceToFaceStateRules.ObserveDialogueClosed(state);
        if (state.State == FaceToFaceState.AwaitingContinuationChoice && npc is not null)
        {
            RememberRepeatTarget(npc);
        }
        if (state.State == FaceToFaceState.Idle)
        {
            npc = null;
        }
    }

    private bool CanArmKiss(StardewNpc speaker)
    {
        var gameState = GameStateCollector.Collect(speaker);
        var customRelationshipType = storyStateStore.State.Relationships
            .Where(relationship =>
                string.Equals(relationship.FromNpcId, "player", StringComparison.OrdinalIgnoreCase) &&
                string.Equals(relationship.ToNpcId, speaker.Name, StringComparison.OrdinalIgnoreCase))
            .Select(relationship => relationship.RelationType)
            .FirstOrDefault();
        return KissInteractionRules.CanArmAfterReply(
            effectiveReply: true,
            RelationshipStageRules.ResolveKey(gameState),
            customRelationshipType);
    }

    private bool CanTriggerPendingKiss(StardewNpc candidate)
    {
        var player = Game1.player;
        return KissInteractionRules.CanTriggerKiss(
            CaptureGate(
                kissDay,
                sameLocation: ReferenceEquals(
                    candidate.currentLocation,
                    Game1.currentLocation),
                npcNearby: IsNearby(candidate)),
            playerCanMove: player?.CanMove == true,
            usingTool: player?.UsingTool == true,
            ridingHorse: player?.isRidingHorse() == true,
            sitting: player?.IsSitting() == true);
    }

    /// <summary>
    /// 面对面交互门槛的**唯一取值点**：续聊与亲吻共用同一批游戏状态，
    /// 不再各自把七个值拼一遍（审计 #34）。判定本身在 <see cref="FaceToFaceGate"/>。
    /// </summary>
    private static FaceToFaceGate CaptureGate(
        int? rememberedDay,
        bool sameLocation,
        bool npcNearby)
    {
        return new FaceToFaceGate(
            WorldReady: Context.IsWorldReady,
            MenuOpen: Game1.activeClickableMenu is not null,
            SameDay: FaceToFaceStateRules.IsSameGameDay(
                rememberedDay,
                Game1.Date.TotalDays),
            SameLocation: sameLocation,
            NpcNearby: npcNearby,
            EventUp: Game1.eventUp,
            Festival: Game1.isFestival());
    }

    private void OnKissCompleted(StardewNpc kissedNpc)
    {
        if (disposed || state.State != FaceToFaceState.Kissing)
        {
            return;
        }

        state = FaceToFaceStateRules.CompleteKiss(state);
        npc = null;
        RememberRepeatTarget(kissedNpc);
    }

    private void OpenChatMenu(StardewNpc target)
    {
        if (conversationService is null)
        {
            return;
        }

        // 打开时先把已累积的历史铺进消息区（只读回看），之后本次会话的新消息继续往后追加。
        // 历史来自 SMAPI 侧的记忆，读多少、怎么映射见 ChatHistoryRules；
        // 发给模型的窗口不受影响。
        Game1.activeClickableMenu = new ChatInputMenu(
            target,
            conversationService,
            storyStateStore,
            OnChatClosed,
            initialMessages: conversationService.RecentMessages(target.Name),
            conversationChannel: ConversationChannel.FaceToFace,
            shareFriendshipLedger: shareFriendshipLedger);
    }

    private void RememberRepeatTarget(StardewNpc speaker)
    {
        lastChatNpc = speaker;
        lastChatDay = Game1.Date.TotalDays;
    }

    private static bool IsNearby(StardewNpc candidate)
    {
        var distance = Vector2.Distance(candidate.Position, Game1.player.Position);
        return distance <= Game1.tileSize * FaceToFaceStateRules.RepeatChatNearbyDistanceInTiles;
    }
}
