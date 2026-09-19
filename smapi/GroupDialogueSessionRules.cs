namespace StardewAI.NPC;

public sealed record GroupDialogueSession(
    GroupDialogueInvitationRecord Invitation,
    IReadOnlyList<GroupDialogueHistoryEntry> PublicHistory,
    bool CanRetry);

public static class GroupDialogueSessionRules
{
    public static GroupDialogueSession Create(GroupDialogueInvitationRecord invitation)
    {
        ArgumentNullException.ThrowIfNull(invitation);
        return new GroupDialogueSession(
            invitation with { Status = GroupInvitationStatus.Accepted },
            Array.Empty<GroupDialogueHistoryEntry>(),
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
