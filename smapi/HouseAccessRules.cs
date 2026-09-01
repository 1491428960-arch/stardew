namespace StardewAI.NPC;

public enum HouseAccessReason
{
    FeatureDisabled,
    ResidentialAllowed,
    MixedBuildingAllowed,
    UnknownResidence,
    UnknownServiceProtection,
    FestivalProtection,
    EventProtection,
    MultiplayerProtection,
    MixedBuildingProtection,
}

public sealed record HouseAccessOptions(
    bool Enabled,
    bool AllowMixedBuildings,
    bool AllowFestivalAccess,
    bool AllowMultiplayerAccess)
{
    public static HouseAccessOptions EnabledForSinglePlayer(
        bool allowMixedBuildings = false) =>
        new(
            Enabled: true,
            AllowMixedBuildings: allowMixedBuildings,
            AllowFestivalAccess: false,
            AllowMultiplayerAccess: false);
}

public sealed record DoorAccessContext
{
    public string? TargetLocationName { get; init; }

    public IReadOnlyList<string> ResidentNpcIds { get; init; } = Array.Empty<string>();

    public bool IsKnownResidence { get; init; }

    public bool HasServiceInteraction { get; init; }

    public bool HasUnknownServiceInteraction { get; init; }

    public bool IsFestival { get; init; }

    public bool IsEventActive { get; init; }

    public bool IsMultiplayer { get; init; }

    public static DoorAccessContext Residential(
        string targetLocationName,
        params string[] residentNpcIds) =>
        new()
        {
            TargetLocationName = targetLocationName,
            ResidentNpcIds = NormalizeNpcIds(residentNpcIds),
            IsKnownResidence = true,
        };

    public static DoorAccessContext MixedResidentialService(
        string targetLocationName,
        string residentNpcId,
        string serviceId) =>
        new()
        {
            TargetLocationName = targetLocationName,
            ResidentNpcIds = NormalizeNpcIds(new[] { residentNpcId }),
            IsKnownResidence = true,
            HasServiceInteraction = !string.IsNullOrWhiteSpace(serviceId),
        };

    public static DoorAccessContext Unknown(string? targetLocationName) =>
        new()
        {
            TargetLocationName = targetLocationName,
            IsKnownResidence = false,
        };

    private static IReadOnlyList<string> NormalizeNpcIds(IEnumerable<string>? npcIds)
    {
        return (npcIds ?? Array.Empty<string>())
            .Where(id => !string.IsNullOrWhiteSpace(id))
            .Select(id => id.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }
}

public sealed record HouseAccessDecision(
    bool AllowPhysicalEntry,
    bool AllowNpcChat,
    bool PreserveVanillaDoor,
    HouseAccessReason Reason);

public static class HouseAccessRules
{
    public static HouseAccessDecision Evaluate(
        DoorAccessContext context,
        HouseAccessOptions options)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(options);

        if (!options.Enabled)
        {
            return Preserve(HouseAccessReason.FeatureDisabled);
        }

        if (!context.IsKnownResidence || context.ResidentNpcIds.Count == 0)
        {
            return Preserve(HouseAccessReason.UnknownResidence);
        }

        // 默认配置保持保守；个人测试档显式允许混合建筑时，已确认的
        // NPC 住宅优先放行。这样医院、商店与住宅共用地图时，不会因为
        // 第三方地图使用了未知 Action 名称而把整栋住宅锁死。
        if (context.HasUnknownServiceInteraction && !options.AllowMixedBuildings)
        {
            return Preserve(HouseAccessReason.UnknownServiceProtection);
        }

        if (context.IsFestival && !options.AllowFestivalAccess)
        {
            return Preserve(HouseAccessReason.FestivalProtection);
        }

        if (context.IsEventActive)
        {
            return Preserve(HouseAccessReason.EventProtection);
        }

        if (context.IsMultiplayer && !options.AllowMultiplayerAccess)
        {
            return Preserve(HouseAccessReason.MultiplayerProtection);
        }

        if (context.HasServiceInteraction && !options.AllowMixedBuildings)
        {
            return Preserve(HouseAccessReason.MixedBuildingProtection);
        }

        return new HouseAccessDecision(
            AllowPhysicalEntry: true,
            AllowNpcChat: true,
            PreserveVanillaDoor: false,
            Reason: context.HasServiceInteraction || context.HasUnknownServiceInteraction
                ? HouseAccessReason.MixedBuildingAllowed
                : HouseAccessReason.ResidentialAllowed);
    }

    private static HouseAccessDecision Preserve(HouseAccessReason reason) =>
        new(
            AllowPhysicalEntry: false,
            AllowNpcChat: false,
            PreserveVanillaDoor: true,
            Reason: reason);
}
