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

    public static bool ShouldObserveDialogueOpened(
        FaceToFaceConversationState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        // The continuation question is rendered by the same DialogueBox type
        // as vanilla NPC speech. Do not let that question restart the vanilla
        // dialogue state before its answer callback runs.
        return state.State is not FaceToFaceState.AwaitingContinuationChoice and
            not FaceToFaceState.AwaitingKiss and
            not FaceToFaceState.Kissing;
    }

    public static bool CanStartRepeatChat(FaceToFaceGate gate)
    {
        ArgumentNullException.ThrowIfNull(gate);
        return gate.AllowsInteraction;
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
