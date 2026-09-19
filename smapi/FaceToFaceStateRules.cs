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

public static class FaceToFaceStateRules
{
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

    public static bool CanStartRepeatChat(
        bool worldReady,
        bool menuOpen,
        bool sameDay,
        bool sameLocation,
        bool npcNearby,
        bool eventUp,
        bool festival)
    {
        return worldReady && !menuOpen && sameDay && sameLocation && npcNearby &&
            !eventUp && !festival;
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
