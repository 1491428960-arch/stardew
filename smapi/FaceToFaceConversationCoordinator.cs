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
    private readonly Action? onReturnToRoster;
    private readonly NpcKissAnimationController kissAnimationController = new();
    private ConversationService? conversationService;
    private StardewNpc? npc;
    private FaceToFaceConversationState state =
        new(FaceToFaceState.Idle, null);
    /// <summary>
    /// **当前挂着的那个会话窗口**挂在哪条频道上；没有窗口时为 <c>null</c>。
    ///
    /// 2026-09-21 补。改前「频道」只作为「刚关掉的那个窗口」的临时属性存在
    /// （04773f6 在 <c>OnMenuChanged</c> 里读 <c>closedChat.ChatChannel</c>），
    /// 于是**只有「退到世界」那一条出口**能看见它：走 <c>exitThisMenu</c>、
    /// 被背包选择器顶掉、被别的菜单替换时，读到的都是「没有频道」。
    /// 提成会话状态之后，任何出口都能问一句「这段会话是线上的吗」。
    /// </summary>
    private string? activeChannel;
    private StardewNpc? lastChatNpc;
    private int? lastChatDay;
    private StardewNpc? kissNpc;
    private int? kissDay;
    private bool disposed;

    public FaceToFaceConversationCoordinator(
        ConversationService? conversationService,
        StoryStateStore storyStateStore,
        Action<StardewNpc?>? runtimeDialogueObserver = null,
        ShareFriendshipLedger? shareFriendshipLedger = null,
        Action? onReturnToRoster = null)
    {
        this.conversationService = conversationService;
        this.storyStateStore = storyStateStore ??
            throw new ArgumentNullException(nameof(storyStateStore));
        this.runtimeDialogueObserver = runtimeDialogueObserver;
        this.shareFriendshipLedger = shareFriendshipLedger ?? new ShareFriendshipLedger();
        this.onReturnToRoster = onReturnToRoster;
    }

    public FaceToFaceConversationState State => state;

    public void ResetRepeatTarget()
    {
        lastChatNpc = null;
        lastChatDay = null;
        kissAnimationController.Reset();
        kissNpc = null;
        kissDay = null;
        // 切场景／跨天：一次会话不可能横跨这两个事件，所以**任何**面对面中间态
        // 到这儿都已经失效。改前只清亲吻两态，Composing（聊天窗被 F8/F9 顶掉后留下的）
        // 与 AwaitingContinuationChoice（提问框被别的菜单顶掉后留下的）会一直挂着，
        // 之后被任意一次 DialogueBox 关闭捡起来弹「要继续聊聊吗？」。
        // 顺带把 npc 也丢掉——那个人多半已经不在这个场景里了。
        state = FaceToFaceStateRules.EndFaceToFaceSessionForRemote(state);
        npc = null;
        activeChannel = null;
    }

    /// <summary>
    /// 从私聊名单（F8）里选了一位**同处一地**的角色：走面对面频道。
    ///
    /// 本方法是**名单专用入口**（唯一的调用点是 <c>ModEntry.StartPrivateChat</c>），
    /// 所以 <paramref name="openedFromPrivateChatRoster"/> 由调用方显式给出、
    /// 不给默认值——将来若多了别的调用点，必须自己回答「这次算不算 F8 打开的」。
    ///
    /// 名单来源只影响「退出后要不要问一句要继续聊聊吗」（用户口径「F8 一律不算当面」），
    /// 频道本身仍是面对面：送礼、亲吻、当面描述都不因此改变。
    /// </summary>
    public bool TryOpenChat(StardewNpc target, bool openedFromPrivateChatRoster)
    {
        ArgumentNullException.ThrowIfNull(target);
        if (disposed || conversationService is null ||
            kissNpc is not null || state.State == FaceToFaceState.Kissing)
        {
            return false;
        }

        npc = target;
        activeChannel = ConversationChannel.FaceToFace;
        state = new FaceToFaceConversationState(
            FaceToFaceState.Composing,
            target.Name);
        OpenChatMenu(target, openedFromPrivateChatRoster);
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
    public bool TryOpenRemoteChat(StardewNpc target, bool openedFromPrivateChatRoster)
    {
        ArgumentNullException.ThrowIfNull(target);
        if (disposed || conversationService is null ||
            kissNpc is not null || state.State == FaceToFaceState.Kissing)
        {
            return false;
        }

        EndRemoteChatSession();
        activeChannel = ConversationChannel.Remote;

        Game1.activeClickableMenu = new ChatInputMenu(
            target,
            conversationService,
            storyStateStore,
            OnRemoteChatClosed,
            initialMessages: conversationService.RecentMessages(target.Name),
            conversationChannel: ConversationChannel.Remote,
            openedFromPrivateChatRoster: openedFromPrivateChatRoster,
            onReturnToRoster: onReturnToRoster,
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
        OpenChatMenu(candidate, openedFromPrivateChatRoster: false);
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

        // 原版寒暄：开一个 DialogueBox。线上会话窗还挂着时不认它——那时候弹出来的
        // 对话框只可能是 Mod 自己的（送礼确认那类），把它当成「又一次当面寒暄」
        // 会用 Game1.currentSpeaker 这个跨对话残留字段整个重写 npc 与状态。
        if (e.NewMenu is DialogueBox &&
            !FaceToFaceStateRules.IsRemoteChannel(activeChannel) &&
            FaceToFaceStateRules.ShouldObserveDialogueOpened(state))
        {
            ObserveDialogueOpened();
            return;
        }

        // 线上会话的窗口离开 activeClickableMenu：一律不进面对面状态机——不弹续聊提问、
        // 不武装亲吻，并把会话状态收敛回空闲。
        //
        // 判据是**那个窗口自己的频道**，不是「关闭回调有没有被调用」：ChatInputMenu 的
        // onClosed 只在 Close()（Esc／「结束」按钮）里触发，走 exitThisMenu 一类路径
        // 退出时不会执行（ModEntry 里就有两处这样退菜单），那时 npc 会留着上一位
        // 面对面角色，下面那条续聊分支就会拿他弹窗。
        //
        // 2026-09-21：这里**不再要求 e.NewMenu is null**。04773f6 只堵了「退到世界」
        // 那一种，而 ChatInputMenu 还有一条直接替换的退出路径——OpenInventoryPicker
        // 把 activeClickableMenu 换成背包选择器，之后再也没人回到这条判定上。
        // 只要离开的是线上频道窗口，无论接下来挂上的是什么，都先把状态收干净。
        if (e.OldMenu is ChatInputMenu closingChat &&
            FaceToFaceStateRules.IsRemoteChannel(closingChat.ChatChannel))
        {
            EndRemoteChatSession();
            activeChannel = null;
            if (e.NewMenu is null)
            {
                return;
            }
        }

        // 面对面会话退出：照旧问一句要不要继续。判定与第二个出口（DialogueBox 关闭）
        // 共用 ShouldOfferContinuationAfterExit，频道、「人还在不在旁边」、
        // 以及「这次是不是从 F8 名单打开的」都是输入。
        //
        // 最前面那条线上分支已经带走了 remote 窗口；走到这里的窗口**都是面对面频道**，
        // 包括 F8 打开、而人恰好站在旁边的那些——它们由窗口自己的来源标记挡住提问。
        if (e.OldMenu is ChatInputMenu faceToFaceChat)
        {
            activeChannel = null;
            if (e.NewMenu is null)
            {
                if (FaceToFaceStateRules.ShouldOfferContinuationAfterExit(
                        state,
                        faceToFaceChat.ChatChannel,
                        hasSpeaker: npc is not null,
                        speakerStillHere: npc is not null && IsSameLocationAndNearby(npc),
                        openedFromPrivateChatRoster: faceToFaceChat.OpenedFromPrivateChatRoster))
                {
                    OfferContinuationChoice(npc!);
                    return;
                }

                // 不弹也得把残留收干净：见 ClearContinuationLeftover 的注释。
                ClearContinuationLeftover();
            }
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
        activeChannel = null;
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
        // 原版对话永远属于「面对面」那条频道：它要么就是我们自己弹的续聊提问
        // （已在上面被 ShouldObserveDialogueOpened 挡住），要么是玩家当面搭话。
        activeChannel = ConversationChannel.FaceToFace;
        state = FaceToFaceStateRules.StartForNpc(
            currentSpeaker?.Name,
            eventUp: Game1.eventUp,
            festival: Game1.isFestival());
        state = FaceToFaceStateRules.ObserveDialogueOpened(state);
    }

    /// <summary>
    /// **第二个弹窗出口**：原版 DialogueBox 关闭。改前这里只有一句
    /// <c>state == AwaitingContinuationChoice &amp;&amp; npc is not null</c> ——
    /// 正是 04773f6 自己定义的根因形态（"只看 state 与 npc 两个跨会话字段"）。
    /// 现在与聊天窗那条出口共用 <see cref="FaceToFaceStateRules.ShouldOfferContinuationAfterExit"/>。
    ///
    /// **不弹的时候也要把残留收干净**：能弹的残留（AwaitingContinuationChoice）
    /// 若留在这里，下一次任何 DialogueBox 关闭都会把它再捡起来 —— 那正是
    /// 「明明没开会话，却突然弹出要继续聊聊吗」的来源。
    /// </summary>
    private void ObserveDialogueClosed()
    {
        state = FaceToFaceStateRules.ObserveDialogueClosed(state);
        if (FaceToFaceStateRules.ShouldOfferContinuationAfterExit(
                state,
                activeChannel,
                hasSpeaker: npc is not null,
                speakerStillHere: npc is not null && IsSameLocationAndNearby(npc),
                openedFromPrivateChatRoster: IsRosterChatStillOpen()))
        {
            OfferContinuationChoice(npc!);
            return;
        }

        ClearContinuationLeftover();
    }

    /// <summary>
    /// 会话结束却不弹续聊提问时，把**还能弹出来的残留**收干净。
    ///
    /// 能弹的残留只有一种：状态停在 <see cref="FaceToFaceState.AwaitingContinuationChoice"/>。
    /// 它是**跨会话**的字段，一旦留着，之后任意一次 <c>DialogueBox</c> 关闭都会经
    /// <see cref="ObserveDialogueClosed"/> 把它推成那句提问——与本次会话是谁毫无关系。
    /// 两个出口（聊天窗关闭、原版 DialogueBox 关闭）在不弹时都必须调用这里，
    /// 否则「不弹」只是把提问推迟到下一次对话。
    /// </summary>
    private void ClearContinuationLeftover()
    {
        if (state.State == FaceToFaceState.AwaitingContinuationChoice)
        {
            state = FaceToFaceStateRules.DismissContinuationChoice(state);
        }

        if (state.State == FaceToFaceState.Idle)
        {
            npc = null;
        }
    }

    /// <summary>
    /// 走「原版 DialogueBox 关闭」这条出口时，那个**从名单打开的聊天窗**是不是还挂在
    /// <c>Game1.activeClickableMenu</c> 上。
    ///
    /// 名单会话的窗口关闭走的是第一个出口（那时新菜单为 <c>null</c>，OldMenu 就是它自己），
    /// 所以这条出口原则上碰不到名单会话；保留这一问是为了两个出口对「名单来源」的读法同源，
    /// 而不是让第二个出口凭一句写死的 false 假装名单不存在。
    /// </summary>
    private static bool IsRosterChatStillOpen()
    {
        return Game1.activeClickableMenu is ChatInputMenu
        {
            OpenedFromPrivateChatRoster: true,
        };
    }

    /// <summary>
    /// 说话人此刻是不是还「就在旁边」：同一地点、且在续聊距离（
    /// <see cref="FaceToFaceStateRules.RepeatChatNearbyDistanceInTiles"/>）以内。
    ///
    /// 续聊提问的用途是「接着当面聊」，所以门槛与续聊入口
    /// （<c>TryOpenRepeatChat</c>）对齐；比它宽松的话，一个已经走开、
    /// 甚至换了地图的残留角色也能让提问弹出来。
    /// </summary>
    private static bool IsSameLocationAndNearby(StardewNpc candidate)
    {
        return ReferenceEquals(candidate.currentLocation, Game1.currentLocation) &&
            IsNearby(candidate);
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
        // 与另外两个面对面入口共用同一处构造（参数逐字相同，改前这里是第二份拷贝）。
        OpenChatMenu(speaker, openedFromPrivateChatRoster: false);
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

    private void OpenChatMenu(StardewNpc target, bool openedFromPrivateChatRoster)
    {
        if (conversationService is null)
        {
            return;
        }

        // 打开时先把已累积的历史铺进消息区（只读回看），之后本次会话的新消息继续往后追加。
        // 历史来自 SMAPI 侧的记忆，读多少、怎么映射见 ChatHistoryRules；
        // 发给模型的窗口不受影响。
        //
        // 三个调用点里只有名单入口（TryOpenChat）会传 true；续聊入口
        // （TryOpenRepeatChat／HandleContinuationChoice）都是「玩家走到跟前按了交互键」
        // 那条路，退出后该照旧问一句要不要继续。
        activeChannel = ConversationChannel.FaceToFace;
        Game1.activeClickableMenu = new ChatInputMenu(
            target,
            conversationService,
            storyStateStore,
            OnChatClosed,
            initialMessages: conversationService.RecentMessages(target.Name),
            conversationChannel: ConversationChannel.FaceToFace,
            openedFromPrivateChatRoster: openedFromPrivateChatRoster,
            onReturnToRoster: onReturnToRoster,
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
