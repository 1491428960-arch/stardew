using System;
using System.Collections.Generic;
using System.Linq;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 话题轮换（2026-10-09）。
///
/// 修的是「群聊全是动物」：此前 <see cref="GroupInvitationGenerator"/> 里
/// <c>MatchingTemplates</c> 排序的最后一步是 `ThenBy(TemplateId, StringComparer.Ordinal)`
/// —— **纯字母序**，而 <c>Generate</c> 只取第一张不重复的。`animals` 以 "a" 开头，
/// **永远排第一**；去重键里含参与者组合，换一组人、或从两人换三人，它就重新可用。
/// 于是存档里 136 / 138 / 140 三张卡全是「养的动物」。
/// </summary>
public sealed class GroupInvitationTopicRotationTests
{
    private static readonly (string Id, string Name)[] Trio =
    {
        ("Abigail", "Abigail"), ("Alex", "Alex"), ("Emily", "Emily"),
    };

    private static string ThemeIdOf(string templateId)
    {
        var separator = templateId.IndexOf(':');
        return separator > 0 ? templateId[..separator] : templateId;
    }

    private static GroupDialogueInvitationRecord[] Generate(
        IReadOnlyList<GroupDialogueInvitationRecord> existing,
        int day,
        params (string Id, string Name)[] participants)
    {
        return new GroupInvitationGenerator(GroupInvitationTemplates.All)
            .Generate(GroupInvitationTeasingTests.Context(null, existing, day, participants))
            .ToArray();
    }

    [Fact]
    public void A_theme_used_two_days_ago_gives_way_to_a_fresher_one()
    {
        // 直接复现用户看到的那一幕：上一次刚聊过动物，下一次不该还是动物。
        // 旧排序下这两张必然是同一个主题（都是 animals），这条断言就是回归闸门。
        var first = Generate(Array.Empty<GroupDialogueInvitationRecord>(), 20, Trio);
        Assert.NotEmpty(first);

        var second = Generate(first, 22, Trio);
        Assert.NotEmpty(second);

        Assert.NotEqual(
            ThemeIdOf(first[0].TemplateId),
            ThemeIdOf(second[0].TemplateId));
    }

    [Fact]
    public void Consecutive_cards_spread_across_many_themes()
    {
        var existing = new List<GroupDialogueInvitationRecord>();
        var themes = new List<string>();
        for (var day = 20; day < 60; day += GroupInvitationRules.GenerationIntervalDays)
        {
            var generated = Generate(existing, day, Trio);
            if (generated.Length == 0)
            {
                continue;
            }

            existing.AddRange(generated);
            themes.Add(ThemeIdOf(generated[0].TemplateId));
        }

        Assert.True(themes.Count >= 8, $"只生成了 {themes.Count} 张卡：{string.Join(",", themes)}");
        Assert.True(
            themes.Distinct(StringComparer.Ordinal).Count() >= 5,
            $"主题过于单一：{string.Join(",", themes)}");
        Assert.True(
            themes.Count(theme => theme == "animals") <= 2,
            $"animals 仍在包场（{themes.Count(theme => theme == "animals")} 次）：{string.Join(",", themes)}");
    }

    [Fact]
    public void A_fresh_save_does_not_start_at_the_alphabetically_first_theme()
    {
        // 全新存档里所有主题的「最近使用天数」都是 int.MinValue，全部并列 ——
        // 没有稳定哈希兜底的话，字母序又会让 animals 包场。
        // 不同组人的 groupKey 不同 ⇒ 兜底哈希给出的起点应当不同。
        var pairs = new[]
        {
            new[] { ("Abigail", "Abigail"), ("Emily", "Emily") },
            new[] { ("Alex", "Alex"), ("Haley", "Haley") },
            new[] { ("Shane", "Shane"), ("Leah", "Leah") },
            new[] { ("Sebastian", "Sebastian"), ("Maru", "Maru") },
        };

        var firsts = pairs
            .Select(pair => Generate(Array.Empty<GroupDialogueInvitationRecord>(), 20, pair))
            .Where(result => result.Length > 0)
            .ToArray();
        Assert.NotEmpty(firsts);

        var distinct = firsts
            .Select(result => ThemeIdOf(result[0].TemplateId))
            .Distinct(StringComparer.Ordinal)
            .Count();
        Assert.True(distinct > 1, "四组人都落到同一个首发主题上 —— 兜底哈希没起作用");

        // 这些组都没有 accepted 记录，谁都不该聊打趣。
        Assert.All(
            firsts.SelectMany(result => result),
            invitation => Assert.False(
                invitation.TemplateId.StartsWith(
                    GroupInvitationTemplates.TeasingThemeId + ":", StringComparison.Ordinal)));
    }
}
