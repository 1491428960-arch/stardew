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

    /// <summary>
    /// 「就在当前地点、能直接聊上」的选人规则：鼠标指向优先，否则最近，再按名字。
    ///
    /// 2026-09-21（B26）起 F8 不再用它**替玩家拍板**——先开私聊名单
    /// （<see cref="PrivateChatRosterRules"/>）让玩家自己选。但这条规则没有退役：
    /// 名单打开时默认选中哪一行就是它算出来的
    /// （<see cref="PrivateChatRosterRules.DefaultSelectedIndex"/> 调用的正是本方法），
    /// 即「自动选人」降级成「预选」，口径仍然只有这一份实现。
    ///
    /// 它还把「床边克隆体会抢走自动目标」这个真实发生过的现象钉在测试里
    /// （<c>NpcTargetResolverTests</c>）：那个克隆体没有好感度记录，
    /// 因此在名单里也进不来——<see cref="KnownNpcResolver"/> 会先把它滤掉。
    /// </summary>
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
