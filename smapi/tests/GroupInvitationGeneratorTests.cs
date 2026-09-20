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

    [Fact]
    public void Generator_only_pairs_two_npcs_even_when_three_are_known()
    {
        // 当前实现只枚举两两组合（EnumeratePairs），所以**自动生成的邀约参与者恒为 2 人**。
        // ⚠️ 2026-09-20：F9 的「自由发起」已被移除（用户决定：选人 UI 的收益不如把预设邀约做好），
        // 因此**三人群聊目前没有任何入口**。若要恢复三人场，正确做法是让本生成器支持三人组合，
        // 而不是恢复那个选人菜单。
        var result = new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
            new GroupInvitationGenerationContext(
                CurrentTotalDays: 20,
                CurrentDateLabel: "Spring 20",
                KnownParticipants: new[]
                {
                    new GroupParticipantCandidate("Abigail", "Abigail", true),
                    new GroupParticipantCandidate("Emily", "Emily", true),
                    new GroupParticipantCandidate("Sebastian", "Sebastian", true),
                },
                ExistingInvitations: Array.Empty<GroupDialogueInvitationRecord>(),
                RecentTopicKeys: Array.Empty<string>(),
                LastCreatedTotalDays: 18));

        var invitation = Assert.Single(result);
        Assert.Equal(2, invitation.Participants.Count);
        // 候选先按 npcId 字典序排好，因此取到的是最前面那一对。
        Assert.Equal(
            new[] { "Abigail", "Emily" },
            invitation.Participants.ToArray());
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
    [InlineData(20, 2, 3)]  // 待处理已满 3 张 → 不生成
    public void Generator_respects_the_interval_and_the_pending_limit(
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
