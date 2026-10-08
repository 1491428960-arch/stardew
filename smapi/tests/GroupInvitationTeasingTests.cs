using System;
using System.Linq;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 「打趣」作为**情境主题**（2026-10-09 改定；此前是 2026-10-05 的「加料」方案）。
///
/// 为什么改：加料版把许可文本追加在引导末尾。实测那段文字确实**一字不差地进了
/// 每一次请求**，但模型在 22 次受控重放里**一次都没有采纳**。原因有两层：
/// ① 引导在 prompt 里只是与 `instruction` 平级的 `invitation.guidance` 字段，
/// 还被 `scope` 声明成「不是 NPC 已确认的事实」；
/// ② 模型真正的锚点是 `topic` —— 观测量到，动物主题的卡进去就真的在聊动物。
/// 于是「让模型看见一段许可」和「让模型把这件事当成主任务」是两回事。
///
/// 判据不变：**在场 ≥2 人**处于已接受状态。一位不算——那会变成当着外人的面
/// 议论不在场者的私事，与 friendship 主题的「不提不在场的人的具体私事」直接冲突。
/// </summary>
public sealed class GroupInvitationTeasingTests
{
    private static readonly (string Id, string Name)[] Pair =
    {
        ("Abigail", "Abigail"), ("Emily", "Emily"),
    };

    internal static GroupInvitationGenerationContext Context(
        IReadOnlyList<string>? accepted,
        IReadOnlyList<GroupDialogueInvitationRecord>? existing,
        int currentTotalDays,
        params (string Id, string Name)[] participants)
    {
        return new GroupInvitationGenerationContext(
            CurrentTotalDays: currentTotalDays,
            CurrentDateLabel: "Spring 20",
            KnownParticipants: participants
                .Select(item => new GroupParticipantCandidate(item.Id, item.Name, true))
                .ToArray(),
            // 固定成「两天前刚生成过」：`ShouldGenerate` 要求间隔 ≥ GenerationIntervalDays，
            // 这样调用方想测哪一天就能测哪一天，不会被生成间隔卡住。
            ExistingInvitations: existing ?? Array.Empty<GroupDialogueInvitationRecord>(),
            RecentTopicKeys: Array.Empty<string>(),
            LastCreatedTotalDays: currentTotalDays - GroupInvitationRules.GenerationIntervalDays,
            AcceptedPolyamoryNpcIds: accepted);
    }

    internal static GroupDialogueInvitationRecord Generate(
        IReadOnlyList<string>? accepted,
        int currentTotalDays,
        IReadOnlyList<GroupDialogueInvitationRecord>? existing,
        params (string Id, string Name)[] participants)
    {
        return Assert.Single(new GroupInvitationGenerator(GroupInvitationTemplates.All)
            .Generate(Context(accepted, existing, currentTotalDays, participants)));
    }

    internal static bool IsTeasing(GroupDialogueInvitationRecord invitation) =>
        invitation.TemplateId.StartsWith(
            GroupInvitationTemplates.TeasingThemeId + ":", StringComparison.Ordinal);

    [Fact]
    public void Both_participants_accepted_makes_teasing_the_topic()
    {
        var invitation = Generate(new[] { "Abigail", "Emily" }, 20, null, Pair);

        Assert.True(IsTeasing(invitation), $"期望打趣主题，实际是 {invitation.TemplateId}");
        // 打趣现在走 `topic`，不再是引导末尾的一段附注 —— 这两条断言
        // 正是「它成了主任务」的可检验形式。
        // 2026-10-09：Topic 从「镇上那点风声」改成话题域「几个人和玩家之间的来往」。
        // 前者是氛围标题，真机上模型会顺着它去聊镇上传闻（矿洞晶石、矿井里的发光眼睛），
        // 整场不碰主题；Title 仍是给玩家看的展示名，保持不变。
        Assert.Equal("几个人和玩家之间的来往", invitation.Topic);
        Assert.Equal("镇上那点风声", invitation.Title);
        Assert.Contains("打趣", invitation.Guidance);
        Assert.Contains("Abigail", invitation.Guidance);
        Assert.Contains("Emily", invitation.Guidance);
    }

    [Fact]
    public void Teasing_direction_is_a_topic_domain_and_guidance_leads_with_a_positive_instruction()
    {
        // 2026-10-09 真机教训形成的两道守卫：
        // ① Direction 会原样变成 topic，必须是「聊什么」的话题域并且点明玩家；
        //    只说「风声」「传闻」之类，模型会跑去聊别的八卦。
        // ② Guidance 必须以正面指示开头。旧版通篇否定子句（不追问／不评判／不表态／
        //    不宣告／不拿…），模型拿不到"要做什么"，实测 0/22 全败；改成先说要做什么、
        //    再划红线之后才开始有命中。
        var theme = GroupInvitationThemes.All["teasing"];

        Assert.Contains("玩家", theme.Direction);
        Assert.StartsWith("拿这件事", theme.Guidance);
    }

    [Fact]
    public void Without_the_accepted_list_the_topic_is_an_ordinary_shared_theme()
    {
        var invitation = Generate(null, 20, null, Pair);

        Assert.False(IsTeasing(invitation));
        Assert.DoesNotContain("打趣", invitation.Guidance);
    }

    [Fact]
    public void An_unrelated_accepted_npc_does_not_enable_teasing()
    {
        // 已接受名单里有别人，但**这组里**只有 Abigail 一个 —— 不该打趣。
        var invitation = Generate(new[] { "Abigail", "Sophia" }, 20, null, Pair);

        Assert.False(IsTeasing(invitation));
        Assert.DoesNotContain("打趣", invitation.Guidance);
    }

    [Fact]
    public void Only_the_participants_who_are_in_on_it_are_named()
    {
        // 三人场：在场两位已接受，第三位不在名单里。指导语只应点名那两位。
        var invitation = Generate(
            new[] { "Abigail", "Emily" },
            20,
            null,
            ("Abigail", "Abigail"), ("Emily", "Emily"), ("Shane", "Shane"));

        Assert.True(IsTeasing(invitation));
        Assert.Contains("Abigail", invitation.Guidance);
        Assert.Contains("Emily", invitation.Guidance);
        Assert.DoesNotContain("Shane", invitation.Guidance);
    }

    [Fact]
    public void Clause_forbids_announcing_relationship_outcomes()
    {
        var invitation = Generate(new[] { "Abigail", "Emily" }, 20, null, Pair);

        // 与既有的「邀约卡不得宣告关系结果」同一条红线。
        Assert.Contains("不要宣告任何关系的结论", invitation.Guidance);
        Assert.Contains("不要拿不在场的人开玩笑", invitation.Guidance);
    }

    [Fact]
    public void Teasing_theme_is_in_the_theme_table_but_not_in_the_per_npc_index()
    {
        // 两个条件同时成立才对：
        // ① 在 `All` 里 —— 否则 `IsKnownTemplateId` 会判它非法，而那会**在
        //    DayStarted 里抛异常、之后再也不生成任何新邀约**（2026-09-20 真机踩到过）；
        // ② 不在 `ThemesByNpc` 里 —— 否则 `SharedThemes` 会把它当成普通共同主题，
        //    任何一组成员都可能莫名其妙地聊起打趣。
        Assert.True(GroupInvitationThemes.All.ContainsKey(GroupInvitationTemplates.TeasingThemeId));
        Assert.DoesNotContain(
            GroupInvitationThemes.ThemesByNpc.Values.SelectMany(themes => themes),
            theme => theme == GroupInvitationTemplates.TeasingThemeId);
    }

    [Fact]
    public void Ordinary_group_templates_never_carry_the_teasing_theme()
    {
        var group = new[] { "Abigail", "Emily", "Shane" };

        Assert.All(
            GroupInvitationTemplates.ForGroup(group),
            template => Assert.False(
                template.TemplateId.StartsWith(
                    GroupInvitationTemplates.TeasingThemeId + ":", StringComparison.Ordinal),
                $"{template.TemplateId} 不该由共同主题表产出"));
    }

    [Fact]
    public void Teasing_template_id_passes_the_whitelist()
    {
        var template = GroupInvitationTemplates.CreateTeasing(
            new[] { "Abigail", "Emily" }, new[] { "Abigail", "Emily" });

        Assert.True(GroupInvitationRules.IsKnownTemplateId(template.TemplateId));
    }

    [Fact]
    public void Guidance_stays_within_the_bridge_limit()
    {
        // Bridge 的 `GroupDialogueRequest.invitation_guidance` 是
        // `Field(max_length=500)` —— 这是**校验**而不是截断：超了会让整个群聊请求
        // 直接 422，比静默丢字段更难看。所以打趣主题自己的引导也必须在这条线以内。
        const int bridgeLimit = 500;
        var template = GroupInvitationTemplates.CreateTeasing(
            new[] { "Abigail", "Emily" }, new[] { "Abigail", "Emily" });

        Assert.True(
            template.Guidance.Length <= GroupInvitationTemplates.MaxGuidanceLength,
            $"打趣引导 {template.Guidance.Length} 字超出预算 {GroupInvitationTemplates.MaxGuidanceLength}");
        Assert.True(template.Guidance.Length <= bridgeLimit);
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

    // ── 「一次性主题」语义（2026-10-09）────────────────────────────────
    //
    // 用户判断：「打趣当个甜点话题触发一次就够了，多次来真的很无聊」。
    // 于是打趣从「按 ExpirationDays 冷却 7 天」改成「这档只来一次」。
    // 下面三条分别守住：它真的不再回来、dev 卡不吃掉这次机会、dev 卡存得进存档。

    [Fact]
    public void Teasing_never_returns_once_it_has_naturally_occurred()
    {
        // 自然来过一次（Abigail + Emily，第 20 天）。
        var happened = Generate(new[] { "Abigail", "Emily" }, 20, null, Pair);
        Assert.True(IsTeasing(happened));

        // 之后一路往后推，**换一组人**（避开 pair-key 去重 —— 否则断言会因为
        // 生成器压根没产出任何卡而空过，测了个寂寞），全都不许再是打趣。
        //
        // 第 27 天起就超过了原来的 7 天冷却窗口，第 400 天则连卡本身都早已过期：
        // 过期只是把 Status 改成 Expired（`ExpireInvitations` 不删记录），
        // 所以「这档来过」这件事必须一直查得到。
        var otherPair = new[] { ("Haley", "Haley"), ("Leah", "Leah") };
        foreach (var day in new[] { 21, 27, 28, 60, 400 })
        {
            var later = Generate(
                new[] { "Haley", "Leah" }, day, new[] { happened }, otherPair);

            Assert.False(
                IsTeasing(later),
                $"第 {day} 天又生成了打趣卡：{later.TemplateId}");
        }
    }

    [Fact]
    public void A_development_authored_card_does_not_consume_the_one_shot_theme()
    {
        var group = new[]
        {
            new GroupParticipantCandidate("Abigail", "Abigail", true),
            new GroupParticipantCandidate("Emily", "Emily", true),
        };
        var devCard = Assert.Single(new GroupInvitationGenerator(GroupInvitationTemplates.All)
            .GenerateForcedTeasing(20, "Spring 20", group));
        Assert.Equal(GroupInvitationRules.DevSource, devCard.Source);

        // 历史里只有这一张 dev 卡 —— 玩家那次真正的机会**还在**。
        // ⚠ 这条同时守着生成器入口的统一过滤：dev 卡的 TemplateId 和 pairKey
        // 与自然生成的**完全相同**，如果入口没把 Source = "dev" 的记录滤掉，
        // 它会从「去重」这条路上把自然生成挡死（不是从冷却那条路）——
        // 症状是「Ctrl+Shift+F9 按过一次，这档就再也不出打趣了」。
        var natural = Generate(new[] { "Abigail", "Emily" }, 20, new[] { devCard }, Pair);

        Assert.True(IsTeasing(natural), $"dev 卡不该消耗掉自然机会，实际是 {natural.TemplateId}");
    }

    [Fact]
    public void The_development_source_passes_the_persistence_whitelist()
    {
        // Source 不是随便一个字符串：`StoryStateValidation` 按白名单校验，
        // 不在名单里的卡会在**存档时被静默丢弃** —— 玩家按 F9 看得见、
        // 存个档回来就没了，只会被当成 bug。
        Assert.True(GroupInvitationRules.IsValidSource(GroupInvitationRules.DevSource));
    }
}
