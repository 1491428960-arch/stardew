using HarmonyLib;
using Microsoft.Xna.Framework;
using StardewModdingAPI;
using StardewValley;
using StardewValley.Locations;

namespace StardewAI.NPC;

/// <summary>
/// Applies the conservative residential-door policy at the final vanilla door
/// check. The map and save data remain untouched; when the policy does not
/// recognize a pure residence, the original method runs unchanged.
/// </summary>
public sealed class HouseAccessController : IDisposable
{
    private const string HarmonyId = "OpenAI.StardewAI.NPC.house-access";

    private static HouseAccessController? active;

    private readonly IMonitor monitor;
    private readonly Func<HouseAccessOptions> optionsProvider;
    private readonly Dictionary<string, ServiceActionClassification> serviceMapCache =
        new(StringComparer.OrdinalIgnoreCase);
    private Harmony? harmony;

    public HouseAccessController(
        IMonitor monitor,
        Func<HouseAccessOptions> optionsProvider)
    {
        this.monitor = monitor ?? throw new ArgumentNullException(nameof(monitor));
        this.optionsProvider = optionsProvider ??
            throw new ArgumentNullException(nameof(optionsProvider));
    }

    public bool IsApplied => harmony is not null;

    public void ResetMapCache() => serviceMapCache.Clear();

    public void Apply()
    {
        if (harmony is not null)
        {
            return;
        }

        var lockedDoorTarget = AccessTools.Method(
            typeof(GameLocation),
            "lockedDoorWarp",
            new[]
            {
                typeof(Point),
                typeof(string),
                typeof(int),
                typeof(int),
                typeof(string),
                typeof(int),
            });
        var performActionTarget = AccessTools.Method(
            typeof(GameLocation),
            "performAction",
            new[]
            {
                typeof(string[]),
                typeof(Farmer),
                typeof(xTile.Dimensions.Location),
            });
        var performTouchActionTarget = AccessTools.Method(
            typeof(GameLocation),
            "performTouchAction",
            new[]
            {
                typeof(string[]),
                typeof(Vector2),
            });
        if (lockedDoorTarget is null &&
            performActionTarget is null &&
            performTouchActionTarget is null)
        {
            monitor.Log(
                "未找到原版房屋门 action 方法，房屋门访问保持原版。",
                LogLevel.Warn);
            return;
        }

        try
        {
            harmony = new Harmony(HarmonyId);
            active = this;
            PatchTarget(
                lockedDoorTarget,
                nameof(LockedDoorWarpPrefix));
            PatchTarget(
                performActionTarget,
                nameof(PerformActionPrefix));
            PatchTarget(
                performTouchActionTarget,
                nameof(PerformTouchActionPrefix));
        }
        catch (Exception exception)
        {
            try
            {
                harmony?.UnpatchAll(HarmonyId);
            }
            catch (Exception cleanupException)
            {
                monitor.Log(
                    $"清理房屋门补丁失败：{cleanupException.Message}",
                    LogLevel.Trace);
            }
            finally
            {
                harmony = null;
                active = null;
            }
            monitor.Log(
                $"安装房屋门补丁失败，已保持原版门禁：{exception.Message}",
                LogLevel.Warn);
        }
    }

    public void TraceInteractionTarget(GameLocation? location, Vector2 grabTile)
    {
        if (location is null)
        {
            return;
        }

        var x = (int)grabTile.X;
        var y = (int)grabTile.Y;
        var properties = new List<string>();
        foreach (var layer in new[] { "Buildings", "Back" })
        {
            foreach (var propertyName in new[] { "Action", "TouchAction", "Door", "Warp" })
            {
                var value = location.doesTileHaveProperty(
                    x,
                    y,
                    propertyName,
                    layer,
                    false);
                if (!string.IsNullOrWhiteSpace(value))
                {
                    properties.Add($"{layer}.{propertyName}={value}");
                }
            }
        }

        monitor.Log(
            $"交互目标诊断：location={location.NameOrUniqueName} tile={x},{y} " +
            $"properties={(properties.Count == 0 ? "<none>" : string.Join(" | ", properties))}",
            LogLevel.Trace);
    }

    public void Dispose()
    {
        harmony?.UnpatchAll(HarmonyId);
        harmony = null;
        if (ReferenceEquals(active, this))
        {
            active = null;
        }
    }

    private static void LockedDoorWarpPrefix(
        Point tile,
        string locationName,
        ref int openTime,
        ref int closeTime,
        ref string? npcName,
        ref int minFriendship)
    {
        active?.TryOpenResidentialDoor(
            tile,
            locationName,
            ref openTime,
            ref closeTime,
            ref npcName,
            ref minFriendship);
    }

    private static void PerformActionPrefix(
        GameLocation __instance,
        string[] __0,
        Farmer __1,
        xTile.Dimensions.Location __2)
    {
        active?.InspectAndRelaxPerformAction(
            __instance,
            __0,
            __1,
            __2);
    }

    private static void PerformTouchActionPrefix(
        GameLocation __instance,
        string[] __0,
        Vector2 __1)
    {
        active?.InspectTouchAction(__instance, __0, __1);
    }

    private void PatchTarget(
        System.Reflection.MethodInfo? target,
        string prefixName)
    {
        if (target is null)
        {
            monitor.Log(
                $"未找到房屋门补丁目标：{prefixName}",
                LogLevel.Trace);
            return;
        }

        monitor.Log(
            $"房屋门补丁目标已找到：{target.DeclaringType?.FullName}.{target.Name} " +
            $"参数={string.Join(", ", target.GetParameters().Select(parameter => parameter.ParameterType.Name))}",
            LogLevel.Trace);
        harmony!.Patch(
            target,
            prefix: new HarmonyMethod(
                typeof(HouseAccessController),
                prefixName));
    }

    private void InspectAndRelaxPerformAction(
        GameLocation sourceLocation,
        string[] actionTokens,
        Farmer who,
        xTile.Dimensions.Location sourceTile)
    {
        if (actionTokens.Length == 0)
        {
            return;
        }

        var actionName = actionTokens[0];
        if (DoorActionParser.IsDoorOrWarpAction(actionName))
        {
            monitor.Log(
                $"房屋门 action 路径：entry=performAction source={sourceLocation.NameOrUniqueName} " +
                $"tile={sourceTile.X},{sourceTile.Y} player={who.Name} " +
                $"action={string.Join(" ", actionTokens)}",
                LogLevel.Trace);
        }

        if (!DoorActionParser.TryParse(actionTokens, out var action) || action is null)
        {
            return;
        }

        var openTime = action.OpenTime;
        var closeTime = action.CloseTime;
        var npcName = action.RequiredNpcId;
        var minFriendship = action.MinimumFriendship ?? 0;
        var allow = TryOpenResidentialDoor(
            new Point(action.DestinationX, action.DestinationY),
            action.TargetLocationName,
            ref openTime,
            ref closeTime,
            ref npcName,
            ref minFriendship);
        if (allow && DoorActionParser.RelaxResidentialGate(actionTokens))
        {
            monitor.Log(
                $"住宅门已在 performAction 上游放行：target={action.TargetLocationName} " +
                $"source={sourceLocation.NameOrUniqueName} tile={sourceTile.X},{sourceTile.Y}",
                LogLevel.Trace);
        }
    }

    private void InspectTouchAction(
        GameLocation sourceLocation,
        string[] actionTokens,
        Vector2 playerStandingPosition)
    {
        if (actionTokens.Length == 0)
        {
            return;
        }

        monitor.Log(
            $"房屋门 action 路径：entry=performTouchAction source={sourceLocation.NameOrUniqueName} " +
            $"playerTile={playerStandingPosition.X / Game1.tileSize:0.##}," +
            $"{playerStandingPosition.Y / Game1.tileSize:0.##} " +
            $"action={string.Join(" ", actionTokens)}",
            LogLevel.Trace);
    }

    private bool TryOpenResidentialDoor(
        Point tile,
        string locationName,
        ref int openTime,
        ref int closeTime,
        ref string? npcName,
        ref int minFriendship)
    {
        monitor.Log(
            $"房屋门检查入口：location={locationName} tile={tile.X},{tile.Y} " +
            $"npc={npcName ?? "<none>"} open={openTime} close={closeTime} friend={minFriendship}",
            LogLevel.Trace);

        HouseAccessOptions options;
        try
        {
            options = optionsProvider();
        }
        catch (Exception exception)
        {
            monitor.Log(
                $"读取房屋门配置失败，已保持原版门禁：{exception.Message}",
                LogLevel.Warn);
            return false;
        }

        if (!options.Enabled || !Context.IsWorldReady)
        {
            return false;
        }

        try
        {
            var resident = string.IsNullOrWhiteSpace(npcName)
                ? null
                : Game1.getCharacterFromName(npcName);
            var targetLocation = Game1.getLocationFromName(locationName);
            var npcHomeMatchesTarget = resident?.getHome() is { } home &&
                SameLocation(home, locationName);
            var serviceActionClassification = targetLocation is null
                ? ServiceActionClassification.None
                : GetServiceActionClassification(targetLocation);
            var targetIsShopLocation = targetLocation is ShopLocation ||
                HouseDoorTargetRules.IsKnownServiceLocation(locationName) ||
                serviceActionClassification == ServiceActionClassification.KnownService;
            var context = HouseDoorTargetRules.CreateContext(
                locationName,
                npcName,
                npcHomeMatchesTarget,
                targetIsShopLocation,
                unknownServiceAction: serviceActionClassification == ServiceActionClassification.Unknown) with
            {
                IsFestival = Game1.isFestival(),
                IsEventActive = Game1.eventUp,
                IsMultiplayer = Game1.IsMultiplayer,
            };
            var decision = HouseAccessRules.Evaluate(
                context,
                options);
            if (!decision.AllowPhysicalEntry)
            {
                monitor.Log(
                    $"住宅门保留原版：{locationName} NPC={npcName ?? "<none>"} " +
                    $"knownResidence={context.IsKnownResidence} residents={context.ResidentNpcIds.Count} " +
                    $"service={context.HasServiceInteraction} unknownService={context.HasUnknownServiceInteraction} " +
                    $"festival={context.IsFestival} event={context.IsEventActive} " +
                    $"multiplayer={context.IsMultiplayer} 原因={decision.Reason}",
                    LogLevel.Trace);
                return false;
            }

            // Preserve the vanilla method's warp destination and collision
            // handling, but remove only the time/NPC gate for this call.
            openTime = 600;
            closeTime = 2600;
            npcName = null;
            minFriendship = -1;
            monitor.Log(
                $"住宅门放行：{locationName} tile={tile.X},{tile.Y} " +
                $"NPC={string.Join(",", context.ResidentNpcIds)} 原因={decision.Reason}",
                LogLevel.Trace);
            return true;
        }
        catch (Exception exception)
        {
            // A modded map or NPC must never make the door patch fatal.
            monitor.Log(
                $"房屋门判定失败，已回退原版：{exception.Message}",
                LogLevel.Trace);
            return false;
        }
    }

    private static bool SameLocation(GameLocation home, string targetLocationName)
    {
        return string.Equals(
                   home.NameOrUniqueName,
                   targetLocationName,
                   StringComparison.OrdinalIgnoreCase) ||
            string.Equals(
                home.Name,
                targetLocationName,
                StringComparison.OrdinalIgnoreCase);
    }

    private ServiceActionClassification GetServiceActionClassification(GameLocation location)
    {
        var locationId = string.IsNullOrWhiteSpace(location.NameOrUniqueName)
            ? location.Name
            : location.NameOrUniqueName;
        if (string.IsNullOrWhiteSpace(locationId))
        {
            return ServiceActionClassification.None;
        }

        if (serviceMapCache.TryGetValue(locationId, out var cached))
        {
            return cached;
        }

        var actions = ReadMapActions(location);
        var classification = HouseDoorTargetRules.ClassifyServiceActions(actions);
        serviceMapCache[locationId] = classification;
        return classification;
    }

    private static IEnumerable<string> ReadMapActions(GameLocation location)
    {
        if (location.Map is null)
        {
            yield break;
        }

        foreach (var layer in location.Map.Layers)
        {
            for (var x = 0; x < layer.LayerWidth; x++)
            {
                for (var y = 0; y < layer.LayerHeight; y++)
                {
                    var tile = layer.Tiles[x, y];
                    if (tile?.Properties is null)
                    {
                        continue;
                    }

                    foreach (var property in tile.Properties)
                    {
                        if (string.Equals(property.Key, "Action", StringComparison.OrdinalIgnoreCase) ||
                            string.Equals(property.Key, "TouchAction", StringComparison.OrdinalIgnoreCase))
                        {
                            yield return property.Value?.ToString() ?? string.Empty;
                        }
                    }
                }
            }
        }
    }
}
