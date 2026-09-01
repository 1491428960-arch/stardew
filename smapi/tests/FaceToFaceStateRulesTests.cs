using StardewAI.NPC;
using Microsoft.Xna.Framework;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class FaceToFaceStateRulesTests
{
    [Fact]
    public void VanillaDialogueClosingOffersContinuationOnlyOnce()
    {
        var state = FaceToFaceStateRules.StartForNpc("Rasmodia");
        state = FaceToFaceStateRules.ObserveDialogueOpened(state);
        state = FaceToFaceStateRules.ObserveDialogueClosed(state);

        Assert.Equal(FaceToFaceState.AwaitingContinuationChoice, state.State);

        state = FaceToFaceStateRules.ChooseContinuation(state, continueChat: true);
        Assert.Equal(FaceToFaceState.Composing, state.State);
        state = FaceToFaceStateRules.ObserveDialogueClosed(state);

        Assert.Equal(FaceToFaceState.AwaitingContinuationChoice, state.State);
        Assert.Equal("Rasmodia", state.NpcId);

        state = FaceToFaceStateRules.ChooseContinuation(state, continueChat: true);

        Assert.Equal(FaceToFaceState.Composing, state.State);
    }

    [Fact]
    public void EventAndFestivalNeverOfferContinuation()
    {
        var eventState = FaceToFaceStateRules.StartForNpc(
            "Rasmodia",
            eventUp: true,
            festival: false);
        var festivalState = FaceToFaceStateRules.StartForNpc(
            "Rasmodia",
            eventUp: false,
            festival: true);

        Assert.Equal(FaceToFaceState.Idle, eventState.State);
        Assert.Equal(FaceToFaceState.Idle, festivalState.State);
        Assert.Equal(FaceToFaceState.Idle,
            FaceToFaceStateRules.ObserveDialogueOpened(eventState).State);
    }

    [Fact]
    public void Continuation_question_does_not_reopen_vanilla_dialogue_state()
    {
        var state = new FaceToFaceConversationState(
            FaceToFaceState.AwaitingContinuationChoice,
            "Rasmodia");

        Assert.False(FaceToFaceStateRules.ShouldObserveDialogueOpened(state));
        Assert.True(FaceToFaceStateRules.ShouldObserveDialogueOpened(
            new FaceToFaceConversationState(
                FaceToFaceState.Idle,
                "Rasmodia")));
    }

    [Fact]
    public void Repeat_chat_requires_the_same_day_nearby_npc_and_empty_menu()
    {
        Assert.True(FaceToFaceStateRules.CanStartRepeatChat(
            worldReady: true,
            menuOpen: false,
            sameDay: true,
            sameLocation: true,
            npcNearby: true,
            eventUp: false,
            festival: false));

        Assert.False(FaceToFaceStateRules.CanStartRepeatChat(
            worldReady: true,
            menuOpen: false,
            sameDay: false,
            sameLocation: true,
            npcNearby: true,
            eventUp: false,
            festival: false));
    }

    [Fact]
    public void Repeat_chat_only_consumes_an_action_that_targets_the_remembered_npc()
    {
        var npcBounds = new Rectangle(7 * 64, 7 * 64, 64, 64);

        Assert.True(FaceToFaceStateRules.InteractionTargetsRememberedNpc(
            npcBounds,
            new Vector2(7, 7),
            tileSize: 64));
        Assert.False(FaceToFaceStateRules.InteractionTargetsRememberedNpc(
            npcBounds,
            new Vector2(8, 7),
            tileSize: 64));
    }

    [Fact]
    public void Closing_the_continuation_question_without_an_answer_ends_that_prompt()
    {
        var awaiting = new FaceToFaceConversationState(
            FaceToFaceState.AwaitingContinuationChoice,
            "Rasmodia");

        var dismissed = FaceToFaceStateRules.DismissContinuationChoice(awaiting);

        Assert.Equal(FaceToFaceState.Idle, dismissed.State);
        Assert.Null(dismissed.NpcId);
    }

    [Theory]
    [InlineData(12, 12, true)]
    [InlineData(12, 13, false)]
    [InlineData(null, 12, false)]
    public void Repeat_chat_target_is_bound_to_the_actual_game_day(
        int? rememberedDay,
        int currentDay,
        bool expected)
    {
        Assert.Equal(
            expected,
            FaceToFaceStateRules.IsSameGameDay(rememberedDay, currentDay));
    }
}
