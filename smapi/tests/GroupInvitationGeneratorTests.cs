using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupInvitationGeneratorTests
{
    [Fact]
    public void Generator_creates_one_neutral_invitation_for_two_known_npcs()
    {
        var generator = new GroupInvitationGenerator(GroupInvitationTemplates.All);
        var result = generator.Generate(new GroupInvitationGenerationContext(
            CurrentTotalDays: 20,
            CurrentDateLabel: "Spring 20",
            KnownParticipants: new[]
            {
                new GroupParticipantCandidate("Abigail", "Abigail", true),
                new GroupParticipantCandidate("Emily", "Emily", true),
            },
            ExistingInvitations: Array.Empty<GroupDialogueInvitationRecord>(),
            RecentTopicKeys: Array.Empty<string>(),
            LastCreatedTotalDays: 18));

        var invitation = Assert.Single(result);
        Assert.Equal(new[] { "Abigail", "Emily" }, invitation.Participants);
        Assert.Equal(GroupInvitationStatus.Unread, invitation.Status);
        Assert.Equal(27, invitation.ExpiresTotalDays);
    }

    [Fact]
    public void Generator_does_not_repeat_recent_template_and_pair()
    {
        var existing = new GroupDialogueInvitationRecord
        {
            InvitationId = "old",
            TemplateId = "neutral-public-topic",
            Participants = new[] { "Abigail", "Emily" },
            ParticipantDisplayNames = new[] { "Abigail", "Emily" },
            Title = "公共话题",
            Topic = "最近的公共小事",
            Guidance = "只作为讨论方向。",
            CreatedOn = "Spring 14",
            ExpiresOn = "Spring 21",
            CreatedTotalDays = 14,
            ExpiresTotalDays = 21,
            Source = "periodic",
            Status = GroupInvitationStatus.Completed,
        };

        var result = new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
            new GroupInvitationGenerationContext(
                20,
                "Spring 20",
                new[]
                {
                    new GroupParticipantCandidate("Abigail", "Abigail", true),
                    new GroupParticipantCandidate("Emily", "Emily", true),
                },
                new[] { existing },
                Array.Empty<string>(),
                18));

        Assert.DoesNotContain(result, item => item.TemplateId == existing.TemplateId &&
            GroupInvitationRules.BuildPairKey(item.Participants) ==
            GroupInvitationRules.BuildPairKey(existing.Participants));
    }

    [Theory]
    [InlineData(20, 3)]   // 偶数天：优先三人，更有群聊感
    [InlineData(21, 2)]   // 奇数天：退回两人
    public void Generator_alternates_between_three_and_two_npcs_by_day(
        int totalDays, int expectedCount)
    {
        // 2026-09-20：F9 的「自由发起」被移除后，三人群聊失去了唯一入口，
        // 所以改由预设邀约承担——用日期做确定性交替（偶数天三人、奇数天两人），
        // 既避免长期只出同一种规模，也不必引入随机数。
        var result = new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
            new GroupInvitationGenerationContext(
                CurrentTotalDays: totalDays,
                CurrentDateLabel: $"Spring {totalDays}",
                KnownParticipants: new[]
                {
                    // 这三个角色对应新增的三人模板 adventure-trio。
                    new GroupParticipantCandidate("Abigail", "Abigail", true),
                    new GroupParticipantCandidate("Sebastian", "Sebastian", true),
                    new GroupParticipantCandidate("Maru", "Maru", true),
                },
                ExistingInvitations: Array.Empty<GroupDialogueInvitationRecord>(),
                RecentTopicKeys: Array.Empty<string>(),
                LastCreatedTotalDays: totalDays - 2));

        var invitation = Assert.Single(result);
        Assert.Equal(expectedCount, invitation.Participants.Count);
    }

    [Fact]
    public void Generator_keeps_making_new_invitations_even_with_several_pending()
    {
        // 用户反馈：每张邀约都得清掉才能刷出新的太蠢。
        // 现在 ShouldGenerate 只看时间间隔；不会无限堆积由过期机制保证
        // （7 天后连 Accepted 也会过期），所以待处理多并不构成阻止理由。
        var existing = Enumerable.Range(0, 5)
            .Select(index => new GroupDialogueInvitationRecord
            {
                InvitationId = $"pending-{index}",
                TemplateId = "neutral-public-topic",
                Participants = new[] { $"Npc{index}", "Other" },
                CreatedTotalDays = 18,
                ExpiresTotalDays = 25,
                Status = GroupInvitationStatus.Unread,
            })
            .ToArray();

        var result = new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
            new GroupInvitationGenerationContext(
                CurrentTotalDays: 20,
                CurrentDateLabel: "Spring 20",
                KnownParticipants: new[]
                {
                    new GroupParticipantCandidate("Abigail", "Abigail", true),
                    new GroupParticipantCandidate("Emily", "Emily", true),
                },
                ExistingInvitations: existing,
                RecentTopicKeys: Array.Empty<string>(),
                LastCreatedTotalDays: 18));

        Assert.Single(result);
    }

    [Fact]
    public void Generator_skips_candidates_without_a_friendship_record()
    {
        var result = new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
            new GroupInvitationGenerationContext(
                20,
                "Spring 20",
                new[]
                {
                    new GroupParticipantCandidate("Abigail", "Abigail", true),
                    new GroupParticipantCandidate("Emily", "Emily", false),
                },
                Array.Empty<GroupDialogueInvitationRecord>(),
                Array.Empty<string>(),
                18));

        // 只剩一个合格候选，凑不满一对。
        Assert.Empty(result);
    }

    [Theory]
    [InlineData(19, 18, 0)]  // 距上次生成只隔 1 天 → 不生成
    [InlineData(20, 19, 0)]  // 同样只隔 1 天
    public void Generator_waits_at_least_two_days_between_invitations(
        int currentTotalDays,
        int lastCreatedTotalDays,
        int pendingCount)
    {
        var existing = Enumerable.Range(0, pendingCount)
            .Select(index => new GroupDialogueInvitationRecord
            {
                InvitationId = $"pending-{index}",
                TemplateId = "neutral-public-topic",
                Participants = new[] { $"Npc{index}", "Other" },
                CreatedTotalDays = 19,
                ExpiresTotalDays = 26,
                Status = GroupInvitationStatus.Unread,
            })
            .ToArray();

        var result = new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
            new GroupInvitationGenerationContext(
                currentTotalDays,
                "Spring 20",
                new[]
                {
                    new GroupParticipantCandidate("Abigail", "Abigail", true),
                    new GroupParticipantCandidate("Emily", "Emily", true),
                },
                existing,
                Array.Empty<string>(),
                lastCreatedTotalDays));

        Assert.Empty(result);
    }
}
