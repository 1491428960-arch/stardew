namespace StardewAI.NPC;

public sealed record GroupInvitationGenerationContext(
    int CurrentTotalDays,
    string CurrentDateLabel,
    IReadOnlyList<GroupParticipantCandidate> KnownParticipants,
    IReadOnlyList<GroupDialogueInvitationRecord> ExistingInvitations,
    IReadOnlyList<string> RecentTopicKeys,
    int? LastCreatedTotalDays);

public sealed class GroupInvitationGenerator
{
    private readonly IReadOnlyList<GroupInvitationTemplate> templates;

    public GroupInvitationGenerator(IReadOnlyList<GroupInvitationTemplate> templates)
    {
        this.templates = templates ?? throw new ArgumentNullException(nameof(templates));
    }

    public IReadOnlyList<GroupDialogueInvitationRecord> Generate(
        GroupInvitationGenerationContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        var pendingCount = context.ExistingInvitations.Count(invitation =>
            invitation.Status is GroupInvitationStatus.Unread or
                GroupInvitationStatus.Deferred or
                GroupInvitationStatus.Accepted);
        if (!GroupInvitationRules.ShouldGenerate(
                context.CurrentTotalDays,
                context.LastCreatedTotalDays,
                pendingCount))
        {
            return Array.Empty<GroupDialogueInvitationRecord>();
        }

        var candidates = context.KnownParticipants
            .Where(candidate => candidate.HasFriendshipRecord &&
                                !string.IsNullOrWhiteSpace(candidate.NpcId) &&
                                !string.IsNullOrWhiteSpace(candidate.DisplayName))
            .GroupBy(candidate => candidate.NpcId.Trim(), StringComparer.OrdinalIgnoreCase)
            .Select(group => group.First())
            .OrderBy(candidate => candidate.NpcId, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (candidates.Length < GroupInvitationRules.MinParticipants)
        {
            return Array.Empty<GroupDialogueInvitationRecord>();
        }

        foreach (var pair in EnumeratePairs(candidates))
        {
            foreach (var template in MatchingTemplates(pair))
            {
                // 与 `GroupInvitationRules.BuildDuplicateKey` 保持同一种归一化（含模板 ID 小写），
                // 否则两边算出的键会因大小写不同而判不出重复。
                var duplicateKey = $"{template.TemplateId.Trim().ToLowerInvariant()}::{GroupInvitationRules.BuildPairKey(
                    pair.Select(candidate => candidate.NpcId))}";
                var isRecentDuplicate = context.ExistingInvitations.Any(invitation =>
                    GroupInvitationRules.BuildDuplicateKey(invitation) == duplicateKey &&
                    context.CurrentTotalDays - invitation.CreatedTotalDays <
                    GroupInvitationRules.ExpirationDays);
                if (isRecentDuplicate || context.RecentTopicKeys.Contains(
                        duplicateKey,
                        StringComparer.OrdinalIgnoreCase))
                {
                    continue;
                }

                return new[] { CreateInvitation(context, template, pair) };
            }
        }

        return Array.Empty<GroupDialogueInvitationRecord>();
    }

    private IEnumerable<GroupInvitationTemplate> MatchingTemplates(
        IReadOnlyList<GroupParticipantCandidate> pair)
    {
        var pairIds = pair.Select(candidate => candidate.NpcId).ToArray();
        return templates
            .Where(template => template.RequiredParticipants.Count == 0 ||
                template.RequiredParticipants.All(required =>
                    pairIds.Contains(required, StringComparer.OrdinalIgnoreCase)))
            .OrderByDescending(template => template.RequiredParticipants.Count)
            .ThenBy(template => template.TemplateId, StringComparer.Ordinal);
    }

    private static IEnumerable<IReadOnlyList<GroupParticipantCandidate>> EnumeratePairs(
        IReadOnlyList<GroupParticipantCandidate> candidates)
    {
        for (var first = 0; first < candidates.Count - 1; first++)
        {
            for (var second = first + 1; second < candidates.Count; second++)
            {
                yield return new[] { candidates[first], candidates[second] };
            }
        }
    }

    private static GroupDialogueInvitationRecord CreateInvitation(
        GroupInvitationGenerationContext context,
        GroupInvitationTemplate template,
        IReadOnlyList<GroupParticipantCandidate> pair)
    {
        var pairKey = GroupInvitationRules.BuildPairKey(pair.Select(candidate => candidate.NpcId));
        return new GroupDialogueInvitationRecord
        {
            InvitationId = $"group:{template.TemplateId}:{pairKey}:{context.CurrentTotalDays}",
            TemplateId = template.TemplateId,
            Participants = pair.Select(candidate => candidate.NpcId).ToArray(),
            ParticipantDisplayNames = pair.Select(candidate => candidate.DisplayName).ToArray(),
            Title = template.Title,
            Topic = template.Topic,
            Guidance = template.Guidance,
            CreatedOn = context.CurrentDateLabel,
            ExpiresOn = $"day {context.CurrentTotalDays + GroupInvitationRules.ExpirationDays}",
            CreatedTotalDays = context.CurrentTotalDays,
            ExpiresTotalDays = context.CurrentTotalDays + GroupInvitationRules.ExpirationDays,
            Source = template.Source,
            Status = GroupInvitationStatus.Unread,
        };
    }
}
