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
    [Fact]
    public void There_are_thousands_of_templates()
    {
        // 用户反馈：模板太匮乏（“阿比全是公式化下矿”）。模板现在是按
        // 「角色组合 × 话题池」程序化生成的，数量应达到四位数。
        var count = GroupInvitationTemplates.All.Count;
        Console.WriteLine($"[Templates] 模板总数 = {count}");
        Assert.True(count >= 1000, $"模板数只有 {count}，应达到四位数");
    }

    [Fact]
    public void Most_pairs_of_known_npcs_share_at_least_one_theme()
    {
        // 主题是从真实对白抽的，覆盖面广（craft/friendship/work 都在 60 个角色以上），
        // 所以绝大多数组合都能找到共同话题；找不到的由生成器兜底到“镇上日常”。
        var npcIds = GroupInvitationThemes.ThemesByNpc.Keys.OrderBy(id => id, StringComparer.Ordinal).ToArray();
        var pairsWithTemplate = new HashSet<string>(StringComparer.Ordinal);
        foreach (var template in GroupInvitationTemplates.All.Where(t => t.RequiredParticipants.Count == 2))
        {
            pairsWithTemplate.Add(string.Join("|", template.RequiredParticipants.OrderBy(x => x, StringComparer.Ordinal)));
        }

        var total = 0;
        var missing = 0;
        for (var first = 0; first < npcIds.Length - 1; first++)
        {
            for (var second = first + 1; second < npcIds.Length; second++)
            {
                total++;
                if (!pairsWithTemplate.Contains(string.Join("|", new[] { npcIds[first], npcIds[second] }.OrderBy(x => x, StringComparer.Ordinal))))
                {
                    missing++;
                }
            }
        }

        // 兜底保证一个都不缺
        Assert.Equal(0, missing);
        Assert.True(total > 1000, $"两两组合只有 {total} 对");
    }

    [Fact]
    public void Abigail_pairs_are_not_all_about_mining()
    {
        // 回归保护：此前只有 6 个模板，Abigail 参与的任何组合都会被塞进“下矿”。
        // 现在她的组合应该分到探险、超自然，以及兜底话题等多种题目。
        var titles = GroupInvitationTemplates.All
            .Where(t => t.RequiredParticipants.Contains("Abigail", StringComparer.OrdinalIgnoreCase))
            .Select(t => t.Title)
            .Distinct(StringComparer.Ordinal)
            .ToArray();

        Assert.True(titles.Length >= 8, $"Abigail 相关模板的题目只有 {titles.Length} 种");
        Console.WriteLine($"[Templates] Abigail 的题目：{string.Join("、", titles.Take(12))}");
        Assert.Contains(titles, title => !title.Contains("矿", StringComparison.Ordinal));
    }
    [Fact]
    public void Diag_print_abigail_templates()
    {
        // 临时诊断：用户反馈“主题是动物，但具体内容还是矿洞”，
        // 需要看实际的 title/topic/guidance 里到底写了什么。
        foreach (var group in new[]
                 {
                     new[] { "Abigail", "Alex" },
                     new[] { "Abigail", "Shane" },
                 })
        {
            Console.WriteLine($"[Diag] === {string.Join(" + ", group)} ===");
            foreach (var template in GroupInvitationTemplates.ForGroup(group))
            {
                Console.WriteLine($"[Diag]   [{template.TemplateId}]");
                Console.WriteLine($"[Diag]   标题={template.Title}");
                Console.WriteLine($"[Diag]   话题={template.Topic}");
                Console.WriteLine($"[Diag]   引导={template.Guidance}");
            }
        }
    }

}
