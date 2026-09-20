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
        var openGate = new FaceToFaceGate(
            WorldReady: true,
            MenuOpen: false,
            SameDay: true,
            SameLocation: true,
            NpcNearby: true,
            EventUp: false,
            Festival: false);

        Assert.True(KissInteractionRules.CanTriggerKiss(
            openGate,
            playerCanMove: true,
            usingTool: false,
            ridingHorse: false,
            sitting: false));

        Assert.False(KissInteractionRules.CanTriggerKiss(
            openGate with { MenuOpen = true },
            playerCanMove: true,
            usingTool: false,
            ridingHorse: false,
            sitting: false));
        Assert.False(KissInteractionRules.CanTriggerKiss(
            openGate,
            playerCanMove: false,
            usingTool: false,
            ridingHorse: false,
            sitting: false));
        Assert.False(KissInteractionRules.CanTriggerKiss(
            openGate,
            playerCanMove: true,
            usingTool: true,
            ridingHorse: false,
            sitting: false));
    }

    /// <summary>
    /// 等价性证据（审计 #33 / #34）：把门槛拆成「七项共同条件（<see cref="FaceToFaceGate"/>）
    /// + 四项玩家动作条件」之后，对全部 2^11 种组合的判定必须与改动前那条 11 项合取
    /// **逐项一致**——测试里直接写出改动前的原式作为期望值。
    /// </summary>
    [Fact]
    public void Kiss_gate_matches_the_original_eleven_term_conjunction_for_every_combination()
    {
        for (var mask = 0; mask < (1 << 11); mask++)
        {
            var gate = new FaceToFaceGate(
                WorldReady: Bit(mask, 0),
                MenuOpen: Bit(mask, 1),
                SameDay: Bit(mask, 2),
                SameLocation: Bit(mask, 3),
                NpcNearby: Bit(mask, 4),
                EventUp: Bit(mask, 5),
                Festival: Bit(mask, 6));
            var playerCanMove = Bit(mask, 7);
            var usingTool = Bit(mask, 8);
            var ridingHorse = Bit(mask, 9);
            var sitting = Bit(mask, 10);

            // 改动前的实现：
            // return worldReady && !menuOpen && sameDay && sameLocation && npcNearby &&
            //     !eventUp && !festival && playerCanMove && !usingTool && !ridingHorse && !sitting;
            var expected = gate.WorldReady &&
                !gate.MenuOpen &&
                gate.SameDay &&
                gate.SameLocation &&
                gate.NpcNearby &&
                !gate.EventUp &&
                !gate.Festival &&
                playerCanMove &&
                !usingTool &&
                !ridingHorse &&
                !sitting;

            Assert.Equal(
                expected,
                KissInteractionRules.CanTriggerKiss(
                    gate,
                    playerCanMove,
                    usingTool,
                    ridingHorse,
                    sitting));
        }
    }

    private static bool Bit(int mask, int index) => (mask & (1 << index)) != 0;

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
