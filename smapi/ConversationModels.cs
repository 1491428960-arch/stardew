using System.Text.Json.Serialization;

namespace StardewAI.NPC;

public static class ConversationIntent
{
    public const string Chat = "chat";
    public const string Topic = "topic";
    public const string Item = "item";
}

public static class ConversationChannel
{
    public const string Remote = "remote";
    public const string FaceToFace = "face_to_face";
}

public sealed record OpenLoopSignal
{
    [JsonPropertyName("action")]
    public string Action { get; init; } = string.Empty;

    [JsonPropertyName("loopId")]
    public string LoopId { get; init; } = string.Empty;

    [JsonPropertyName("topic")]
    public string? Topic { get; init; }

    [JsonPropertyName("shortSummary")]
    public string? ShortSummary { get; init; }
}

public sealed class ItemConversationContext
{
    public ItemConversationContext(
        string itemId,
        string displayName,
        string category,
        int quality,
        string action,
        int giftTaste,
        ItemInteractionKind itemKind = ItemInteractionKind.Other,
        bool consumesItem = false,
        int friendshipAwarded = 0,
        ItemSpecialInteraction specialInteraction = ItemSpecialInteraction.None)
    {
        ItemId = itemId;
        DisplayName = displayName;
        Category = category;
        Quality = quality;
        Action = action;
        GiftTaste = giftTaste;
        ItemKind = itemKind.ToString().ToLowerInvariant();
        ConsumesItem = consumesItem;
        FriendshipAwarded = friendshipAwarded;
        SpecialInteraction = SpecialInteractionValue(specialInteraction);
    }

    [JsonPropertyName("itemId")]
    public string ItemId { get; }

    [JsonPropertyName("displayName")]
    public string DisplayName { get; }

    [JsonPropertyName("category")]
    public string Category { get; }

    [JsonPropertyName("quality")]
    public int Quality { get; }

    [JsonPropertyName("action")]
    public string Action { get; }

    [JsonPropertyName("giftTaste")]
    public int GiftTaste { get; }

    [JsonPropertyName("itemKind")]
    public string ItemKind { get; }

    [JsonPropertyName("consumesItem")]
    public bool ConsumesItem { get; }

    [JsonPropertyName("friendshipAwarded")]
    public int FriendshipAwarded { get; }

    /// <summary>
    /// 枚举 → Bridge 协议值。
    ///
    /// 2026-09-20 修（契约审计）：此前直接 <c>ToString().ToLowerInvariant()</c>，
    /// 于是 <c>MineralTasting</c> 发成 <c>"mineraltasting"</c>，而 Bridge 的
    /// <c>special_interaction</c> 只认 <c>"mineral_tasting"</c>（带下划线）——
    /// 结果矮人与 Abigail 的矿石物品对话被 422 挡掉、退化成兜底回复。
    /// 显式写映射，避免枚举名与协议值再次悄悄耦合。
    /// </summary>
    private static string SpecialInteractionValue(ItemSpecialInteraction value) => value switch
    {
        ItemSpecialInteraction.MineralTasting => "mineral_tasting",
        _ => "none",
    };

    [JsonPropertyName("specialInteraction")]
    public string SpecialInteraction { get; }
}

public sealed record ConversationRequest(
    string NpcId,
    string Message,
    string Intent,
    NpcGameState? GameState,
    IReadOnlyList<string> RecentFacts,
    ItemConversationContext? ItemContext,
    RelationshipWorldSnapshot? RelationshipWorld,
    string Channel = ConversationChannel.Remote);

public sealed record ConversationTurnResult(BridgeDialogueResponse Response, bool Recorded)
{
    public string Reply => Response.Reply;

    public bool Fallback => Response.Fallback;
}

public sealed record GroupDialogueParticipant(
    [property: JsonPropertyName("npcId")] string NpcId,
    [property: JsonPropertyName("displayName")] string DisplayName,
    [property: JsonPropertyName("gameState")] NpcGameState? GameState = null);

public sealed record GroupDialogueRequest(
    string Message,
    IReadOnlyList<GroupDialogueParticipant> Participants,
    string? InvitationTopic,
    string? InvitationGuidance,
    IReadOnlyList<GroupDialogueHistoryEntry> History,
    string? ActiveSpeakerNpcId = null,
    NpcGameState? GameState = null,
    IReadOnlyList<string>? RecentFacts = null,
    RelationshipWorldSnapshot? RelationshipWorld = null,
    string Provider = "auto");
