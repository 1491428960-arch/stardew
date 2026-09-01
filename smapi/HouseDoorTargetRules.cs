namespace StardewAI.NPC;

public enum ServiceActionClassification
{
    None,
    KnownService,
    Unknown,
}

/// <summary>
/// Converts runtime door metadata into the conservative access context used by
/// <see cref="HouseAccessRules"/>. It intentionally requires the NPC's home to
/// match the target location before treating a door as residential.
/// </summary>
public static class HouseDoorTargetRules
{
    private static readonly IReadOnlySet<string> KnownServiceLocations =
        new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "AdventureGuild",
            "AnimalShop",
            "Blacksmith",
            "Carpenter",
            "FishShop",
            "Hospital",
            "Saloon",
            "ScienceHouse",
            "SeedShop",
            "WizardHouse",
        };

    public static DoorAccessContext CreateContext(
        string? targetLocationName,
        string? requiredNpcId,
        bool npcHomeMatchesTarget,
        bool targetIsShopLocation,
        bool unknownServiceAction = false)
    {
        var normalizedTarget = Normalize(targetLocationName);
        var normalizedNpc = Normalize(requiredNpcId);
        var knownServiceWithoutNpcGate =
            normalizedNpc is null &&
            normalizedTarget is not null &&
            targetIsShopLocation &&
            KnownServiceLocations.Contains(normalizedTarget);
        var isKnownResidence = (npcHomeMatchesTarget &&
                normalizedTarget is not null &&
                normalizedNpc is not null) ||
            knownServiceWithoutNpcGate;
        var hasServiceInteraction = targetIsShopLocation ||
            (normalizedTarget is not null &&
                KnownServiceLocations.Contains(normalizedTarget));

        return new DoorAccessContext
        {
            TargetLocationName = normalizedTarget,
            ResidentNpcIds = npcHomeMatchesTarget && normalizedNpc is not null
                ? new[] { normalizedNpc }
                : knownServiceWithoutNpcGate && normalizedTarget is not null
                    ? new[] { normalizedTarget }
                    : Array.Empty<string>(),
            IsKnownResidence = isKnownResidence,
            HasServiceInteraction = hasServiceInteraction,
            HasUnknownServiceInteraction = unknownServiceAction && !hasServiceInteraction,
        };
    }

    public static bool IsKnownServiceLocation(string? locationName)
    {
        var normalized = Normalize(locationName);
        return normalized is not null && KnownServiceLocations.Contains(normalized);
    }

    public static bool HasServiceAction(IEnumerable<string>? actions)
    {
        return ClassifyServiceActions(actions) == ServiceActionClassification.KnownService;
    }

    public static ServiceActionClassification ClassifyServiceActions(
        IEnumerable<string>? actions)
    {
        if (actions is null)
        {
            return ServiceActionClassification.None;
        }

        var hasUnknown = false;
        foreach (var actionText in actions)
        {
            var actionName = actionText?
                .Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries)
                .FirstOrDefault();
            if (string.IsNullOrWhiteSpace(actionName))
            {
                continue;
            }

            if (IsKnownServiceAction(actionName))
            {
                return ServiceActionClassification.KnownService;
            }

            if (!KnownNonServiceActions.Contains(actionName))
            {
                hasUnknown = true;
            }
        }

        return hasUnknown
            ? ServiceActionClassification.Unknown
            : ServiceActionClassification.None;
    }

    private static readonly IReadOnlySet<string> KnownNonServiceActions =
        new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "Bed", "Book", "Chest", "Crib", "Door", "FishingTile", "Harvest",
            "HoeDirt", "Ladder", "LockedDoorWarp", "Mailbox", "Message", "OpenDoor",
            "PickUp", "Sign", "Stair", "TouchAction", "TV", "Warp", "Water",
        };

    private static bool IsKnownServiceAction(string actionName)
    {
        return actionName.Contains("shop", StringComparison.OrdinalIgnoreCase) ||
            actionName.Contains("store", StringComparison.OrdinalIgnoreCase) ||
            actionName.Contains("vendor", StringComparison.OrdinalIgnoreCase) ||
            actionName.Contains("merchant", StringComparison.OrdinalIgnoreCase) ||
            actionName.Contains("bookseller", StringComparison.OrdinalIgnoreCase) ||
            actionName.Contains("theater", StringComparison.OrdinalIgnoreCase) ||
            actionName.Contains("icecream", StringComparison.OrdinalIgnoreCase) ||
            actionName.Contains("mermaid", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(actionName, "Buy", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(actionName, "Purchase", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(actionName, "Trade", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(actionName, "Boat", StringComparison.OrdinalIgnoreCase);
    }

    private static string? Normalize(string? value)
    {
        return string.IsNullOrWhiteSpace(value)
            ? null
            : value.Trim();
    }
}
