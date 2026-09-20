using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 三人场邀约：自动生成的邀约不再恒为 2 人。
///
/// 背景：2026-09-20 移除了 F9 的「自由发起」——而它此前是**三人群聊的唯一入口**
/// （`GroupInvitationGenerator` 只枚举两两组合）。用户对此的表述是
/// “不如钻研下怎么把预设的做得更好”，所以三人群聊改由**预设邀约**承担。
///
/// 设计：**用日期做确定性交替**——偶数天优先三人组合，奇数天优先两人组合。
/// 这样既避免长期只出同一种规模，也不必引入随机数（可测）。
/// 规则层的 `MinParticipants=2 / MaxParticipants=3` 本来就已经允许 3 人，
/// Bridge 侧也一直是 `min_length=2, max_length=3`，所以这里只改生成策略。
/// </summary>
public sealed class GroupInvitationTripleTests
{
    private static readonly GroupParticipantCandidate[] Two =
    {
        new("Abigail", "Abigail", true),
        new("Emily", "Emily", true),
    };

    /// <summary>这三个角色对应新增的三人模板。</summary>
    private static readonly GroupParticipantCandidate[] Three =
    {
        new("Abigail", "Abigail", true),
        new("Sebastian", "Sebastian", true),
        new("Maru", "Maru", true),
    };

    private static IReadOnlyList<GroupDialogueInvitationRecord> Generate(
        int totalDays,
        IReadOnlyList<GroupParticipantCandidate> candidates) =>
        new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
            new GroupInvitationGenerationContext(
                CurrentTotalDays: totalDays,
                CurrentDateLabel: $"Spring {totalDays}",
                KnownParticipants: candidates,
                ExistingInvitations: Array.Empty<GroupDialogueInvitationRecord>(),
                RecentTopicKeys: Array.Empty<string>(),
                LastCreatedTotalDays: totalDays - 2));

    [Fact]
    public void An_even_day_prefers_a_three_npc_invitation()
    {
        var invitation = Assert.Single(Generate(20, Three));

        Assert.Equal(3, invitation.Participants.Count);
        Assert.Equal(3, invitation.ParticipantDisplayNames.Count);
        // 键与人数无关，三人组合也能算出去重键。
        Assert.Equal(
            GroupInvitationRules.BuildPairKey(invitation.Participants),
            string.Join(
                "|",
                invitation.Participants
                    .Select(id => id.ToLowerInvariant())
                    .OrderBy(id => id, StringComparer.Ordinal)));
    }

    [Fact]
    public void An_odd_day_falls_back_to_a_two_npc_invitation()
    {
        var invitation = Assert.Single(Generate(21, Three));

        Assert.Equal(2, invitation.Participants.Count);
    }

    [Fact]
    public void Two_candidates_always_produce_a_two_npc_invitation()
    {
        foreach (var day in new[] { 20, 21 })
        {
            var invitation = Assert.Single(Generate(day, Two));

            Assert.Equal(2, invitation.Participants.Count);
        }
    }

    [Fact]
    public void The_three_npc_template_wins_for_a_three_npc_group()
    {
        // 模板按 RequiredParticipants.Count 降序排，所以三人模板会排在前面；
        // 而它要求三个角色都在组合里，两人组合匹配不到。
        var invitation = Assert.Single(Generate(20, Three));

        Assert.Contains(
            invitation.TemplateId,
            GroupInvitationTemplates.All
                .Where(template => template.RequiredParticipants.Count == 3)
                .Select(template => template.TemplateId));
    }

    [Fact]
    public void A_two_npc_group_never_gets_a_three_npc_template()
    {
        var invitation = Assert.Single(Generate(20, Two));

        var template = GroupInvitationTemplates.All.Single(
            item => item.TemplateId == invitation.TemplateId);
        Assert.True(template.RequiredParticipants.Count <= 2);
    }
}
