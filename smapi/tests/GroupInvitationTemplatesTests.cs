using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupInvitationTemplatesTests
{
    [Fact]
    public void Every_template_carries_the_fields_the_generator_needs()
    {
        Assert.NotEmpty(GroupInvitationTemplates.All);

        foreach (var template in GroupInvitationTemplates.All)
        {
            Assert.False(string.IsNullOrWhiteSpace(template.TemplateId));
            Assert.False(string.IsNullOrWhiteSpace(template.Title));
            Assert.False(string.IsNullOrWhiteSpace(template.Topic));
            Assert.False(string.IsNullOrWhiteSpace(template.Guidance));
            // 来源必须落在规则允许的集合里，否则生成的邀约会被判为无效。
            Assert.True(
                GroupInvitationRules.IsValidSource(template.Source),
                $"模板 {template.TemplateId} 的来源不合法：{template.Source}");
        }
    }

    [Fact]
    public void Template_ids_are_unique()
    {
        var ids = GroupInvitationTemplates.All
            .Select(template => template.TemplateId)
            .ToArray();

        Assert.Equal(ids.Length, ids.Distinct(StringComparer.Ordinal).Count());
    }

    [Fact]
    public void Required_participants_are_two_to_three_distinct_names()
    {
        foreach (var template in GroupInvitationTemplates.All)
        {
            // 不限定参与者的模板（公共话题）允许为空列表。
            if (template.RequiredParticipants.Count == 0)
            {
                continue;
            }

            Assert.InRange(template.RequiredParticipants.Count, 2, 3);
            Assert.Equal(
                template.RequiredParticipants.Count,
                template.RequiredParticipants
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .Count());
        }
    }
}
