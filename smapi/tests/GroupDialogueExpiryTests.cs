using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// <c>GroupDialogueCoordinator.ExpireInvitations</c>（每天开始时执行）此前完全没有测试。
/// 这里固化它的状态流转：到达过期日时，仍处于“未决”的状态会改成 <c>Expired</c>；
/// 已终结的状态（<c>Expired</c>/<c>Completed</c>/<c>Dismissed</c>）不被重复处理。
///
/// 注意 <c>Accepted</c> **也会被过期**——这是清理机制：生成新邀约时的 <c>pendingCount</c>
/// 把 <c>Accepted</c> 计入名额，若不清理，一个接受后一直没完成的邀约会让待处理名额永久被占。
/// 若将来要改成“保护进行中的会话”，从这几条测试就能看出影响面。
/// </summary>
public sealed class GroupDialogueExpiryTests
{
    private static GroupDialogueInvitationRecord Invitation(
        string invitationId,
        GroupInvitationStatus status,
        int createdTotalDays = 20,
        int expiresTotalDays = 27) =>
        new()
        {
            InvitationId = invitationId,
            TemplateId = "neutral-public-topic",
            Participants = new[] { "Abigail", "Emily" },
            ParticipantDisplayNames = new[] { "Abigail", "Emily" },
            // StoryStateStore.Replace 会校验状态完整性，这些字段不能省。
            Title = "公共话题",
            Topic = "最近的公共小事",
            Guidance = "只作为讨论方向。",
            CreatedOn = $"day {createdTotalDays}",
            ExpiresOn = $"day {expiresTotalDays}",
            CreatedTotalDays = createdTotalDays,
            ExpiresTotalDays = expiresTotalDays,
            Source = "periodic",
            Status = status,
        };

    private static StoryStateStore StoreWith(params GroupDialogueInvitationRecord[] invitations)
    {
        var store = new StoryStateStore();
        store.Replace(store.State with { GroupDialogueInvitations = invitations });
        return store;
    }

    /// <summary>只跑“日切”这一步；参与者为空，因此不会生成新邀约。</summary>
    private static void RunDay(StoryStateStore store, int totalDays) =>
        new GroupDialogueCoordinator(
            store,
            new GroupInvitationGenerator(GroupInvitationTemplates.All),
            () => Array.Empty<GroupParticipantCandidate>(),
            () => totalDays,
            () => $"Spring {totalDays}").OnDayStarted();

    [Theory]
    [InlineData(GroupInvitationStatus.Unread)]
    [InlineData(GroupInvitationStatus.Deferred)]
    [InlineData(GroupInvitationStatus.Accepted)]
    public void Pending_states_become_expired_on_the_expiry_day(GroupInvitationStatus status)
    {
        var store = StoreWith(Invitation("invite", status));

        RunDay(store, 27);

        var invitation = Assert.Single(store.State.GroupDialogueInvitations);
        Assert.Equal(GroupInvitationStatus.Expired, invitation.Status);
    }

    [Theory]
    [InlineData(GroupInvitationStatus.Expired)]
    [InlineData(GroupInvitationStatus.Completed)]
    [InlineData(GroupInvitationStatus.Dismissed)]
    public void Finished_states_are_left_untouched(GroupInvitationStatus status)
    {
        var store = StoreWith(Invitation("invite", status));

        RunDay(store, 40);  // 远超过期日

        var invitation = Assert.Single(store.State.GroupDialogueInvitations);
        Assert.Equal(status, invitation.Status);
    }

    [Fact]
    public void Invitation_is_kept_on_the_day_before_expiry()
    {
        var store = StoreWith(Invitation("invite", GroupInvitationStatus.Unread));

        RunDay(store, 26);

        var invitation = Assert.Single(store.State.GroupDialogueInvitations);
        Assert.Equal(GroupInvitationStatus.Unread, invitation.Status);
    }

    [Fact]
    public void An_expired_invitation_does_not_block_the_next_generation()
    {
        // 一张已在第 27 天过期的邀约不应拦住后续生成。
        // 顺带钉住去重窗口：同一模板 + 同一组合只在“距创建不满 7 天”时算重复，
        // 这里 27 - 20 = 7 已到窗口边界（不算重复），所以新邀约应当生成。
        var store = StoreWith(Invitation("expiring", GroupInvitationStatus.Unread, 20, 27));
        var candidates = new[]
        {
            new GroupParticipantCandidate("Abigail", "Abigail", true),
            new GroupParticipantCandidate("Emily", "Emily", true),
        };
        var coordinator = new GroupDialogueCoordinator(
            store,
            new GroupInvitationGenerator(GroupInvitationTemplates.All),
            () => candidates,
            () => 27,
            () => "Spring 27");

        coordinator.OnDayStarted();

        var invitations = store.State.GroupDialogueInvitations;
        Assert.Equal(
            1,
            invitations.Count(item => item.Status == GroupInvitationStatus.Expired));
        Assert.Equal(2, invitations.Count);
        Assert.Equal(1, invitations.Count(item => item.CreatedTotalDays == 27));
    }
}
