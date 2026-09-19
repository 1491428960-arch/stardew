using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class KissInteractionRulesTests
{
    [Theory]
    [InlineData("dating", null, true)]
    [InlineData("married", null, true)]
    [InlineData("parent", null, true)]
    [InlineData("friend", null, false)]
    [InlineData("close", null, false)]
    [InlineData("friend", "dating", true)]
    [InlineData("friend", "engaged", true)]
    [InlineData("friend", "married", true)]
    public void Kiss_can_only_arm_for_an_established_romantic_relationship(
        string relationshipStage,
        string? customRelationshipType,
        bool expected)
    {
        Assert.Equal(
            expected,
            KissInteractionRules.CanArmAfterReply(
                effectiveReply: true,
                relationshipStage,
                customRelationshipType));
    }

    [Fact]
    public void Fallback_or_empty_reply_never_arms_a_kiss()
    {
        Assert.False(KissInteractionRules.CanArmAfterReply(
            effectiveReply: false,
            relationshipStage: "dating",
            customRelationshipType: null));
    }

    [Fact]
    public void Kiss_requires_a_live_nearby_world_and_free_player()
    {
        Assert.True(KissInteractionRules.CanTriggerKiss(
            worldReady: true,
            menuOpen: false,
            sameDay: true,
            sameLocation: true,
            npcNearby: true,
            eventUp: false,
            festival: false,
            playerCanMove: true,
            usingTool: false,
            ridingHorse: false,
            sitting: false));

        Assert.False(KissInteractionRules.CanTriggerKiss(
            worldReady: true,
            menuOpen: true,
            sameDay: true,
            sameLocation: true,
            npcNearby: true,
            eventUp: false,
            festival: false,
            playerCanMove: true,
            usingTool: false,
            ridingHorse: false,
            sitting: false));
        Assert.False(KissInteractionRules.CanTriggerKiss(
            worldReady: true,
            menuOpen: false,
            sameDay: true,
            sameLocation: true,
            npcNearby: true,
            eventUp: false,
            festival: false,
            playerCanMove: false,
            usingTool: false,
            ridingHorse: false,
            sitting: false));
        Assert.False(KissInteractionRules.CanTriggerKiss(
            worldReady: true,
            menuOpen: false,
            sameDay: true,
            sameLocation: true,
            npcNearby: true,
            eventUp: false,
            festival: false,
            playerCanMove: true,
            usingTool: true,
            ridingHorse: false,
            sitting: false));
    }

    [Theory]
    [InlineData(499, false, false)]
    [InlineData(500, true, true)]
    [InlineData(500, false, false)]
    [InlineData(2000, false, true)]
    public void Kiss_completion_waits_for_the_animation_or_uses_a_two_second_safety_cap(
        double elapsedMilliseconds,
        bool playerCanMove,
        bool expected)
    {
        Assert.Equal(
            expected,
            KissInteractionRules.ShouldCompleteKiss(
                elapsedMilliseconds,
                playerCanMove));
    }
}
