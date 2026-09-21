using System.Collections;
using System.Globalization;
using System.Reflection;
using System.Text.Json.Serialization;
using StardewValley;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

public sealed class NpcGameState
{
    [JsonPropertyName("npcId")]
    public string? NpcId { get; init; }

    [JsonPropertyName("displayName")]
    public string? DisplayName { get; init; }

    [JsonPropertyName("gender")]
    public string? Gender { get; init; }

    [JsonPropertyName("location")]
    public string? Location { get; init; }

    [JsonPropertyName("season")]
    public string? Season { get; init; }

    [JsonPropertyName("date")]
    public string? Date { get; init; }

    [JsonPropertyName("weather")]
    public string? Weather { get; init; }

    [JsonPropertyName("time")]
    public int? Time { get; init; }

    [JsonPropertyName("friendship")]
    public int? Friendship { get; init; }

    [JsonPropertyName("friendshipHearts")]
    public int? FriendshipHearts { get; init; }

    [JsonPropertyName("relationship")]
    public string? Relationship { get; init; }

    [JsonPropertyName("marriageStatus")]
    public string? MarriageStatus { get; init; }

    [JsonPropertyName("childrenCount")]
    public int? ChildrenCount { get; init; }

    [JsonPropertyName("completedEventIds")]
    public IReadOnlyList<string> CompletedEventIds { get; init; } = Array.Empty<string>();

    [JsonPropertyName("sourceMods")]
    public IReadOnlyList<string> SourceMods { get; init; } = Array.Empty<string>();

    [JsonPropertyName("warnings")]
    public IReadOnlyList<string> Warnings { get; init; } = Array.Empty<string>();
}

public sealed record RuntimeNpcState(
    string? NpcId,
    string? DisplayName,
    string? Gender,
    string? Location,
    int? Friendship,
    string? Relationship);

public sealed record RuntimeStoryState(
    string? MarriageStatus = null,
    int? ChildrenCount = null,
    IReadOnlyList<string>? CompletedEventIds = null);

public sealed record RuntimeWorldState(
    string? Season,
    int? Day,
    bool? IsRaining,
    int? Time);

public interface IModRegistryStatus
{
    bool IsLoaded(string uniqueId);
}

public static class GameStateCollector
{
    /// <summary>
    /// 发往 Bridge 的 <c>completedEventIds</c> 上限。
    /// </summary>
    /// <remarks>
    /// 事件链门控（Bridge 侧 <c>resolve_relationship_gate</c>）要求「已完成的全部事件」，
    /// 截断会让门控把已完成的事件误判成未完成，从而把已婚等既成关系压回 <c>acquaintance</c>
    /// （2026-09-21：用户存档 391 条被截到 128 条，7 个配了事件门的角色里 6 个被压级）。
    /// 因此这里只做防御性上限、不再承担业务语义；512 覆盖正常存档（含 SVE 等大型扩展）的
    /// 事件总量，Bridge 侧 <c>NpcGameState.completed_event_ids</c> 的上限必须与此保持一致，
    /// 否则超出部分会被 422 拒绝（<c>extra="forbid"</c> + 长度校验）。
    /// </remarks>
    public const int MaxCompletedEventIds = 512;

    private static readonly IModRegistryStatus EmptyModRegistry = new EmptyModRegistryStatus();
    private static IModRegistryStatus modRegistry = EmptyModRegistry;

    private static readonly (string Marker, string[] UniqueIds)[] ModFamilies =
    {
        (
            "SVE",
            new[]
            {
                "FlashShifter.SVECode",
                "FlashShifter.StardewValleyExpandedCP",
                "FlashShifter.SVE-FTM",
            }),
        (
            "female-bachelors",
            new[]
            {
                "Invatorzen.idcsm",
                "female.bachelors.beach",
                "female.bachelors.winter",
            }),
        (
            "Romanceable Rasmodius",
            new[]
            {
                "Nom0ri.RomRas",
                "Parrot.RomRas",
                "Dacar.SeasRomRasmodia",
            }),
    };

    public static void ConfigureModRegistry(IModRegistryStatus registry)
    {
        modRegistry = registry ?? EmptyModRegistry;
    }

    public static NpcGameState Collect(StardewNpc? npc)
    {
        if (npc is null)
        {
            return Empty("NPC unavailable");
        }

        var warnings = new List<string>();
        var npcId = ReadString(npc, "Name", warnings, "npcId");
        var displayName = ReadString(npc, "displayName", warnings, "displayName");
        var gender = ReadString(npc, "Gender", warnings, "gender");
        var locationObject = ReadMember(npc, "currentLocation");
        var location = ReadString(locationObject, "NameOrUniqueName") ??
                       ReadString(locationObject, "Name");
        if (location is null)
        {
            warnings.Add("location unavailable");
        }

        var season = ReadStaticString("currentSeason");
        if (season is null)
        {
            warnings.Add("season unavailable");
        }

        var day = ReadStaticInt("dayOfMonth");
        if (day is null)
        {
            warnings.Add("date unavailable");
        }

        var isRaining = ReadStaticBool("isRaining");
        var weather = isRaining.HasValue ? (isRaining.Value ? "rain" : "clear") : null;
        if (weather is null)
        {
            warnings.Add("weather unavailable");
        }
        var time = ReadStaticInt("timeOfDay");
        if (time is null)
        {
            warnings.Add("time unavailable");
        }

        var (friendship, relationship) = ReadFriendship(npcId);
        if (friendship is null)
        {
            warnings.Add("friendship unavailable");
        }

        var state = Collect(
            new RuntimeNpcState(npcId, displayName, gender, location, friendship, relationship),
            new RuntimeWorldState(season, day, isRaining, time),
            modRegistry,
            ReadRuntimeStoryState(npcId, relationship));

        return new NpcGameState
        {
            NpcId = state.NpcId,
            DisplayName = state.DisplayName,
            Gender = state.Gender,
            Location = state.Location,
            Season = state.Season,
            Date = state.Date,
            Weather = state.Weather,
            Time = state.Time,
            Friendship = state.Friendship,
            FriendshipHearts = state.FriendshipHearts,
            Relationship = state.Relationship,
            MarriageStatus = state.MarriageStatus,
            ChildrenCount = state.ChildrenCount,
            CompletedEventIds = state.CompletedEventIds,
            SourceMods = state.SourceMods,
            Warnings = warnings.Concat(state.Warnings).Distinct().ToArray(),
        };
    }

    public static NpcGameState Collect(
        RuntimeNpcState npc,
        RuntimeWorldState world,
        IModRegistryStatus registry,
        RuntimeStoryState? story = null)
    {
        var warnings = new List<string>();
        var normalizedStory = NormalizeStoryState(story, npc.Relationship);
        AddWarningWhenMissing(npc.NpcId, warnings, "npcId");
        AddWarningWhenMissing(npc.DisplayName, warnings, "displayName");
        AddWarningWhenMissing(npc.Gender, warnings, "gender");
        AddWarningWhenMissing(npc.Location, warnings, "location");
        AddWarningWhenMissing(world.Season, warnings, "season");
        if (!world.Day.HasValue)
        {
            warnings.Add("date unavailable");
        }

        var weather = world.IsRaining.HasValue
            ? world.IsRaining.Value ? "rain" : "clear"
            : null;
        if (weather is null)
        {
            warnings.Add("weather unavailable");
        }

        if (!world.Time.HasValue)
        {
            warnings.Add("time unavailable");
        }

        if (!npc.Friendship.HasValue)
        {
            warnings.Add("friendship unavailable");
        }

        return new NpcGameState
        {
            NpcId = npc.NpcId,
            DisplayName = npc.DisplayName,
            Gender = npc.Gender,
            Location = npc.Location,
            Season = world.Season,
            Date = world.Day?.ToString(CultureInfo.InvariantCulture),
            Weather = weather,
            Time = world.Time,
            Friendship = npc.Friendship,
            FriendshipHearts = ToFriendshipHearts(npc.Friendship),
            Relationship = npc.Relationship,
            MarriageStatus = normalizedStory.MarriageStatus,
            ChildrenCount = normalizedStory.ChildrenCount,
            CompletedEventIds = normalizedStory.CompletedEventIds ?? Array.Empty<string>(),
            SourceMods = DetectSourceMods(registry, warnings),
            Warnings = warnings,
        };
    }

    private static NpcGameState Empty(string warning)
    {
        return new NpcGameState { Warnings = new[] { warning } };
    }

    private static string? ReadString(object? source, string memberName)
    {
        try
        {
            return ReadMember(source, memberName)?.ToString();
        }
        catch
        {
            return null;
        }
    }

    private static string? ReadString(
        object source,
        string memberName,
        ICollection<string> warnings,
        string label)
    {
        var value = ReadString(source, memberName);
        if (value is null)
        {
            warnings.Add($"{label} unavailable");
        }

        return value;
    }

    private static object? ReadStatic(string memberName)
    {
        try
        {
            var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;
            var property = typeof(Game1).GetProperty(memberName, flags);
            if (property is not null)
            {
                return property.GetValue(null);
            }

            return typeof(Game1).GetField(memberName, flags)?.GetValue(null);
        }
        catch
        {
            return null;
        }
    }

    private static object? ReadMember(object? source, string memberName)
    {
        if (source is null)
        {
            return null;
        }

        try
        {
            var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            var type = source.GetType();
            var property = type.GetProperty(memberName, flags);
            if (property is not null)
            {
                return property.GetValue(source);
            }

            return type.GetField(memberName, flags)?.GetValue(source);
        }
        catch
        {
            return null;
        }
    }

    private static object? ReadMethod(object? source, string methodName)
    {
        if (source is null)
        {
            return null;
        }

        try
        {
            var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            var method = source.GetType().GetMethod(methodName, flags, Type.EmptyTypes);
            return method?.Invoke(source, null);
        }
        catch
        {
            return null;
        }
    }

    private static string? ReadStaticString(string memberName)
    {
        return ReadStatic(memberName)?.ToString();
    }

    private static int? ReadStaticInt(string memberName)
    {
        var value = ReadStatic(memberName);
        try
        {
            return value is null ? null : Convert.ToInt32(value, CultureInfo.InvariantCulture);
        }
        catch
        {
            return null;
        }
    }

    private static bool? ReadStaticBool(string memberName)
    {
        var value = ReadStatic(memberName);
        try
        {
            return value is null ? null : Convert.ToBoolean(value, CultureInfo.InvariantCulture);
        }
        catch
        {
            return null;
        }
    }

    private static (int? Friendship, string? Relationship) ReadFriendship(string? npcId)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(npcId))
            {
                return (null, null);
            }

            var data = ReadMember(Game1.player, "friendshipData");
            if (!FriendshipDataAccessor.TryGetValue(data, npcId, out var friendship))
            {
                return (null, null);
            }

            var points = ReadMember(friendship, "Points");
            var status = ReadString(friendship, "Status");
            return (
                points is null ? null : Convert.ToInt32(points, CultureInfo.InvariantCulture),
                status);
        }
        catch
        {
            return (null, null);
        }
    }

    private static RuntimeStoryState ReadRuntimeStoryState(
        string? npcId,
        string? relationship)
    {
        var marriageStatus = DeriveMarriageStatus(relationship);
        var spouse = ReadString(Game1.player, "spouse");
        var childrenCount = string.Equals(spouse, npcId, StringComparison.OrdinalIgnoreCase)
            ? ReadChildrenCount()
            : null;
        var completedEventIds = ReadEnumerableStrings(
            ReadMember(Game1.player, "eventsSeen"),
            maxCount: MaxCompletedEventIds);

        return new RuntimeStoryState(marriageStatus, childrenCount, completedEventIds);
    }

    private static RuntimeStoryState NormalizeStoryState(
        RuntimeStoryState? story,
        string? relationship)
    {
        var marriageStatus = story?.MarriageStatus;
        if (string.IsNullOrWhiteSpace(marriageStatus))
        {
            marriageStatus = DeriveMarriageStatus(relationship);
        }

        var childrenCount = story?.ChildrenCount;
        if (childrenCount is < 0)
        {
            childrenCount = null;
        }

        return new RuntimeStoryState(
            string.IsNullOrWhiteSpace(marriageStatus) ? null : marriageStatus.Trim(),
            childrenCount,
            NormalizeEventIds(story?.CompletedEventIds));
    }

    private static string? DeriveMarriageStatus(string? relationship)
    {
        if (string.IsNullOrWhiteSpace(relationship))
        {
            return null;
        }

        var normalized = relationship.Trim().ToLowerInvariant();
        return normalized switch
        {
            "married" or "roommate" or "dating" or "divorced" => normalized,
            _ => null,
        };
    }

    private static int? ToFriendshipHearts(int? friendship)
    {
        return friendship.HasValue
            ? Math.Clamp(friendship.Value / 250, 0, 14)
            : null;
    }

    private static int? ReadChildrenCount()
    {
        var children = ReadMethod(Game1.player, "getChildren") ??
                       ReadMember(Game1.player, "children");
        if (children is not IEnumerable values)
        {
            return null;
        }

        var count = 0;
        foreach (var _ in values)
        {
            count++;
        }

        return Math.Max(0, count);
    }

    private static IReadOnlyList<string> ReadEnumerableStrings(
        object? source,
        int maxCount)
    {
        if (source is not IEnumerable values)
        {
            return Array.Empty<string>();
        }

        var result = new List<string>();
        foreach (var value in values)
        {
            var text = value?.ToString()?.Trim();
            if (string.IsNullOrWhiteSpace(text) || result.Contains(text, StringComparer.Ordinal))
            {
                continue;
            }

            result.Add(text);
            if (result.Count >= maxCount)
            {
                break;
            }
        }

        return result;
    }

    private static IReadOnlyList<string> NormalizeEventIds(
        IReadOnlyList<string>? eventIds)
    {
        if (eventIds is null || eventIds.Count == 0)
        {
            return Array.Empty<string>();
        }

        return eventIds
            .Where(id => !string.IsNullOrWhiteSpace(id))
            .Select(id => id.Trim())
            .Distinct(StringComparer.Ordinal)
            .Take(MaxCompletedEventIds)
            .ToArray();
    }

    private static IReadOnlyList<string> DetectSourceMods(
        IModRegistryStatus? registry,
        ICollection<string> warnings)
    {
        var sourceMods = new List<string>();
        foreach (var family in ModFamilies)
        {
            var familyLoaded = false;
            foreach (var uniqueId in family.UniqueIds)
            {
                bool loaded;
                try
                {
                    loaded = registry?.IsLoaded(uniqueId) == true;
                }
                catch
                {
                    loaded = false;
                    warnings.Add($"mod registry unavailable: {uniqueId}");
                }

                if (!loaded)
                {
                    continue;
                }

                if (!familyLoaded)
                {
                    sourceMods.Add(family.Marker);
                    familyLoaded = true;
                }

                sourceMods.Add(uniqueId);
            }
        }

        return sourceMods;
    }

    private static void AddWarningWhenMissing(
        string? value,
        ICollection<string> warnings,
        string label)
    {
        if (value is null)
        {
            warnings.Add($"{label} unavailable");
        }
    }

    private sealed class EmptyModRegistryStatus : IModRegistryStatus
    {
        public bool IsLoaded(string uniqueId)
        {
            return false;
        }
    }
}
