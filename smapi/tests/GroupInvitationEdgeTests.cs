using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 邀约规则的两处边界回归：
/// 一是模板表与规则内的模板清单是**两个真相源**，漂移了必须能被测试发现；
/// 二是组合去重键必须整体大小写不敏感，否则同一组人换个写法就会重复生成邀约。
/// </summary>
public sealed class GroupInvitationEdgeTests
{
    [Fact]
    public void Every_declared_template_is_recognised_by_the_rules()
    {
        Assert.NotEmpty(GroupInvitationTemplates.All);

        foreach (var template in GroupInvitationTemplates.All)
        {
            Assert.True(
                GroupInvitationRules.IsKnownTemplateId(template.TemplateId),
                $"模板 {template.TemplateId} 未被 GroupInvitationRules 认可（两处模板清单已漂移）");
        }
    }

    [Fact]
    public void Pair_key_is_case_insensitive_across_the_whole_key()
    {
        var canonical = GroupInvitationRules.BuildPairKey(new[] { "Abigail", "Emily" });
        var lowercased = GroupInvitationRules.BuildPairKey(new[] { "abigail", "emily" });
        var mixed = GroupInvitationRules.BuildPairKey(new[] { "EMILY", "abigail" });

        Assert.Equal(canonical, lowercased);
        Assert.Equal(canonical, mixed);
    }

    [Fact]
    public void Pair_key_ignores_order_blank_and_duplicates()
    {
        Assert.Equal(
            GroupInvitationRules.BuildPairKey(new[] { "Abigail", "Emily" }),
            GroupInvitationRules.BuildPairKey(new[] { " emily ", "Abigail", "ABIGAIL", "" }));
    }

    [Fact]
    public void Duplicate_key_ignores_participant_order_and_whitespace()
    {
        // 不钉死分隔符（那只是内存去重键的实现细节，换一种拼法不该让测试假失败），
        // 只断言真正重要的语义：同一组人无论写法与顺序如何，都必须得到同一个键。
        var ordered = Record("mineral-and-mystery", "abigail", "Emily");
        var reversed = Record("mineral-and-mystery", "  EMILY  ", "Abigail");
        var padded = Record("  mineral-and-mystery  ", "abigail", "emily");

        Assert.Equal(
            GroupInvitationRules.BuildDuplicateKey(ordered),
            GroupInvitationRules.BuildDuplicateKey(reversed));
        Assert.Equal(
            GroupInvitationRules.BuildDuplicateKey(ordered),
            GroupInvitationRules.BuildDuplicateKey(padded));
    }

    private static GroupDialogueInvitationRecord Record(
        string templateId,
        params string[] participants) =>
        new()
        {
            InvitationId = "invite-1",
            TemplateId = templateId,
            Participants = participants,
        };
}
