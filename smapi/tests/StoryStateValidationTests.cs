using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class StoryStateValidationTests
{
    [Fact]
    public void Valid_memory_contains_required_provenance_fields()
    {
        var errors = StoryStateValidation.Validate(ValidMemory());

        Assert.Empty(errors);
    }

    [Fact]
    public void Memory_rejects_missing_source_confidence_date_participants_and_scope()
    {
        var memory = new MemoryRecord
        {
            MemoryId = "memory-1",
            OwnerNpcId = "Sophia",
            Content = "玩家帮助我完成了葡萄园工作。",
            Participants = Array.Empty<string>(),
        };

        var errors = StoryStateValidation.Validate(memory);

        Assert.Contains(errors, error => error.Contains("source", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(errors, error => error.Contains("confidence", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(errors, error => error.Contains("gameDate", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(errors, error => error.Contains("participants", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(errors, error => error.Contains("knowledgeScope", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void Memory_rejects_confidence_outside_zero_to_one()
    {
        var memory = ValidMemory() with { Confidence = 1.1 };

        var errors = StoryStateValidation.Validate(memory);

        Assert.Contains(errors, error => error.Contains("confidence", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void Memory_rejects_importance_outside_zero_to_three()
    {
        var memory = ValidMemory() with { Importance = 4 };

        var errors = StoryStateValidation.Validate(memory);

        Assert.Contains(errors, error => error.Contains("importance", StringComparison.OrdinalIgnoreCase));
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
        Canonical = false,
        Evidence = "conversation:session-1",
    };
}
