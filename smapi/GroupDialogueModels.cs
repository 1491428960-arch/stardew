using System.Text.Json.Serialization;

namespace StardewAI.NPC;

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum GroupInvitationStatus
{
    Unread,
    Deferred,
    Accepted,
    Dismissed,
    Completed,
    Expired,
}

public sealed record GroupDialogueInvitationRecord
{
    [JsonPropertyName("invitationId")]
    public string InvitationId { get; init; } = string.Empty;

    [JsonPropertyName("templateId")]
    public string TemplateId { get; init; } = string.Empty;

    [JsonPropertyName("participants")]
    public IReadOnlyList<string> Participants { get; init; } = Array.Empty<string>();

    [JsonPropertyName("participantDisplayNames")]
    public IReadOnlyList<string> ParticipantDisplayNames { get; init; } = Array.Empty<string>();

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("topic")]
    public string Topic { get; init; } = string.Empty;

    [JsonPropertyName("guidance")]
    public string Guidance { get; init; } = string.Empty;

    [JsonPropertyName("createdOn")]
    public string CreatedOn { get; init; } = string.Empty;

    [JsonPropertyName("expiresOn")]
    public string ExpiresOn { get; init; } = string.Empty;

    [JsonPropertyName("createdTotalDays")]
    public int CreatedTotalDays { get; init; }

    [JsonPropertyName("expiresTotalDays")]
    public int ExpiresTotalDays { get; init; }

    [JsonPropertyName("source")]
    public string Source { get; init; } = "periodic";

    [JsonPropertyName("status")]
    public GroupInvitationStatus Status { get; init; } = GroupInvitationStatus.Unread;
}

public sealed record GroupParticipantCandidate(
    string NpcId,
    string DisplayName,
    bool HasFriendshipRecord);

public sealed record GroupDialogueHistoryEntry(
    [property: JsonPropertyName("speakerType")] string SpeakerType,
    [property: JsonPropertyName("speakerId")] string SpeakerId,
    [property: JsonPropertyName("content")] string Content,
    [property: JsonPropertyName("addressedTo")] IReadOnlyList<string>? AddressedTo = null);
