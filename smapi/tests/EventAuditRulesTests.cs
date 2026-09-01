using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class EventAuditRulesTests
{
    [Fact]
    public void Audit_is_read_only_and_does_not_mutate_seen_event_input()
    {
        var seenEvents = new List<string> { "100", "Mod.EventA" };
        var input = new EventAuditSnapshot(
            "ScienceHouse",
            800,
            eventIsActive: false,
            currentEventId: null,
            seenEvents,
            new[] { "100" });

        var observation = EventAuditRules.Observe(input);

        Assert.Equal(new[] { "100", "Mod.EventA" }, seenEvents);
        Assert.False(observation.ModWouldMutateGameState);
        Assert.Equal("ScienceHouse", observation.LocationName);
        Assert.Empty(observation.NewSeenEventIds);
    }

    [Fact]
    public void Audit_reports_new_seen_event_ids_without_writing_them()
    {
        var observation = EventAuditRules.Observe(
            new EventAuditSnapshot(
                "SeedShop",
                1030,
                eventIsActive: true,
                currentEventId: "Pierre.Intro",
                new[] { "100", "Pierre.Intro" },
                new[] { "Pierre.Intro" }),
            previousSeenEventIds: new[] { "100" });

        Assert.Equal(new[] { "Pierre.Intro" }, observation.NewSeenEventIds);
        Assert.Equal("Pierre.Intro", observation.CurrentEventId);
        Assert.True(observation.EventIsActive);
        Assert.False(observation.ModWouldMutateGameState);
    }

    [Fact]
    public void Audit_deduplicates_and_ignores_blank_event_ids()
    {
        var observation = EventAuditRules.Observe(
            new EventAuditSnapshot(
                "Town",
                1200,
                eventIsActive: false,
                currentEventId: null,
                new[] { "", "A", "A", "  " },
                Array.Empty<string>()),
            previousSeenEventIds: Array.Empty<string>());

        Assert.Equal(new[] { "A" }, observation.NewSeenEventIds);
    }
}
