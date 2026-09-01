namespace StardewAI.NPC;

public sealed record EventAuditSnapshot
{
    public string? LocationName { get; }

    public int? Time { get; }

    public bool EventIsActive { get; }

    public string? CurrentEventId { get; }

    public IReadOnlyList<string> SeenEventIds { get; }

    public IReadOnlyList<string> EventIdsSinceLocationChange { get; }

    public EventAuditSnapshot(
        string? locationName,
        int? time,
        bool eventIsActive,
        string? currentEventId,
        IEnumerable<string>? seenEventIds,
        IEnumerable<string>? eventIdsSinceLocationChange)
    {
        LocationName = NormalizeText(locationName);
        Time = time;
        EventIsActive = eventIsActive;
        CurrentEventId = NormalizeText(currentEventId);
        SeenEventIds = NormalizeIds(seenEventIds);
        EventIdsSinceLocationChange = NormalizeIds(eventIdsSinceLocationChange);
    }

    private static string? NormalizeText(string? value)
    {
        return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    }

    private static IReadOnlyList<string> NormalizeIds(IEnumerable<string>? values)
    {
        return (values ?? Array.Empty<string>())
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value.Trim())
            .Distinct(StringComparer.Ordinal)
            .ToArray();
    }
}

public sealed record EventAuditObservation(
    string? LocationName,
    int? Time,
    bool EventIsActive,
    string? CurrentEventId,
    IReadOnlyList<string> NewSeenEventIds,
    IReadOnlyList<string> EventIdsSinceLocationChange,
    bool ModWouldMutateGameState);

public static class EventAuditRules
{
    public static EventAuditObservation Observe(
        EventAuditSnapshot current,
        IEnumerable<string>? previousSeenEventIds = null)
    {
        ArgumentNullException.ThrowIfNull(current);

        // 首次观察没有可比较的基线，只记录当前快照，不把已有事件误报为本次新事件。
        var previous = previousSeenEventIds is null
            ? current.SeenEventIds
            : NormalizeIds(previousSeenEventIds);
        var newSeenEventIds = current.SeenEventIds
            .Except(previous, StringComparer.Ordinal)
            .ToArray();

        return new EventAuditObservation(
            LocationName: current.LocationName,
            Time: current.Time,
            EventIsActive: current.EventIsActive,
            CurrentEventId: current.CurrentEventId,
            NewSeenEventIds: newSeenEventIds,
            EventIdsSinceLocationChange: current.EventIdsSinceLocationChange,
            // 这里只表示本 Mod 没有直接写入存档/事件集合；原版地点进入流程
            // 仍可能按自身规则更新 eventsSeen、firstVisit 或剧情状态。
            ModWouldMutateGameState: false);
    }

    private static IReadOnlyList<string> NormalizeIds(IEnumerable<string>? values)
    {
        return (values ?? Array.Empty<string>())
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value.Trim())
            .Distinct(StringComparer.Ordinal)
            .ToArray();
    }
}
