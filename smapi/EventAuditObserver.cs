namespace StardewAI.NPC;

public sealed class EventAuditObserver
{
    private IReadOnlyList<string>? previousSeenEventIds;

    public EventAuditObservation Observe(EventAuditSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);

        var observation = EventAuditRules.Observe(snapshot, previousSeenEventIds);
        previousSeenEventIds = snapshot.SeenEventIds.ToArray();
        return observation;
    }

    public void Reset()
    {
        previousSeenEventIds = null;
    }
}
