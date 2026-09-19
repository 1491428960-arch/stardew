namespace StardewAI.NPC;

public static class KissInteractionRules
{
    public const double MinimumAnimationMilliseconds = 500;
    public const double MaximumAnimationMilliseconds = 2000;

    private static readonly HashSet<string> RomanticStages = new(StringComparer.OrdinalIgnoreCase)
    {
        "dating",
        "married",
        "parent",
    };

    private static readonly HashSet<string> RomanticRelationshipTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "dating",
        "engaged",
        "married",
    };

    public static bool CanArmAfterReply(
        bool effectiveReply,
        string? relationshipStage,
        string? customRelationshipType)
    {
        if (!effectiveReply)
        {
            return false;
        }

        return RomanticStages.Contains(relationshipStage?.Trim() ?? string.Empty) ||
            RomanticRelationshipTypes.Contains(customRelationshipType?.Trim() ?? string.Empty);
    }

    public static bool CanTriggerKiss(
        bool worldReady,
        bool menuOpen,
        bool sameDay,
        bool sameLocation,
        bool npcNearby,
        bool eventUp,
        bool festival,
        bool playerCanMove,
        bool usingTool,
        bool ridingHorse,
        bool sitting)
    {
        return worldReady &&
            !menuOpen &&
            sameDay &&
            sameLocation &&
            npcNearby &&
            !eventUp &&
            !festival &&
            playerCanMove &&
            !usingTool &&
            !ridingHorse &&
            !sitting;
    }

    public static bool ShouldCompleteKiss(
        double elapsedMilliseconds,
        bool playerCanMove)
    {
        if (elapsedMilliseconds < MinimumAnimationMilliseconds)
        {
            return false;
        }

        return playerCanMove || elapsedMilliseconds >= MaximumAnimationMilliseconds;
    }
}
