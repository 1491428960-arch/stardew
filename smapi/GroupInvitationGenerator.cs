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

        // 只受时间间隔约束：待处理再多也不阻止生成（用户反馈“每个刷了就得清太蠢”）。
        // 不会无限堆积的理由见 GroupInvitationRules.ShouldGenerate 的注释。
        if (!GroupInvitationRules.ShouldGenerate(
                context.CurrentTotalDays,
                context.LastCreatedTotalDays))
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

        // 三人场更像群聊、两人更像私聊，所以两种规模要交替出现。
        //
        // ⚠️ 2026-09-20 修正：最初用「天数奇偶」做交替，但**生成间隔恰好也是 2 天**，
        // 于是每次生成的天数奇偶性永远相同——两人场会一直两人、三人场会一直三人。
        // 改成看**上一张邀约是几人**：上一张不足三人，这一张就优先三人。
        // 同样不引入随机数，生成结果可测、可复现。
        var lastParticipantCount = context.ExistingInvitations
            .Where(invitation => invitation.Participants is { Count: > 0 })
            .OrderByDescending(invitation => invitation.CreatedTotalDays)
            .Select(invitation => invitation.Participants.Count)
            .FirstOrDefault();
        var preferThree = candidates.Length >= GroupInvitationRules.MaxParticipants &&
                          lastParticipantCount < GroupInvitationRules.MaxParticipants;
                          foreach (var group in EnumerateGroups(candidates, preferThree))
        {
            foreach (var template in MatchingTemplates(group))
            {
                // 与 `GroupInvitationRules.BuildDuplicateKey` 保持同一种归一化（含模板 ID 小写），
                // 否则两边算出的键会因大小写不同而判不出重复。
                var duplicateKey = $"{template.TemplateId.Trim().ToLowerInvariant()}::{GroupInvitationRules.BuildPairKey(
                    group.Select(candidate => candidate.NpcId))}";
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

                return new[] { CreateInvitation(context, template, group) };
            }
        }

        return Array.Empty<GroupDialogueInvitationRecord>();
    }

    /// <summary>
    /// 为这组人取可用模板。**按需生成**：模板是按「角色 × 共同主题」算出来的，
    /// 全组合预生成会有 35 万个对象（约 150 MB），对 mod 不可接受。
    /// </summary>
    private IEnumerable<GroupInvitationTemplate> MatchingTemplates(
        IReadOnlyList<GroupParticipantCandidate> group)
    {

        var groupIds = group.Select(candidate => candidate.NpcId).ToArray();
        // 按需生成：模板由「角色 × 共同主题」算出，全组合预生成会有 35 万个对象
        // （约 150 MB），对 mod 不可接受。这里只为当前这组候选算一次。
        var generated = GroupInvitationTemplates.ForGroup(groupIds);
        return templates
            .Concat(generated)
            .Where(template => template.RequiredParticipants.Count == 0 ||
                template.RequiredParticipants.All(required =>
                    groupIds.Contains(required, StringComparer.OrdinalIgnoreCase)))
            .GroupBy(template => template.TemplateId, StringComparer.Ordinal)
            .Select(grouping => grouping.First())
            .OrderByDescending(template => template.RequiredParticipants.Count)
            .ThenBy(template => template.TemplateId, StringComparer.Ordinal);
    }

    /// <summary>
    /// 枚举候选组合：**按 <paramref name="preferThree"/> 决定先试三人还是先试两人**。
    ///
    /// 2026-09-20：此前这里只枚举两两组合（`EnumeratePairs`），而 F9 的「自由发起」
    /// 被移除后**三人群聊就没了入口**——所以三人组合改由预设邀约承担。
    /// 规则层的 MinParticipants=2 / MaxParticipants=3 本来就允许三人，
    /// Bridge 侧也一直是 min_length=2, max_length=3，不必改动。
    /// </summary>
    private static IEnumerable<IReadOnlyList<GroupParticipantCandidate>> EnumerateGroups(
        IReadOnlyList<GroupParticipantCandidate> candidates,
        bool preferThree)
    {
        if (preferThree)
        {
            foreach (var group in EnumerateTriples(candidates))
            {
                yield return group;
            }
        }

        for (var first = 0; first < candidates.Count - 1; first++)
        {
            for (var second = first + 1; second < candidates.Count; second++)
            {
                yield return new[] { candidates[first], candidates[second] };
            }
        }

        if (!preferThree)
        {
            foreach (var group in EnumerateTriples(candidates))
            {
                yield return group;
            }
        }
    }

    /// <summary>三个候选以上才有产出；不足三个时返回空序列。</summary>
    private static IEnumerable<IReadOnlyList<GroupParticipantCandidate>> EnumerateTriples(
        IReadOnlyList<GroupParticipantCandidate> candidates)
    {
        for (var first = 0; first < candidates.Count - 2; first++)
        {
            for (var second = first + 1; second < candidates.Count - 1; second++)
            {
                for (var third = second + 1; third < candidates.Count; third++)
                {
                    yield return new[]
                    {
                        candidates[first], candidates[second], candidates[third],
                    };
                }
            }
        }
    }

    private static GroupDialogueInvitationRecord CreateInvitation(
        GroupInvitationGenerationContext context,
        GroupInvitationTemplate template,
        IReadOnlyList<GroupParticipantCandidate> group)
    {
        var pairKey = GroupInvitationRules.BuildPairKey(group.Select(candidate => candidate.NpcId));
        return new GroupDialogueInvitationRecord
        {
            InvitationId = $"group:{template.TemplateId}:{pairKey}:{context.CurrentTotalDays}",
            TemplateId = template.TemplateId,
            Participants = group.Select(candidate => candidate.NpcId).ToArray(),
            ParticipantDisplayNames = group.Select(candidate => candidate.DisplayName).ToArray(),
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
