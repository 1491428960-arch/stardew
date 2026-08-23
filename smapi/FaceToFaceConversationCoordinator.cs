using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;
using StardewValley.Menus;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

/// <summary>
/// 观察原版 DialogueBox 的生命周期，在对白自然结束后提供一次续聊选择。
/// </summary>
public sealed class FaceToFaceConversationCoordinator
{
    private readonly StoryStateStore storyStateStore;
    private ConversationService? conversationService;
    private StardewNpc? npc;
    private FaceToFaceConversationState state =
        new(FaceToFaceState.Idle, null);
    private bool disposed;

    public FaceToFaceConversationCoordinator(
        ConversationService? conversationService,
        StoryStateStore storyStateStore)
    {
        this.conversationService = conversationService;
        this.storyStateStore = storyStateStore ??
            throw new ArgumentNullException(nameof(storyStateStore));
    }

    public FaceToFaceConversationState State => state;

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

        if (e.NewMenu is DialogueBox)
        {
            ObserveDialogueOpened();
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
        if (state.State == FaceToFaceState.Idle)
        {
            npc = null;
        }
    }
}
