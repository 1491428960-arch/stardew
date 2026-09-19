using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupDialogueSessionRulesTests
{
    [Fact]
    public void Successful_first_turn_completes_accepted_invitation()
    {
        var invitation = AcceptedInvitation();

        var next = GroupDialogueSessionRules.ApplyResult(
            invitation,
            new[]
            {
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Abigail",
                    Content = "我有点想知道。",
                },
            },
            fallback: false);

        Assert.Equal(GroupInvitationStatus.Completed, next.Status);
    }

    [Fact]
    public void Failed_turn_keeps_invitation_retryable_and_drops_history()
    {
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());

        var result = GroupDialogueSessionRules.ApplyResult(
            session,
            Array.Empty<BridgeGroupTurn>(),
            fallback: true);

        Assert.Empty(result.PublicHistory);
        Assert.True(result.CanRetry);
        Assert.Equal(GroupInvitationStatus.Accepted, result.Invitation.Status);
    }

    [Fact]
    public void Multi_turn_replies_all_land_in_public_history_in_order()
    {
        // 策略切成 multi_turn 之后，一次请求返回 2～3 个回合是常态。
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());

        var result = GroupDialogueSessionRules.ApplyResult(
            session,
            new[]
            {
                new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "我会放点吵的。" },
                new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "那我挑安静的。" },
                new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "那就一人一首。" },
            },
            fallback: false);

        Assert.Equal(
            new[] { "Abigail", "Emily", "Abigail" },
            result.PublicHistory.Select(entry => entry.SpeakerId).ToArray());
        Assert.All(result.PublicHistory, entry => Assert.Equal("npc", entry.SpeakerType));
        Assert.Equal(GroupInvitationStatus.Completed, result.Invitation.Status);
        Assert.False(result.CanRetry);
    }

    [Fact]
    public void One_unknown_speaker_rejects_the_whole_batch()
    {
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());

        var result = GroupDialogueSessionRules.ApplyResult(
            session,
            new[]
            {
                new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "我先说。" },
                new BridgeGroupTurn { SpeakerNpcId = "Lewis", Content = "名单外的人不该出现。" },
            },
            fallback: false);

        Assert.Empty(result.PublicHistory);
        Assert.True(result.CanRetry);
        Assert.Equal(GroupInvitationStatus.Accepted, result.Invitation.Status);
    }

    [Fact]
    public void Addressed_targets_outside_the_roster_are_dropped_but_kept_in_order()
    {
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());

        var result = GroupDialogueSessionRules.ApplyResult(
            session,
            new[]
            {
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Abigail",
                    Content = "Emily 你呢？",
                    AddressedTo = new[] { "Emily", "outsider", "emily" },
                },
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Emily",
                    Content = "我在挑布料。",
                    AddressedTo = new[] { "player" },
                },
            },
            fallback: false);

        Assert.Equal(new[] { "Emily" }, result.PublicHistory[0].AddressedTo);
        Assert.Empty(result.PublicHistory[1].AddressedTo!);
    }

    [Fact]
    public void A_second_batch_appends_to_the_existing_public_history()
    {
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());
        var first = GroupDialogueSessionRules.ApplyResult(
            session,
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "第一轮。" } },
            fallback: false);

        var second = GroupDialogueSessionRules.ApplyResult(
            first,
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "第二轮。" } },
            fallback: false);

        Assert.Equal(
            new[] { "Abigail", "Emily" },
            second.PublicHistory.Select(entry => entry.SpeakerId).ToArray());
    }

    private static GroupDialogueInvitationRecord AcceptedInvitation() => new()
    {
        InvitationId = "invite-1",
        TemplateId = "neutral-public-topic",
        Participants = new[] { "Abigail", "Emily" },
        ParticipantDisplayNames = new[] { "Abigail", "Emily" },
        Title = "公共话题",
        Topic = "最近的公共小事",
        Guidance = "只作为讨论方向。",
        CreatedOn = "Spring 20",
        ExpiresOn = "Spring 27",
        CreatedTotalDays = 20,
        ExpiresTotalDays = 27,
        Source = "periodic",
        Status = GroupInvitationStatus.Accepted,
    };
}
