using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class NpcTargetResolverTests
{
    [Fact]
    public void Resolves_the_internal_wizard_name_when_Rasmodia_display_name_is_not_an_internal_id()
    {
        var resolved = NpcTargetResolver.ResolveTargetName(
            candidate => candidate == "Wizard");

        Assert.Equal("Wizard", resolved);
    }

    [Fact]
    public void Prefers_Rasmodia_if_a_mod_adds_that_as_a_real_internal_name()
    {
        var resolved = NpcTargetResolver.ResolveTargetName(
            candidate => candidate is "Rasmodia" or "Wizard");

        Assert.Equal("Rasmodia", resolved);
    }

    [Fact]
    public void Selects_a_nearby_friendship_npc_when_no_legacy_template_is_present()
    {
        var resolved = NpcTargetResolver.SelectFriendshipTarget(new[]
        {
            new NpcTargetCandidate("Caroline", true, false, 9f, false),
            new NpcTargetCandidate("Marnie", true, true, 25f, false),
        });

        Assert.Equal("Marnie", resolved?.NpcId);
    }

    [Fact]
    public void Interaction_target_beats_a_closer_friendship_npc()
    {
        var resolved = NpcTargetResolver.SelectFriendshipTarget(new[]
        {
            new NpcTargetCandidate("Caroline", true, true, 4f, false),
            new NpcTargetCandidate("Marnie", true, true, 25f, true),
        });

        Assert.Equal("Marnie", resolved?.NpcId);
    }

    [Fact]
    public void Ignores_npcs_without_friendship_records_and_empty_candidates()
    {
        var resolved = NpcTargetResolver.SelectFriendshipTarget(new[]
        {
            new NpcTargetCandidate("", true, true, 1f, true),
            new NpcTargetCandidate("Pierre", false, true, 1f, true),
        });

        Assert.Null(resolved);
    }

    /// <summary>
    /// 复现「按 F8 默认连上那个（测试）克隆体」的现象。
    ///
    /// 克隆体是**唯一**能靠 <see cref="TestNpcPlacementRules.IsDialogueTargetWithoutFriendshipRecord"/>
    /// 在没有好感度记录的情况下进入候选池的 NPC，而它又被生成在玩家床边（离玩家最近），
    /// 于是距离优先的排序把它排到了真角色前面。
    /// </summary>
    [Fact]
    public void Bedside_test_npc_steals_the_F8_target_from_a_farther_real_npc()
    {
        var resolved = NpcTargetResolver.SelectFriendshipTarget(new[]
        {
            FarmhouseCandidate(
                TestNpcPlacementRules.InternalName,
                distance: 3f,
                hasFriendshipRecord: false),
            FarmhouseCandidate("Abigail", distance: 8f),
        });

        Assert.Equal(TestNpcPlacementRules.InternalName, resolved?.NpcId);
    }

    /// <summary>
    /// 关掉注入后（克隆体不再进候选池，农舍里只剩真角色），
    /// F8 选中的是最近的那个真角色——婚后角色都在屋里，随手一按就能对上人。
    /// </summary>
    [Fact]
    public void Without_the_test_npc_F8_selects_the_nearest_real_npc()
    {
        var resolved = NpcTargetResolver.SelectFriendshipTarget(new[]
        {
            FarmhouseCandidate("Abigail", distance: 8f),
            FarmhouseCandidate("Emily", distance: 12f),
        });

        Assert.Equal("Abigail", resolved?.NpcId);
    }

    /// <summary>
    /// 克隆体在场也不是无条件优先：真角色站得更近时选真角色。
    /// 它抢走目标靠的是「距离最近 + 无记录也能进池」，不是名字特权。
    /// </summary>
    [Fact]
    public void A_closer_real_npc_still_beats_the_bedside_test_npc()
    {
        var resolved = NpcTargetResolver.SelectFriendshipTarget(new[]
        {
            FarmhouseCandidate(
                TestNpcPlacementRules.InternalName,
                distance: 6f,
                hasFriendshipRecord: false),
            FarmhouseCandidate("Abigail", distance: 2f),
        });

        Assert.Equal("Abigail", resolved?.NpcId);
    }

    /// <summary>
    /// 与 <c>ModEntry.ResolveFriendshipTarget</c> 同一套候选构造：原始好感度记录
    /// （克隆体**没有**记录）经 <see cref="TestNpcPlacementRules.IsDialogueTargetWithoutFriendshipRecord"/>
    /// 的豁免规则折算成候选的 <c>HasFriendshipRecord</c>；同在农舍、距离已知、鼠标未指向它。
    /// </summary>
    private static NpcTargetCandidate FarmhouseCandidate(
        string npcId,
        float distance,
        bool hasFriendshipRecord = true)
    {
        return new NpcTargetCandidate(
            npcId,
            HasFriendshipRecord: hasFriendshipRecord ||
                TestNpcPlacementRules.IsDialogueTargetWithoutFriendshipRecord(npcId),
            IsInCurrentLocation: true,
            Distance: distance,
            IsInteractionTarget: false);
    }
}
