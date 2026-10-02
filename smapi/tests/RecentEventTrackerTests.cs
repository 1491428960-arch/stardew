using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 「昨天完成了哪个事件」的唯一来源（2026-09-27）。
///
/// Bridge 侧完全推不出来这件事：它拿到的 `completedEventIds` 是**累积全集**、
/// 不含完成时间，所以「新完成的」必须由游戏端在跨天时算好送过去。
/// 这个类就是那个计算 —— 粒度必须是**天**，不能复用 `EventAuditObserver`：
/// 那个 observer 每次换图都可能被调用，算出来的是「自上次观察以来」，
/// 拿它当「昨天」会在玩家一天进出几次房间时把同一批事件反复上报。
/// </summary>
public sealed class RecentEventTrackerTests
{
    [Fact]
    public void First_observation_reports_nothing_because_there_is_no_baseline()
    {
        var tracker = new RecentEventTracker();

        // ⚠ 首次必须空手而归。存档里可能已经有几百个 old events，
        // 把它们当「昨天刚发生」会让玩家一进游戏就收到一堆莫名其妙的后续消息。
        Assert.Empty(tracker.ObserveDay(new[] { "13", "20", "384882" }));
    }

    [Fact]
    public void Reports_events_added_since_the_previous_day()
    {
        var tracker = new RecentEventTracker();
        tracker.ObserveDay(new[] { "13", "20" });

        Assert.Equal(new[] { "2119820" }, tracker.ObserveDay(new[] { "13", "20", "2119820" }));
    }

    [Fact]
    public void Reports_nothing_when_the_day_adds_nothing()
    {
        var tracker = new RecentEventTracker();
        tracker.ObserveDay(new[] { "13", "20" });

        Assert.Empty(tracker.ObserveDay(new[] { "13", "20" }));
    }

    [Fact]
    public void Reports_each_event_only_once()
    {
        var tracker = new RecentEventTracker();
        tracker.ObserveDay(new[] { "13" });

        Assert.Equal(new[] { "20" }, tracker.ObserveDay(new[] { "13", "20" }));
        // 第二天它已经在基线里了，不该再报一次。
        Assert.Empty(tracker.ObserveDay(new[] { "13", "20" }));
    }

    [Fact]
    public void Event_ids_are_case_sensitive()
    {
        var tracker = new RecentEventTracker();
        tracker.ObserveDay(new[] { "abc" });

        // `EventAuditRules` 的契约：`"A"` 与 `"a"` 是两个不同的事件
        // （与 NPC ID 忽略大小写的规则相反）。大小写合并会掩盖真实差异。
        Assert.Equal(new[] { "ABC" }, tracker.ObserveDay(new[] { "abc", "ABC" }));
    }

    [Fact]
    public void A_shrinking_set_does_not_report_anything()
    {
        var tracker = new RecentEventTracker();
        tracker.ObserveDay(new[] { "13", "20", "30" });

        // 读档回退、切存档、或上游读失败都会让集合变小。
        // 变小永远不是「新事件」，绝不能报。
        Assert.Empty(tracker.ObserveDay(new[] { "13" }));
    }

    [Fact]
    public void Blank_and_duplicate_ids_are_normalized()
    {
        var tracker = new RecentEventTracker();
        tracker.ObserveDay(new[] { " 13 ", "", "13" });

        // 规范化后与基线一致，所以没有新事件。
        Assert.Empty(tracker.ObserveDay(new[] { "13" }));
    }

    [Fact]
    public void Several_new_events_are_reported_in_a_stable_order()
    {
        var tracker = new RecentEventTracker();
        tracker.ObserveDay(Array.Empty<string>());

        var reported = tracker.ObserveDay(new[] { "zzz", "aaa", "mmm" });

        // 顺序稳定才谈得上可复现：Bridge 侧按 id 排序取第一条，
        // 但游戏端送过来的顺序不该是随机的。
        Assert.Equal(reported.OrderBy(value => value, StringComparer.Ordinal), reported);
    }

    [Fact]
    public void Empty_first_observation_still_establishes_a_baseline()
    {
        var tracker = new RecentEventTracker();

        // 新档第一天：空集合也要被当成基线，否则第二天的第一个事件
        // 会因为「上次是 null」而被吞掉。
        Assert.Empty(tracker.ObserveDay(Array.Empty<string>()));

        Assert.Equal(new[] { "13" }, tracker.ObserveDay(new[] { "13" }));
    }

    [Fact]
    public void Reset_discards_the_baseline()
    {
        var tracker = new RecentEventTracker();
        tracker.ObserveDay(new[] { "13" });
        tracker.ObserveDay(new[] { "13", "20" });

        tracker.Reset();

        // 回到「首次观察」语义：不拿旧基线去猜新事件。
        Assert.Empty(tracker.ObserveDay(new[] { "13", "20" }));
    }

    [Fact]
    public void Null_input_is_treated_as_an_empty_snapshot()
    {
        var tracker = new RecentEventTracker();
        tracker.ObserveDay(new[] { "13" });

        Assert.Empty(tracker.ObserveDay(null));
    }
}
