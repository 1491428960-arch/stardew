using StardewAI.NPC;
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
        Assert.Equal(
            FaceToFaceState.Idle,
            FaceToFaceStateRules.ObserveDialogueClosed(state).State);
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
}
