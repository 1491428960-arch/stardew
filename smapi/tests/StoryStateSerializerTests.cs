using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class StoryStateSerializerTests
{
    [Fact]
    public void Serialize_and_load_preserves_schema_version_and_memory_provenance()
    {
        var state = StoryStateEnvelope.Empty with
        {
            Memories = new[] { ValidMemory() },
        };

        var json = StoryStateSerializer.Serialize(state);
        var loaded = StoryStateSerializer.Load(json);

        Assert.Equal(StoryStateEnvelope.CurrentSchemaVersion, loaded.State.SchemaVersion);
        var memory = Assert.Single(loaded.State.Memories);
        Assert.Equal(MemorySource.PlayerChat, memory.Source);
        Assert.Equal(MemoryKnowledgeScope.Participants, memory.KnowledgeScope);
        Assert.Empty(loaded.Warnings);
    }

    [Fact]
    public void Load_returns_empty_state_and_warning_for_invalid_json()
    {
        var loaded = StoryStateSerializer.Load("{not-json");

        Assert.Empty(loaded.State.Memories);
        Assert.Contains(loaded.Warnings, warning => warning.Contains("JSON", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void Load_returns_empty_state_and_warning_for_future_schema()
    {
        var loaded = StoryStateSerializer.Load("{\"schemaVersion\":2,\"memories\":[]}");

        Assert.Empty(loaded.State.Memories);
        Assert.Contains(loaded.Warnings, warning => warning.Contains("schema", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void Load_skips_invalid_memory_and_keeps_valid_memory()
    {
        var json = """
        {
          "schemaVersion": 1,
          "memories": [
            {
              "memoryId": "memory-1",
              "ownerNpcId": "Sophia",
              "kind": "fact",
              "content": "玩家帮助我完成了葡萄园工作。",
              "source": "PlayerChat",
              "confidence": 0.9,
              "gameDate": "Spring 14",
              "participants": ["Sophia", "player"],
              "knowledgeScope": "Participants",
              "knownBy": ["Sophia", "player"],
              "importance": 1,
              "canonical": false,
              "evidence": "conversation:session-1"
            },
            {
              "memoryId": "",
              "ownerNpcId": "Sophia",
              "kind": "fact",
              "content": "这条记忆缺少来源。",
              "source": null,
              "confidence": 0.5,
              "gameDate": "Spring 14",
              "participants": ["Sophia"],
              "knowledgeScope": "Participants",
              "importance": 1,
              "canonical": false,
              "evidence": "test"
            }
          ]
        }
        """;

        var loaded = StoryStateSerializer.Load(json);

        var memory = Assert.Single(loaded.State.Memories);
        Assert.Equal("memory-1", memory.MemoryId);
        Assert.Contains(loaded.Warnings, warning => warning.Contains("memory", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void Serialize_rejects_state_with_invalid_memory()
    {
        var state = StoryStateEnvelope.Empty with
        {
            Memories = new[]
            {
                ValidMemory() with { Confidence = 1.2 },
            },
        };

        Assert.Throws<ArgumentException>(() => StoryStateSerializer.Serialize(state));
    }

    private static MemoryRecord ValidMemory() => new()
    {
        MemoryId = "memory-1",
        OwnerNpcId = "Sophia",
        Kind = "fact",
        Content = "玩家帮助我完成了葡萄园工作。",
        Source = MemorySource.PlayerChat,
        Confidence = 0.9,
        GameDate = "Spring 14",
        Participants = new[] { "Sophia", "player" },
        KnowledgeScope = MemoryKnowledgeScope.Participants,
        KnownBy = new[] { "Sophia", "player" },
        Importance = 1,
        Evidence = "conversation:session-1",
    };
}
