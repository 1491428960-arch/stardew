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

    [JsonPropertyName("relationship")]
    public string? Relationship { get; init; }

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
            modRegistry);

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
            Relationship = state.Relationship,
            SourceMods = state.SourceMods,
            Warnings = warnings.Concat(state.Warnings).Distinct().ToArray(),
        };
    }

    public static NpcGameState Collect(
        RuntimeNpcState npc,
        RuntimeWorldState world,
        IModRegistryStatus registry)
    {
        var warnings = new List<string>();
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
            Relationship = npc.Relationship,
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

            var data = ReadMember(Game1.player, "friendshipData") as IDictionary;
            if (data is null || !data.Contains(npcId))
            {
                return (null, null);
            }

            var friendship = data[npcId];
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
