namespace StardewAI.NPC;

/// <summary>
/// 记录同一游戏日内已经领取过分享好感奖励的 NPC。
/// </summary>
public sealed class ShareFriendshipLedger
{
    private readonly HashSet<string> claimedNpcIds = new(StringComparer.OrdinalIgnoreCase);
    private int? currentGameDay;

    public bool TryClaim(string? npcId, int gameDay)
    {
        var normalizedNpcId = npcId?.Trim() ?? string.Empty;
        if (normalizedNpcId.Length == 0)
        {
            return false;
        }

        if (currentGameDay != gameDay)
        {
            currentGameDay = gameDay;
            claimedNpcIds.Clear();
        }

        return claimedNpcIds.Add(normalizedNpcId);
    }

    public void Reset()
    {
        currentGameDay = null;
        claimedNpcIds.Clear();
    }
}
