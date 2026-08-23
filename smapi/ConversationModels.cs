using System.Text.Json.Serialization;

namespace StardewAI.NPC;

public static class ConversationIntent
{
    public const string Chat = "chat";
    public const string Topic = "topic";
    public const string Item = "item";
}

public sealed class ItemConversationContext
{
    public ItemConversationContext(
        string itemId,
        string displayName,
        string category,
        int quality,
        string action,
        int giftTaste)
    {
        ItemId = itemId;
        DisplayName = displayName;
        Category = category;
        Quality = quality;
        Action = action;
        GiftTaste = giftTaste;
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
}

public sealed record ConversationRequest(
    string NpcId,
    string Message,
    string Intent,
    NpcGameState? GameState,
    IReadOnlyList<string> RecentFacts,
    ItemConversationContext? ItemContext);

public sealed record ConversationTurnResult(BridgeDialogueResponse Response, bool Recorded)
{
    public string Reply => Response.Reply;

    public bool Fallback => Response.Fallback;
}
