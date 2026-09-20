using System.Collections.Generic;
using System.Linq;

namespace StardewAI.NPC;

public sealed record GroupInvitationTemplate(
    string TemplateId,
    string Title,
    string Topic,
    string Guidance,
    string Source,
    IReadOnlyList<string> RequiredParticipants);

/// <summary>
/// 群聊邀约模板表。**按「角色 × 共同主题」程序化生成，主题与例句都来自真实对白。**
///
/// 背景（2026-09-20 用户反馈）：
/// ① “这模板太匮乏了，阿比全是公式化下矿，起码得有个四位数的模板吧”；
/// ② 只靠兴趣标签“太刻板印象了，我们应该还有根据每个人物的剧情和对白总结出来的更细的东西”。
///
/// 所以这里的主题**不是手编标签**，而是离线脚本从索引的 10084 条 styleSamples 里
/// 按关键词匹配抽取的（见 GroupInvitationThemes），并且**每个角色在每个主题下
/// 都保留了真实说过的原句**。生成模板时：
/// - 话题 = 这组人**共同聊到过**的主题；
/// - 引导里附上他们各自的原话，让模型有据可依（但明确要求不要照抄）。
///
/// 于是 Abigail 的话题取决于她和谁在一组：跟 Shane 会落到别处，而不是永远“下矿”。
/// </summary>
public static class GroupInvitationTemplates
{
    /// <summary>三人组合每个主题最多取几条（不限制的话三人组合会很多）。</summary>
    /// <summary>没有任何共同主题时的兜底（名单外角色、资料太薄的组合）。</summary>
    private const string FallbackThemeId = "town";

    /// <summary>
    /// 两两组合的模板（**只用于测试与检视**；生产路径走 <see cref="ForGroup"/>）。
    ///
    /// ⚠️ 不要把三人组合也预生成进来：88 个角色的三人组合有 10 万组，
    /// 乘上共同主题会产生 **35 万个模板对象**，常驻内存约 150 MB —— 对 mod
    /// 不可接受（2026-09-20 实测到这个数字后改成按需生成）。
    /// </summary>
    public static IReadOnlyList<GroupInvitationTemplate> All { get; } = BuildPairs();

    private static IReadOnlyList<GroupInvitationTemplate> BuildPairs()
    {
        var npcIds = KnownNpcIds();
        var templates = new List<GroupInvitationTemplate>();
        for (var first = 0; first < npcIds.Length - 1; first++)
        {
            for (var second = first + 1; second < npcIds.Length; second++)
            {
                templates.AddRange(ForGroup(new[] { npcIds[first], npcIds[second] }));
            }
        }

        return templates;
    }

    /// <summary>
    /// **为这一组人即时生成模板**：取他们的共同主题，每个主题一条。
    ///
    /// 生成器只对“当前实际存在的这组候选”调用它，所以不需要预生成全部组合。
    /// 没有共同主题时用兜底主题，保证任意两人都有话可聊。
    /// </summary>
    public static IReadOnlyList<GroupInvitationTemplate> ForGroup(IReadOnlyList<string> group)
    {
        ArgumentNullException.ThrowIfNull(group);
        if (group.Count < 2)
        {
            return Array.Empty<GroupInvitationTemplate>();
        }

        var shared = SharedThemes(group);
        // 兜底：主题表是从真实对白抽的，资料太薄的组合可能一条共同主题都没有——
        // 不兜底就会出现“这两个人永远生成不出邀约”。
        if (shared.Count == 0)
        {
            shared.Add(FallbackThemeId);
        }

        var groupKey = string.Join("|", group.Select(id => id.ToLowerInvariant()));
        var templates = new List<GroupInvitationTemplate>();
        foreach (var themeId in shared)
        {
            if (!GroupInvitationThemes.All.TryGetValue(themeId, out var theme))
            {
                continue;
            }

            templates.Add(new GroupInvitationTemplate(
                $"{themeId}:{groupKey}",
                theme.Title,
                theme.Direction,
                BuildGuidance(theme, group),
                "periodic",
                group));
        }

        return templates;
    }

    /// <summary>资料够用的角色（在至少两个主题上有真实对白）。</summary>
    private static string[] KnownNpcIds() =>
        GroupInvitationThemes.SamplesByNpcTheme.Keys
            .Select(key => key.Split('|')[0])
            .Distinct(StringComparer.Ordinal)
            .OrderBy(id => id, StringComparer.Ordinal)
            .ToArray();

    /// <summary>
    /// 引导语：主题自己的收束要求 ＋ 参与者在该主题下说过的原话。
    /// 原话是给模型的“语气与立场的参照”，不是让它们复读。
    /// </summary>
    private static string BuildGuidance(GroupInvitationThemes.Theme theme, IReadOnlyList<string> group)
    {
        var lines = new List<string>
        {
            $"聊的是参与者各自的经验与看法。{theme.Guidance}",
        };

        foreach (var npcId in group)
        {
            if (GroupInvitationThemes.SamplesByNpcTheme.TryGetValue($"{npcId}|{theme.Id}", out var samples)
                && samples.Length > 0)
            {
                lines.Add($"{npcId} 以前说过：「{samples[0]}」");
            }
        }

        lines.Add("上面这些是他们的语气与立场参照，**不要照抄**，也不要假定别人已经知道这些内容。");
        return string.Join("", lines);
    }

    /// <summary>组内所有人都聊到过的主题。</summary>
    private static List<string> SharedThemes(IReadOnlyList<string> group)
    {
        var shared = new List<string>();
        if (group.Count == 0 || !GroupInvitationThemes.ThemesByNpc.TryGetValue(group[0], out var first))
        {
            return shared;
        }

        foreach (var theme in first)
        {
            var inAll = true;
            for (var index = 1; index < group.Count; index++)
            {
                if (!GroupInvitationThemes.ThemesByNpc.TryGetValue(group[index], out var other)
                    || !other.Contains(theme, System.StringComparer.Ordinal))
                {
                    inAll = false;
                    break;
                }
            }

            if (inAll)
            {
                shared.Add(theme);
            }
        }

        return shared;
    }
}
