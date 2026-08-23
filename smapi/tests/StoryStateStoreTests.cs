using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class StoryStateStoreTests
{
    [Fact]
    public void Load_applies_valid_state_and_serialize_round_trips_it()
    {
        var store = new StoryStateStore();
        var expected = new StoryStateEnvelope
        {
            StoryEvents = new[]
            {
                new StoryEventRecord
                {
                    EventId = "vanilla:event-1",
                    SourceMod = "vanilla",
                    SourceKey = "event-1",
                    Participants = new[] { "Wizard", "player" },
                    Status = "completed",
                    GameDate = "Spring 14",
                    Canonical = true,
                    Summary = "玩家完成了法师塔事件",
                },
            },
        };

        store.Load(StoryStateSerializer.Serialize(expected));

        Assert.Single(store.State.StoryEvents);
        Assert.Equal("vanilla:event-1", store.State.StoryEvents[0].EventId);
        using var document = JsonDocument.Parse(store.Serialize());
        Assert.Equal(1, document.RootElement.GetProperty("schemaVersion").GetInt32());
        Assert.Equal(
            "completed",
            document.RootElement.GetProperty("storyEvents")[0].GetProperty("status").GetString());
        Assert.Empty(store.LastWarnings);
    }

    [Fact]
    public void Load_invalid_json_resets_state_and_keeps_warnings()
    {
        var store = new StoryStateStore();
        store.Load("{not-json");

        Assert.Empty(store.State.StoryEvents);
        Assert.Empty(store.State.Memories);
        Assert.Contains("invalid", store.LastWarnings[0]);
    }

    [Fact]
    public void Reset_clears_loaded_state_and_warnings()
    {
        var store = new StoryStateStore();
        store.Load(StoryStateSerializer.Serialize(new StoryStateEnvelope
        {
            Relationships = new[]
            {
                new RelationshipEdgeRecord
                {
                    FromNpcId = "player",
                    ToNpcId = "Wizard",
                    RelationType = "friend",
                },
            },
        }));

        store.Reset();

        Assert.Empty(store.State.Relationships);
        Assert.Empty(store.LastWarnings);
    }

    [Fact]
    public void RecordConversation_updates_the_loaded_state_for_the_next_save()
    {
        var store = new StoryStateStore();
        store.RecordConversation(
            new NpcGameState
            {
                NpcId = "Sophia",
                Date = "Spring 14",
                FriendshipHearts = 6,
                Relationship = "friend",
            },
            "葡萄园最近怎么样？",
            "最近还不错。",
            usedFallback: false);

        Assert.Single(store.State.Memories);
        Assert.Single(store.State.InteractionProgresses);
        Assert.Equal("Spring 14", store.State.Memories[0].GameDate);
    }

    [Fact]
    public void RecentMemoryFacts_returns_only_the_current_npc_and_caps_results()
    {
        var store = new StoryStateStore();
        var state = StoryStateEnvelope.Empty with
        {
            Memories = Enumerable.Range(1, 8)
                .Select(index => new MemoryRecord
                {
                    MemoryId = $"sophia-{index}",
                    OwnerNpcId = "Sophia",
                    Content = $"Sophia 记忆 {index}",
                    Source = MemorySource.PlayerChat,
                    Confidence = 0.8,
                    GameDate = $"Spring {index}",
                    Participants = new[] { "Sophia", "player" },
                    KnowledgeScope = MemoryKnowledgeScope.Participants,
                    KnownBy = new[] { "Sophia", "player" },
                })
                .Append(new MemoryRecord
                {
                    MemoryId = "wizard-1",
                    OwnerNpcId = "Wizard",
                    Content = "不应泄露给 Sophia",
                    Source = MemorySource.PlayerChat,
                    Confidence = 0.8,
                    GameDate = "Spring 9",
                    Participants = new[] { "Wizard", "player" },
                    KnowledgeScope = MemoryKnowledgeScope.Participants,
                    KnownBy = new[] { "Wizard", "player" },
                })
                .ToArray(),
        };
        store.Replace(state);

        var facts = store.RecentMemoryFacts("Sophia", limit: 6);

        Assert.Equal(6, facts.Count);
        Assert.All(facts, fact => Assert.Contains("Sophia", fact));
        Assert.DoesNotContain(facts, fact => fact.Contains("Wizard"));
    }
}
