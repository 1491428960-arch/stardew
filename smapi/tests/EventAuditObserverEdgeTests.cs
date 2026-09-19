using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// <c>EventAuditObserver</c> 是每帧喂快照的有状态包装，回答“这一轮新增看到了哪些原版事件”。
/// 已有 <c>EventAuditObserverTests</c> 覆盖了首次不误报与 <c>Reset</c> 清基线；
/// 这里补上它没碰的四件事：入参校验、同一快照重复观察的幂等性、
/// 基线是**上一次快照**而不是累计并集（事件消失后再出现会重新上报），
/// 以及事件 ID 在比较时保持大小写敏感。
/// </summary>
public sealed class EventAuditObserverEdgeTests
{
    [Fact]
    public void Observe_rejects_a_null_snapshot()
    {
        var observer = new EventAuditObserver();

        Assert.Throws<ArgumentNullException>(() => observer.Observe(null!));
    }

    [Fact]
    public void Repeated_observations_of_the_same_snapshot_report_nothing_new()
    {
        var observer = new EventAuditObserver();

        var first = observer.Observe(Snapshot("Town", 800, "100"));
        var second = observer.Observe(Snapshot("Town", 800, "100"));
        var third = observer.Observe(Snapshot("Town", 800, "100"));

        Assert.Empty(first.NewSeenEventIds);
        Assert.Empty(second.NewSeenEventIds);
        Assert.Empty(third.NewSeenEventIds);
        // 没有新增事件时也必须带出当前读数：审计对账不能因为“本轮无新增”而丢掉现场。
        Assert.Equal("Town", third.LocationName);
        Assert.Equal(800, third.Time);
        Assert.Equal(new[] { "100" }, third.EventIdsSinceLocationChange);
        Assert.False(third.ModWouldMutateGameState);
    }

    [Fact]
    public void An_event_that_leaves_the_snapshot_and_returns_is_reported_again()
    {
        var observer = new EventAuditObserver();
        observer.Observe(Snapshot("Town", 800, "100"));

        var grown = observer.Observe(Snapshot("Town", 810, "100", "200"));
        Assert.Equal(new[] { "200" }, grown.NewSeenEventIds);

        // 读档 / 回退后 "200" 从 eventsSeen 里消失：基线随快照滑动，它不再算“已见”。
        var shrunk = observer.Observe(Snapshot("Town", 900, "100"));
        Assert.Empty(shrunk.NewSeenEventIds);

        // 再次出现时会被重新上报为新增——基线是**上一次快照**，不是累计并集。
        var regained = observer.Observe(Snapshot("Town", 910, "100", "200"));
        Assert.Equal(new[] { "200" }, regained.NewSeenEventIds);
    }

    [Fact]
    public void Event_ids_are_compared_case_sensitively_across_observations()
    {
        var observer = new EventAuditObserver();
        observer.Observe(Snapshot("Town", 800, "Mod.PierreIntro"));

        var observation = observer.Observe(Snapshot("Town", 810, "mod.pierreintro"));

        // 原版事件 ID 是精确字符串：大小写不同就是不同事件，
        // 合并二者会掩盖“事件集合真的变了”这类对账差异。
        Assert.Equal(new[] { "mod.pierreintro" }, observation.NewSeenEventIds);
    }

    [Fact]
    public void Reset_clears_the_baseline_but_still_reports_the_current_reading()
    {
        var observer = new EventAuditObserver();
        observer.Observe(Snapshot("Town", 800, "100"));

        observer.Reset();
        var observation = observer.Observe(Snapshot("Farm", 1230, "100", "200"));

        // Reset 只丢弃基线：已有事件不再算新增，但现场读数照常透传。
        Assert.Empty(observation.NewSeenEventIds);
        Assert.Equal("Farm", observation.LocationName);
        Assert.Equal(1230, observation.Time);
        Assert.Equal(new[] { "100", "200" }, observation.EventIdsSinceLocationChange);
    }

    private static EventAuditSnapshot Snapshot(
        string location,
        int time,
        params string[] seenEventIds) =>
        new(
            locationName: location,
            time: time,
            eventIsActive: false,
            currentEventId: null,
            seenEventIds: seenEventIds,
            eventIdsSinceLocationChange: seenEventIds);
}
