namespace StardewAI.NPC;

public static class GroupInvitationRules
{
    public const int MinParticipants = 2;
    public const int MaxParticipants = 3;
    public const int GenerationIntervalDays = 2;
    /// <summary>
    /// 多人对话中心**一屏最多画几张邀约卡**。
    ///
    /// 2026-09-20：它此前叫 `MaxPendingInvitations` 并**同时**用作“待处理上限”——
    /// 于是玩家不把旧卡处理掉就永远刷不出新的（用户反馈：“每个刷了就得清也太蠢了”）。
    /// 现在它**只管显示**：生成侧不再受待处理数量限制，因为
    /// ① 过期机制（<see cref="ExpirationDays"/> 天）保证不会无限堆积；
    /// ② 显示按创建日倒序取最新的几张，旧的仍在存档里、到点自动过期。
    /// 面板高度 680 − 标题 − 底部按钮 ≈ 放得下 4 行（每行 92 + 间距）。
    /// </summary>
    public const int MaxVisibleInvitations = 4;
    public const int ExpirationDays = 7;

    private static readonly HashSet<string> KnownTemplateIds = new(StringComparer.Ordinal)
    {
        "neutral-public-topic",
        "mineral-and-mystery",
        "research-follow-up",
        "adventure-trio",
        "seasonal-chores",
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

    /// <summary>
    /// 是否该生成新邀约。**只看时间间隔，不看待处理数量**。
    ///
    /// 2026-09-20（用户反馈）：此前这里还有一条 `pendingCount >= 3 → false`，
    /// 结果是“玩家必须把旧卡处理掉才会刷出新的”。而那条限制原本是为了防止
    /// 名额被“接受后一直没完成”的邀约永久占用——**过期机制已经解决了这个问题**
    /// （见 GroupDialogueExpiryTests：连 Accepted 也会在 7 天后过期），
    /// 所以这里不再需要它。
    /// </summary>
    public static bool ShouldGenerate(
        int currentTotalDays,
        int? lastCreatedTotalDays)
    {
        if (currentTotalDays < 0)
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
