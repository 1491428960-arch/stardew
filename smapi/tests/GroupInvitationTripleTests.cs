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
        IReadOnlyList<GroupParticipantCandidate> candidates,
        params GroupDialogueInvitationRecord[] existing) =>
        new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
            new GroupInvitationGenerationContext(
                CurrentTotalDays: totalDays,
                CurrentDateLabel: $"Spring {totalDays}",
                KnownParticipants: candidates,
                ExistingInvitations: existing,
                RecentTopicKeys: Array.Empty<string>(),
                LastCreatedTotalDays: totalDays - 2));

    [Fact]
    public void A_three_npc_invitation_is_preferred_when_the_last_one_was_smaller()
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
    public void A_two_npc_invitation_follows_a_three_npc_one()
    {
        // 上一张是三人 → 这一张回到两人；交替与「天数奇偶」无关
        // （生成间隔也是 2 天，用奇偶做交替会让规模永远不变）。
        var previous = new GroupDialogueInvitationRecord
        {
            InvitationId = "prev",
            TemplateId = "adventure-trio",
            Participants = new[] { "Abigail", "Sebastian", "Maru" },
            ParticipantDisplayNames = new[] { "Abigail", "Sebastian", "Maru" },
            Title = "上一张",
            Topic = "上一张",
            Guidance = "上一张",
            CreatedOn = "Spring 18",
            ExpiresOn = "day 25",
            CreatedTotalDays = 18,
            ExpiresTotalDays = 25,
            Source = "periodic",
            Status = GroupInvitationStatus.Completed,
        };

        var invitation = Assert.Single(Generate(20, Three, previous));

        Assert.Equal(2, invitation.Participants.Count);
    }

    [Fact]
    public void The_same_day_parity_does_not_freeze_the_group_size()
    {
        // 回归保护：这条正是那个 bug —— 生成间隔是 2 天，所以连续几次生成
        // 的天数奇偶性相同；若用奇偶决定规模，两人场会永远是两人场。
        var previous = new GroupDialogueInvitationRecord
        {
            InvitationId = "prev",
            TemplateId = "neutral-public-topic",
            Participants = new[] { "Abigail", "Alex" },
            ParticipantDisplayNames = new[] { "Abigail", "Alex" },
            Title = "上一张",
            Topic = "上一张",
            Guidance = "上一张",
            CreatedOn = "Spring 18",
            ExpiresOn = "day 25",
            CreatedTotalDays = 129,
            ExpiresTotalDays = 136,
            Source = "periodic",
            Status = GroupInvitationStatus.Completed,
        };

        // 129 与 131 同为奇数——旧实现下两次都会是两人场。
        var invitation = Assert.Single(Generate(131, Three, previous));

        Assert.Equal(3, invitation.Participants.Count);
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

        // 模板现在按需生成（All 只含两两组合，避免 35 万个对象常驻内存），
        // 所以这里直接检查“为这三个人生成的模板”里有没有它。
        // 注意顺序：ForGroup 内部按字母序拼 key，这里的顺序要与之一致才能对上。
        var forGroup = GroupInvitationTemplates.ForGroup(new[] { "Abigail", "Maru", "Sebastian" });
        Assert.Contains(invitation.TemplateId, forGroup.Select(template => template.TemplateId));
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
