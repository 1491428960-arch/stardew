namespace StardewAI.NPC;

public sealed record GroupDialogueSession(
    GroupDialogueInvitationRecord Invitation,
    IReadOnlyList<GroupDialogueHistoryEntry> PublicHistory,
    bool CanRetry);

public static class GroupDialogueSessionRules
{
    /// <summary>
    /// 开一场群聊会话。
    ///
    /// <paramref name="restoredLines"/> 是**存档里那一场的发言序列**（F9 续读，2026-09-21）：
    /// 关掉菜单再进来时，发给模型的公开历史与面板上的气泡都从这里接回来，不再是一片空白。
    ///
    /// 传进来的整串（玩家与 NPC 都在）**整串进** <see cref="GroupDialogueSession.PublicHistory"/>：
    /// 请求历史与场次记录现在是同一串发言（2026-09-22 改，理由见
    /// <see cref="GroupSessionRules.ToRequestHistory"/>）。面板与请求读的是两个不同容器
    /// （面板读 <c>GroupDialogueMenu.visibleMessages</c>），所以玩家那句**只画一次**。
    /// </summary>
    public static GroupDialogueSession Create(
        GroupDialogueInvitationRecord invitation,
        IReadOnlyList<GroupDialogueHistoryEntry>? restoredLines = null)
    {
        ArgumentNullException.ThrowIfNull(invitation);
        return new GroupDialogueSession(
            invitation with { Status = GroupInvitationStatus.Accepted },
            GroupSessionRules.ToRequestHistory(restoredLines),
            CanRetry: false);
    }

    public static GroupDialogueInvitationRecord ApplyResult(
        GroupDialogueInvitationRecord invitation,
        IReadOnlyList<BridgeGroupTurn> turns,
        bool fallback)
    {
        ArgumentNullException.ThrowIfNull(invitation);
        var usable = !fallback && HasUsableTurns(invitation, turns);
        return GroupInvitationRules.AfterConversationResult(invitation, usable);
    }

    /// <summary>
    /// 这一轮的结果并进会话历史。
    ///
    /// <paramref name="playerMessage"/> 是**玩家这一轮真正说出口的那一句**
    /// （开场那一轮玩家没说话，传 null／空即可，不会留下空的玩家行）。
    ///
    /// 玩家行与 NPC 回合一起经由 <see cref="GroupSessionRules.AppendTurn"/> 落进历史 ——
    /// F9 画面、存档场次、请求历史三处由同一个函数产出，玩家那句因此不会再只存在于其中两处
    /// （2026-09-22 修：改前这里只追加 <paramref name="turns"/>，玩家那句**从不进请求历史**，
    /// 于是模型看不到玩家参与过这场对话；理由与实测见
    /// <see cref="GroupSessionRules.ToRequestHistory"/>）。
    ///
    /// 失败轮（fallback／有名单外发言人）一条都不写，**玩家那句也不写**：
    /// 与面板撤回自己那句话、存档不建场次是同一条判据
    /// （见 <see cref="GroupSessionRules.Append"/>）。
    /// </summary>
    public static GroupDialogueSession ApplyResult(
        GroupDialogueSession session,
        string? playerMessage,
        IReadOnlyList<BridgeGroupTurn> turns,
        bool fallback)
    {
        ArgumentNullException.ThrowIfNull(session);
        var participantIds = session.Invitation.Participants
            .Where(id => !string.IsNullOrWhiteSpace(id))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        // 目标归一化用：把模型写的任意大小写映射回名单里的规范写法，
        // 避免同一个人以 "Emily" 与 "emily" 两种写法重复出现在同一条历史里。
        var canonicalIdByKey = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var id in session.Invitation.Participants)
        {
            if (!string.IsNullOrWhiteSpace(id))
            {
                canonicalIdByKey.TryAdd(id.Trim(), id.Trim());
            }
        }

        var candidateTurns = turns ?? Array.Empty<BridgeGroupTurn>();
        var validTurns = !fallback &&
                         candidateTurns.Count > 0 &&
                         candidateTurns.All(turn => IsValidTurn(turn, participantIds));
        if (!validTurns)
        {
            return session with
            {
                Invitation = session.Invitation with { Status = GroupInvitationStatus.Accepted },
                CanRetry = true,
            };
        }

        // 「拼接」整个交给 GroupSessionRules.AppendTurn（玩家行 + 回合，裁剪与上限都在那边），
        // 这里只做它做不到的一件事：addressedTo 的名单归一化 —— 只有这一层拿得到在场名单。
        // 归一化必须在交给 AppendTurn **之前**做，否则名单外的目标会随历史进请求体
        // （AppendTurn 只做 trim 与去重，不认识名单）。
        var normalizedTurns = candidateTurns
            .Select(turn => new BridgeGroupTurn
            {
                SpeakerNpcId = turn.SpeakerNpcId.Trim(),
                Content = turn.Content.Trim(),
                AddressedTo = (turn.AddressedTo ?? Array.Empty<string>())
                    .Select(id => id?.Trim() ?? string.Empty)
                    .Where(id => canonicalIdByKey.ContainsKey(id))
                    .Select(id => canonicalIdByKey[id])
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .Take(GroupInvitationRules.MaxParticipants)
                    .ToArray(),
            })
            .ToArray();
        return session with
        {
            Invitation = session.Invitation with { Status = GroupInvitationStatus.Completed },
            PublicHistory = GroupSessionRules.AppendTurn(
                session.PublicHistory,
                playerMessage,
                normalizedTurns),
            CanRetry = false,
        };
    }

    /// <summary>
    /// 刚开一场群聊（还没有任何公开历史）时，应当由 NPC 先起头。
    ///
    /// 玩家接受邀约后一句话都没说，若仍要求玩家先开口，邀约就起不到引导作用
    /// （2026-09-20 用户反馈）。Bridge 侧已支持「空玩家消息 ⇒ 开场」的语义。
    ///
    /// <paramref name="openingAlreadyRequested"/> 由调用方持有，用于保证整场只自动开场一次；
    /// <see cref="GroupDialogueSession.CanRetry"/> 为真表示上一次请求失败过，
    /// 此时**不能**再自动发——否则会变成无限重试，把重试交给玩家。
    /// </summary>
    public static bool ShouldOpenWithNpc(
        GroupDialogueSession session,
        bool openingAlreadyRequested)
    {
        ArgumentNullException.ThrowIfNull(session);
        return !openingAlreadyRequested
               && !session.CanRetry
               && session.PublicHistory.Count == 0;
    }

    public static bool IsValidTurn(
        BridgeGroupTurn? turn,
        IReadOnlySet<string> participantIds)
    {
        return turn is not null &&
               participantIds is not null &&
               !string.IsNullOrWhiteSpace(turn.SpeakerNpcId) &&
               participantIds.Contains(turn.SpeakerNpcId.Trim()) &&
               !string.IsNullOrWhiteSpace(turn.Content);
    }

    private static bool HasUsableTurns(
        GroupDialogueInvitationRecord invitation,
        IReadOnlyList<BridgeGroupTurn>? turns)
    {
        if (turns is null || turns.Count == 0)
        {
            return false;
        }

        var participantIds = invitation.Participants.ToHashSet(StringComparer.OrdinalIgnoreCase);
        return turns.All(turn => IsValidTurn(turn, participantIds));
    }
}
