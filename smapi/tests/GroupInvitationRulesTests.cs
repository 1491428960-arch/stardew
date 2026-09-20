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
}
