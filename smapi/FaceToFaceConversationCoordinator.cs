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
    private ConversationService? conversationService;
    private StardewNpc? npc;
    private FaceToFaceConversationState state =
        new(FaceToFaceState.Idle, null);
    private StardewNpc? lastChatNpc;
    private int? lastChatDay;
    private bool disposed;

    public FaceToFaceConversationCoordinator(
        ConversationService? conversationService,
        StoryStateStore storyStateStore,
        Action<StardewNpc?>? runtimeDialogueObserver = null)
    {
        this.conversationService = conversationService;
        this.storyStateStore = storyStateStore ??
            throw new ArgumentNullException(nameof(storyStateStore));
        this.runtimeDialogueObserver = runtimeDialogueObserver;
    }

    public FaceToFaceConversationState State => state;

    public void ResetRepeatTarget()
    {
        lastChatNpc = null;
        lastChatDay = null;
    }

    public bool TryOpenRepeatChat(Vector2 interactionTile)
    {
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
                worldReady: Context.IsWorldReady,
                menuOpen: Game1.activeClickableMenu is not null,
                sameDay: FaceToFaceStateRules.IsSameGameDay(
                    lastChatDay,
                    Game1.Date.TotalDays),
                sameLocation: sameLocation,
                npcNearby: npcNearby,
                eventUp: Game1.eventUp,
                festival: Game1.isFestival()) ||
            !npcTargeted ||
            conversationService is null)
        {
            return false;
        }

        npc = candidate;
        state = new FaceToFaceConversationState(
            FaceToFaceState.Composing,
            candidate!.Name);
        Game1.activeClickableMenu = new ChatInputMenu(
            candidate,
            conversationService,
            storyStateStore,
            OnChatClosed);
        return true;
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

        if (e.OldMenu is ChatInputMenu && e.NewMenu is null &&
            state.State == FaceToFaceState.AwaitingContinuationChoice &&
            npc is not null)
        {
            OfferContinuationChoice(npc);
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
        state = new FaceToFaceConversationState(FaceToFaceState.Idle, null);
        npc = null;
        lastChatNpc = null;
        lastChatDay = null;
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
            OnChatClosed);
    }

    private void OnChatClosed()
    {
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

    private void RememberRepeatTarget(StardewNpc speaker)
    {
        lastChatNpc = speaker;
        lastChatDay = Game1.Date.TotalDays;
    }

    private static bool IsNearby(StardewNpc candidate)
    {
        var distance = Vector2.Distance(candidate.Position, Game1.player.Position);
        return distance <= Game1.tileSize * 2.5f;
    }
}
