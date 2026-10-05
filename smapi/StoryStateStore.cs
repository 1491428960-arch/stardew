using System.Text.Json.Serialization;

namespace StardewAI.NPC;

public sealed record RelationshipWorldSnapshot(
    [property: JsonIgnore] string ViewerNpcId,
    [property: JsonPropertyName("objectiveRelationships")] IReadOnlyList<RelationshipEdgeRecord> ObjectiveRelationships,
    [property: JsonPropertyName("views")] IReadOnlyList<RelationshipViewRecord> Views,
    [property: JsonPropertyName("mediation")] RelationshipMediationRecord? Mediation,
    [property: JsonPropertyName("jealousy")] RelationshipJealousyRecord? Jealousy)
{
    [JsonPropertyName("openLoops")]
    public IReadOnlyList<OpenLoopRecord> OpenLoops { get; init; } = Array.Empty<OpenLoopRecord>();
}

/// <summary>
/// 保存当前存档对应的故事状态；不直接修改 Stardew Valley 的原版状态。
/// </summary>
public sealed class StoryStateStore
{
    public StoryStateEnvelope State { get; private set; } = StoryStateEnvelope.Empty;

    public IReadOnlyList<string> LastWarnings { get; private set; } = Array.Empty<string>();

    public void Load(string? json)
    {
        var result = StoryStateSerializer.Load(json);
        State = result.State;
        LastWarnings = result.Warnings;
    }

    public string Serialize()
    {
        return StoryStateSerializer.Serialize(State);
    }

    public void RecordConversation(
        NpcGameState gameState,
        string playerMessage,
        string npcReply,
        bool usedFallback)
    {
        Replace(ConversationStateRules.RecordConversation(
            State,
            gameState,
            playerMessage,
            npcReply,
            usedFallback));
    }

    /// <summary>
    /// 写入一条长期记忆（例如群聊里挑出的重要事实或约定）。
    /// 与 RecordConversation 的区别是它不绑定一问一答格式，只承载一句简短陈述；
    /// 按 MemoryId 去重，并维持与单聊记忆相同的总量/单条长度上限——
    /// 两者都取自 <see cref="MemoryRules"/>，不再各写一份常量。
    /// </summary>
    public void RecordMemoryHighlight(string npcId, string content, string gameDate)
    {
        // 记忆记录要求 gameDate 非空；拿不到日期就别写，避免留下无效记录让 Serialize 抛异常。
        if (string.IsNullOrWhiteSpace(npcId) ||
            string.IsNullOrWhiteSpace(content) ||
            string.IsNullOrWhiteSpace(gameDate))
        {
            return;
        }

        var owner = npcId.Trim();
        var trimmed = content.Trim();
        var memory = new MemoryRecord
        {
            MemoryId = BuildGroupMemoryId(owner, trimmed),
            OwnerNpcId = owner,
            Kind = "fact",
            Content = MemoryRules.Truncate(trimmed, MemoryRules.MaxTextLength),
            Source = MemorySource.PlayerChat,
            Confidence = 0.75,
            GameDate = gameDate.Trim(),
            Participants = new[] { owner, "player" },
            KnowledgeScope = MemoryKnowledgeScope.Participants,
            KnownBy = new[] { owner, "player" },
            Importance = 1,
            Canonical = false,
            Status = MemoryStatus.Active,
            Evidence = "bridge-group-dialogue",
        };

        var memories = State.Memories.ToList();
        if (memories.Any(item => string.Equals(item.MemoryId, memory.MemoryId, StringComparison.Ordinal)))
        {
            return;
        }

        memories.Add(memory);
        if (memories.Count > MemoryRules.MaxCount)
        {
            memories = memories.TakeLast(MemoryRules.MaxCount).ToList();
        }

        Replace(State with { Memories = memories });
    }

    public IReadOnlyList<string> RecentMemoryFacts(string npcId, int limit = 6)
    {
        if (string.IsNullOrWhiteSpace(npcId) || limit <= 0)
        {
            return Array.Empty<string>();
        }

        var cappedLimit = Math.Min(limit, 8);
        return State.Memories
            .Reverse()
            .Where(memory =>
                IsLatentKnowledge(memory) == false &&
                string.Equals(memory.OwnerNpcId, npcId, StringComparison.OrdinalIgnoreCase) &&
                !string.IsNullOrWhiteSpace(memory.Content))
            .Take(cappedLimit)
            .Select(memory =>
                string.IsNullOrWhiteSpace(memory.GameDate)
                    ? memory.Content.Trim()
                    : $"记忆（{memory.GameDate.Trim()}）：{memory.Content.Trim()}")
            .ToArray();
    }

    /// <summary>
    /// 该 NPC 的**隐性知识**：她在场听见的、**别人**说过的话（2026-10-04）。
    ///
    /// 需求原话：「群聊记忆中别的 npc 说了什么能不能作为一个隐性的知识库这样的形式，
    /// **我不主动提到就不唤醒**」。
    ///
    /// ⚠ 与 <see cref="RecentMemoryFacts"/> 是**互斥的两条路**，不是包含关系：
    /// 隐性知识若同时进 `recent_memory`，那张卡的「把记忆自然用起来」指令会让模型
    /// 主动提起，与需求正好相反。项目实测过 **「取最宽」** —— 同类约束有多个实例时
    /// 跟最松的那个，所以两个通道都送等于约束失效。
    ///
    /// ⚠ 不带 `记忆（日期）：` 抬头：那是普通记忆的口径。隐性知识卡有自己的结构与
    /// 指令，套同一层抬头会让模型把两者当成同一类东西。
    ///
    /// 条数封顶避免群聊攒久了线性增长挤占 prompt。
    /// </summary>
    public IReadOnlyList<string> LatentKnowledge(string npcId, int limit = 12)
    {
        if (string.IsNullOrWhiteSpace(npcId) || limit <= 0)
        {
            return Array.Empty<string>();
        }

        var cappedLimit = Math.Min(limit, 12);
        return State.Memories
            .Reverse()
            .Where(memory =>
                IsLatentKnowledge(memory) &&
                string.Equals(memory.OwnerNpcId, npcId, StringComparison.OrdinalIgnoreCase) &&
                !string.IsNullOrWhiteSpace(memory.Content))
            .Take(cappedLimit)
            .Select(memory => memory.Content.Trim())
            .ToArray();
    }

    /// <summary>
    /// 这条记忆是不是「隐性知识」——判据只有一个：来源是 NPC 之间
    /// （<see cref="MemorySource.NpcNpcEvent"/>）。
    ///
    /// 用 `Source` 而不是 `KnowledgeScope` 判定：`Participants` 这个范围
    /// **玩家说的话也用**（见 <see cref="RecordMemoryHighlight"/>），拿范围当判据
    /// 会把玩家的话错分到隐性知识里去。
    /// </summary>
    private static bool IsLatentKnowledge(MemoryRecord memory)
    {
        return memory.Source == MemorySource.NpcNpcEvent &&
               memory.Status == MemoryStatus.Active;
    }

    public void Replace(StoryStateEnvelope state)
    {
        ArgumentNullException.ThrowIfNull(state);
        _ = StoryStateSerializer.Serialize(state);
        State = state;
        LastWarnings = Array.Empty<string>();
    }

    public bool TrySetGroupInvitationStatus(
        string invitationId,
        GroupInvitationStatus status)
    {
        if (string.IsNullOrWhiteSpace(invitationId) ||
            !GroupInvitationRules.IsValidStatus(status))
        {
            return false;
        }

        var normalizedId = invitationId.Trim();
        var found = false;
        var invitations = State.GroupDialogueInvitations
            .Select(invitation =>
            {
                if (!string.Equals(invitation.InvitationId, normalizedId, StringComparison.Ordinal))
                {
                    return invitation;
                }

                found = true;
                return invitation with { Status = status };
            })
            .ToArray();
        if (!found)
        {
            return false;
        }

        Replace(State with { GroupDialogueInvitations = invitations });
        return true;
    }

    public RelationshipWorldSnapshot RelationshipSnapshotFor(string npcId)
    {
        var viewerNpcId = npcId?.Trim() ?? string.Empty;
        if (viewerNpcId.Length == 0)
        {
            return new RelationshipWorldSnapshot(
                viewerNpcId,
                Array.Empty<RelationshipEdgeRecord>(),
                Array.Empty<RelationshipViewRecord>(),
                null,
                null);
        }

        var objectiveRelationships = State.Relationships
            .Where(relationship =>
                string.Equals(relationship.FromNpcId, "player", StringComparison.OrdinalIgnoreCase) &&
                string.Equals(relationship.ToNpcId, viewerNpcId, StringComparison.OrdinalIgnoreCase))
            .ToArray();

        var views = State.RelationshipViews
            .Where(view => string.Equals(view.OwnerNpcId, viewerNpcId, StringComparison.OrdinalIgnoreCase))
            .ToList();

        foreach (var relationship in State.Relationships.Where(relationship =>
                     string.Equals(relationship.FromNpcId, "player", StringComparison.OrdinalIgnoreCase) &&
                     string.Equals(relationship.RelationType, "married", StringComparison.Ordinal) &&
                     !string.IsNullOrWhiteSpace(relationship.PublicEventId) &&
                     !string.IsNullOrWhiteSpace(relationship.ToNpcId)))
        {
            var publicView = new RelationshipViewRecord
            {
                OwnerNpcId = viewerNpcId,
                SubjectNpcId = relationship.ToNpcId,
                // 2026-10-04：婚姻的另一端必须一起投出去。原先这里只写 SubjectNpcId，
                // 于是「X 已婚」是一句没有宾语的话 —— 配偶的亲属（如 Olivia 的儿子
                // Victor）读到它，最多推出「我妈妈结婚了」，推不出新郎就是玩家。
                // 用 relationship.FromNpcId 而不是硬写 "player"：这个循环本身已经
                // 按 FromNpcId=="player" 过滤，取字段值可以让「将来支持 NPC↔NPC
                // 婚姻」时这里不用再改一次。
                CounterpartNpcId = relationship.FromNpcId,
                RelationType = "married",
                Visibility = "known",
                Source = "wedding",
                ObservedOn = relationship.PublicOn,
                Evidence = relationship.PublicEventId,
            };
            var existingIndex = views.FindIndex(view =>
                string.Equals(view.SubjectNpcId, relationship.ToNpcId, StringComparison.OrdinalIgnoreCase));
            if (existingIndex >= 0)
            {
                views[existingIndex] = publicView;
            }
            else
            {
                views.Add(publicView);
            }
        }

        return new RelationshipWorldSnapshot(
            viewerNpcId,
            objectiveRelationships,
            views,
            State.Mediations.FirstOrDefault(mediation =>
                string.Equals(mediation.NpcId, viewerNpcId, StringComparison.OrdinalIgnoreCase)),
            State.Jealousies.FirstOrDefault(jealousy =>
                string.Equals(jealousy.NpcId, viewerNpcId, StringComparison.OrdinalIgnoreCase)))
        {
            OpenLoops = State.OpenLoops
                .Where(openLoop =>
                    string.Equals(openLoop.NpcId, viewerNpcId, StringComparison.OrdinalIgnoreCase) &&
                    (openLoop.Status == "open" || openLoop.Status == "in_progress"))
                .ToArray(),
        };
    }

    public void ApplyOpenLoopSignal(
        NpcGameState gameState,
        string channel,
        OpenLoopSignal signal)
    {
        ArgumentNullException.ThrowIfNull(gameState);
        ArgumentNullException.ThrowIfNull(signal);

        var npcId = RequireText(gameState.NpcId, nameof(gameState.NpcId));
        var loopId = signal.LoopId?.Trim() ?? string.Empty;
        var action = signal.Action?.Trim() ?? string.Empty;
        if (loopId.Length == 0)
        {
            return;
        }

        var existing = State.OpenLoops.FirstOrDefault(openLoop =>
            string.Equals(openLoop.LoopId, loopId, StringComparison.Ordinal));
        if (existing is not null &&
            !string.Equals(existing.NpcId, npcId, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        if (string.Equals(channel, ConversationChannel.Remote, StringComparison.Ordinal) &&
            string.Equals(action, "open", StringComparison.Ordinal))
        {
            if (existing is not null && (existing.Status == "resolved" || existing.Status == "cancelled"))
            {
                return;
            }

            var topic = signal.Topic?.Trim() ?? string.Empty;
            var shortSummary = signal.ShortSummary?.Trim() ?? string.Empty;
            if (topic.Length == 0 || shortSummary.Length == 0)
            {
                return;
            }

            var openLoop = existing is null
                ? new OpenLoopRecord
                {
                    LoopId = loopId,
                    NpcId = npcId,
                    Topic = topic,
                    OriginChannel = ConversationChannel.Remote,
                    NextChannel = ConversationChannel.FaceToFace,
                    Status = "open",
                    ShortSummary = shortSummary,
                    CreatedOn = RequireText(gameState.Date, nameof(gameState.Date)),
                }
                : existing with
                {
                    Topic = topic,
                    ShortSummary = shortSummary,
                };
            var openLoops = State.OpenLoops
                .Where(openLoop => !ReferenceEquals(openLoop, existing))
                .Append(openLoop)
                .ToArray();
            Replace(State with { OpenLoops = openLoops });
            return;
        }

        if (string.Equals(channel, ConversationChannel.FaceToFace, StringComparison.Ordinal) &&
            (string.Equals(action, "continue", StringComparison.Ordinal) ||
             string.Equals(action, "resolve", StringComparison.Ordinal)) &&
            existing is not null &&
            (existing.Status == "open" || existing.Status == "in_progress"))
        {
            var updatedStatus = string.Equals(action, "resolve", StringComparison.Ordinal)
                ? "resolved"
                : "in_progress";
            Replace(State with
            {
                OpenLoops = State.OpenLoops
                    .Select(openLoop => ReferenceEquals(openLoop, existing)
                        ? openLoop with { Status = updatedStatus }
                        : openLoop)
                    .ToArray(),
            });
        }
    }

    /// <summary>
    /// 把游戏里现存的婚姻同步成公开关系事实（2026-10-04）。
    ///
    /// **为什么需要它**：复数恋爱与婚姻的那一整套世界观（公开发布 / 逐人视角 / 接受度）
    /// 在 2026-09-05 就建好了，广播通道也是通的——<see cref="RelationshipSnapshotFor"/>
    /// 会把带 <c>PublicEventId</c> 的婚姻播给**所有** NPC 的 <c>known</c> 视角。
    /// 但钥匙从来没被拧过：<c>State.Relationships</c> 在生产代码里一个写入点都没有，
    /// 于是 <see cref="RecordPublicWedding"/> 找不到匹配边就提前 return，
    /// <c>PublicEventId</c> 恒为 null，广播循环永不执行。
    /// 表现就是「两个都跟玩家结了婚的人，互相不知道对方存在」。
    ///
    /// **为什么在这里收口**：调用方只负责回答「现在谁是配偶」，
    /// 边与视图的构造复用 <see cref="RecordPublicWedding"/> 的既有语义，
    /// 不另立第二套广播逻辑——广播由 <see cref="RelationshipSnapshotFor"/> 统一做。
    /// </summary>
    /// <returns>本次新增/补全了多少条关系边；0 表示无事可做。</returns>
    public int SyncMarriages(IReadOnlyList<string>? spouseNpcIds, string gameDate)
    {
        if (spouseNpcIds is null || spouseNpcIds.Count == 0)
        {
            return 0;
        }

        var date = string.IsNullOrWhiteSpace(gameDate) ? "unknown" : gameDate.Trim();
        var wanted = spouseNpcIds
            .Select(id => id?.Trim() ?? string.Empty)
            .Where(id => id.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (wanted.Length == 0)
        {
            return 0;
        }

        var relationships = State.Relationships.ToList();
        var changed = 0;
        foreach (var spouse in wanted)
        {
            var index = relationships.FindIndex(relationship =>
                string.Equals(relationship.FromNpcId, "player", StringComparison.OrdinalIgnoreCase) &&
                string.Equals(relationship.ToNpcId, spouse, StringComparison.OrdinalIgnoreCase) &&
                string.Equals(relationship.RelationType, "married", StringComparison.Ordinal));
            var eventId = $"wedding:{spouse}";

            if (index < 0)
            {
                relationships.Add(new RelationshipEdgeRecord
                {
                    FromNpcId = "player",
                    ToNpcId = spouse,
                    RelationType = "married",
                    Source = "player_spouse",
                    Canonical = true,
                    UpdatedOn = date,
                    StartedOn = date,
                    PublicEventId = eventId,
                    PublicOn = date,
                });
                changed++;
                continue;
            }

            // 已经有边、也已经有公开事件：不动它。婚礼纪念日的【原件】比这次同步更权威。
            if (!string.IsNullOrWhiteSpace(relationships[index].PublicEventId))
            {
                continue;
            }

            relationships[index] = relationships[index] with
            {
                PublicEventId = eventId,
                PublicOn = date,
            };
            changed++;
        }

        if (changed == 0)
        {
            return 0;
        }

        Replace(State with { Relationships = relationships.ToArray() });
        return changed;
    }

    public void RecordPublicWedding(string subjectNpcId, string eventId, string gameDate)
    {
        var subject = RequireText(subjectNpcId, nameof(subjectNpcId));
        var publicEventId = RequireText(eventId, nameof(eventId));
        var publicOn = RequireText(gameDate, nameof(gameDate));
        var matched = false;
        var relationships = State.Relationships
            .Select(relationship =>
            {
                if (!string.Equals(relationship.FromNpcId, "player", StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(relationship.ToNpcId, subject, StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(relationship.RelationType, "married", StringComparison.Ordinal))
                {
                    return relationship;
                }

                matched = true;
                return relationship with
                {
                    PublicEventId = publicEventId,
                    PublicOn = publicOn,
                };
            })
            .ToArray();

        if (!matched)
        {
            return;
        }

        var views = State.RelationshipViews
            .Select(view => string.Equals(view.SubjectNpcId, subject, StringComparison.OrdinalIgnoreCase)
                ? view with
                {
                    RelationType = "married",
                    Visibility = "known",
                    Source = "wedding",
                    ObservedOn = publicOn,
                    Evidence = publicEventId,
                }
                : view)
            .ToArray();
        Replace(State with { Relationships = relationships, RelationshipViews = views });
    }

    public void DiscloseRelationship(string viewerNpcId, string subjectNpcId, string relationType)
    {
        var viewer = RequireText(viewerNpcId, nameof(viewerNpcId));
        var subject = RequireText(subjectNpcId, nameof(subjectNpcId));
        var type = RequireText(relationType, nameof(relationType));
        if (!RelationshipTypeRules.IsSupported(type))
        {
            throw new ArgumentException("关系类型无效。", nameof(relationType));
        }

        if (!State.Relationships.Any(relationship =>
                string.Equals(relationship.FromNpcId, "player", StringComparison.OrdinalIgnoreCase) &&
                string.Equals(relationship.ToNpcId, subject, StringComparison.OrdinalIgnoreCase) &&
                string.Equals(relationship.RelationType, type, StringComparison.Ordinal)))
        {
            return;
        }

        var found = false;
        var views = State.RelationshipViews
            .Select(view =>
            {
                if (!string.Equals(view.OwnerNpcId, viewer, StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(view.SubjectNpcId, subject, StringComparison.OrdinalIgnoreCase))
                {
                    return view;
                }

                found = true;
                return view with
                {
                    RelationType = type,
                    Visibility = "known",
                    Source = "player_statement",
                };
            })
            .ToList();
        if (!found)
        {
            views.Add(new RelationshipViewRecord
            {
                OwnerNpcId = viewer,
                SubjectNpcId = subject,
                RelationType = type,
                Visibility = "known",
                Source = "player_statement",
            });
        }

        Replace(State with { RelationshipViews = views.ToArray() });
    }

    public void ResolveMediation(string npcId, string outcome, string? nextStep = null)
    {
        var id = RequireText(npcId, nameof(npcId));
        var resolvedOutcome = RequireText(outcome, nameof(outcome));
        if (!AcceptanceOutcomes.Contains(resolvedOutcome))
        {
            throw new ArgumentException("调解结果无效。", nameof(outcome));
        }

        // 2026-10-04：not_ready 是「这轮没谈成」，不是结论。
        //
        // 写成 resolved 会让 NPC 永远停在不接受上——玩家没有第二次机会，
        // 而设计文档要求情绪靠后续相处与履约恢复，不是一次性判定。
        // 保留 active，下次对话还能继续谈，直到谈成为止。
        var status = string.Equals(resolvedOutcome, "not_ready", StringComparison.Ordinal)
            ? "active"
            : "resolved";

        var mediation = new RelationshipMediationRecord
        {
            NpcId = id,
            Status = status,
            Outcome = resolvedOutcome,
            NextStep = string.IsNullOrWhiteSpace(nextStep) ? null : nextStep.Trim(),
        };
        var mediations = State.Mediations
            .Where(item => !string.Equals(item.NpcId, id, StringComparison.OrdinalIgnoreCase))
            .Append(mediation)
            .ToArray();
        Replace(State with { Mediations = mediations });
    }

    /// <summary>
    /// 给已经有婚姻关系的 NPC 落一条「接受」调解记录（2026-10-04）。
    ///
    /// **为什么需要**：<c>acceptanceByNpc</c> 在 C# 侧从来没有写入点，Bridge
    /// 里因此恒为 None，压缩卡就不输出 acceptance 键——Prompt 里【完全没有】
    /// 当前 NPC 对这段关系的态度。模型遇到「我跟别人也结了婚」只能自己发挥成
    /// 「歧异 / 需要时间接受」，而存档里她们已经结婚很久了。
    ///
    /// **为什么直接写 accepted，而不是走一遍调解流程**：产品规则是「调解只对
    /// 机制上线时已经存在的那一批角色成立，之后新发生的关系默认已知晓并接受」
    /// ——每个新伴侣都来一遍协商会困扰玩家。而调解的终态必然是接受，所以对
    /// 「已经结婚很久」的局面，直接落终态语义等价，只是把该省的那一次对话省掉。
    ///
    /// **只写一次**：已经有任何调解记录的 NPC 直接跳过，所以反复读档、每天同步
    /// 都不会重复写，也不会覆盖玩家真正谈出来的 conditional / not_ready。
    /// 这也是「首次发现剧情只演一次」的落点。
    /// </summary>
    /// <returns>新写入的记录数；0 表示所有配偶都已有记录。</returns>
    public int EnsureSpouseAcceptance(IReadOnlyList<string>? spouseNpcIds)
    {
        if (spouseNpcIds is null || spouseNpcIds.Count == 0)
        {
            return 0;
        }

        var known = new HashSet<string>(
            State.Mediations.Select(item => item.NpcId),
            StringComparer.OrdinalIgnoreCase);
        var added = new List<RelationshipMediationRecord>();
        foreach (var raw in spouseNpcIds)
        {
            var id = raw?.Trim();
            if (string.IsNullOrEmpty(id) || !known.Add(id))
            {
                continue;
            }

            added.Add(new RelationshipMediationRecord
            {
                NpcId = id,
                Status = "resolved",
                Outcome = "accepted",
            });
        }

        if (added.Count == 0)
        {
            return 0;
        }

        Replace(State with { Mediations = State.Mediations.Concat(added).ToArray() });
        return added.Count;
    }

    public void RecordJealousy(string npcId, string trigger, string intensity, string need)
    {
        var id = RequireText(npcId, nameof(npcId));
        var jealousyTrigger = RequireText(trigger, nameof(trigger));
        var jealousyIntensity = RequireText(intensity, nameof(intensity));
        var jealousyNeed = RequireText(need, nameof(need));
        if (!JealousyTriggers.Contains(jealousyTrigger))
        {
            throw new ArgumentException("嫉妒触发器无效。", nameof(trigger));
        }

        if (!JealousyIntensities.Contains(jealousyIntensity))
        {
            throw new ArgumentException("嫉妒强度无效。", nameof(intensity));
        }

        var previous = State.Jealousies.FirstOrDefault(item =>
            string.Equals(item.NpcId, id, StringComparison.OrdinalIgnoreCase));
        var jealousy = new RelationshipJealousyRecord
        {
            NpcId = id,
            Active = true,
            Trigger = jealousyTrigger,
            Intensity = jealousyIntensity,
            Need = jealousyNeed,
            LastResolvedTrigger = previous?.LastResolvedTrigger,
        };
        var jealousies = State.Jealousies
            .Where(item => !string.Equals(item.NpcId, id, StringComparison.OrdinalIgnoreCase))
            .Append(jealousy)
            .ToArray();
        Replace(State with { Jealousies = jealousies });
    }

    public void RecoverJealousy(string npcId, string responseAction)
    {
        var id = RequireText(npcId, nameof(npcId));
        if (!RecoveryActions.Contains(responseAction))
        {
            return;
        }

        var jealousy = State.Jealousies.FirstOrDefault(item =>
            string.Equals(item.NpcId, id, StringComparison.OrdinalIgnoreCase));
        if (jealousy is null || !jealousy.Active)
        {
            return;
        }

        var recovered = jealousy with
        {
            Active = false,
            Trigger = null,
            Intensity = null,
            Need = null,
            LastResolvedTrigger = jealousy.Trigger,
        };
        var jealousies = State.Jealousies
            .Select(item => string.Equals(item.NpcId, id, StringComparison.OrdinalIgnoreCase)
                ? recovered
                : item)
            .ToArray();
        Replace(State with { Jealousies = jealousies });
    }

    /// <summary>
    /// 每日关系结算（2026-10-04）：按角色【自己的】对话记录触发或解除嫉妒。
    ///
    /// **为什么放 C# 而不是交给模型判**：触发嫉妒需要的全部事实（上次单独说话是
    /// 哪天、有没有拖着没兑现的约定）在存档里都是现成的结构化数据。本地算零成本、
    /// 可单测，也不必把「谁被冷落了」这种推断交给模型去猜。
    ///
    /// **两道闸门，缺一不可**：
    /// ① 没有 <see cref="InteractionProgress.LastCountedGameDate"/> 的角色一律不算——
    ///    没有记录代表「这个维度还没建立」，不等于被冷落。读档时 17 个配偶里只有
    ///    真聊过的那几个有记录，少了这道闸门就会一觉醒来满镇子集体吃醋。
    /// ② 已经在吃醋的角色不叠加——同一时刻只保留一条当前情绪，恢复才有意义。
    ///
    /// **恢复也在这里**：当天确实和 TA 说过话就解除嫉妒。设计文档要求情绪靠「回应、
    /// 解释、履约、后续相处」恢复，而不是把状态强制重置，所以这里只认「真的聊过」。
    /// </summary>
    /// <returns>人类可读的变更说明，供日志与测试使用。</returns>
    public IReadOnlyList<string> SettleDailyJealousy(
        string today,
        IReadOnlyList<InteractionProgress>? progresses,
        IReadOnlyList<string>? spouseNpcIds)
    {
        var changes = new List<string>();
        if (string.IsNullOrWhiteSpace(today) || spouseNpcIds is null || spouseNpcIds.Count == 0)
        {
            return changes;
        }

        var todayIndex = DayIndexOf(today);
        if (todayIndex < 0)
        {
            return changes;
        }

        var byNpc = new Dictionary<string, InteractionProgress>(StringComparer.OrdinalIgnoreCase);
        foreach (var item in progresses ?? Array.Empty<InteractionProgress>())
        {
            if (item is not null && !string.IsNullOrWhiteSpace(item.NpcId))
            {
                byNpc[item.NpcId.Trim()] = item;
            }
        }

        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var raw in spouseNpcIds)
        {
            var id = raw?.Trim();
            if (string.IsNullOrEmpty(id) || !seen.Add(id))
            {
                continue;
            }

            var jealousy = State.Jealousies.FirstOrDefault(item =>
                string.Equals(item.NpcId, id, StringComparison.OrdinalIgnoreCase));
            byNpc.TryGetValue(id, out var recorded);
            var lastSeen = recorded?.LastCountedGameDate;

            // 今天聊过：恢复优先于一切，先解开心结再谈别的。
            if (!string.IsNullOrWhiteSpace(lastSeen) &&
                string.Equals(lastSeen.Trim(), today.Trim(), StringComparison.OrdinalIgnoreCase))
            {
                if (jealousy is { Active: true })
                {
                    RecoverJealousy(id, "offer_time");
                    changes.Add($"恢复:{id}<-{jealousy.Trigger}");
                }

                continue;
            }

            if (jealousy is { Active: true })
            {
                continue;
            }

            if (string.IsNullOrWhiteSpace(lastSeen))
            {
                continue;
            }

            var seenIndex = DayIndexOf(lastSeen);
            if (seenIndex < 0)
            {
                continue;
            }

            // 拖着没兑现的约定比「只是没怎么见面」更具体，优先报这个。
            var stalePromise = State.OpenLoops.FirstOrDefault(loop =>
                loop is not null &&
                string.Equals(loop.NpcId, id, StringComparison.OrdinalIgnoreCase) &&
                string.Equals(loop.Status, "open", StringComparison.Ordinal) &&
                DayIndexOf(loop.CreatedOn) is var createdOn &&
                createdOn >= 0 &&
                todayIndex - createdOn >= BrokenPromiseDays);
            if (stalePromise is not null)
            {
                RecordJealousy(id, "broken_promise", "moderate", "把答应过的事做完");
                changes.Add($"嫉妒:{id}<-broken_promise");
                continue;
            }

            var gap = todayIndex - seenIndex;
            if (gap < 0)
            {
                gap += DaysPerYear;
            }

            var intensity = gap >= CompanionHighDays ? "high"
                : gap >= CompanionModerateDays ? "moderate"
                : gap >= CompanionLightDays ? "light"
                : null;
            if (intensity is null)
            {
                continue;
            }

            RecordJealousy(id, "companionship", intensity, "固定的相处时间");
            changes.Add($"嫉妒:{id}<-companionship/{intensity}({gap}d)");
        }

        return changes;
    }

    /// <summary>一季 28 天，四季 112 天（存档不含年份，跨年按加一轮处理）。</summary>
    private const int DaysPerSeason = 28;

    private const int DaysPerYear = DaysPerSeason * 4;

    /// <summary>约定拖着多久没兑现算失信。</summary>
    private const int BrokenPromiseDays = 7;

    private const int CompanionLightDays = 14;

    private const int CompanionModerateDays = 21;

    private const int CompanionHighDays = 28;

    /// <summary>
    /// 把 "Spring 14" 这样的日期标签换成可作差的绝对天序号。
    /// 无法识别时返回 -1——调用方一律跳过。宁可这次不算，也不能把坏数据
    /// 当成「很久没见面」而凭空制造一场嫉妒。
    /// </summary>
    private static int DayIndexOf(string? dateLabel)
    {
        if (string.IsNullOrWhiteSpace(dateLabel))
        {
            return -1;
        }

        var parts = dateLabel.Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 2)
        {
            return -1;
        }

        var season = parts[0].ToLowerInvariant() switch
        {
            "spring" => 0,
            "summer" => 1,
            "fall" => 2,
            "winter" => 3,
            _ => -1,
        };
        if (season < 0 || !int.TryParse(parts[1], out var day) || day < 1 || day > DaysPerSeason)
        {
            return -1;
        }

        return season * DaysPerSeason + day;
    }

    public void Reset()
    {
        State = StoryStateEnvelope.Empty;
        LastWarnings = Array.Empty<string>();
    }

    private static readonly HashSet<string> AcceptanceOutcomes = new(StringComparer.Ordinal)
    {
        "accepted",
        "conditional",
        "not_ready",
    };

    private static readonly HashSet<string> JealousyTriggers = new(StringComparer.Ordinal)
    {
        "time",
        "companionship",
        "broken_promise",
        "comparison",
        "affection_imbalance",
    };

    private static readonly HashSet<string> JealousyIntensities = new(StringComparer.Ordinal)
    {
        "light",
        "moderate",
        "high",
    };

    private static readonly HashSet<string> RecoveryActions = new(StringComparer.Ordinal)
    {
        "acknowledge_and_explain",
        "keep_promise",
        "offer_time",
        "give_space",
    };

    private static string RequireText(string? value, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("文本不能为空。", parameterName);
        }

        return value.Trim();
    }

    /// <summary>
    /// 群聊长期记忆的稳定 id。前缀与载荷形态与单聊不同（群聊按「所有者 + 一句陈述」去重），
    /// 但哈希构造与位数统一走 <see cref="MemoryRules.BuildId"/>。
    /// </summary>
    private static string BuildGroupMemoryId(string owner, string content)
    {
        var normalizedOwner = owner.ToLowerInvariant();
        return MemoryRules.BuildId(
            kind: "group",
            owner: normalizedOwner,
            payload: $"{normalizedOwner}\n{content}");
    }
}
