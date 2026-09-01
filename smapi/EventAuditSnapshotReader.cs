using System.Collections;
using System.Globalization;
using System.Reflection;
using StardewValley;

namespace StardewAI.NPC;

public static class EventAuditSnapshotReader
{
    public static EventAuditSnapshot Read(object? location)
    {
        var currentEvent = ReadStatic("CurrentEvent") ?? ReadStatic("currentEvent");
        var eventIsActive = ReadStaticBool("eventUp") ?? currentEvent is not null;
        var currentEventId = ReadString(currentEvent, "id") ??
                             ReadString(currentEvent, "eventId") ??
                             ReadString(currentEvent, "ID");

        return new EventAuditSnapshot(
            locationName: ReadString(location, "NameOrUniqueName") ??
                          ReadString(location, "Name"),
            time: ReadStaticInt("timeOfDay"),
            eventIsActive,
            currentEventId,
            ReadEnumerableStrings(ReadMember(Game1.player, "eventsSeen")),
            ReadEnumerableStrings(ReadStatic("eventsSeenSinceLastLocationChange")));
    }

    private static object? ReadStatic(string memberName)
    {
        try
        {
            const BindingFlags flags = BindingFlags.Public |
                                       BindingFlags.NonPublic |
                                       BindingFlags.Static;
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
            const BindingFlags flags = BindingFlags.Public |
                                       BindingFlags.NonPublic |
                                       BindingFlags.Instance;
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

    private static string? ReadString(object? source, string memberName)
    {
        return ReadMember(source, memberName)?.ToString();
    }

    private static int? ReadStaticInt(string memberName)
    {
        var value = ReadStatic(memberName);
        try
        {
            return value is null
                ? null
                : Convert.ToInt32(value, CultureInfo.InvariantCulture);
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
            return value is null
                ? null
                : Convert.ToBoolean(value, CultureInfo.InvariantCulture);
        }
        catch
        {
            return null;
        }
    }

    private static IReadOnlyList<string> ReadEnumerableStrings(object? source)
    {
        if (source is not IEnumerable values)
        {
            return Array.Empty<string>();
        }

        var result = new List<string>();
        foreach (var value in values)
        {
            var text = value?.ToString()?.Trim();
            if (string.IsNullOrWhiteSpace(text) ||
                result.Contains(text, StringComparer.Ordinal))
            {
                continue;
            }

            result.Add(text);
        }

        return result;
    }
}
