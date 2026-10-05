using System;
using System.Linq;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 「把已接受的多元关系当打趣加进群聊话题」（2026-10-05，阶段二「素材」）。
///
/// 落点选择（用户 2026-10-05 定 A）：**不新增主题**，而是给**已经被选中的那张邀约**
/// 追加一段情境约束。理由是丙的裁定原话是「把这个作为**打趣加入**群聊话题」——
/// 是加料，不是换成「这次群聊聊打趣」。好处是话题选择逻辑一个字都不用动，
/// 也避开了「打趣主题永远抢占选择」那种会让群聊变单调的排序问题。
///
/// 判据：**在场 ≥2 人**处于已接受状态。一位不算——那会变成当着外人的面议论
/// 不在场者的私事，与 friendship 主题的「不提不在场的人的具体私事」直接冲突。
/// </summary>
public sealed class GroupInvitationTeasingTests
{
    private static GroupInvitationGenerationContext Context(
        IReadOnlyList<string>? accepted,
        params (string Id, string Name)[] participants)
    {
        return new GroupInvitationGenerationContext(
            CurrentTotalDays: 20,
            CurrentDateLabel: "Spring 20",
            KnownParticipants: participants
                .Select(item => new GroupParticipantCandidate(item.Id, item.Name, true))
                .ToArray(),
            ExistingInvitations: Array.Empty<GroupDialogueInvitationRecord>(),
            RecentTopicKeys: Array.Empty<string>(),
            LastCreatedTotalDays: 18,
            AcceptedPolyamoryNpcIds: accepted);
    }

    private static GroupDialogueInvitationRecord Generate(
        IReadOnlyList<string>? accepted,
        params (string Id, string Name)[] participants)
    {
        var result = new GroupInvitationGenerator(GroupInvitationTemplates.All)
            .Generate(Context(accepted, participants));
        return Assert.Single(result);
    }

    private static readonly (string Id, string Name)[] Pair =
    {
        ("Abigail", "Abigail"), ("Emily", "Emily"),
    };

    [Fact]
    public void Both_participants_accepted_adds_the_teasing_clause()
    {
        var invitation = Generate(new[] { "Abigail", "Emily" }, Pair);

        Assert.Contains("打趣", invitation.Guidance);
        Assert.Contains("Abigail", invitation.Guidance);
        Assert.Contains("Emily", invitation.Guidance);
    }

    [Fact]
    public void Without_the_accepted_list_nothing_is_added()
    {
        var invitation = Generate(null, Pair);

        Assert.DoesNotContain("打趣", invitation.Guidance);
    }

    [Fact]
    public void An_unrelated_accepted_npc_does_not_enable_teasing()
    {
        // 已接受名单里有别人，但**这组里**只有 Abigail 一个 —— 不该打趣。
        var invitation = Generate(new[] { "Abigail", "Sophia" }, Pair);

        Assert.DoesNotContain("打趣", invitation.Guidance);
    }

    [Fact]
    public void Teasing_does_not_change_topic_or_title()
    {
        var plain = Generate(null, Pair);
        var teased = Generate(new[] { "Abigail", "Emily" }, Pair);

        // 打趣是加料：话题与标题必须一字不变，否则它就成了「换了个话题」。
        Assert.Equal(plain.Topic, teased.Topic);
        Assert.Equal(plain.Title, teased.Title);
        Assert.Equal(plain.TemplateId, teased.TemplateId);
        Assert.StartsWith(plain.Guidance, teased.Guidance, StringComparison.Ordinal);
    }

    [Fact]
    public void Clause_forbids_announcing_relationship_outcomes()
    {
        var invitation = Generate(new[] { "Abigail", "Emily" }, Pair);

        // 与既有的「邀约卡不得宣告关系结果」同一条红线。
        Assert.Contains("不要宣告任何关系的结论", invitation.Guidance);
        Assert.Contains("不要拿不在场的人开玩笑", invitation.Guidance);
    }

    [Fact]
    public void Only_the_participants_who_are_in_on_it_are_named()
    {
        // 三人场：在场两位已接受，第三位不在名单里。名单只应出现那两位。
        var invitation = Generate(
            new[] { "Abigail", "Emily" },
            ("Abigail", "Abigail"), ("Emily", "Emily"), ("Shane", "Shane"));

        Assert.Contains("打趣", invitation.Guidance);
        var clause = invitation.Guidance.Substring(invitation.Guidance.IndexOf("另外：", StringComparison.Ordinal));
        Assert.Contains("Abigail", clause);
        Assert.Contains("Emily", clause);
        Assert.DoesNotContain("Shane", clause);
    }

    [Fact]
    public void Guidance_stays_within_the_bridge_limit()
    {
        // Bridge 的 `GroupDialogueRequest.invitation_guidance` 是
        // `Field(max_length=500)` —— 这是**校验**而不是截断：超了会让整个群聊请求
        // 直接 422，比静默丢字段更难看。而追加打趣许可正是在吃这条余量，
        // 所以在这里守住上界。
        //
        // 三人场是最坏情况（模板表 `All` 只含两两组合，量不到它）。
        //
        // 先用**真实存在**的两两组合量出实际最坏值：88 人的两两组合已在 `All` 里，
        // 而且是生产里常态出现的规模。这里不作估算，直接取实测最大值。
        const int bridgeLimit = 500;
        var longestPair = GroupInvitationTemplates.All
            .OrderByDescending(template => template.Guidance.Length)
            .First();
        var clause = GroupInvitationTemplates.TeasingClause(
            longestPair.RequiredParticipants,
            longestPair.RequiredParticipants);
        Assert.NotNull(clause);

        // 模板自身必须在预算内（否则不用打趣就已经会 422）。
        Assert.True(
            longestPair.Guidance.Length <= GroupInvitationTemplates.MaxGuidanceLength,
            $"模板 {longestPair.TemplateId} 自身 {longestPair.Guidance.Length} 字已超出预算");
        // 再走**真实拼接路径**：先给子句留位、截引导、再接子句。
        var teased = GroupInvitationTemplates.ClampGuidance(
            longestPair.Guidance, clause!.Length) + clause;
        Assert.True(
            teased.Length <= GroupInvitationTemplates.MaxGuidanceLength,
            $"最坏两人场（{longestPair.TemplateId}）拼上打趣后 {teased.Length} 字，超出预算 {GroupInvitationTemplates.MaxGuidanceLength}");
        Assert.True(teased.Length <= bridgeLimit);
        // 截的是引导，不是新加的语义：子句必须完整活下来。
        Assert.EndsWith(clause, teased, StringComparison.Ordinal);
    }

    [Fact]
    public void Every_generated_template_fits_the_budget()
    {
        Assert.All(
            GroupInvitationTemplates.All,
            template => Assert.True(
                template.Guidance.Length <= GroupInvitationTemplates.MaxGuidanceLength,
                $"{template.TemplateId} 的引导 {template.Guidance.Length} 字超出预算"));
    }
}
