using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

public enum FaceToFaceState
{
    Idle,
    VanillaDialogueOpen,
    AwaitingContinuationChoice,
    Composing,
    AwaitingKiss,
    Kissing,
}

public sealed record FaceToFaceConversationState(
    FaceToFaceState State,
    string? NpcId);

/// <summary>
/// 一次面对面交互（续聊、亲吻）共用的**游戏状态门槛快照**。
///
/// 2026-09-20（语义层审计 #34）：这七个取值此前在
/// <see cref="FaceToFaceConversationCoordinator"/> 的两个方法体里各拼一次
/// ——续聊侧 7 个实参、亲吻侧 11 个（前 7 个逐字相同），两处无任何共享点，
/// 一旦其中一个条件变化就会静默漂移。现在取值与判定都只此一处。
/// </summary>
public sealed record FaceToFaceGate(
    bool WorldReady,
    bool MenuOpen,
    bool SameDay,
    bool SameLocation,
    bool NpcNearby,
    bool EventUp,
    bool Festival)
{
    /// <summary>续聊与亲吻共同要求的七项是否全部成立。</summary>
    public bool AllowsInteraction =>
        WorldReady && !MenuOpen && SameDay && SameLocation && NpcNearby && !EventUp && !Festival;
}

public static class FaceToFaceStateRules
{
    /// <summary>
    /// 续聊（交互键）要求「上次记住的 NPC」在多近之内。
    ///
    /// 注意：**F8 入口没有这条距离上限**（它只按距离排序，见
    /// <see cref="NpcTargetResolver.SelectFriendshipTarget"/>），所以「F8 能聊到的 NPC」
    /// 与「能续聊的 NPC」集合本就不同（审计 #35，与待办 B26 相关）。
    /// 这里只把数值收敛成一个有名常量，判定口径不变。
    /// </summary>
    public const float RepeatChatNearbyDistanceInTiles = 2.5f;

    /// <summary>
    /// 一次 DialogueBox 打开时，要不要把它当成「玩家正在跟 NPC 当面说话」。
    ///
    /// **Mod 自己弹的 DialogueBox 与玩家自己弹的 DialogueBox 长得一模一样**
    /// （续聊提问、送礼确认都是 <c>createQuestionDialogue</c>），所以这里要按
    /// **状态**把它们排除掉，而不能只看「新菜单是 DialogueBox」：
    ///
    /// - <see cref="FaceToFaceState.AwaitingContinuationChoice"/>：续聊提问本身。
    ///   放它进来的话，提问会在回答回调跑之前先把状态重置成原版对话态
    ///   （2026-09-20 的既有防护）。
    /// - <see cref="FaceToFaceState.Composing"/>：**AI 聊天窗还开着**。
    ///   2026-09-21 补。改前这份排除表漏了它，于是玩家在聊天窗里送礼时，
    ///   那个确认框会被当成「又一次原版寒暄」：状态被顶成
    ///   <see cref="FaceToFaceState.VanillaDialogueOpen"/>，而 <c>npc</c> 被
    ///   <c>Game1.currentSpeaker</c> 整个重写（这个字段是跨对话残留的，可能是别人、
    ///   也可能已经是 null）。此后任意一次 DialogueBox 关闭都会经第二个出口
    ///   把那份被污染的状态推成「要继续聊聊吗？」——**与本次会话是谁毫无关系**。
    ///   聊天窗开着时玩家不可能再去跟别的 NPC 交互，所以这条排除不会误伤原版对话。
    /// - 亲吻两态：动画进行中不该被任何对话框打断。
    ///
    /// 线上会话那条另有防线（协调器按频道判定，见
    /// <see cref="ShouldOfferContinuationAfterExit"/>）：线上不进面对面状态机。
    /// </summary>
    public static bool ShouldObserveDialogueOpened(
        FaceToFaceConversationState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        return state.State is not FaceToFaceState.AwaitingContinuationChoice and
            not FaceToFaceState.Composing and
            not FaceToFaceState.AwaitingKiss and
            not FaceToFaceState.Kissing;
    }

    public static bool CanStartRepeatChat(FaceToFaceGate gate)
    {
        ArgumentNullException.ThrowIfNull(gate);
        return gate.AllowsInteraction;
    }

    /// <summary>
    /// 这次会话是不是线上频道（<c>channel=remote</c>，人不在同一地点）。
    /// </summary>
    public static bool IsRemoteChannel(string? channel)
    {
        return string.Equals(
            channel,
            ConversationChannel.Remote,
            StringComparison.Ordinal);
    }

    /// <summary>
    /// 线上会话开启／结束时，把**面对面**的会话状态收敛回空闲。
    ///
    /// 线上刻意不进面对面那套状态机——续聊提问与吻别的前提都是人就在旁边
    /// （见 <see cref="FaceToFaceConversationCoordinator.TryOpenRemoteChat"/>）。
    /// 但状态是**跨会话**的字段：一次被打断的面对面会话会把
    /// <see cref="FaceToFaceState.Composing"/>／<see cref="FaceToFaceState.AwaitingContinuationChoice"/>
    /// 留在里面，之后任何一次 DialogueBox 或聊天窗关闭都可能把它捡起来，
    /// 弹出本该只在当面出现的续聊提问。所以线上会话的两端都必须显式收干净。
    ///
    /// 亲吻两态原样保留：亲吻动画进行中不该被线上会话打断
    /// （线上入口本就会在亲吻未消费时拒绝打开）。
    /// </summary>
    public static FaceToFaceConversationState EndFaceToFaceSessionForRemote(
        FaceToFaceConversationState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        return state.State is FaceToFaceState.AwaitingKiss or FaceToFaceState.Kissing
            ? state
            : new FaceToFaceConversationState(FaceToFaceState.Idle, null);
    }

    /// <summary>
    /// 一次聊天窗关闭（回到世界）之后，要不要弹「要继续聊聊吗？」。
    ///
    /// **频道是判定的一部分**：线上会话不进面对面状态机，无论状态里还留着什么、
    /// 手里还攥着哪位角色，都不弹。此前这里只看 state 与 npc，线上之所以"看起来"
    /// 不弹，只是因为 <c>OnRemoteChatClosed</c> 恰好把 npc 清了——那条回调只在
    /// <c>ChatInputMenu.Close()</c>（Esc／「结束」按钮）里被调用，走
    /// <c>exitThisMenu</c> 一类路径退出时不会触发，npc 于是留着上一位面对面角色，
    /// 提问照样弹出来。
    /// </summary>
    public static bool ShouldOfferContinuationAfterChatClosed(
        FaceToFaceConversationState state,
        bool remoteChannelClosed,
        bool hasSpeaker)
    {
        ArgumentNullException.ThrowIfNull(state);
        return !remoteChannelClosed &&
            state.State == FaceToFaceState.AwaitingContinuationChoice &&
            hasSpeaker;
    }

    /// <summary>
    /// 一次会话结束之后要不要弹「要继续聊聊吗？」——**两个出口共用这一个判定**。
    ///
    /// 出口一：<c>ChatInputMenu</c> 关闭（Esc／「结束」按钮／<c>exitThisMenu</c>／被别的菜单顶掉）。
    /// 出口二：原版 <c>DialogueBox</c> 关闭（协调器的 <c>ObserveDialogueClosed</c>）。
    ///
    /// 2026-09-21（用户第二次反馈「线上退出后又弹」）：<c>04773f6</c> 只把**频道**
    /// 接进了出口一，出口二至今仍写着「state 是待续聊 且 npc 非空就弹」——
    /// 那正是该提交自己定义的根因形态（原话：「弹窗出口只看 <c>state</c> 和 <c>npc</c>
    /// 两个跨会话字段，完全不看这次关闭的是哪条频道」）。它当时用「线上入口两端收敛」
    /// 间接盖住了出口二，但收敛只挂在**线上入口**上：任何不经过该入口的残留
    /// （面对面聊天被 F8/F9/背包选择器打断、切场景、回标题）都绕得过去。
    ///
    /// 现在两个出口都走这里：想弹就得同时过「不是线上频道」「状态是待续聊」
    /// 「手里有说话人」「那个人此刻真的还在旁边」四关。
    /// </summary>
    /// <param name="sessionChannel">刚结束的那次会话挂在哪条频道上（取值见 <see cref="ConversationChannel"/>）。</param>
    /// <param name="speakerStillHere">
    /// 说话人此刻是不是还在同一地点、且在续聊距离内。续聊入口
    /// （<c>TryOpenRepeatChat</c>）本来就要求这一条，弹窗不该比它更宽松 ——
    /// 否则残留的上一任角色会让一个**根本用不了**的提问冒出来。
    /// </param>
    public static bool ShouldOfferContinuationAfterExit(
        FaceToFaceConversationState state,
        string? sessionChannel,
        bool hasSpeaker,
        bool speakerStillHere)
    {
        ArgumentNullException.ThrowIfNull(state);
        return speakerStillHere &&
            ShouldOfferContinuationAfterChatClosed(
                state,
                remoteChannelClosed: IsRemoteChannel(sessionChannel),
                hasSpeaker: hasSpeaker);
    }

    public static bool IsSameGameDay(int? rememberedDay, int currentDay)
    {
        return rememberedDay.HasValue && rememberedDay.Value == currentDay;
    }

    public static bool InteractionTargetsRememberedNpc(
        Rectangle npcBounds,
        Vector2 grabTile,
        int tileSize)
    {
        if (tileSize <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(tileSize));
        }

        var interactionBounds = new Rectangle(
            (int)Math.Floor(grabTile.X) * tileSize,
            (int)Math.Floor(grabTile.Y) * tileSize,
            tileSize,
            tileSize);
        return npcBounds.Intersects(interactionBounds);
    }

    public static FaceToFaceConversationState DismissContinuationChoice(
        FaceToFaceConversationState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        return state.State == FaceToFaceState.AwaitingContinuationChoice
            ? new FaceToFaceConversationState(FaceToFaceState.Idle, null)
            : state;
    }

    public static FaceToFaceConversationState StartForNpc(
        string? npcId,
        bool eventUp = false,
        bool festival = false)
    {
        return string.IsNullOrWhiteSpace(npcId) || eventUp || festival
            ? new FaceToFaceConversationState(FaceToFaceState.Idle, null)
            : new FaceToFaceConversationState(FaceToFaceState.Idle, npcId.Trim());
    }

    public static FaceToFaceConversationState ObserveDialogueOpened(
        FaceToFaceConversationState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        return state.State == FaceToFaceState.Idle && state.NpcId is not null
            ? state with { State = FaceToFaceState.VanillaDialogueOpen }
            : state;
    }

    public static FaceToFaceConversationState ObserveDialogueClosed(
        FaceToFaceConversationState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        return state.State switch
        {
            FaceToFaceState.VanillaDialogueOpen => state with
            {
                State = FaceToFaceState.AwaitingContinuationChoice,
            },
            FaceToFaceState.Composing => state with
            {
                State = FaceToFaceState.AwaitingContinuationChoice,
            },
            _ => state,
        };
    }

    public static FaceToFaceConversationState ArmKissAfterReply(
        FaceToFaceConversationState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        return state.State == FaceToFaceState.Composing && state.NpcId is not null
            ? state with { State = FaceToFaceState.AwaitingKiss }
            : state;
    }

    public static FaceToFaceConversationState BeginKiss(
        FaceToFaceConversationState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        return state.State == FaceToFaceState.AwaitingKiss
            ? state with { State = FaceToFaceState.Kissing }
            : state;
    }

    public static FaceToFaceConversationState CompleteKiss(
        FaceToFaceConversationState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        return state.State == FaceToFaceState.Kissing
            ? new FaceToFaceConversationState(FaceToFaceState.Idle, null)
            : state;
    }

    public static FaceToFaceConversationState ChooseContinuation(
        FaceToFaceConversationState state,
        bool continueChat)
    {
        ArgumentNullException.ThrowIfNull(state);
        if (state.State != FaceToFaceState.AwaitingContinuationChoice)
        {
            return state;
        }

        return continueChat && state.NpcId is not null
            ? state with { State = FaceToFaceState.Composing }
            : new FaceToFaceConversationState(FaceToFaceState.Idle, null);
    }
}
