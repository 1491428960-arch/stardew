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
            lastCreatedTotalDays));
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
