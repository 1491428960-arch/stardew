namespace StardewAI.NPC;

public sealed record KnownNpc(string NpcId, string DisplayName);

public static class KnownNpcResolver
{
    public static IReadOnlyList<KnownNpc> Resolve(
        IEnumerable<string>? friendshipKeys,
        Func<string, KnownNpc?> resolveNpc)
    {
        ArgumentNullException.ThrowIfNull(resolveNpc);

        if (friendshipKeys is null)
        {
            return Array.Empty<KnownNpc>();
        }

        var result = new List<KnownNpc>();
        foreach (var rawKey in friendshipKeys)
        {
            var npcId = rawKey?.Trim();
            if (string.IsNullOrWhiteSpace(npcId) ||
                string.Equals(npcId, "player", StringComparison.OrdinalIgnoreCase) ||
                TestNpcPlacementRules.IsDialogueTargetWithoutFriendshipRecord(npcId))
            {
                continue;
            }

            if (result.Any(item => string.Equals(item.NpcId, npcId, StringComparison.OrdinalIgnoreCase)))
            {
                continue;
            }

            KnownNpc? resolved;
            try
            {
                resolved = resolveNpc(npcId);
            }
            catch
            {
                resolved = null;
            }

            if (resolved is null ||
                string.IsNullOrWhiteSpace(resolved.NpcId) ||
                string.IsNullOrWhiteSpace(resolved.DisplayName))
            {
                continue;
            }

            result.Add(new KnownNpc(resolved.NpcId.Trim(), resolved.DisplayName.Trim()));
        }

        return result;
    }
}
