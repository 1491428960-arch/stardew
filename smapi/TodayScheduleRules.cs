using System.Text.Json.Serialization;

namespace StardewAI.NPC;

/// <summary>
/// 当日日程里的一条安排：游戏端原始时刻 + **已本地化**的地点名。
/// </summary>
/// <remarks>
/// <para>
/// <c>Time</c> 用星露谷自己的 <c>timeOfDay</c> 表示法（600–2600、HHMM 读法、
/// 小时允许 ≥ 24）：600 = 6:00，2400 = 午夜 0:00，2600 = 次日 2:00。
/// 时段词的中文映射**不在这里做**——它属于 Bridge 侧
/// <c>scene.py::time_of_day_label</c>（唯一一份时段表），C# 侧只透传原始整数。
/// </para>
/// <para>
/// <c>Location</c> 优先给 <see cref="StardewValley.GameLocation.DisplayName"/>
/// （游戏内语言，如「鹈鹕镇」），取不到时回退到地图标识符（如 <c>Town</c>）。
/// 两种形态都能进 prompt，但**只有前者是给人读的**，所以
/// <see cref="TodayScheduleRules"/> 只保证「非空」，不保证「已本地化」。
/// </para>
/// </remarks>
public sealed record TodayScheduleEntry(
    [property: JsonPropertyName("time")] int Time,
    [property: JsonPropertyName("location")] string Location);

/// <summary>
/// 当日日程的投影规则：把 <c>NPC.Schedule</c> 的原始字典整理成可外发的条目。
/// </summary>
/// <remarks>
/// <para>
/// **分工**：这里只做「读取之后的确定性整理」——过滤非法时刻与空地点、
/// 按时间排序、合并相邻的同地点停留、限长、限制条数。**压缩成人话**（时段标签、
/// 砍到 2–3 条）在 Bridge 侧 <c>today_schedule.py</c>，因为它要用
/// <c>scene.py</c> 那份唯一的时段表。
/// </para>
/// <para>
/// **失效方向**：任何一步出问题都返回**空列表**，绝不返回半成品。空列表在 Bridge
/// 侧表现为「这一轮没有今日安排卡」——退化成没有日程，而不是给出错误的地点。
/// </para>
/// </remarks>
public static class TodayScheduleRules
{
    /// <summary>
    /// 外发条数上限。真实日程一天通常 3–6 段，12 足够宽裕；
    /// 它防的是异常数据（自定义 NPC 塞进几十段）把请求体撑爆——
    /// Bridge 侧的 <c>today_schedule</c> 字段有同样的长度上限，超了会 422。
    /// </summary>
    public const int MaxEntries = 12;

    /// <summary>
    /// 单个地点名的长度上限。中文地点名通常在 2–6 字，40 是防御性上限
    /// （异常数据里出现过整段对白被当成地点名的情况）。
    /// </summary>
    public const int MaxLocationLength = 40;

    /// <summary>
    /// 日程里 <c>bed</c>（回家睡觉）对应的语义标记；Bridge 侧把它渲染成「家」。
    /// </summary>
    /// <remarks>
    /// 这是一个**跨侧契约**：<c>TodayScheduleEntry.Location</c> 里要么是显示名
    /// （中文或地图标识符），要么就是这个标记。<c>bed</c> 的含义由游戏数据确定
    /// （回家睡觉），所以转成标记是**翻译**而不是猜测——早先试过用
    /// <c>NPC.DefaultMap</c> 顶替，实测会把「夜里在家」写成「夜里在哈维的诊所」，
    /// 因为已婚 NPC 的 <c>DefaultMap</c> 仍记着原住址。
    /// </remarks>
    public const string HomeLocationMarker = "home";

    /// <summary>
    /// 日程里的 <c>bed</c> 原样写法；<see cref="NormalizeLocationName"/> 把它转成
    /// <see cref="HomeLocationMarker"/>。
    /// </summary>
    public const string BedMarker = "bed";

    /// <summary>
    /// 地点名的第一道归一：去掉空白、把 <c>bed</c> 换成语义标记；空值返回 <c>null</c>。
    /// </summary>
    public static string? NormalizeLocationName(string? raw)
    {
        var value = raw?.Trim();
        if (string.IsNullOrEmpty(value))
        {
            return null;
        }

        return string.Equals(value, BedMarker, StringComparison.OrdinalIgnoreCase)
            ? HomeLocationMarker
            : value;
    }

    /// <summary>
    /// 把日程字典整理成待外发的条目；输入为 <c>null</c>、空、或全是不合法条目时返回空列表。
    /// </summary>
    /// <param name="schedule">时刻 → 地点名（原始或已本地化）。</param>
    /// <param name="localize">
    /// 地点名 → 显示名的本地化委托；返回 <c>null</c>/空串表示取不到，此时保留原名。
    /// 传 <c>null</c> 表示不做本地化（测试与非游戏环境）。
    /// </param>
    public static IReadOnlyList<TodayScheduleEntry> Project(
        IEnumerable<KeyValuePair<int, string?>>? schedule,
        Func<string, string?>? localize = null)
    {
        if (schedule is null)
        {
            return Array.Empty<TodayScheduleEntry>();
        }

        var entries = new List<TodayScheduleEntry>();
        try
        {
            foreach (var pair in schedule)
            {
                if (!IsValidTime(pair.Key))
                {
                    continue;
                }

                var raw = pair.Value?.Trim();
                if (string.IsNullOrEmpty(raw))
                {
                    // 地点读不出来就丢掉这一条：宁可少一段安排，
                    // 也不要让模型看到「上午在（空）」。
                    continue;
                }

                var name = Localize(raw, localize) ?? raw;
                if (name.Length > MaxLocationLength)
                {
                    name = name[..MaxLocationLength];
                }

                entries.Add(new TodayScheduleEntry(pair.Key, name));
            }
        }
        catch
        {
            // 枚举过程中抛异常（自定义 NPC 的惰性集合）→ 整张卡不要了。
            return Array.Empty<TodayScheduleEntry>();
        }

        if (entries.Count == 0)
        {
            return Array.Empty<TodayScheduleEntry>();
        }

        // `NPC.Schedule` 是 Dictionary，迭代顺序不保证，所以这里显式排序。
        entries.Sort(static (left, right) => left.Time.CompareTo(right.Time));

        var result = new List<TodayScheduleEntry>();
        foreach (var entry in entries)
        {
            if (result.Count > 0)
            {
                var last = result[^1];
                // 同一时刻只留第一条：游戏偶尔会用同一时刻登记两段，
                // 保留先出现的那条，避免同一时段给出两个地点。
                if (last.Time == entry.Time)
                {
                    continue;
                }

                // 相邻同地点合并：`900 葡萄园 / 1200 葡萄园 / 1400 酒窖`
                // 说明的是「从 9 点起一直在葡萄园」，三段并一段。
                if (string.Equals(last.Location, entry.Location, StringComparison.Ordinal))
                {
                    continue;
                }
            }

            result.Add(entry);
            if (result.Count >= MaxEntries)
            {
                break;
            }
        }

        return result;
    }

    /// <summary>
    /// 时刻是否是可解释的星露谷 <c>timeOfDay</c>：600–2600 且分钟位合法。
    /// </summary>
    /// <remarks>
    /// 与 Bridge 侧 <c>scene.py::time_of_day_label</c> 的范围判定保持一致
    /// （同一把尺子，两处都拒绝 760 这种分钟位非法的取值）。
    /// </remarks>
    public static bool IsValidTime(int time)
    {
        if (time is < 600 or > 2600)
        {
            return false;
        }

        return time % 100 <= 59;
    }

    private static string? Localize(string name, Func<string, string?>? localize)
    {
        if (localize is null)
        {
            return null;
        }

        try
        {
            var localized = localize(name)?.Trim();
            return string.IsNullOrEmpty(localized) ? null : localized;
        }
        catch
        {
            // 本地化失败本身不是错误：回退到地图标识符即可。
            return null;
        }
    }
}
