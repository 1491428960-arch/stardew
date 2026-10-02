namespace StardewAI.NPC;

/// <summary>
/// 「昨天完成了哪个事件」的唯一来源（2026-09-27）。
///
/// Bridge 侧**推不出**这件事：它拿到的 `completedEventIds` 是累积全集、不含完成时间。
/// 所以「刚完成的」必须由游戏端在跨天时算好送过去，这个类就是那个计算。
///
/// ⚠ **粒度是「天」，这是它不能复用 <see cref="EventAuditObserver"/> 的原因。**
/// 那个 observer 每次换图都可能被调用，算出来的是「自上次观察以来」；
/// 玩家一天进出几次房间，同一批事件就会被反复上报，第二天早上会收到好几条
/// 指向同一件事的后续消息。
/// </summary>
public sealed class RecentEventTracker
{
    private IReadOnlyList<string>? previousDayEventIds;

    /// <summary>
    /// 在 `DayStarted` 时调用一次：返回自上一次调用以来新完成的事件 id。
    ///
    /// 首次调用**必定返回空**——存档里可能已经有几百个历史事件，
    /// 把它们当成「昨天刚发生」会让玩家一读档就收到一堆莫名其妙的后续消息。
    /// </summary>
    public IReadOnlyList<string> ObserveDay(IEnumerable<string>? seenEventIds)
    {
        var current = EventAuditRules.NormalizeIds(seenEventIds);
        var previous = previousDayEventIds;
        previousDayEventIds = current;

        if (previous is null)
        {
            // 没有基线时把当前快照本身当基线。空集合也要走这一步 ——
            // 否则新档第一天的第二个事件会因为没有基线而被吞掉。
            return Array.Empty<string>();
        }

        return current
            // ⚠ `StringComparer.Ordinal`：事件 ID 大小写敏感（`EventAuditRules` 的契约），
            // 与 NPC ID 忽略大小写的规则**恰好相反**。合并会掩盖真实差异。
            .Except(previous, StringComparer.Ordinal)
            // 顺序稳定才谈得上可复现。Bridge 侧按 id 排序取第一条，
            // 但游戏端送过去的顺序不该取决于 HashSet 的枚举顺序。
            .OrderBy(value => value, StringComparer.Ordinal)
            .ToArray();
    }

    public void Reset()
    {
        previousDayEventIds = null;
    }
}
