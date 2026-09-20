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

    /// <summary>
    /// 旧版硬编码的模板 ID —— **不要删**，否则玩家存档里已经存在的旧邀约会变成“不合法”。
    /// </summary>
    private static readonly HashSet<string> LegacyTemplateIds = new(StringComparer.Ordinal)
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
        // 2026-09-20：模板现在是「角色组合 × 话题」程序化生成的，同一个组合对应
        // 多个模板 ID。若继续把 TemplateId 算进键里，“同一对人”会被判成不重复，
        // 于是接连刷出同一个组合。所以去重键**只看参与者组合**：同一组人 7 天内
        // 不重复，而每次的话题可以不同（47 人两两有 1081 种组合，足够轮换）。
        return BuildPairKey(invitation.Participants);
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

    /// <summary>
    /// 模板 ID 是否合法。
    ///
    /// 2026-09-20：模板改成按「主题 × 角色组合」**按需生成**之后，
    /// 穷举白名单不再可行——`GroupInvitationTemplates.All` 只含两两组合，
    /// 而生成器还会产出三人模板，于是三人邀约写入时被判“templateId is invalid”，
    /// **抛异常导致整个 DayStarted 中断、再也不生成新邀约**（真机踩到过）。
    /// 所以这里改成：**旧 ID 直接认，新格式按“主题前缀在主题表里”判断**。
    /// </summary>
    public static bool IsKnownTemplateId(string? templateId)
    {
        if (string.IsNullOrWhiteSpace(templateId))
        {
            return false;
        }

        var id = templateId.Trim();
        if (LegacyTemplateIds.Contains(id))
        {
            return true;
        }

        var separator = id.IndexOf(':');
        return separator > 0
            && GroupInvitationThemes.All.ContainsKey(id[..separator]);
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
