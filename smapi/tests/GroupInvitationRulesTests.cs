using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupInvitationRulesTests
{
    [Fact]
    public void Invitation_requires_two_to_three_unique_participants()
    {
        Assert.True(GroupInvitationRules.IsValidParticipantCount(2));
        Assert.True(GroupInvitationRules.IsValidParticipantCount(3));
        Assert.False(GroupInvitationRules.IsValidParticipantCount(1));
        Assert.False(GroupInvitationRules.IsValidParticipantCount(4));
    }

    [Fact]
    public void Invitation_key_is_order_independent_for_duplicate_detection()
    {
        var first = GroupInvitationRules.BuildPairKey(new[] { "Abigail", "Emily" });
        var second = GroupInvitationRules.BuildPairKey(new[] { "Emily", "Abigail" });

        Assert.Equal(first, second);
    }

    [Fact]
    public void New_invitation_is_allowed_only_every_two_total_days()
    {
        Assert.True(GroupInvitationRules.ShouldGenerate(20, 18));
        Assert.False(GroupInvitationRules.ShouldGenerate(19, 18));
    }

    [Fact]
    public void Generating_is_never_blocked_by_pending_invitations()
    {
        // 用户反馈：每张都得清掉才能来新的太蠢。
        // 现在 ShouldGenerate 只看时间间隔；不会无限堆积由过期机制保证
        // （见 GroupDialogueExpiryTests：连 Accepted 也会在 7 天后过期）。
        Assert.True(GroupInvitationRules.ShouldGenerate(20, 18));
        Assert.True(GroupInvitationRules.ShouldGenerate(100, 98));
    }

    [Fact]
    public void The_visible_limit_is_only_about_displaying()
    {
        // 显示上限存在只是因为它要画进固定高度的面板；
        // 它**不**参与生成判断（那正是用户抱怨的那条旧限制）。
        Assert.True(GroupInvitationRules.MaxVisibleInvitations >= 3);
    }

    [Fact]
    public void Invitation_expires_after_seven_total_days()
    {
        Assert.False(GroupInvitationRules.IsExpired(26, createdTotalDays: 20, expiresTotalDays: 27));
        Assert.True(GroupInvitationRules.IsExpired(27, createdTotalDays: 20, expiresTotalDays: 27));
    }

    [Fact]
    public void Failed_request_does_not_complete_invitation()
    {
        var accepted = new GroupDialogueInvitationRecord
        {
            InvitationId = "invite-1",
            Participants = new[] { "Abigail", "Emily" },
            Status = GroupInvitationStatus.Accepted,
        };

        var next = GroupInvitationRules.AfterConversationResult(accepted, usableReply: false);

        Assert.Equal(GroupInvitationStatus.Accepted, next.Status);
    }

    // ── 2026-09-21 用户口径：聊完不删；到期后不能继续聊，但可以点进去看记录 ──────────

    private static GroupDialogueInvitationRecord Card(
        GroupInvitationStatus status,
        int createdTotalDays = 20,
        int expiresTotalDays = 27) =>
        new()
        {
            InvitationId = "invite-1",
            Participants = new[] { "Abigail", "Emily" },
            ParticipantDisplayNames = new[] { "阿比盖尔", "艾米丽" },
            Title = "公共话题",
            Topic = "最近的公共小事",
            CreatedTotalDays = createdTotalDays,
            ExpiresTotalDays = expiresTotalDays,
            Status = status,
        };

    [Fact]
    public void A_card_with_an_archived_session_stays_after_the_expiry_day()
    {
        // 到期日当天：卡片仍在（记录还在），只是不能再发言。
        var invitation = Card(GroupInvitationStatus.Completed);

        Assert.True(GroupInvitationRules.ShouldShowInHub(invitation, 27, hasArchivedSession: true));
        Assert.True(GroupInvitationRules.ShouldShowInHub(invitation, 400, hasArchivedSession: true));
        Assert.True(GroupInvitationRules.IsReadOnly(27, invitation));
    }

    [Fact]
    public void A_card_without_a_session_still_disappears_when_it_expires()
    {
        // 没聊过、也没有任何东西可看的卡沿用旧规则：到点消失，不占列表。
        Assert.True(GroupInvitationRules.ShouldShowInHub(Card(GroupInvitationStatus.Unread), 26, false));
        Assert.False(GroupInvitationRules.ShouldShowInHub(Card(GroupInvitationStatus.Unread), 27, false));
        Assert.False(GroupInvitationRules.ShouldShowInHub(
            Card(GroupInvitationStatus.Expired),
            26,
            hasArchivedSession: false));
    }

    [Fact]
    public void A_card_with_a_session_survives_the_expired_status_too()
    {
        // 场次已经写进存档、但菜单还没来得及把卡置成 Completed 时（例如写完就关游戏），
        // 日切会把 Accepted 改成 Expired。记录既然在，入口就得在 —— 否则数据还在、没地方看。
        Assert.True(GroupInvitationRules.ShouldShowInHub(
            Card(GroupInvitationStatus.Expired),
            40,
            hasArchivedSession: true));
    }

    [Fact]
    public void Dismissing_a_card_still_hides_it_even_with_a_session()
    {
        // 「忽略」是玩家明确的「我不想再看到它」，不该被「记录还在」覆盖。
        Assert.False(GroupInvitationRules.ShouldShowInHub(
            Card(GroupInvitationStatus.Dismissed),
            21,
            hasArchivedSession: true));
    }

    [Fact]
    public void A_card_can_be_continued_until_the_expiry_day()
    {
        var invitation = Card(GroupInvitationStatus.Completed);

        Assert.False(GroupInvitationRules.IsReadOnly(26, invitation));
        Assert.True(GroupInvitationRules.ShouldShowInHub(invitation, 26, hasArchivedSession: true));
    }

    [Fact]
    public void Primary_button_text_distinguishes_the_three_states()
    {
        Assert.Equal("接受", GroupInvitationRules.PrimaryActionLabel(hasArchivedSession: false, readOnly: false));
        Assert.Equal("继续", GroupInvitationRules.PrimaryActionLabel(hasArchivedSession: true, readOnly: false));
        Assert.Equal(
            GroupReadOnlyRules.ActionLabel,
            GroupInvitationRules.PrimaryActionLabel(hasArchivedSession: true, readOnly: true));
        Assert.Equal("回看", GroupInvitationRules.PrimaryActionLabel(hasArchivedSession: true, readOnly: true));
    }

    [Fact]
    public void Finished_cards_sort_after_the_ones_that_are_still_open()
    {
        // 一屏只有 4 张卡：已聊过的卡若与未读卡混排，玩家的新邀约会被挤出屏幕。
        Assert.Equal(0, GroupInvitationRules.HubSortTier(hasArchivedSession: false));
        Assert.Equal(1, GroupInvitationRules.HubSortTier(hasArchivedSession: true));
        Assert.True(
            GroupInvitationRules.HubSortTier(hasArchivedSession: false) <
            GroupInvitationRules.HubSortTier(hasArchivedSession: true));
    }
}
