using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class StoryStateSerializerTests
{
    [Fact]
    public void StorageKeyUsesSmapiCompatibleCharacters()
    {
        Assert.Matches("^[A-Za-z0-9_.-]+$", StoryStateSerializer.StorageKey);
    }

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
            null,
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

    [Fact]
    public void Serialize_and_load_preserves_relationship_views_mediation_and_jealousy()
    {
        var expected = StoryStateEnvelope.Empty with
        {
            Relationships = new[]
            {
                new RelationshipEdgeRecord
                {
                    FromNpcId = "player",
                    ToNpcId = "Sophia",
                    RelationType = "married",
                    StartedOn = "Spring 10",
                    PublicEventId = "wedding:sophia",
                    PublicOn = "Spring 10",
                },
            },
            RelationshipViews = new[]
            {
                new RelationshipViewRecord
                {
                    OwnerNpcId = "Alex",
                    SubjectNpcId = "Sophia",
                    RelationType = "married",
                    Visibility = "known",
                    Source = "wedding",
                },
            },
            Mediations = new[]
            {
                new RelationshipMediationRecord
                {
                    NpcId = "Alex",
                    Status = "resolved",
                    Outcome = "conditional",
                },
            },
            Jealousies = new[]
            {
                new RelationshipJealousyRecord
                {
                    NpcId = "Alex",
                    Active = true,
                    Trigger = "time",
                    Intensity = "light",
                    Need = "固定的相处时间",
                },
            },
        };

        var loaded = StoryStateSerializer.Load(StoryStateSerializer.Serialize(expected));

        Assert.Equal("wedding:sophia", Assert.Single(loaded.State.Relationships).PublicEventId);
        Assert.Equal("known", Assert.Single(loaded.State.RelationshipViews).Visibility);
        Assert.Equal("conditional", Assert.Single(loaded.State.Mediations).Outcome);
        Assert.True(Assert.Single(loaded.State.Jealousies).Active);
    }

    [Fact]
    public void Serialize_and_load_preserves_open_loops_without_schedule_fields()
    {
        var expected = StoryStateEnvelope.Empty with
        {
            OpenLoops = new[]
            {
                new OpenLoopRecord
                {
                    LoopId = "wizard:rune:Spring-14",
                    NpcId = "Wizard",
                    Topic = "rune_review",
                    OriginChannel = "remote",
                    NextChannel = "face_to_face",
                    Status = "open",
                    ShortSummary = "线上留下了核对符文数据的话题",
                    CreatedOn = "Spring 14",
                },
            },
        };

        var json = StoryStateSerializer.Serialize(expected);
        var loaded = StoryStateSerializer.Load(json);

        var loop = Assert.Single(loaded.State.OpenLoops);
        Assert.Equal("wizard:rune:Spring-14", loop.LoopId);
        Assert.DoesNotContain("scheduledAt", json, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("location", json, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Load_missing_open_loops_keeps_old_state_compatible()
    {
        var loaded = StoryStateSerializer.Load("{\"schemaVersion\":1,\"memories\":[]}");

        Assert.Empty(loaded.State.OpenLoops);
        Assert.Empty(loaded.Warnings);
    }

    [Fact]
    public void Serialize_and_load_preserves_group_dialogue_invitations()
    {
        var expected = StoryStateEnvelope.Empty with
        {
            GroupDialogueInvitations = new[] { ValidGroupInvitation() },
        };

        var json = StoryStateSerializer.Serialize(expected);
        var loaded = StoryStateSerializer.Load(json);

        var invitation = Assert.Single(loaded.State.GroupDialogueInvitations);
        Assert.Equal("invite-1", invitation.InvitationId);
        Assert.Equal(GroupInvitationStatus.Unread, invitation.Status);
        Assert.Empty(loaded.Warnings);
        Assert.DoesNotContain("authorization", json, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("providerPayload", json, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Load_missing_group_dialogue_invitations_keeps_old_state_compatible()
    {
        var loaded = StoryStateSerializer.Load("{\"schemaVersion\":1,\"memories\":[]}");

        Assert.Empty(loaded.State.GroupDialogueInvitations);
        Assert.Empty(loaded.Warnings);
    }

    [Fact]
    public void Load_skips_invalid_group_dialogue_invitation_and_keeps_valid_one()
    {
        var json = """
        {
          "schemaVersion": 1,
          "groupDialogueInvitations": [
            {
              "invitationId": "valid",
              "templateId": "neutral-public-topic",
              "participants": ["Abigail", "Emily"],
              "participantDisplayNames": ["Abigail", "Emily"],
              "title": "公共话题",
              "topic": "最近的公共小事",
              "guidance": "只作为讨论方向。",
              "createdOn": "Spring 20",
              "expiresOn": "Spring 27",
              "createdTotalDays": 20,
              "expiresTotalDays": 27,
              "source": "periodic",
              "status": "Unread"
            },
            {
              "invitationId": "invalid",
              "templateId": "unknown-template",
              "participants": ["Abigail"],
              "participantDisplayNames": ["Abigail"],
              "title": "坏卡",
              "topic": "",
              "guidance": "",
              "createdOn": "Spring 20",
              "expiresOn": "Spring 27",
              "createdTotalDays": 20,
              "expiresTotalDays": 27,
              "source": "periodic",
              "status": "Unread"
            }
          ]
        }
        """;

        var loaded = StoryStateSerializer.Load(json);

        Assert.Equal("valid", Assert.Single(loaded.State.GroupDialogueInvitations).InvitationId);
        Assert.Contains(loaded.Warnings, warning =>
            warning.Contains("group invitation invalid", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void Load_skips_invalid_open_loop_and_keeps_valid_open_loop()
    {
        var json = """
        {
          "schemaVersion": 1,
          "openLoops": [
            {"loopId":"valid","npcId":"Wizard","topic":"rune_review","originChannel":"remote","nextChannel":"face_to_face","status":"open","shortSummary":"核对符文","createdOn":"Spring 14"},
            {"loopId":"bad","npcId":"Wizard","topic":"rune_review","originChannel":"remote","nextChannel":"face_to_face","status":"open","shortSummary":"","createdOn":"Spring 14"}
          ]
        }
        """;

        var loaded = StoryStateSerializer.Load(json);

        Assert.Equal("valid", Assert.Single(loaded.State.OpenLoops).LoopId);
        Assert.Contains(loaded.Warnings, warning => warning.Contains("open loop", StringComparison.OrdinalIgnoreCase));
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

    private static GroupDialogueInvitationRecord ValidGroupInvitation() => new()
    {
        InvitationId = "invite-1",
        TemplateId = "neutral-public-topic",
        Participants = new[] { "Abigail", "Emily" },
        ParticipantDisplayNames = new[] { "Abigail", "Emily" },
        Title = "公共话题",
        Topic = "最近的公共小事",
        Guidance = "只作为讨论方向。",
        CreatedOn = "Spring 20",
        ExpiresOn = "Spring 27",
        CreatedTotalDays = 20,
        ExpiresTotalDays = 27,
        Source = "periodic",
        Status = GroupInvitationStatus.Unread,
    };
}
