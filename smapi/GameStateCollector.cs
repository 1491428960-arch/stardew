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

    [JsonPropertyName("warnings")]
    public IReadOnlyList<string> Warnings { get; init; } = Array.Empty<string>();
}

public static class GameStateCollector
{
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

        return new NpcGameState
        {
            NpcId = npcId,
            DisplayName = displayName,
            Gender = gender,
            Location = location,
            Season = season,
            Date = day?.ToString(CultureInfo.InvariantCulture),
            Weather = weather,
            Time = time,
            Friendship = friendship,
            Relationship = relationship,
            Warnings = warnings,
        };
    }

    private static NpcGameState Empty(string warning)
    {
        return new NpcGameState { Warnings = new[] { warning } };
    }

    private static string? ReadString(object? source, string memberName)
    {
        return ReadMember(source, memberName)?.ToString();
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
        return value is null ? null : Convert.ToInt32(value, CultureInfo.InvariantCulture);
    }

    private static bool? ReadStaticBool(string memberName)
    {
        var value = ReadStatic(memberName);
        return value is null ? null : Convert.ToBoolean(value, CultureInfo.InvariantCulture);
    }

    private static (int? Friendship, string? Relationship) ReadFriendship(string? npcId)
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
        var status = ReadMember(friendship, "Status")?.ToString();
        return (points is null ? null : Convert.ToInt32(points, CultureInfo.InvariantCulture), status);
    }
}
