namespace StardewAI.NPC;

public sealed record NpcTargetCandidate(
    string NpcId,
    bool HasFriendshipRecord,
    bool IsInCurrentLocation,
    float Distance,
    bool IsInteractionTarget);

public static class NpcTargetResolver
{
    private static readonly string[] CandidateNames = { "Rasmodia", "Wizard" };

    public static string? ResolveTargetName(Func<string, bool> isAvailable)
    {
        return CandidateNames.FirstOrDefault(isAvailable);
    }

    public static NpcTargetCandidate? SelectFriendshipTarget(
        IEnumerable<NpcTargetCandidate> candidates)
    {
        ArgumentNullException.ThrowIfNull(candidates);

        return candidates
            .Where(candidate =>
                !string.IsNullOrWhiteSpace(candidate.NpcId) &&
                candidate.HasFriendshipRecord &&
                candidate.IsInCurrentLocation &&
                !float.IsNaN(candidate.Distance) &&
                !float.IsInfinity(candidate.Distance) &&
                candidate.Distance >= 0)
            .OrderByDescending(candidate => candidate.IsInteractionTarget)
            .ThenBy(candidate => candidate.Distance)
            .ThenBy(candidate => candidate.NpcId, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault();
    }
}
