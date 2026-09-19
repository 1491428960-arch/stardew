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
    public void New_invitation_is_allowed_only_every_two_total_days_when_pending_limit_is_not_reached()
    {
        Assert.True(GroupInvitationRules.ShouldGenerate(20, 18, pendingCount: 0));
        Assert.False(GroupInvitationRules.ShouldGenerate(19, 18, pendingCount: 0));
        Assert.False(GroupInvitationRules.ShouldGenerate(20, 18, pendingCount: 3));
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
