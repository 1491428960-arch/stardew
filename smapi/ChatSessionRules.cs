namespace StardewAI.NPC;

public static class ChatSessionRules
{
    public static bool IsEffectiveResponse(ConversationTurnResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        return !result.Fallback && !string.IsNullOrWhiteSpace(result.Reply);
    }

    public static bool IsValuableRelationshipRepair(
        ConversationTurnResult result,
        string? playerMessage,
        RelationshipWorldSnapshot? relationshipWorld)
    {
        ArgumentNullException.ThrowIfNull(result);
        return result.Recorded && IsEffectiveResponse(result) &&
            RelationshipRepairRules.IsValuableRelationshipRepair(
                playerMessage,
                result.Reply,
                relationshipWorld);
    }
}
