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

    // 下面两条是**接线测试**（2026-10-05）：Generator 支持「打趣」还不够，
    // 必须证明 OnDayStarted 真的把 accepted 那批人传下去了 ——
    // 「能力做好了但没人调用」是这个项目反复出现的失败形态
    // （`DiscloseRelationship` 至今零生产调用点就是同一个形状）。

    [Fact]
    public void Coordinator_feeds_accepted_spouses_into_the_invitation_generator()
    {
        var store = new StoryStateStore();
        Assert.Equal(2, store.EnsureSpouseAcceptance(new[] { "Abigail", "Emily" }));
        var coordinator = new GroupDialogueCoordinator(
            store,
            new GroupInvitationGenerator(GroupInvitationTemplates.All),
            () => new[]
            {
                new GroupParticipantCandidate("Abigail", "Abigail", true),
                new GroupParticipantCandidate("Emily", "Emily", true),
            },
            () => 20,
            () => "Spring 20");

        coordinator.OnDayStarted();

        var invitation = Assert.Single(store.State.GroupDialogueInvitations);
        Assert.Contains("打趣", invitation.Guidance);
    }

    [Fact]
    public void Coordinator_teases_nobody_when_no_mediation_record_is_accepted()
    {
        // 对照：没有 accepted 记录时，即便这两人就是玩家的配偶也不会打趣 ——
        // 判据是「已接受」，不是「是配偶」。
        var store = new StoryStateStore();
        var coordinator = new GroupDialogueCoordinator(
            store,
            new GroupInvitationGenerator(GroupInvitationTemplates.All),
            () => new[]
            {
                new GroupParticipantCandidate("Abigail", "Abigail", true),
                new GroupParticipantCandidate("Emily", "Emily", true),
            },
            () => 20,
            () => "Spring 20");

        coordinator.OnDayStarted();

        var invitation = Assert.Single(store.State.GroupDialogueInvitations);
        Assert.DoesNotContain("打趣", invitation.Guidance);
    }
}
