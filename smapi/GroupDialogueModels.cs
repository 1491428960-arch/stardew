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

/// <summary>
/// **一场群聊**：一次 F9 会话里真正发生过的完整发言序列（谁说的、说了什么、按顺序）。
///
/// 2026-09-21：此前群聊在回看档案里只有「每位参与者本人发言合并成一条」的转述摘要——
/// 玩家自己的话没有独立气泡、别人的话完全不在、没说过话的人一条都没有，
/// 于是「F8 回看整场群聊」根本做不到。现在一场群聊自成一个形态：
/// 一场一条记录、内含整串 <see cref="Lines"/>，不再拆进按 NPC 的条目里
/// （见 <see cref="GroupSessionRules"/> 与被它替掉的旧写法）。
///
/// 三条边界：
/// 1. **一条记录服务所有参与者**：F8 在每位在场 NPC 的面板里都能翻到同一场，
///    存的是同一份（不是每人一份转述）；场上没说过话的人也留在
///    <see cref="Participants"/> 名单里（抬头会写「都有谁在」），只是不产生空气泡；
/// 2. **随存档走**：经 <see cref="ChatHistoryArchive"/> 与私聊档案一起写进当前存档，
///    读不到/格式不对就空手开局，绝不拦住载入（见 <c>GroupSessionRules.Normalize</c>）；
/// 3. **与请求同源**：这是给玩家翻的档案，同时也是发给模型的请求历史
///    ——<see cref="GroupDialogueSession.PublicHistory"/> 由
///    <see cref="GroupSessionRules.ToRequestHistory"/> 从这边的发言序列投影而来，
///    **玩家那句也在请求里**（2026-09-22 起；旧口径是「请求只有 NPC 发言」，
///    已被实测证伪，理由见 <see cref="GroupSessionRules.ToRequestHistory"/>）。
/// </summary>
public sealed record GroupChatSessionRecord
{
    /// <summary>场次标识：直接用邀约卡 id —— 同一张卡重开就是同一场（F9 续读靠它找回历史）。</summary>
    [JsonPropertyName("sessionId")]
    public string SessionId { get; init; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; init; } = string.Empty;

    [JsonPropertyName("topic")]
    public string Topic { get; init; } = string.Empty;

    /// <summary>发生日期的人类可读写法（如 <c>秋 12</c>），给抬头用。</summary>
    [JsonPropertyName("dateLabel")]
    public string DateLabel { get; init; } = string.Empty;

    /// <summary>发生日（游戏内总天数）；读回后用来排序与排障，不参与显示。</summary>
    [JsonPropertyName("totalDays")]
    public int TotalDays { get; init; }

    /// <summary>在场的 NPC id（含自始至终没说话的那位）。</summary>
    [JsonPropertyName("participants")]
    public IReadOnlyList<string> Participants { get; init; } = Array.Empty<string>();

    /// <summary>与 <see cref="Participants"/> 同序的显示名；缺位时退回 id 本身。</summary>
    [JsonPropertyName("participantDisplayNames")]
    public IReadOnlyList<string> ParticipantDisplayNames { get; init; } = Array.Empty<string>();

    /// <summary>与私聊回看条目共用同一个序号空间，F8 靠它把两者并成一条时间线（见 <see cref="BridgeClient"/>）。</summary>
    [JsonPropertyName("sequence")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? Sequence { get; init; }

    /// <summary>完整发言序列，按发生顺序（玩家发言与 NPC 发言都在里面）。
    /// 它同时是请求历史的来源，见类型注释第 3 条。</summary>
    [JsonPropertyName("lines")]
    public IReadOnlyList<GroupDialogueHistoryEntry> Lines { get; init; } =
        Array.Empty<GroupDialogueHistoryEntry>();
}
