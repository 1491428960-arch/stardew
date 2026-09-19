using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupDialogueCoordinatorTests
{
    [Fact]
    public void KnownNpcResolver_keeps_only_friendship_keys_with_loaded_characters()
    {
        var result = KnownNpcResolver.Resolve(
            new[] { "Abigail", "UnknownNpc", "player" },
            npcId => npcId == "Abigail"
                ? new KnownNpc("Abigail", "Abigail")
                : null);

        var npc = Assert.Single(result);
        Assert.Equal("Abigail", npc.NpcId);
    }

    [Fact]
    public void Coordinator_does_not_add_a_second_invitation_on_the_same_day()
    {
        var store = new StoryStateStore();
        var generator = new GroupInvitationGenerator(GroupInvitationTemplates.All);
        var candidates = new[]
        {
            new GroupParticipantCandidate("Abigail", "Abigail", true),
            new GroupParticipantCandidate("Emily", "Emily", true),
        };
        var coordinator = new GroupDialogueCoordinator(
            store,
            generator,
            () => candidates,
            () => 20,
            () => "Spring 20");

        coordinator.OnDayStarted();
        var first = store.State.GroupDialogueInvitations.ToArray();
        coordinator.OnDayStarted();
        var second = store.State.GroupDialogueInvitations.ToArray();

        var firstInvitation = Assert.Single(first);
        var secondInvitation = Assert.Single(second);
        Assert.Equal(firstInvitation.InvitationId, secondInvitation.InvitationId);
    }
}
