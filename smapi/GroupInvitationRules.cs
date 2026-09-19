namespace StardewAI.NPC;

public static class GroupInvitationRules
{
    public const int MinParticipants = 2;
    public const int MaxParticipants = 3;
    public const int GenerationIntervalDays = 2;
    public const int MaxPendingInvitations = 3;
    public const int ExpirationDays = 7;

    private static readonly HashSet<string> KnownTemplateIds = new(StringComparer.Ordinal)
    {
        "neutral-public-topic",
        "mineral-and-mystery",
        "research-follow-up",
        "social-perspective",
    };

    private static readonly HashSet<string> Sources = new(StringComparer.Ordinal)
    {
        "periodic",
        "relationship",
        "story",
    };

    public static bool IsValidParticipantCount(int count)
    {
        return count is >= MinParticipants and <= MaxParticipants;
    }

    public static string BuildPairKey(IEnumerable<string> npcIds)
    {
        ArgumentNullException.ThrowIfNull(npcIds);

        // 去重键必须**整体**大小写不敏感：先把每个 ID 规范化为小写再排序拼接。
        // 否则同一组人写成 Abigail|Emily 与 abigail|emily 会得到两个不同的键，
        // 让“最近组合去重”失效、重复生成同一张邀约卡。
        return string.Join(
            "|",
            npcIds
                .Where(id => !string.IsNullOrWhiteSpace(id))
                .Select(id => id.Trim().ToLowerInvariant())
                .Distinct(StringComparer.Ordinal)
                .OrderBy(id => id, StringComparer.Ordinal));
    }

    public static string BuildDuplicateKey(GroupDialogueInvitationRecord invitation)
    {
        ArgumentNullException.ThrowIfNull(invitation);
        // 模板 ID 也要归一化成小写：本方法的契约是“整个去重键大小写不敏感”，
        // 只 Trim 会让大小写不同的模板 ID 产生不同的键。
        return $"{invitation.TemplateId.Trim().ToLowerInvariant()}::" +
            BuildPairKey(invitation.Participants);
    }

    public static bool ShouldGenerate(
        int currentTotalDays,
        int? lastCreatedTotalDays,
        int pendingCount)
    {
        if (currentTotalDays < 0 || pendingCount >= MaxPendingInvitations)
        {
            return false;
        }

        return !lastCreatedTotalDays.HasValue ||
            currentTotalDays - lastCreatedTotalDays.Value >= GenerationIntervalDays;
    }

    public static bool IsExpired(
        int currentTotalDays,
        int createdTotalDays,
        int expiresTotalDays)
    {
        return currentTotalDays >= expiresTotalDays &&
            expiresTotalDays > createdTotalDays;
    }

    public static GroupDialogueInvitationRecord AfterConversationResult(
        GroupDialogueInvitationRecord invitation,
        bool usableReply)
    {
        ArgumentNullException.ThrowIfNull(invitation);
        return usableReply
            ? invitation with { Status = GroupInvitationStatus.Completed }
            : invitation;
    }

    public static bool IsKnownTemplateId(string? templateId)
    {
        return !string.IsNullOrWhiteSpace(templateId) && KnownTemplateIds.Contains(templateId.Trim());
    }

    public static bool IsValidSource(string? source)
    {
        return !string.IsNullOrWhiteSpace(source) && Sources.Contains(source.Trim());
    }

    public static bool IsValidStatus(GroupInvitationStatus status)
    {
        return Enum.IsDefined(status);
    }
}
