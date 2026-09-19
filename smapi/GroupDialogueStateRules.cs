namespace StardewAI.NPC;

public static class GroupDialogueStateRules
{
    public static NpcGameState? ResolveActiveSpeakerState(
        IReadOnlyList<GroupDialogueParticipant> participants,
        Func<string, NpcGameState?> resolveState)
    {
        ArgumentNullException.ThrowIfNull(participants);
        ArgumentNullException.ThrowIfNull(resolveState);

        var activeSpeakerNpcId = participants.FirstOrDefault()?.NpcId?.Trim();
        return string.IsNullOrWhiteSpace(activeSpeakerNpcId)
            ? null
            : resolveState(activeSpeakerNpcId);
    }

    /// <summary>
    /// 为每个参与者解析各自的状态。群聊里非发言人同样需要正确的阶段与好感，
    /// 解析不到时该项保持 null，不用别人的状态顶替。
    /// </summary>
    public static IReadOnlyList<GroupDialogueParticipant> ResolveParticipantStates(
        IReadOnlyList<GroupDialogueParticipant> participants,
        Func<string, NpcGameState?> resolveState)
    {
        ArgumentNullException.ThrowIfNull(participants);
        ArgumentNullException.ThrowIfNull(resolveState);

        var resolved = new List<GroupDialogueParticipant>(participants.Count);
        foreach (var participant in participants)
        {
            var npcId = participant.NpcId?.Trim();
            var state = string.IsNullOrWhiteSpace(npcId) ? null : resolveState(npcId);
            resolved.Add(state is null ? participant : participant with { GameState = state });
        }

        return resolved;
    }
}
