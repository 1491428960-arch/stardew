using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class EventAuditObserverTests
{
    [Fact]
    public void Observer_reports_event_seen_after_the_previous_snapshot()
    {
        var observer = new EventAuditObserver();

        Assert.Empty(observer.Observe(Snapshot("Town", "100")).NewSeenEventIds);

        var observation = observer.Observe(
            Snapshot("SeedShop", "100", "Mod.PierreIntro", eventIsActive: true));

        Assert.Equal(new[] { "Mod.PierreIntro" }, observation.NewSeenEventIds);
        Assert.Equal("Mod.PierreIntro", observation.CurrentEventId);
        Assert.True(observation.EventIsActive);
    }

    [Fact]
    public void Reset_discards_previous_event_baseline()
    {
        var observer = new EventAuditObserver();
        observer.Observe(Snapshot("Town", "100"));
        observer.Observe(Snapshot("Town", "100", "A"));

        observer.Reset();

        var observation = observer.Observe(Snapshot("Town", "100", "A"));

        Assert.Empty(observation.NewSeenEventIds);
    }

    private static EventAuditSnapshot Snapshot(
        string location,
        params string[] seenEventIds) =>
        new(
            locationName: location,
            time: 800,
            eventIsActive: false,
            currentEventId: null,
            seenEventIds,
            Array.Empty<string>());

    private static EventAuditSnapshot Snapshot(
        string location,
        string baselineEventId,
        string currentEventId,
        bool eventIsActive) =>
        new(
            locationName: location,
            time: 800,
            eventIsActive,
            currentEventId,
            new[] { baselineEventId, currentEventId },
            new[] { currentEventId });
}
