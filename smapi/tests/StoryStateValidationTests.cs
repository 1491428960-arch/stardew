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

    [Fact]
    public void Relationship_records_reject_missing_identity_and_invalid_enums()
    {
        var viewErrors = StoryStateValidation.Validate(new RelationshipViewRecord
        {
            OwnerNpcId = "",
            SubjectNpcId = "Sophia",
            RelationType = "dating",
            Visibility = "maybe",
            Source = "rumor",
        });
        var mediationErrors = StoryStateValidation.Validate(new RelationshipMediationRecord
        {
            NpcId = "Alex",
            Status = "resolved",
            Outcome = "maybe",
        });
        var jealousyErrors = StoryStateValidation.Validate(new RelationshipJealousyRecord
        {
            NpcId = "Alex",
            Active = true,
            Trigger = "time",
            Intensity = "extreme",
        });

        Assert.Contains(viewErrors, error => error.Contains("ownerNpcId", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(viewErrors, error => error.Contains("visibility", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(mediationErrors, error => error.Contains("outcome", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(jealousyErrors, error => error.Contains("intensity", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void Open_loop_requires_current_npc_identity_and_safe_channels()
    {
        var errors = StoryStateValidation.Validate(new OpenLoopRecord
        {
            LoopId = "loop-1",
            NpcId = "Wizard",
            Topic = "符文",
            OriginChannel = "face_to_face",
            NextChannel = "remote",
            Status = "open",
            ShortSummary = "核对符文数据",
            CreatedOn = "Spring 14",
        });

        Assert.Contains(errors, error => error.Contains("originChannel", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(errors, error => error.Contains("nextChannel", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void Open_loop_rejects_missing_required_fields_and_unknown_status()
    {
        var errors = StoryStateValidation.Validate(new OpenLoopRecord
        {
            Status = "unknown",
        });

        Assert.Contains(errors, error => error.Contains("loopId", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(errors, error => error.Contains("npcId", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(errors, error => error.Contains("topic", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(errors, error => error.Contains("shortSummary", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(errors, error => error.Contains("createdOn", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(errors, error => error.Contains("status", StringComparison.OrdinalIgnoreCase));
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
