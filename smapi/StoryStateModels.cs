using System.Text.Json.Serialization;

namespace StardewAI.NPC;

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum MemorySource
{
    VanillaEvent,
    ModEvent,
    Gift,
    ScheduleObservation,
    PlayerChat,
    NpcNpcEvent,
    SystemInference,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum MemoryKnowledgeScope
{
    Private,
    Participants,
    NpcGroup,
    Public,
    PlayerOnly,
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum MemoryStatus
{
    Active,
    Corrected,
    Superseded,
    Forgotten,
}

public sealed record StoryEventRecord
{
    [JsonPropertyName("eventId")]
    public string EventId { get; init; } = string.Empty;

    [JsonPropertyName("sourceMod")]
    public string SourceMod { get; init; } = string.Empty;

    [JsonPropertyName("sourceKey")]
    public string SourceKey { get; init; } = string.Empty;

    [JsonPropertyName("participants")]
    public IReadOnlyList<string> Participants { get; init; } = Array.Empty<string>();

    [JsonPropertyName("status")]
    public string Status { get; init; } = "unknown";

    [JsonPropertyName("gameDate")]
    public string GameDate { get; init; } = string.Empty;

    [JsonPropertyName("canonical")]
    public bool Canonical { get; init; }

    [JsonPropertyName("summary")]
    public string Summary { get; init; } = string.Empty;
}

public sealed record KnowledgeRecord
{
    [JsonPropertyName("memoryId")]
    public string MemoryId { get; init; } = string.Empty;

    [JsonPropertyName("ownerNpcId")]
    public string OwnerNpcId { get; init; } = string.Empty;

    [JsonPropertyName("knowledgeScope")]
    public MemoryKnowledgeScope? KnowledgeScope { get; init; }

    [JsonPropertyName("knownBy")]
    public IReadOnlyList<string> KnownBy { get; init; } = Array.Empty<string>();
}

public sealed record RelationshipEdgeRecord
{
    [JsonPropertyName("fromNpcId")]
    public string FromNpcId { get; init; } = string.Empty;

    [JsonPropertyName("toNpcId")]
    public string ToNpcId { get; init; } = string.Empty;

    [JsonPropertyName("relationType")]
    public string RelationType { get; init; } = string.Empty;

    [JsonPropertyName("strength")]
    public double Strength { get; init; }

    [JsonPropertyName("tension")]
    public double Tension { get; init; }

    [JsonPropertyName("source")]
    public string Source { get; init; } = string.Empty;

    [JsonPropertyName("canonical")]
    public bool Canonical { get; init; }

    [JsonPropertyName("updatedOn")]
    public string UpdatedOn { get; init; } = string.Empty;

    [JsonPropertyName("startedOn")]
    public string? StartedOn { get; init; }

    [JsonPropertyName("publicEventId")]
    public string? PublicEventId { get; init; }

    [JsonPropertyName("publicOn")]
    public string? PublicOn { get; init; }
}

public sealed record RelationshipViewRecord
{
    [JsonPropertyName("ownerNpcId")]
    public string OwnerNpcId { get; init; } = string.Empty;

    [JsonPropertyName("subjectNpcId")]
    public string SubjectNpcId { get; init; } = string.Empty;

    [JsonPropertyName("relationType")]
    public string RelationType { get; init; } = string.Empty;

    [JsonPropertyName("visibility")]
    public string Visibility { get; init; } = string.Empty;

    [JsonPropertyName("source")]
    public string Source { get; init; } = string.Empty;

    [JsonPropertyName("observedOn")]
    public string? ObservedOn { get; init; }

    [JsonPropertyName("evidence")]
    public string? Evidence { get; init; }
}

public sealed record RelationshipMediationRecord
{
    [JsonPropertyName("npcId")]
    public string NpcId { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = "none";

    [JsonPropertyName("outcome")]
    public string? Outcome { get; init; }

    [JsonPropertyName("nextStep")]
    public string? NextStep { get; init; }
}

public sealed record RelationshipJealousyRecord
{
    [JsonPropertyName("npcId")]
    public string NpcId { get; init; } = string.Empty;

    [JsonPropertyName("active")]
    public bool Active { get; init; }

    [JsonPropertyName("trigger")]
    public string? Trigger { get; init; }

    [JsonPropertyName("intensity")]
    public string? Intensity { get; init; }

    [JsonPropertyName("need")]
    public string? Need { get; init; }

    [JsonPropertyName("lastResolvedTrigger")]
    public string? LastResolvedTrigger { get; init; }
}

public sealed record OpenLoopRecord
{
    [JsonPropertyName("loopId")]
    public string LoopId { get; init; } = string.Empty;

    [JsonPropertyName("npcId")]
    public string NpcId { get; init; } = string.Empty;

    [JsonPropertyName("topic")]
    public string Topic { get; init; } = string.Empty;

    [JsonPropertyName("originChannel")]
    public string OriginChannel { get; init; } = string.Empty;

    [JsonPropertyName("nextChannel")]
    public string NextChannel { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = "open";

    [JsonPropertyName("shortSummary")]
    public string ShortSummary { get; init; } = string.Empty;

    [JsonPropertyName("createdOn")]
    public string CreatedOn { get; init; } = string.Empty;
}

public sealed record InteractionProgress
{
    [JsonPropertyName("npcId")]
    public string NpcId { get; init; } = string.Empty;

    [JsonPropertyName("stage")]
    public string Stage { get; init; } = string.Empty;

    [JsonPropertyName("effectiveSessions")]
    public int EffectiveSessions { get; init; }

    [JsonPropertyName("requiredSessions")]
    public int RequiredSessions { get; init; }

    [JsonPropertyName("lastCountedGameDate")]
    public string? LastCountedGameDate { get; init; }

    [JsonPropertyName("lastInteractionFingerprint")]
    public string? LastInteractionFingerprint { get; init; }

    public static InteractionProgress Create(string npcId, string stage)
    {
        if (string.IsNullOrWhiteSpace(npcId))
        {
            throw new ArgumentException("NPC ID 不能为空。", nameof(npcId));
        }

        if (string.IsNullOrWhiteSpace(stage))
        {
            throw new ArgumentException("关系阶段不能为空。", nameof(stage));
        }

        return new InteractionProgress
        {
            NpcId = npcId.Trim(),
            Stage = stage.Trim(),
            RequiredSessions = RelationshipStageRules.IsMajorStage(stage) ? 5 : 4,
        };
    }
}

public sealed record ConversationAttempt(
    string GameDate,
    string PlayerMessage,
    string NpcReply,
    bool UsedFallback);

public sealed record MemoryRecord
{
    [JsonPropertyName("memoryId")]
    public string MemoryId { get; init; } = string.Empty;

    [JsonPropertyName("ownerNpcId")]
    public string OwnerNpcId { get; init; } = string.Empty;

    [JsonPropertyName("kind")]
    public string Kind { get; init; } = "fact";

    [JsonPropertyName("content")]
    public string Content { get; init; } = string.Empty;

    [JsonPropertyName("source")]
    public MemorySource? Source { get; init; }

    [JsonPropertyName("confidence")]
    public double? Confidence { get; init; }

    [JsonPropertyName("gameDate")]
    public string GameDate { get; init; } = string.Empty;

    [JsonPropertyName("participants")]
    public IReadOnlyList<string> Participants { get; init; } = Array.Empty<string>();

    [JsonPropertyName("knowledgeScope")]
    public MemoryKnowledgeScope? KnowledgeScope { get; init; }

    [JsonPropertyName("knownBy")]
    public IReadOnlyList<string> KnownBy { get; init; } = Array.Empty<string>();

    [JsonPropertyName("importance")]
    public int Importance { get; init; }

    [JsonPropertyName("canonical")]
    public bool Canonical { get; init; }

    [JsonPropertyName("expiresOn")]
    public string? ExpiresOn { get; init; }

    [JsonPropertyName("status")]
    public MemoryStatus Status { get; init; } = MemoryStatus.Active;

    [JsonPropertyName("evidence")]
    public string Evidence { get; init; } = string.Empty;
}

public sealed record StoryStateEnvelope
{
    public const int CurrentSchemaVersion = 1;

    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = CurrentSchemaVersion;

    [JsonPropertyName("memories")]
    public IReadOnlyList<MemoryRecord> Memories { get; init; } = Array.Empty<MemoryRecord>();

    [JsonPropertyName("storyEvents")]
    public IReadOnlyList<StoryEventRecord> StoryEvents { get; init; } = Array.Empty<StoryEventRecord>();

    [JsonPropertyName("knowledge")]
    public IReadOnlyList<KnowledgeRecord> Knowledge { get; init; } = Array.Empty<KnowledgeRecord>();

    [JsonPropertyName("relationships")]
    public IReadOnlyList<RelationshipEdgeRecord> Relationships { get; init; } = Array.Empty<RelationshipEdgeRecord>();

    [JsonPropertyName("relationshipViews")]
    public IReadOnlyList<RelationshipViewRecord> RelationshipViews { get; init; } = Array.Empty<RelationshipViewRecord>();

    [JsonPropertyName("mediations")]
    public IReadOnlyList<RelationshipMediationRecord> Mediations { get; init; } = Array.Empty<RelationshipMediationRecord>();

    [JsonPropertyName("jealousies")]
    public IReadOnlyList<RelationshipJealousyRecord> Jealousies { get; init; } = Array.Empty<RelationshipJealousyRecord>();

    [JsonPropertyName("openLoops")]
    public IReadOnlyList<OpenLoopRecord> OpenLoops { get; init; } = Array.Empty<OpenLoopRecord>();

    [JsonPropertyName("groupDialogueInvitations")]
    public IReadOnlyList<GroupDialogueInvitationRecord> GroupDialogueInvitations { get; init; } =
        Array.Empty<GroupDialogueInvitationRecord>();

    [JsonPropertyName("interactionProgresses")]
    public IReadOnlyList<InteractionProgress> InteractionProgresses { get; init; } = Array.Empty<InteractionProgress>();

    public static StoryStateEnvelope Empty => new();
}

public sealed record StoryStateLoadResult(
    StoryStateEnvelope State,
    IReadOnlyList<string> Warnings);
