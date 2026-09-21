namespace StardewAI.NPC;

/// <summary>
/// 私聊名单的一行**原始数据**：由 <c>ModEntry</c> 从游戏状态取好之后传进来。
/// 规则类不碰 <c>Game1</c>，于是「谁排在前面」「点下去走哪条频道」「打开时预选谁」
/// 都能脱离游戏被测试。
/// </summary>
public sealed record PrivateChatRosterSource(
    string NpcId,
    string DisplayName,
    bool IsPresent,
    float DistanceInTiles,
    bool IsInteractionTarget = false);

/// <summary>
/// 名单里算好的一行：排序位置、在场状态、以及点下去会走的频道。
///
/// <see cref="DistanceInTiles"/> 与 <see cref="IsInteractionTarget"/> 只为
/// <see cref="PrivateChatRosterRules.DefaultSelectedIndex"/> 服务——它们不是显示数据，
/// 而是「预选哪一行」那条老规则（<see cref="NpcTargetResolver.SelectFriendshipTarget"/>）
/// 的输入；离开名单之后没人再读。
/// </summary>
public sealed record PrivateChatRosterEntry(
    string NpcId,
    string DisplayName,
    bool IsPresent,
    bool IsNearby,
    string Channel,
    float DistanceInTiles = float.MaxValue,
    bool IsInteractionTarget = false)
{
    /// <summary>
    /// 列表右侧的状态字。它的作用是让玩家**点之前就知道会发生什么**：
    /// 「身边」= 当面聊，「同处一地」= 走过去就能当面聊，「线上」= 手机式远程聊天。
    /// </summary>
    public string StatusLabel => IsNearby
        ? "身边"
        : IsPresent
            ? "同处一地"
            : "线上";
}

/// <summary>
/// 私聊名单（B26：F8 支持选择对话对象）的规则。
///
/// **解锁口径不在这里**：名单本身来自 <see cref="KnownNpcResolver"/>，
/// 也就是「存档里已经有好感度记录的角色」——星露谷只为**已经打过照面**的村民建立这条
/// 记录（游戏里「社交」页显示的就是这一份），所以名单天然随游戏进度增长，
/// 与 F9 群聊用的是同一份解析。
///
/// 这里只负责：排序、在场判定、频道判定、**预选哪一行**、列表容量与滚动。
/// </summary>
public static class PrivateChatRosterRules
{
    /// <summary>名单行高。比群聊邀约卡（92）矮，因为私聊名单可能有几十人。</summary>
    public const int RowHeight = 56;

    /// <summary>列表区上下留白，避免第一行/最后一行贴着凹槽边缘。</summary>
    public const int ListPadding = 8;

    /// <summary>
    /// 整理名单：过滤无效行、按 ID 去重、算出在场与频道、再排序。
    ///
    /// 排序规则（越靠前越「顺手」）：
    /// 身边（2.5 格内，按交互键就能续聊的那批）→ 同处一地 → 线上；
    /// 同一档内按距离由近到远，最后按显示名兜底，保证顺序稳定可复现。
    ///
    /// 排序决定的是**列表长什么样**；打开时预选哪一行由
    /// <see cref="DefaultSelectedIndex"/> 决定，两者只有一处会分叉——
    /// 鼠标正指着某位角色时预选会跟着鼠标走（老 F8 的「鼠标指向优先」），
    /// 那时选中行可能不在第一行，这是有意的。
    /// </summary>
    public static IReadOnlyList<PrivateChatRosterEntry> Build(
        IEnumerable<PrivateChatRosterSource>? sources)
    {
        if (sources is null)
        {
            return Array.Empty<PrivateChatRosterEntry>();
        }

        var rows = new List<(PrivateChatRosterEntry Entry, float Distance)>();
        foreach (var source in sources)
        {
            if (source is null)
            {
                continue;
            }

            var npcId = source.NpcId?.Trim();
            var displayName = source.DisplayName?.Trim();
            if (string.IsNullOrWhiteSpace(npcId) || string.IsNullOrWhiteSpace(displayName))
            {
                continue;
            }

            if (rows.Any(row =>
                    string.Equals(row.Entry.NpcId, npcId, StringComparison.OrdinalIgnoreCase)))
            {
                continue;
            }

            rows.Add((
                new PrivateChatRosterEntry(
                    npcId,
                    displayName,
                    source.IsPresent,
                    IsNearby(source.IsPresent, source.DistanceInTiles),
                    ResolveChannel(source.IsPresent),
                    source.DistanceInTiles,
                    source.IsInteractionTarget),
                SortDistance(source.DistanceInTiles)));
        }

        return rows
            .OrderByDescending(row => row.Entry.IsNearby)
            .ThenByDescending(row => row.Entry.IsPresent)
            .ThenBy(row => row.Distance)
            .ThenBy(row => row.Entry.DisplayName, StringComparer.OrdinalIgnoreCase)
            .ThenBy(row => row.Entry.NpcId, StringComparer.OrdinalIgnoreCase)
            .Select(row => row.Entry)
            .ToArray();
    }

    /// <summary>
    /// 要不要把名单摆出来让玩家挑。
    ///
    /// **一个人时不摆**：没有可选项，多按一次回车只是仪式感——玩家在镇上认识第一个人
    /// 之后按 F8，应当直接进私聊。空名单同样不摆（<c>ModEntry</c> 会提示「还没有认识的
    /// 角色」，而不是弹一个空列表出来让人对着发呆）。
    /// </summary>
    public static bool ShouldShowRoster(int entryCount)
    {
        if (entryCount < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(entryCount));
        }

        return entryCount > 1;
    }

    /// <summary>
    /// 名单打开时**预选**哪一行：沿用 F8 改前的自动选人规则
    /// （<see cref="NpcTargetResolver.SelectFriendshipTarget"/> —— 鼠标指向优先，
    /// 否则当前地点里距离最近，再按名字序），只是把它从「替你决定」降级成「替你预选」，
    /// 玩家仍能上下键改。规则本身**没有第二份实现**：改口径只改那一处。
    ///
    /// 候选都来自 <see cref="KnownNpcResolver"/>，即**都已经有好感度记录**，
    /// 所以那条记录过滤在这里恒成立；不在当前地点的行由规则自己排除。
    /// 当前地点一个人都挑不出来时返回 0 —— 名单已按「身边 → 同处一地 → 线上」排序，
    /// 第 0 行就是最顺手的那位线上角色。
    /// </summary>
    public static int DefaultSelectedIndex(IReadOnlyList<PrivateChatRosterEntry>? entries)
    {
        if (entries is null || entries.Count == 0)
        {
            return 0;
        }

        var selected = NpcTargetResolver.SelectFriendshipTarget(
            entries.Select(entry => new NpcTargetCandidate(
                NpcId: entry.NpcId,
                HasFriendshipRecord: true,
                IsInCurrentLocation: entry.IsPresent,
                Distance: entry.DistanceInTiles,
                IsInteractionTarget: entry.IsInteractionTarget)));

        if (selected is null)
        {
            return 0;
        }

        for (var index = 0; index < entries.Count; index++)
        {
            if (string.Equals(entries[index].NpcId, selected.NpcId, StringComparison.OrdinalIgnoreCase))
            {
                return index;
            }
        }

        return 0;
    }

    /// <summary>
    /// 上下键／滚轮移动选中行：夹在名单两端，**不循环**——名单可能有几十人，
    /// 到头绕回另一头会让「一直按住下键」突然跳回顶部，是误操作来源。
    /// </summary>
    public static int MoveSelection(int selectedIndex, int delta, int totalCount)
    {
        if (totalCount < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(totalCount));
        }

        if (totalCount == 0)
        {
            return 0;
        }

        var target = (long)selectedIndex + delta;
        return (int)Math.Clamp(target, 0L, totalCount - 1L);
    }

    /// <summary>
    /// 能不能走「面对面」：**判据是在不在同一地点，不是距离**。
    ///
    /// 频道的语义差别在于「能不能看见对方」：Bridge 侧 <c>remote</c> 的指令是
    /// 「只表达当前想法或提出待确认安排，**不写成已经见面**」，而 <c>face_to_face</c>
    /// 允许回应当面反应。同处一地的角色玩家随时能走到跟前，所以算见面；
    /// 不同地点只能是线上。
    ///
    /// 距离只影响排序与「身边」标记，不参与这条判定——否则站在屋子另一头
    /// 就会莫名其妙被降级成线上聊天。
    /// </summary>
    public static string ResolveChannel(bool isPresent)
    {
        return isPresent ? ConversationChannel.FaceToFace : ConversationChannel.Remote;
    }

    /// <summary>
    /// 「身边」= 玩家按一下交互键就能续聊的那个范围，
    /// 与面对面续聊共用 <see cref="FaceToFaceStateRules.RepeatChatNearbyDistanceInTiles"/>，
    /// 不另立一套距离标准。距离取不到（NaN／无穷／负数）时一律不算身边。
    /// </summary>
    public static bool IsNearby(bool isPresent, float distanceInTiles)
    {
        return isPresent &&
            !float.IsNaN(distanceInTiles) &&
            !float.IsInfinity(distanceInTiles) &&
            distanceInTiles >= 0f &&
            distanceInTiles <= FaceToFaceStateRules.RepeatChatNearbyDistanceInTiles;
    }

    /// <summary>列表区能放下几行（至少一行，免得高度算错时整个列表消失）。</summary>
    public static int VisibleCapacity(int listHeight)
    {
        var usable = listHeight - (ListPadding * 2);
        return Math.Max(1, usable / RowHeight);
    }

    /// <summary>能滚到的最靠后的起始行；装得下时为 0（也就是不滚）。</summary>
    public static int MaxStartIndex(int totalCount, int visibleCapacity)
    {
        if (totalCount < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(totalCount));
        }

        if (visibleCapacity <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(visibleCapacity));
        }

        return Math.Max(0, totalCount - visibleCapacity);
    }

    /// <summary>
    /// 当前该画哪一段：起始行先按 <see cref="ChatScrollRules"/> 夹进合法区间
    /// （滚动规则沿用聊天窗那一份，不再写第二套），再切出这一屏。
    /// </summary>
    public static IReadOnlyList<PrivateChatRosterEntry> VisibleEntries(
        IReadOnlyList<PrivateChatRosterEntry>? entries,
        int startIndex,
        int visibleCapacity)
    {
        // 先校验参数再看列表：容量非法是调用方的 bug，不该因为「恰好列表是空的」
        // 就被静默吞掉——与 MaxStartIndex 的 fail-fast 保持一致。
        if (visibleCapacity <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(visibleCapacity));
        }

        if (entries is null || entries.Count == 0)
        {
            return Array.Empty<PrivateChatRosterEntry>();
        }

        var start = ChatScrollRules.ClampStartIndex(
            startIndex,
            MaxStartIndex(entries.Count, visibleCapacity));
        var count = Math.Min(visibleCapacity, entries.Count - start);
        var visible = new PrivateChatRosterEntry[count];
        for (var index = 0; index < count; index++)
        {
            visible[index] = entries[start + index];
        }

        return visible;
    }

    /// <summary>把某一行滚进可视区（键盘上下键 / 点到列表外的行时用）。</summary>
    public static int ScrollTo(int startIndex, int rowIndex, int totalCount, int visibleCapacity)
    {
        var maxStart = MaxStartIndex(totalCount, visibleCapacity);
        var start = ChatScrollRules.ClampStartIndex(startIndex, maxStart);
        if (rowIndex < start)
        {
            return ChatScrollRules.ClampStartIndex(rowIndex, maxStart);
        }

        var lastVisible = start + visibleCapacity - 1;
        return rowIndex > lastVisible
            ? ChatScrollRules.ClampStartIndex(rowIndex - visibleCapacity + 1, maxStart)
            : start;
    }

    /// <summary>
    /// 排序用的距离：取不到距离的行一律排到最后，而不是当成 0 排到最前
    /// （否则一个「不知道在哪」的角色会插到身边的人前面）。
    /// </summary>
    private static float SortDistance(float distanceInTiles)
    {
        return float.IsNaN(distanceInTiles) ||
            float.IsInfinity(distanceInTiles) ||
            distanceInTiles < 0f
            ? float.MaxValue
            : distanceInTiles;
    }
}
