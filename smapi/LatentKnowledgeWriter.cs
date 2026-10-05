namespace StardewAI.NPC;

/// <summary>
/// 把群聊里 NPC 之间的发言写成长期记忆（2026-10-04）。
///
/// 它是 <see cref="GroupUtteranceRules"/>（纯函数，决定「谁该记住什么」）到
/// <see cref="StoryStateStore"/>（真正落盘）之间的那一层。生产路径
/// （<c>GroupDialogueMenu</c>）与离线验证共用，避免两处各写一份。
///
/// 与 <see cref="StoryStateStore.RecordMemoryHighlight"/> 的分工：
/// 那个记**玩家**说的话（同一句复制给在场每个人），本类记 **NPC 之间**说的话
/// （每位在场者记住**别人**说的，自己说的不记）。
/// </summary>
public static class LatentKnowledgeWriter
{
    /// <summary>
    /// 落盘并返回实际写入的条数（0 表示没有可写内容，调用方据此跳过后续动作）。
    ///
    /// `gameDate` 为空时整批不写：<see cref="MemoryRecord.GameDate"/> 要求非空，
    /// 写空日期会让序列化抛异常。与既有 `RecordMemoryHighlight` 同一守则。
    /// </summary>
    public static int Record(
        StoryStateStore store,
        IEnumerable<string>? participantNpcIds,
        IEnumerable<GroupUtterance>? utterances,
        string gameDate)
    {
        ArgumentNullException.ThrowIfNull(store);

        if (string.IsNullOrWhiteSpace(gameDate))
        {
            return 0;
        }

        var writes = GroupUtteranceRules.Plan(participantNpcIds, utterances);
        if (writes.Count == 0)
        {
            return 0;
        }

        var date = gameDate.Trim();
        var memories = store.State.Memories.ToList();
        var existing = new HashSet<string>(
            memories.Select(memory => memory.MemoryId),
            StringComparer.Ordinal);
        var added = 0;

        foreach (var write in writes)
        {
            var memory = new MemoryRecord
            {
                MemoryId = BuildLatentKnowledgeId(write),
                OwnerNpcId = write.OwnerNpcId,
                Kind = "fact",
                Content = write.Content,
                Source = write.Source,
                Confidence = 0.75,
                GameDate = date,
                Participants = write.Participants,
                KnowledgeScope = write.KnowledgeScope,
                KnownBy = write.KnownBy,
                Importance = 1,
                Canonical = false,
                Status = MemoryStatus.Active,
                Evidence = "bridge-group-utterance",
            };

            // 幂等：群聊菜单可能在重试或回顾时再次走到这里。
            if (!existing.Add(memory.MemoryId))
            {
                continue;
            }

            memories.Add(memory);
            added++;
        }

        if (added == 0)
        {
            return 0;
        }

        if (memories.Count > MemoryRules.MaxCount)
        {
            memories = memories.TakeLast(MemoryRules.MaxCount).ToList();
        }

        store.Replace(store.State with { Memories = memories });
        return added;
    }

    /// <summary>
    /// 记忆标识由「归属人 + 内容」决定，因此同一句话重复到达时自然幂等。
    ///
    /// ⚠ 刻意**不含日期**：同一句话跨天重复说，应该还是一条知识，
    /// 而不是每天新增一条把 prompt 撑满。
    /// </summary>
    private static string BuildLatentKnowledgeId(GroupUtteranceKnowledge write)
    {
        var raw = $"latent:{write.OwnerNpcId}:{write.Content}";
        using var sha = System.Security.Cryptography.SHA256.Create();
        var hash = sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(raw));
        return "latent-" + Convert.ToHexString(hash, 0, 12).ToLowerInvariant();
    }
}