namespace StardewAI.NPC;

public static class DialogueEntryRules
{
    public static bool CanOpen(
        bool enabled,
        bool worldReady,
        bool hasMenu,
        bool hasConversationService)
    {
        return enabled && worldReady && !hasMenu && hasConversationService;
    }

    public static bool CanOpenGroup(
        bool enabled,
        bool worldReady,
        bool hasMenu,
        bool hasBridgeClient)
    {
        return enabled && worldReady && !hasMenu && hasBridgeClient;
    }
}
