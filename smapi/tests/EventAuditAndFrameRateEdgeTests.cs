using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// <c>EventAuditSnapshot</c> 的规范化与审计契约。
/// 事件审计只读、用于对账“本 Mod 有没有动过原版事件状态”，
/// 因此两件事必须钉住：快照入参被规范化到什么程度，以及审计本身永不写入。
/// 注意事件 ID 的大小写是**敏感**的（与 <c>ShareFriendshipLedger</c> 的 NPC ID 不同）：
/// 原版事件 ID 是精确字符串，合并 "A" 与 "a" 会掩盖真实差异。
/// </summary>
public sealed class EventAuditSnapshotEdgeTests
{
    [Fact]
    public void Snapshot_trims_text_but_keeps_event_ids_case_sensitive()
    {
        var snapshot = new EventAuditSnapshot(
            "  ScienceHouse  ",
            800,
            eventIsActive: false,
            currentEventId: "  Pierre.Intro  ",
            new[] { "A", "a", " A ", "", "   " },
            new[] { "X", "x" });

        Assert.Equal("ScienceHouse", snapshot.LocationName);
        Assert.Equal("Pierre.Intro", snapshot.CurrentEventId);
        // 去空白 + 去重，但大小写不同的 ID 都要保留
        Assert.Equal(new[] { "A", "a" }, snapshot.SeenEventIds);
        Assert.Equal(new[] { "X", "x" }, snapshot.EventIdsSinceLocationChange);
    }

    [Fact]
    public void Snapshot_maps_blank_text_to_null()
    {
        var snapshot = new EventAuditSnapshot(
            "   ",
            800,
            eventIsActive: false,
            currentEventId: null,
            null,
            null);

        Assert.Null(snapshot.LocationName);
        Assert.Null(snapshot.CurrentEventId);
        Assert.Empty(snapshot.SeenEventIds);
        Assert.Empty(snapshot.EventIdsSinceLocationChange);
    }

    [Fact]
    public void Observation_passes_through_location_time_and_recent_event_ids()
    {
        var observation = EventAuditRules.Observe(new EventAuditSnapshot(
            "Town",
            1210,
            eventIsActive: true,
            currentEventId: "Town.Festival",
            new[] { "100" },
            new[] { "Town.Festival" }));

        Assert.Equal("Town", observation.LocationName);
        Assert.Equal(1210, observation.Time);
        Assert.True(observation.EventIsActive);
        Assert.Equal("Town.Festival", observation.CurrentEventId);
        Assert.Equal(new[] { "Town.Festival" }, observation.EventIdsSinceLocationChange);
        // 审计永不声称本 Mod 会改状态（这条是只读契约）
        Assert.False(observation.ModWouldMutateGameState);
    }

    [Fact]
    public void First_observation_never_reports_existing_events_as_new()
    {
        // 不传基线时，快照里已有的事件不能被当成“本次新增”。
        var observation = EventAuditRules.Observe(new EventAuditSnapshot(
            "Town",
            900,
            eventIsActive: false,
            currentEventId: null,
            new[] { "100", "200" },
            Array.Empty<string>()));

        Assert.Empty(observation.NewSeenEventIds);
    }

    [Fact]
    public void Previous_ids_are_normalised_before_comparing()
    {
        // 基线里的空白与重复项不应影响“新增”的判定。
        var observation = EventAuditRules.Observe(
            new EventAuditSnapshot(
                "Town",
                900,
                eventIsActive: false,
                currentEventId: null,
                new[] { "100", "200" },
                Array.Empty<string>()),
            previousSeenEventIds: new[] { "  100  ", "100", "" });

        Assert.Equal(new[] { "200" }, observation.NewSeenEventIds);
    }
}

/// <summary>
/// <c>FrameRateSampler</c> 的窗口语义：窗口按**实际经过时间**结算
/// （不是固定按配置值），结算后从**结算那一刻**重新开始计时。
/// </summary>
public sealed class FrameRateSamplerEdgeTests
{
    [Fact]
    public void Rejects_null_report_callback()
    {
        Assert.Throws<ArgumentNullException>(
            () => new FrameRateSampler(null!));
    }

    [Fact]
    public void A_gap_longer_than_the_window_is_reported_as_the_actual_window()
    {
        // 配置窗口 1000ms，但这一帧在 5000ms 后才渲染：
        // 采样器报的是**实际经过的 5000ms**，而不是配置值。
        var now = 0L;
        var samples = new List<FrameRateSample>();
        var sampler = new FrameRateSampler(
            samples.Add,
            windowMilliseconds: 1000,
            elapsedMilliseconds: () => now);

        sampler.OnRendered();
        now = 5000;
        sampler.OnRendered();

        var sample = Assert.Single(samples);
        Assert.Equal(5000, sample.WindowMilliseconds);
        Assert.Equal(2, sample.RenderedFrames);
        Assert.Equal(0.4, sample.FramesPerSecond, 3);
    }

    [Fact]
    public void The_next_window_starts_at_the_moment_of_the_report()
    {
        var now = 0L;
        var samples = new List<FrameRateSample>();
        var sampler = new FrameRateSampler(
            samples.Add,
            windowMilliseconds: 1000,
            elapsedMilliseconds: () => now);

        now = 1000;
        sampler.OnRendered();
        Assert.Single(samples);

        // 距上次结算 999ms：仍在窗口内，不该报
        now = 1999;
        sampler.OnRendered();
        Assert.Single(samples);

        // 满 1000ms：结算
        now = 2000;
        sampler.OnRendered();
        Assert.Equal(2, samples.Count);
        Assert.Equal(1000, samples[1].WindowMilliseconds);
    }
}
