namespace StardewAI.NPC;

public static class StoryStateValidation
{
    private static readonly HashSet<string> VisibilityValues = new(StringComparer.Ordinal)
    {
        "known",
        "suspected",
        "unknown",
    };

    private static readonly HashSet<string> ViewSources = new(StringComparer.Ordinal)
    {
        "none",
        "observation",
        "rumor",
        "direct_question",
        "player_statement",
        "wedding",
    };

    private static readonly HashSet<string> MediationStatuses = new(StringComparer.Ordinal)
    {
        "none",
        "offered",
        "active",
        "resolved",
    };

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

    private static readonly HashSet<string> OpenLoopStatuses = new(StringComparer.Ordinal)
    {
        "open",
        "in_progress",
        "resolved",
        "cancelled",
    };

    public static IReadOnlyList<string> Validate(MemoryRecord? memory)
    {
        var errors = new List<string>();
        if (memory is null)
        {
            errors.Add("memory record is null");
            return errors;
        }

        if (string.IsNullOrWhiteSpace(memory.MemoryId))
        {
            errors.Add("memoryId is required");
        }

        if (string.IsNullOrWhiteSpace(memory.OwnerNpcId))
        {
            errors.Add("ownerNpcId is required");
        }

        if (string.IsNullOrWhiteSpace(memory.Content))
        {
            errors.Add("content is required");
        }

        if (memory.Source is null)
        {
            errors.Add("source is required");
        }

        if (memory.Confidence is null || memory.Confidence is < 0 or > 1)
        {
            errors.Add("confidence must be between 0 and 1");
        }

        if (string.IsNullOrWhiteSpace(memory.GameDate))
        {
            errors.Add("gameDate is required");
        }

        if (memory.Participants is null || memory.Participants.Count == 0 ||
            memory.Participants.Any(string.IsNullOrWhiteSpace))
        {
            errors.Add("participants must contain at least one NPC or player");
        }

        if (memory.KnowledgeScope is null)
        {
            errors.Add("knowledgeScope is required");
        }

        if (memory.Importance is < 0 or > 3)
        {
            errors.Add("importance must be between 0 and 3");
        }

        return errors;
    }

    public static IReadOnlyList<string> Validate(RelationshipViewRecord? view)
    {
        var errors = new List<string>();
        if (view is null)
        {
            errors.Add("relationship view is null");
            return errors;
        }

        if (string.IsNullOrWhiteSpace(view.OwnerNpcId))
        {
            errors.Add("ownerNpcId is required");
        }

        if (string.IsNullOrWhiteSpace(view.SubjectNpcId))
        {
            errors.Add("subjectNpcId is required");
        }

        if (!RelationshipTypeRules.IsSupported(view.RelationType))
        {
            errors.Add("relationType is invalid");
        }

        if (!VisibilityValues.Contains(view.Visibility))
        {
            errors.Add("visibility is invalid");
        }

        if (!ViewSources.Contains(view.Source))
        {
            errors.Add("source is invalid");
        }

        return errors;
    }

    public static IReadOnlyList<string> Validate(RelationshipMediationRecord? mediation)
    {
        var errors = new List<string>();
        if (mediation is null)
        {
            errors.Add("relationship mediation is null");
            return errors;
        }

        if (string.IsNullOrWhiteSpace(mediation.NpcId))
        {
            errors.Add("npcId is required");
        }

        if (!MediationStatuses.Contains(mediation.Status))
        {
            errors.Add("status is invalid");
        }

        if (mediation.Outcome is not null && !AcceptanceOutcomes.Contains(mediation.Outcome))
        {
            errors.Add("outcome is invalid");
        }

        return errors;
    }

    public static IReadOnlyList<string> Validate(RelationshipJealousyRecord? jealousy)
    {
        var errors = new List<string>();
        if (jealousy is null)
        {
            errors.Add("relationship jealousy is null");
            return errors;
        }

        if (string.IsNullOrWhiteSpace(jealousy.NpcId))
        {
            errors.Add("npcId is required");
        }

        if (jealousy.Trigger is not null && !JealousyTriggers.Contains(jealousy.Trigger))
        {
            errors.Add("trigger is invalid");
        }

        if (jealousy.Intensity is not null && !JealousyIntensities.Contains(jealousy.Intensity))
        {
            errors.Add("intensity is invalid");
        }

        return errors;
    }

    public static IReadOnlyList<string> Validate(OpenLoopRecord? openLoop)
    {
        var errors = new List<string>();
        if (openLoop is null)
        {
            errors.Add("open loop is null");
            return errors;
        }

        if (string.IsNullOrWhiteSpace(openLoop.LoopId))
        {
            errors.Add("loopId is required");
        }

        if (string.IsNullOrWhiteSpace(openLoop.NpcId))
        {
            errors.Add("npcId is required");
        }

        if (string.IsNullOrWhiteSpace(openLoop.Topic))
        {
            errors.Add("topic is required");
        }

        // 频道名统一走常量：此前这两处写的是字面量，而同一代码库的
        // ConversationModels.ConversationChannel 已有 Remote/FaceToFace——
        // 改常量值时会静默漏掉字面量（2026-09-20 跨层重复扫描发现）。
        if (!string.Equals(openLoop.OriginChannel, ConversationChannel.Remote, StringComparison.Ordinal))
        {
            errors.Add("originChannel must be remote");
        }

        if (!string.Equals(openLoop.NextChannel, ConversationChannel.FaceToFace, StringComparison.Ordinal))
        {
            errors.Add("nextChannel must be face_to_face");
        }

        if (!OpenLoopStatuses.Contains(openLoop.Status))
        {
            errors.Add("status is invalid");
        }

        if (string.IsNullOrWhiteSpace(openLoop.ShortSummary))
        {
            errors.Add("shortSummary is required");
        }

        if (string.IsNullOrWhiteSpace(openLoop.CreatedOn))
        {
            errors.Add("createdOn is required");
        }

        return errors;
    }

    public static IReadOnlyList<string> Validate(GroupDialogueInvitationRecord? invitation)
    {
        var errors = new List<string>();
        if (invitation is null)
        {
            errors.Add("group invitation is null");
            return errors;
        }

        if (string.IsNullOrWhiteSpace(invitation.InvitationId))
        {
            errors.Add("invitationId is required");
        }

        if (!GroupInvitationRules.IsKnownTemplateId(invitation.TemplateId))
        {
            errors.Add("templateId is invalid");
        }

        var participants = invitation.Participants ?? Array.Empty<string>();
        var participantDisplayNames = invitation.ParticipantDisplayNames ?? Array.Empty<string>();
        if (!GroupInvitationRules.IsValidParticipantCount(participants.Count))
        {
            errors.Add("participants must contain two or three NPCs");
        }
        else if (participants.Any(string.IsNullOrWhiteSpace) ||
                 participants
                     .Where(id => !string.IsNullOrWhiteSpace(id))
                     .Distinct(StringComparer.OrdinalIgnoreCase)
                     .Count() != participants.Count)
        {
            errors.Add("participants must be unique and non-empty");
        }

        if (participantDisplayNames.Count != participants.Count ||
            participantDisplayNames.Any(string.IsNullOrWhiteSpace))
        {
            errors.Add("participantDisplayNames must match participants");
        }

        if (string.IsNullOrWhiteSpace(invitation.Title))
        {
            errors.Add("title is required");
        }

        if (string.IsNullOrWhiteSpace(invitation.Topic))
        {
            errors.Add("topic is required");
        }

        if (string.IsNullOrWhiteSpace(invitation.Guidance))
        {
            errors.Add("guidance is required");
        }

        if (string.IsNullOrWhiteSpace(invitation.CreatedOn))
        {
            errors.Add("createdOn is required");
        }

        if (string.IsNullOrWhiteSpace(invitation.ExpiresOn))
        {
            errors.Add("expiresOn is required");
        }

        if (invitation.CreatedTotalDays < 0 ||
            invitation.ExpiresTotalDays <= invitation.CreatedTotalDays)
        {
            errors.Add("invitation day range is invalid");
        }

        if (!GroupInvitationRules.IsValidSource(invitation.Source))
        {
            errors.Add("source is invalid");
        }

        if (!GroupInvitationRules.IsValidStatus(invitation.Status))
        {
            errors.Add("status is invalid");
        }

        return errors;
    }
}
