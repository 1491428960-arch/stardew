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
    /// 传进来的整串（玩家与 NPC 都在）只有 NPC 那部分进 <see cref="GroupDialogueSession.PublicHistory"/>
    /// —— 请求体里的历史一直只有 NPC 发言，续读不该偷偷改掉发给模型的东西
    /// （见 <see cref="GroupSessionRules.ToPublicHistory"/>）；玩家自己的话由面板照旧显示。
    /// </summary>
    public static GroupDialogueSession Create(
        GroupDialogueInvitationRecord invitation,
        IReadOnlyList<GroupDialogueHistoryEntry>? restoredLines = null)
    {
        ArgumentNullException.ThrowIfNull(invitation);
        return new GroupDialogueSession(
            invitation with { Status = GroupInvitationStatus.Accepted },
            GroupSessionRules.ToPublicHistory(restoredLines),
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

    public static GroupDialogueSession ApplyResult(
        GroupDialogueSession session,
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

        var addedHistory = candidateTurns
            .Select(turn => new GroupDialogueHistoryEntry(
                "npc",
                turn.SpeakerNpcId.Trim(),
                turn.Content.Trim(),
                (turn.AddressedTo ?? Array.Empty<string>())
                    .Select(id => id?.Trim() ?? string.Empty)
                    .Where(id => canonicalIdByKey.ContainsKey(id))
                    .Select(id => canonicalIdByKey[id])
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .Take(GroupInvitationRules.MaxParticipants)
                    .ToArray()))
            .ToArray();
        return session with
        {
            Invitation = session.Invitation with { Status = GroupInvitationStatus.Completed },
            PublicHistory = session.PublicHistory.Concat(addedHistory).ToArray(),
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
