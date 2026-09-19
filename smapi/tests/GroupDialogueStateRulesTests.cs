using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupDialogueStateRulesTests
{
    [Fact]
    public void ResolveActiveSpeakerState_uses_the_request_active_speaker_and_preserves_event_ids()
    {
        var state = new NpcGameState
        {
            NpcId = "Wizard",
            CompletedEventIds = new[] { "1000075", "1724096" },
        };
        var calls = new List<string>();

        var result = GroupDialogueStateRules.ResolveActiveSpeakerState(
            new[]
            {
                new GroupDialogueParticipant("Wizard", "Rasmodia"),
                new GroupDialogueParticipant("Shane", "Shane"),
            },
            npcId =>
            {
                calls.Add(npcId);
                return npcId == "Wizard" ? state : null;
            });

        Assert.Same(state, result);
        Assert.Equal(new[] { "Wizard" }, calls);
        Assert.Equal(new[] { "1000075", "1724096" }, result!.CompletedEventIds);
    }

    [Fact]
    public void ResolveActiveSpeakerState_returns_null_when_participants_have_no_active_speaker()
    {
        var called = false;

        var result = GroupDialogueStateRules.ResolveActiveSpeakerState(
            Array.Empty<GroupDialogueParticipant>(),
            _ =>
            {
                called = true;
                return new NpcGameState();
            });

        Assert.Null(result);
        Assert.False(called);
    }

    [Fact]
    public void ResolveParticipantStates_gives_every_participant_its_own_state()
    {
        var wizardState = new NpcGameState { NpcId = "Wizard", FriendshipHearts = 10 };
        var shaneState = new NpcGameState { NpcId = "Shane", FriendshipHearts = 2 };
        var calls = new List<string>();

        var resolved = GroupDialogueStateRules.ResolveParticipantStates(
            new[]
            {
                new GroupDialogueParticipant("Wizard", "Rasmodia"),
                new GroupDialogueParticipant("Shane", "Shane"),
            },
            npcId =>
            {
                calls.Add(npcId);
                return npcId switch
                {
                    "Wizard" => wizardState,
                    "Shane" => shaneState,
                    _ => null,
                };
            });

        Assert.Equal(new[] { "Wizard", "Shane" }, calls);
        Assert.Same(wizardState, resolved[0].GameState);
        Assert.Same(shaneState, resolved[1].GameState);
        // 阶段不同不能被同一份状态覆盖
        Assert.NotEqual(resolved[0].GameState!.FriendshipHearts, resolved[1].GameState!.FriendshipHearts);
    }

    [Fact]
    public void ResolveParticipantStates_keeps_unresolved_participant_unknown()
    {
        var offlineState = new NpcGameState { NpcId = "Wizard" };

        var resolved = GroupDialogueStateRules.ResolveParticipantStates(
            new[]
            {
                new GroupDialogueParticipant("Wizard", "Rasmodia"),
                new GroupDialogueParticipant("Sophia", "Sophia"),
            },
            npcId => npcId == "Wizard" ? offlineState : null);

        Assert.Same(offlineState, resolved[0].GameState);
        // 解析不到时保持未知，不能拿别人的状态顶替
        Assert.Null(resolved[1].GameState);
    }
}
