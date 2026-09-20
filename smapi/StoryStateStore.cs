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
                string.Equals(memory.OwnerNpcId, npcId, StringComparison.OrdinalIgnoreCase) &&
                !string.IsNullOrWhiteSpace(memory.Content))
            .Take(cappedLimit)
            .Select(memory =>
                string.IsNullOrWhiteSpace(memory.GameDate)
                    ? memory.Content.Trim()
                    : $"记忆（{memory.GameDate.Trim()}）：{memory.Content.Trim()}")
            .ToArray();
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

        var mediation = new RelationshipMediationRecord
        {
            NpcId = id,
            Status = "resolved",
            Outcome = resolvedOutcome,
            NextStep = string.IsNullOrWhiteSpace(nextStep) ? null : nextStep.Trim(),
        };
        var mediations = State.Mediations
            .Where(item => !string.Equals(item.NpcId, id, StringComparison.OrdinalIgnoreCase))
            .Append(mediation)
            .ToArray();
        Replace(State with { Mediations = mediations });
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
