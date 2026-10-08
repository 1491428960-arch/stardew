using System.Linq;

namespace StardewAI.NPC;

public sealed class GroupDialogueCoordinator
{
    private readonly StoryStateStore storyStateStore;
    private readonly GroupInvitationGenerator invitationGenerator;
    private readonly Func<IReadOnlyList<GroupParticipantCandidate>> participantProvider;
    private readonly Func<int> currentTotalDaysProvider;
    private readonly Func<string> currentDateLabelProvider;
    private readonly Func<bool>? openHub;
    private readonly Action? closeHub;

    public GroupDialogueCoordinator(
        StoryStateStore storyStateStore,
        GroupInvitationGenerator invitationGenerator,
        Func<IReadOnlyList<GroupParticipantCandidate>> participantProvider,
        Func<int> currentTotalDaysProvider,
        Func<string> currentDateLabelProvider,
        Func<bool>? openHub = null,
        Action? closeHub = null)
    {
        this.storyStateStore = storyStateStore ?? throw new ArgumentNullException(nameof(storyStateStore));
        this.invitationGenerator = invitationGenerator ?? throw new ArgumentNullException(nameof(invitationGenerator));
        this.participantProvider = participantProvider ?? throw new ArgumentNullException(nameof(participantProvider));
        this.currentTotalDaysProvider = currentTotalDaysProvider ?? throw new ArgumentNullException(nameof(currentTotalDaysProvider));
        this.currentDateLabelProvider = currentDateLabelProvider ?? throw new ArgumentNullException(nameof(currentDateLabelProvider));
        this.openHub = openHub;
        this.closeHub = closeHub;
    }

    /// <summary>最近一次 OnDayStarted 的关键事实，供 ModEntry 打日志用。</summary>
    public string LastDiagnostics { get; private set; } = "(尚未运行)";

    public void OnDayStarted()
    {
        var currentTotalDays = currentTotalDaysProvider();
        ExpireInvitations(currentTotalDays);

        var invitations = storyStateStore.State.GroupDialogueInvitations;
        var lastCreatedTotalDays = invitations
            .Select(invitation => (int?)invitation.CreatedTotalDays)
            .OrderByDescending(value => value)
            .FirstOrDefault();
        var candidates = participantProvider();
        var generated = invitationGenerator.Generate(new GroupInvitationGenerationContext(
            currentTotalDays,
            currentDateLabelProvider(),
            candidates,
            invitations,
            Array.Empty<string>(),
            lastCreatedTotalDays,
            // 已接受「玩家有多位亲密对象」的角色：`EnsureSpouseAcceptance` 在同步婚姻时
            // 写下的 outcome=accepted。把它交给生成器，让「打趣」只在**在场至少两位**
            // 已接受者时才成为话题（2026-10-09 前是加在引导末尾的一段许可）。
            storyStateStore.State.Mediations
                .Where(mediation => string.Equals(
                    mediation.Outcome, "accepted", StringComparison.OrdinalIgnoreCase))
                .Select(mediation => mediation.NpcId)
                .ToArray()));
        var pending = invitations.Count(invitation =>
            invitation.Status is GroupInvitationStatus.Unread or
                GroupInvitationStatus.Deferred or
                GroupInvitationStatus.Accepted);
        LastDiagnostics =
            $"day={currentTotalDays} lastCreated={lastCreatedTotalDays?.ToString() ?? "无"} " +
            $"候选={candidates.Count} 记录={invitations.Count} 未处理={pending} 本次生成={generated.Count}";
        if (generated.Count == 0)
        {
            return;
        }

        storyStateStore.Replace(storyStateStore.State with
        {
            GroupDialogueInvitations = invitations.Concat(generated).ToArray(),
        });
    }

    /// <summary>
    /// 开发用：无视冷却与生成节奏，直接塞一张打趣卡进队列
    /// （Ctrl+Shift+F9 / 控制台 <c>ainpc_invite</c>）。
    ///
    /// 参与者由调用方给定 —— ModEntry 那边能拿到 <c>Game1</c> 填本地化显示名，
    /// 而本类只有 provider，拿不到。
    ///
    /// ⚠ 造出来的是一张**正常卡**：会随存档落盘，也会占掉打趣主题的 7 天冷却。
    /// 这正是「验的就是真东西」的代价，不是缺陷。
    /// </summary>
    public string TryInjectTeasingInvitation(IReadOnlyList<GroupParticipantCandidate> group)
    {
        ArgumentNullException.ThrowIfNull(group);
        if (group.Count < GroupInvitationRules.MinParticipants)
        {
            return $"参与者只有 {group.Count} 位，打趣至少要 {GroupInvitationRules.MinParticipants} 位";
        }

        var generated = invitationGenerator.GenerateForcedTeasing(
            currentTotalDaysProvider(),
            currentDateLabelProvider(),
            group);
        var invitations = storyStateStore.State.GroupDialogueInvitations;
        storyStateStore.Replace(storyStateStore.State with
        {
            GroupDialogueInvitations = invitations.Concat(generated).ToArray(),
        });
        var summary =
            $"已造出打趣卡 {generated[0].InvitationId}；参与者 " +
            $"{string.Join("/", group.Select(candidate => candidate.NpcId))}";
        LastDiagnostics = $"dev 注入：{summary}";
        return summary;
    }

    public bool TryOpen()
    {
        return openHub?.Invoke() == true;
    }

    public void CloseIfOpen()
    {
        closeHub?.Invoke();
    }

    private void ExpireInvitations(int currentTotalDays)
    {
        var changed = false;
        var next = storyStateStore.State.GroupDialogueInvitations
            .Select(invitation =>
            {
                if (!GroupInvitationRules.IsExpired(
                        currentTotalDays,
                        invitation.CreatedTotalDays,
                        invitation.ExpiresTotalDays) ||
                    invitation.Status == GroupInvitationStatus.Expired ||
                    invitation.Status == GroupInvitationStatus.Completed ||
                    invitation.Status == GroupInvitationStatus.Dismissed)
                {
                    return invitation;
                }

                changed = true;
                return invitation with { Status = GroupInvitationStatus.Expired };
            })
            .ToArray();
        if (changed)
        {
            storyStateStore.Replace(storyStateStore.State with
            {
                GroupDialogueInvitations = next,
            });
        }
    }
}
