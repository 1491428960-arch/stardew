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
}
