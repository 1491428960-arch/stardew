using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GameStateCollectorTests
{
    [Fact]
    public void Collect_marks_sve_when_an_sve_mod_is_loaded()
    {
        var result = GameStateCollector.Collect(
            Npc("Sophia", "Sophia", "Female"),
            World(),
            new FakeModRegistry("FlashShifter.SVECode"));

        Assert.Contains("SVE", result.SourceMods);
        Assert.Contains("FlashShifter.SVECode", result.SourceMods);
    }

    [Fact]
    public void Collect_does_not_apply_sve_source_when_sve_is_not_loaded()
    {
        var result = GameStateCollector.Collect(
            Npc("Sophia", "Sophia", "Female"),
            World(),
            new FakeModRegistry());

        Assert.DoesNotContain("SVE", result.SourceMods);
        Assert.DoesNotContain("FlashShifter.SVECode", result.SourceMods);
    }

    [Fact]
    public void Collect_uses_current_display_name_and_relationship_for_female_bachelor()
    {
        var result = GameStateCollector.Collect(
            Npc("Alex", "Alexis", "Female", relationship: "dating"),
            World(),
            new FakeModRegistry("female.bachelors.beach"));

        Assert.Contains("female-bachelors", result.SourceMods);
        Assert.Equal("Alexis", result.DisplayName);
        Assert.Equal("dating", result.Relationship);
    }

    [Fact]
    public void Collect_uses_current_display_name_and_relationship_for_rasmodia()
    {
        var result = GameStateCollector.Collect(
            Npc("Wizard", "Rasmodia", "Female", relationship: "married"),
            World(),
            new FakeModRegistry("Nom0ri.RomRas"));

        Assert.Contains("Romanceable Rasmodius", result.SourceMods);
        Assert.Equal("Rasmodia", result.DisplayName);
        Assert.Equal("married", result.Relationship);
    }

    [Fact]
    public void Collect_keeps_basic_runtime_state_for_unknown_npc()
    {
        var result = GameStateCollector.Collect(
            Npc("UnknownNpc", "Unknown display", "Male", "Town", 120),
            World("Summer", 14, isRaining: true, time: 1830),
            new FakeModRegistry());

        Assert.Equal("UnknownNpc", result.NpcId);
        Assert.Equal("Unknown display", result.DisplayName);
        Assert.Equal("Male", result.Gender);
        Assert.Equal("Town", result.Location);
        Assert.Equal("Summer", result.Season);
        Assert.Equal("14", result.Date);
        Assert.Equal("rain", result.Weather);
        Assert.Equal(1830, result.Time);
        Assert.Equal(120, result.Friendship);
        Assert.Empty(result.SourceMods);
    }

    private static RuntimeNpcState Npc(
        string npcId,
        string displayName,
        string gender,
        string location = "Town",
        int? friendship = 80,
        string? relationship = "friend") =>
        new(npcId, displayName, gender, location, friendship, relationship);

    private static RuntimeWorldState World(
        string season = "Spring",
        int day = 1,
        bool isRaining = false,
        int time = 1200) =>
        new(season, day, isRaining, time);

    private sealed class FakeModRegistry : IModRegistryStatus
    {
        private readonly HashSet<string> loadedIds;

        public FakeModRegistry(params string[] loadedIds)
        {
            this.loadedIds = loadedIds.ToHashSet(StringComparer.OrdinalIgnoreCase);
        }

        public bool IsLoaded(string uniqueId) => loadedIds.Contains(uniqueId);
    }
}
