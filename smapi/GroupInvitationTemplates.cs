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
    /// <summary>
    /// 引导语的字节预算（2026-10-05）。**这不是美观问题，是硬约束**：
    /// Bridge 的 <c>GroupDialogueRequest.invitation_guidance</c> 是
    /// <c>Field(max_length=500)</c> —— pydantic 的**校验**而非截断，超了会让
    /// 整个群聊请求直接 422，玩家看到的是一句「群聊打不开」。
    ///
    /// 实测：两人场最坏的一条（`health:demetrius|linus`）已是 **430 字**，
    /// 三人场只会更长——所以模板生成必须在这条线上收敛。
    /// 留 20 字余量，不贴着 500 走。
    /// </summary>
    public const int MaxGuidanceLength = 480;
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

        var groupKey = BuildGroupKey(group);
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
        return ClampGuidance(string.Join("", lines));
    }

    /// <summary>
    /// 把引导截到 <see cref="MaxGuidanceLength"/> 以内，并预留 <paramref name="reserved"/>
    /// 字给调用方随后要追加的内容。
    ///
    /// （2026-10-09 起生产路径已无调用方 —— 打趣从「追加到引导末尾」改成了独立主题。
    /// 参数保留，因为它描述的是截断语义本身，将来要拼接别的内容时不至于重写这里。）
    ///
    /// 只在超限时才动文本，所以现有那些本来就够短的模板**一个字节都不变**。
    /// 截断处补一个省略号：让「这句被截过」在文本里看得见，而不是让模型读到一个
    /// 断掉的句子却毫不知情。
    /// </summary>
    public static string ClampGuidance(string guidance, int reserved = 0)
    {
        var limit = Math.Max(0, MaxGuidanceLength - Math.Max(0, reserved));
        if (guidance.Length <= limit)
        {
            return guidance;
        }

        return limit <= 1 ? string.Empty : guidance.Substring(0, limit - 1) + "…";
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

    /// <summary>情境主题的 ID（不进 <see cref="GroupInvitationThemes.ThemesByNpc"/>）。</summary>
    public const string TeasingThemeId = "teasing";

    /// <summary>
    /// **一次性主题**：同一个存档里只该出现一次，来过就永远不再来
    /// （2026-10-09 用户判断：「打趣当个甜点话题触发一次就够了，多次来真的很无聊」）。
    ///
    /// 为什么它是「耗尽」而不是「冷却」：`animals` 那类日常话题可以反复聊，
    /// 因为信息量在话题本身；打趣的信息量全在「这件事被摆到台面上」的那一下，
    /// 第二次就只剩重复。重放数据也一致 —— 打趣命中率只有 1/3–1/2，
    /// 靠的正是意外感。
    ///
    /// 判据只看**自然生成**的历史：dev 入口
    /// （<see cref="GroupInvitationRules.DevSource"/>）造的卡不算数，
    /// 否则按一下 Ctrl+Shift+F9 就把玩家这档真正的那次机会用掉了。
    /// </summary>
    public static readonly IReadOnlySet<string> OneShotThemeIds =
        new HashSet<string>(StringComparer.Ordinal) { TeasingThemeId };

    /// <summary>
    /// 「打趣」的**触发判据**（2026-10-05 定，2026-10-09 沿用）：**在场至少两位**
    /// 已接受玩家的多元关系。
    ///
    /// 判据为什么要求**在场**两位：只有一位时，这句话会变成当着外人的面议论
    /// 不在场者的私事，与 friendship 主题写明的「不提不在场的人的具体私事」直接冲突。
    /// </summary>
    public static bool CanTease(
        IReadOnlyList<string> group,
        IReadOnlyList<string>? acceptedNpcIds)
    {
        ArgumentNullException.ThrowIfNull(group);
        return InOnIt(group, acceptedNpcIds).Length >= 2;
    }

    /// <summary>
    /// 「打趣」主题的模板（2026-10-09）。**不来自共同主题表，而是情境触发** ——
    /// 由生成器在 <see cref="CanTease"/> 成立且不在冷却期时注入。
    ///
    /// 为什么从「引导末尾的加料」改成「主题本体」（2026-10-09 实测转向）：
    /// 作为加料，这段文本确实一字不差地进了每一次请求，但模型在 **22 次受控重放里
    /// 一次都没有采纳**。原因有两层：① 引导在 prompt 里只是与 `instruction` 平级的
    /// `invitation.guidance` 字段，还被 `scope` 声明成「不是 NPC 已确认的事实」；
    /// ② 模型真正的锚点是 `topic` —— 观测量到，动物主题的卡进去就真的在聊动物。
    /// 「让模型看见一段许可」和「让模型把这件事当成主任务」是两回事。
    /// </summary>
    public static GroupInvitationTemplate CreateTeasing(
        IReadOnlyList<string> group,
        IReadOnlyList<string>? acceptedNpcIds)
    {
        ArgumentNullException.ThrowIfNull(group);
        var theme = GroupInvitationThemes.All[TeasingThemeId];
        var names = string.Join("、", InOnIt(group, acceptedNpcIds));
        return new GroupInvitationTemplate(
            $"{TeasingThemeId}:{BuildGroupKey(group)}",
            theme.Title,
            theme.Direction,
            ClampGuidance($"{names} 和玩家在一起这件事，镇上早就不是秘密了。{theme.Guidance}"),
            "periodic",
            group);
    }

    private static string[] InOnIt(IReadOnlyList<string> group, IReadOnlyList<string>? acceptedNpcIds)
    {
        if (acceptedNpcIds is null || group.Count < 2)
        {
            return System.Array.Empty<string>();
        }

        var accepted = new System.Collections.Generic.HashSet<string>(
            acceptedNpcIds, System.StringComparer.OrdinalIgnoreCase);
        return group
            .Where(id => !string.IsNullOrWhiteSpace(id) && accepted.Contains(id))
            .ToArray();
    }

    private static string BuildGroupKey(IReadOnlyList<string> group) =>
        string.Join("|", group.Select(id => id.ToLowerInvariant()));
}
