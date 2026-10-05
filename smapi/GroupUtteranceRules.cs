namespace StardewAI.NPC;

/// <summary>群聊里某个 NPC 说的一句话。</summary>
public sealed record GroupUtterance(string SpeakerNpcId, string Content);

/// <summary>一条待写入的隐性知识：某位在场者记住的「别人说过什么」。</summary>
public sealed record GroupUtteranceKnowledge(
    string OwnerNpcId,
    string Content,
    MemorySource Source,
    MemoryKnowledgeScope KnowledgeScope,
    IReadOnlyList<string> KnownBy,
    IReadOnlyList<string> Participants);

/// <summary>
/// 群聊里**别的 NPC**说的话 → 隐性知识（2026-10-04）。
///
/// 用户口径：
/// - 「群聊记忆中别的 npc 说了什么能不能作为一个隐性的知识库这样的形式，
///    我不主动提到就不唤醒」
/// - 「我想的『有机连结』大概就是有一个感觉上是连续的 NPC 的人格，
///    他不会因为在 F8 还是 F9 中出现导致不像同一个人」
///
/// 与 <see cref="GroupMemoryRules"/> 的分工：
/// - <see cref="GroupMemoryRules"/>：**玩家**说的话（Bridge 挑出的高亮），
///   在场每人各记一条**同一句**。
/// - 本类：**NPC 之间**说的话，每位在场者记住**别人**说的，
///   自己说的不记（她自己的发言走发送窗口，见 <c>BridgeClient.RememberGroupTurn</c>，
///   第一人称；在这里再记一份会变成「听说我自己说过」的荒唐转述）。
///
/// 纯函数，生产路径与离线验证共用，避免两处各写一份。
/// </summary>
public static class GroupUtteranceRules
{
    /// <summary>每位在场者单次场次最多记住几条别人的发言。</summary>
    /// <remarks>
    /// 上限存在的理由：群聊攒久了隐性知识会线性增长，最终挤占 prompt。
    /// 与「闲聊进不进记忆」无关——这里只保证**量的可控**。
    /// </remarks>
    public const int MaxPerNpc = 6;

    /// <summary>单条隐性知识正文的长度上限（与长期记忆同一口径）。</summary>
    public const int MaxTextLength = MemoryRules.MaxTextLength;

    public static IReadOnlyList<GroupUtteranceKnowledge> Plan(
        IEnumerable<string>? participantNpcIds,
        IEnumerable<GroupUtterance>? utterances)
    {
        if (participantNpcIds is null || utterances is null)
        {
            return Array.Empty<GroupUtteranceKnowledge>();
        }

        var participants = Normalize(participantNpcIds);
        // 单人群聊不存在；没有「别的 NPC」也就无所谓隐性知识。
        if (participants.Length < 2)
        {
            return Array.Empty<GroupUtteranceKnowledge>();
        }

        var wanted = new HashSet<string>(participants, StringComparer.OrdinalIgnoreCase);
        var writes = new List<GroupUtteranceKnowledge>();
        // 每位在场者各自去重，避免同一句话因说话人多次开口而重复占额度。
        var seenByOwner = new Dictionary<string, HashSet<string>>(StringComparer.OrdinalIgnoreCase);

        foreach (var owner in participants)
        {
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            seenByOwner[owner] = seen;
            var count = 0;

            foreach (var utterance in utterances)
            {
                if (count >= MaxPerNpc)
                {
                    break;
                }

                var speaker = utterance.SpeakerNpcId?.Trim();
                if (string.IsNullOrWhiteSpace(speaker) || !wanted.Contains(speaker))
                {
                    // 伪造/串味的发言（说话人不在场）整条丢弃，不产生
                    // 「她记得一个当时不在场的人说过的话」这种不可能的知识。
                    continue;
                }

                // 自己说的不记——那是发送窗口的事。
                if (string.Equals(speaker, owner, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                var content = utterance.Content?.Trim();
                if (string.IsNullOrWhiteSpace(content))
                {
                    continue;
                }

                var line = $"{memorySpeakerLabel(speaker)}：{MemoryRules.Truncate(content, MaxTextLength)}";
                if (!seen.Add(line))
                {
                    continue;
                }

                writes.Add(new GroupUtteranceKnowledge(
                    OwnerNpcId: owner,
                    Content: line,
                    Source: MemorySource.NpcNpcEvent,
                    KnowledgeScope: MemoryKnowledgeScope.Participants,
                    KnownBy: participants,
                    Participants: participants));
                count++;
            }
        }

        return writes;
    }

    private static string memorySpeakerLabel(string speaker) => $"听说 {speaker} 说";

    private static string[] Normalize(IEnumerable<string> values)
    {
        return values
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }
}