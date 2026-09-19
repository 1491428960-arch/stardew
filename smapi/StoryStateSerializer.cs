using System.Text.Json;
using System.Text.Json.Serialization;

namespace StardewAI.NPC;

public static class StoryStateSerializer
{
    public const string StorageKey = "stardew-ai-npc.story-state.v1";

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
    };

    public static string Serialize(StoryStateEnvelope state)
    {
        ArgumentNullException.ThrowIfNull(state);
        if (state.SchemaVersion != StoryStateEnvelope.CurrentSchemaVersion)
        {
            throw new ArgumentException(
                $"不支持的故事状态版本：{state.SchemaVersion}。",
                nameof(state));
        }

        var errors = ValidateMemories(state.Memories);
        errors = errors
            .Concat(ValidateRelationshipViews(state.RelationshipViews))
            .Concat(ValidateMediations(state.Mediations))
            .Concat(ValidateJealousies(state.Jealousies))
            .Concat(ValidateOpenLoops(state.OpenLoops))
            .Concat(ValidateGroupDialogueInvitations(state.GroupDialogueInvitations))
            .ToList();
        if (errors.Count > 0)
        {
            throw new ArgumentException(
                $"故事状态包含无效记录：{string.Join("；", errors)}。",
                nameof(state));
        }

        return JsonSerializer.Serialize(state, JsonOptions);
    }

    public static StoryStateLoadResult Load(string? json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return EmptyWithWarning("story state JSON is empty");
        }

        StoryStateEnvelope? state;
        try
        {
            state = JsonSerializer.Deserialize<StoryStateEnvelope>(json, JsonOptions);
        }
        catch (JsonException)
        {
            return EmptyWithWarning("story state JSON is invalid");
        }

        if (state is null)
        {
            return EmptyWithWarning("story state JSON contains no state");
        }

        if (state.SchemaVersion != StoryStateEnvelope.CurrentSchemaVersion)
        {
            return EmptyWithWarning(
                $"story state schema {state.SchemaVersion} is unsupported");
        }

        var warnings = new List<string>();
        var validMemories = new List<MemoryRecord>();
        foreach (var memory in state.Memories ?? Array.Empty<MemoryRecord>())
        {
            var errors = StoryStateValidation.Validate(memory);
            if (errors.Count == 0)
            {
                validMemories.Add(memory);
                continue;
            }

            var memoryId = memory is null || string.IsNullOrWhiteSpace(memory.MemoryId)
                ? "unknown"
                : memory.MemoryId.Trim();
            warnings.Add($"memory {memoryId} skipped: {string.Join(", ", errors)}");
        }

        var validViews = new List<RelationshipViewRecord>();
        foreach (var view in state.RelationshipViews ?? Array.Empty<RelationshipViewRecord>())
        {
            var viewErrors = StoryStateValidation.Validate(view);
            if (viewErrors.Count == 0)
            {
                validViews.Add(view);
                continue;
            }

            var ownerNpcId = view is null || string.IsNullOrWhiteSpace(view.OwnerNpcId)
                ? "unknown"
                : view.OwnerNpcId.Trim();
            warnings.Add($"relationship view {ownerNpcId} skipped: {string.Join(", ", viewErrors)}");
        }

        var validMediations = new List<RelationshipMediationRecord>();
        foreach (var mediation in state.Mediations ?? Array.Empty<RelationshipMediationRecord>())
        {
            var mediationErrors = StoryStateValidation.Validate(mediation);
            if (mediationErrors.Count == 0)
            {
                validMediations.Add(mediation);
                continue;
            }

            var npcId = mediation is null || string.IsNullOrWhiteSpace(mediation.NpcId)
                ? "unknown"
                : mediation.NpcId.Trim();
            warnings.Add($"mediation {npcId} skipped: {string.Join(", ", mediationErrors)}");
        }

        var validJealousies = new List<RelationshipJealousyRecord>();
        foreach (var jealousy in state.Jealousies ?? Array.Empty<RelationshipJealousyRecord>())
        {
            var jealousyErrors = StoryStateValidation.Validate(jealousy);
            if (jealousyErrors.Count == 0)
            {
                validJealousies.Add(jealousy);
                continue;
            }

            var npcId = jealousy is null || string.IsNullOrWhiteSpace(jealousy.NpcId)
                ? "unknown"
                : jealousy.NpcId.Trim();
            warnings.Add($"jealousy {npcId} skipped: {string.Join(", ", jealousyErrors)}");
        }

        var validOpenLoops = new List<OpenLoopRecord>();
        foreach (var openLoop in state.OpenLoops ?? Array.Empty<OpenLoopRecord>())
        {
            var openLoopErrors = StoryStateValidation.Validate(openLoop);
            if (openLoopErrors.Count == 0)
            {
                validOpenLoops.Add(openLoop);
                continue;
            }

            var loopId = openLoop is null || string.IsNullOrWhiteSpace(openLoop.LoopId)
                ? "unknown"
                : openLoop.LoopId.Trim();
            warnings.Add($"open loop {loopId} skipped: {string.Join(", ", openLoopErrors)}");
        }

        var validGroupDialogueInvitations = new List<GroupDialogueInvitationRecord>();
        foreach (var invitation in state.GroupDialogueInvitations ?? Array.Empty<GroupDialogueInvitationRecord>())
        {
            var invitationErrors = StoryStateValidation.Validate(invitation);
            if (invitationErrors.Count == 0)
            {
                validGroupDialogueInvitations.Add(invitation);
                continue;
            }

            var invitationId = invitation is null || string.IsNullOrWhiteSpace(invitation.InvitationId)
                ? "unknown"
                : invitation.InvitationId.Trim();
            warnings.Add(
                $"group invitation {invitationId} skipped: {string.Join(", ", invitationErrors)}");
        }

        return new StoryStateLoadResult(
            state with
            {
                Memories = validMemories,
                StoryEvents = state.StoryEvents ?? Array.Empty<StoryEventRecord>(),
                Knowledge = state.Knowledge ?? Array.Empty<KnowledgeRecord>(),
                Relationships = state.Relationships ?? Array.Empty<RelationshipEdgeRecord>(),
                RelationshipViews = validViews,
                Mediations = validMediations,
                Jealousies = validJealousies,
                OpenLoops = validOpenLoops,
                GroupDialogueInvitations = validGroupDialogueInvitations,
                InteractionProgresses = state.InteractionProgresses ?? Array.Empty<InteractionProgress>(),
            },
            warnings);
    }

    private static IReadOnlyList<string> ValidateMemories(
        IEnumerable<MemoryRecord>? memories)
    {
        var errors = new List<string>();
        foreach (var memory in memories ?? Array.Empty<MemoryRecord>())
        {
            var memoryErrors = StoryStateValidation.Validate(memory);
            if (memoryErrors.Count > 0)
            {
                var memoryId = memory is null || string.IsNullOrWhiteSpace(memory.MemoryId)
                    ? "unknown"
                    : memory.MemoryId.Trim();
                errors.Add($"{memoryId}: {string.Join(", ", memoryErrors)}");
            }
        }

        return errors;
    }

    private static IReadOnlyList<string> ValidateRelationshipViews(
        IEnumerable<RelationshipViewRecord>? views)
    {
        var errors = new List<string>();
        foreach (var view in views ?? Array.Empty<RelationshipViewRecord>())
        {
            var viewErrors = StoryStateValidation.Validate(view);
            if (viewErrors.Count > 0)
            {
                var ownerNpcId = view is null || string.IsNullOrWhiteSpace(view.OwnerNpcId)
                    ? "unknown"
                    : view.OwnerNpcId.Trim();
                errors.Add($"relationship view {ownerNpcId}: {string.Join(", ", viewErrors)}");
            }
        }

        return errors;
    }

    private static IReadOnlyList<string> ValidateMediations(
        IEnumerable<RelationshipMediationRecord>? mediations)
    {
        var errors = new List<string>();
        foreach (var mediation in mediations ?? Array.Empty<RelationshipMediationRecord>())
        {
            var mediationErrors = StoryStateValidation.Validate(mediation);
            if (mediationErrors.Count > 0)
            {
                var npcId = mediation is null || string.IsNullOrWhiteSpace(mediation.NpcId)
                    ? "unknown"
                    : mediation.NpcId.Trim();
                errors.Add($"mediation {npcId}: {string.Join(", ", mediationErrors)}");
            }
        }

        return errors;
    }

    private static IReadOnlyList<string> ValidateJealousies(
        IEnumerable<RelationshipJealousyRecord>? jealousies)
    {
        var errors = new List<string>();
        foreach (var jealousy in jealousies ?? Array.Empty<RelationshipJealousyRecord>())
        {
            var jealousyErrors = StoryStateValidation.Validate(jealousy);
            if (jealousyErrors.Count > 0)
            {
                var npcId = jealousy is null || string.IsNullOrWhiteSpace(jealousy.NpcId)
                    ? "unknown"
                    : jealousy.NpcId.Trim();
                errors.Add($"jealousy {npcId}: {string.Join(", ", jealousyErrors)}");
            }
        }

        return errors;
    }

    private static IReadOnlyList<string> ValidateOpenLoops(
        IEnumerable<OpenLoopRecord>? openLoops)
    {
        var errors = new List<string>();
        foreach (var openLoop in openLoops ?? Array.Empty<OpenLoopRecord>())
        {
            var openLoopErrors = StoryStateValidation.Validate(openLoop);
            if (openLoopErrors.Count > 0)
            {
                var loopId = openLoop is null || string.IsNullOrWhiteSpace(openLoop.LoopId)
                    ? "unknown"
                    : openLoop.LoopId.Trim();
                errors.Add($"open loop {loopId}: {string.Join(", ", openLoopErrors)}");
            }
        }

        return errors;
    }

    private static IReadOnlyList<string> ValidateGroupDialogueInvitations(
        IEnumerable<GroupDialogueInvitationRecord>? invitations)
    {
        var errors = new List<string>();
        foreach (var invitation in invitations ?? Array.Empty<GroupDialogueInvitationRecord>())
        {
            var invitationErrors = StoryStateValidation.Validate(invitation);
            if (invitationErrors.Count > 0)
            {
                var invitationId = invitation is null || string.IsNullOrWhiteSpace(invitation.InvitationId)
                    ? "unknown"
                    : invitation.InvitationId.Trim();
                errors.Add($"{invitationId}: {string.Join(", ", invitationErrors)}");
            }
        }

        return errors;
    }

    private static StoryStateLoadResult EmptyWithWarning(string warning)
    {
        return new StoryStateLoadResult(
            StoryStateEnvelope.Empty,
            new[] { warning });
    }
}
