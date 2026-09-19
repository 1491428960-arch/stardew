using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 端到端钉住 `GroupInvitationRules.BuildPairKey`（以及模板 ID）的归一化：
/// **存档里的旧卡用原始大小写、当天候选用小写**时，去重键仍须相等，
/// 否则会重复生成同一张邀约卡。
///
/// 这个缺口是一次独立复核指出来的：既有的
/// `Generator_does_not_repeat_recent_template_and_pair` 两侧大小写相同，
/// `Coordinator_does_not_add_a_second_invitation_on_the_same_day` 又实际被
/// `ShouldGenerate` 的 2 天间隔挡住——两条都没覆盖“大小写不一致”这个组合。
/// 复核同时发现 **`BuildDuplicateKey` 里的模板 ID 此前只被 `Trim()`、没有转小写**，
/// 与其“整个去重键大小写不敏感”的注释承诺不符。
/// </summary>
public sealed class GroupInvitationCaseInsensitiveDedupTests
{
    private static GroupDialogueInvitationRecord StoredInvitation(
        string templateId,
        string[] participants,
        int createdTotalDays) =>
        new()
        {
            InvitationId =
                $"group:{templateId}:{string.Join("|", participants).ToLowerInvariant()}:{createdTotalDays}",
            TemplateId = templateId,
            Participants = participants,
            ParticipantDisplayNames = participants,
            Title = "公共话题",
            Topic = "最近的公共小事",
            Guidance = "只作为讨论方向。",
            CreatedOn = $"day {createdTotalDays}",
            ExpiresOn = $"day {createdTotalDays + 7}",
            CreatedTotalDays = createdTotalDays,
            ExpiresTotalDays = createdTotalDays + 7,
            Source = "periodic",
            Status = GroupInvitationStatus.Completed,
        };

    private static GroupDialogueInvitationRecord Record(string templateId) =>
        StoredInvitation(templateId, new[] { "Abigail", "Emily" }, 20);

    [Fact]
    public void Stored_invitation_still_counts_as_recent_when_candidate_case_differs()
    {
        // 存档里记的是 Abigail/Emily，当天候选是小写的 abigail/emily——只差大小写。
        var existing = StoredInvitation("neutral-public-topic", new[] { "Abigail", "Emily" }, 19);

        var result = new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
            new GroupInvitationGenerationContext(
                CurrentTotalDays: 20,
                CurrentDateLabel: "Spring 20",
                KnownParticipants: new[]
                {
                    new GroupParticipantCandidate("abigail", "Abigail", true),
                    new GroupParticipantCandidate("emily", "Emily", true),
                },
                ExistingInvitations: new[] { existing },
                RecentTopicKeys: Array.Empty<string>(),
                LastCreatedTotalDays: 18));  // 距上次 2 天 → 时间条件已满足

        // 断言要针对**模板**而不是“什么都不生成”：其他模板与这一对的去重键不同，仍可能生成。
        Assert.DoesNotContain(result, item => item.TemplateId == "neutral-public-topic");
    }

    [Fact]
    public void A_different_pair_is_still_generated_normally()
    {
        // 反向对照：换了人就不该被去重拦住，否则上一条断言可能是因别的原因空转。
        var existing = StoredInvitation("neutral-public-topic", new[] { "Abigail", "Emily" }, 19);

        var result = new GroupInvitationGenerator(GroupInvitationTemplates.All).Generate(
            new GroupInvitationGenerationContext(
                20,
                "Spring 20",
                new[]
                {
                    new GroupParticipantCandidate("Sebastian", "Sebastian", true),
                    new GroupParticipantCandidate("Leah", "Leah", true),
                },
                new[] { existing },
                Array.Empty<string>(),
                18));

        Assert.Single(result);
    }

    [Fact]
    public void Duplicate_key_normalises_the_template_id_too()
    {
        // 契约是“整个去重键大小写不敏感”，而模板 ID 此前只被 Trim()——
        // 大小写不同的模板 ID 会产生不同的键。这条钉住该修复。
        Assert.Equal(
            GroupInvitationRules.BuildDuplicateKey(Record("neutral-public-topic")),
            GroupInvitationRules.BuildDuplicateKey(Record("NEUTRAL-PUBLIC-TOPIC")));
        Assert.Equal(
            GroupInvitationRules.BuildDuplicateKey(Record("neutral-public-topic")),
            GroupInvitationRules.BuildDuplicateKey(Record("  Neutral-Public-Topic  ")));
    }
}
