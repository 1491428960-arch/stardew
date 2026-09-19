using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 群聊「开场」：刚开一场群聊、还没有任何公开历史时，应当由 NPC 先起头。
///
/// 起因（2026-09-20 用户反馈）：接受邀约后玩家一句话都没说，
/// 而原来的流程要求玩家先开口，邀约因此起不到引导作用。
/// Bridge 侧已支持「空玩家消息 ⇒ 开场」的语义，这里判定的是**什么时候该发那一次请求**。
/// </summary>
public sealed class GroupDialogueOpeningRulesTests
{
    private static GroupDialogueSession FreshSession()
    {
        return GroupDialogueSessionRules.Create(
            new GroupDialogueInvitationRecord
            {
                InvitationId = "inv-1",
                Topic = "矿洞传闻",
                Guidance = "围绕最近发现的矿石聊聊",
                Participants = new[] { "Abigail", "Sebastian" },
            });
    }

    [Fact]
    public void A_fresh_session_should_open_with_the_npcs()
    {
        var session = FreshSession();

        Assert.True(GroupDialogueSessionRules.ShouldOpenWithNpc(session, openingAlreadyRequested: false));
    }

    [Fact]
    public void An_empty_history_after_a_failed_turn_should_not_auto_open_again()
    {
        // 失败会让 CanRetry 为真——若在这里再自动发一次，就会变成无限重试。
        var session = GroupDialogueSessionRules.ApplyResult(
            FreshSession(),
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "…" } },
            fallback: true);

        Assert.True(session.CanRetry);
        Assert.False(GroupDialogueSessionRules.ShouldOpenWithNpc(session, openingAlreadyRequested: false));
    }

    [Fact]
    public void A_session_that_already_asked_should_not_ask_again()
    {
        var session = FreshSession();

        Assert.False(GroupDialogueSessionRules.ShouldOpenWithNpc(session, openingAlreadyRequested: true));
    }

    [Fact]
    public void A_session_that_already_has_history_should_not_auto_open()
    {
        var session = GroupDialogueSessionRules.ApplyResult(
            FreshSession(),
            new[]
            {
                new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "听说矿洞那边有新东西。" },
            },
            fallback: false);

        Assert.NotEmpty(session.PublicHistory);
        Assert.False(GroupDialogueSessionRules.ShouldOpenWithNpc(session, openingAlreadyRequested: false));
    }

    [Fact]
    public void The_rule_requires_a_session()
    {
        Assert.Throws<ArgumentNullException>(
            () => GroupDialogueSessionRules.ShouldOpenWithNpc(null!, openingAlreadyRequested: false));
    }
}
