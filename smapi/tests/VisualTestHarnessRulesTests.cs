using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class VisualTestHarnessRulesTests
{
    [Fact]
    public void DisabledEnvironmentDoesNotStartHarness()
    {
        Assert.False(VisualTestHarnessRules.IsEnabled(null));
        Assert.False(VisualTestHarnessRules.IsEnabled("0"));
    }

    [Fact]
    public void EnabledEnvironmentRequiresSafeSaveNameAndOutputDirectory()
    {
        var options = VisualTestHarnessRules.Parse(
            new Dictionary<string, string?>
            {
                ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                ["STARDEW_AI_NPC_VISUAL_SAVE_NAME"] = "test_447101921",
                ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
            });

        Assert.True(options.Enabled);
        Assert.Equal("test_447101921", options.SaveName);
        Assert.Equal("chat-empty", options.ScenarioId);
        Assert.Equal("capture", options.ActionId);
        Assert.Null(options.BackBufferWidth);
        Assert.Null(options.BackBufferHeight);
    }

    [Fact]
    public void EnabledEnvironmentAcceptsExplicitTopicAction()
    {
        var options = VisualTestHarnessRules.Parse(
            new Dictionary<string, string?>
            {
                ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
                ["STARDEW_AI_NPC_VISUAL_ACTION"] = "topic",
            });

        Assert.Equal("topic", options.ActionId);
    }

    [Fact]
    public void EnabledEnvironmentAcceptsExplicitGroupHubAction()
    {
        var options = VisualTestHarnessRules.Parse(
            new Dictionary<string, string?>
            {
                ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
                ["STARDEW_AI_NPC_VISUAL_ACTION"] = "group-hub",
            });

        Assert.Equal("group-hub", options.ActionId);
    }

    [Fact]
    public void UnknownVisualActionFailsClosed()
    {
        Assert.Throws<ArgumentException>(() => VisualTestHarnessRules.Parse(
            new Dictionary<string, string?>
            {
                ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
                ["STARDEW_AI_NPC_VISUAL_ACTION"] = "click-everything",
            }));
    }

    [Fact]
    public void TopicActionWaitsForRenderedMenuBeforeTriggering()
    {
        Assert.False(VisualTestHarnessRules.CanTriggerTopicAction(
            actionId: "topic",
            menuReady: false,
            actionTriggered: false,
            activeMenuFrames: 6));
        Assert.False(VisualTestHarnessRules.CanTriggerTopicAction(
            actionId: "topic",
            menuReady: true,
            actionTriggered: false,
            activeMenuFrames: 2));
        Assert.True(VisualTestHarnessRules.CanTriggerTopicAction(
            actionId: "topic",
            menuReady: true,
            actionTriggered: false,
            activeMenuFrames: 3));
        Assert.False(VisualTestHarnessRules.CanTriggerTopicAction(
            actionId: "topic",
            menuReady: true,
            actionTriggered: true,
            activeMenuFrames: 3));
        Assert.False(VisualTestHarnessRules.CanTriggerTopicAction(
            actionId: "capture",
            menuReady: true,
            actionTriggered: false,
            activeMenuFrames: 3));
    }

    [Fact]
    public void GroupHubActionWaitsForStableMenuBeforeTriggering()
    {
        Assert.False(VisualTestHarnessRules.CanTriggerGroupHubAction(
            actionId: "group-hub",
            menuReady: false,
            actionTriggered: false,
            activeMenuFrames: 3));
        Assert.False(VisualTestHarnessRules.CanTriggerGroupHubAction(
            actionId: "group-hub",
            menuReady: true,
            actionTriggered: true,
            activeMenuFrames: 3));
        Assert.False(VisualTestHarnessRules.CanTriggerGroupHubAction(
            actionId: "group-hub",
            menuReady: true,
            actionTriggered: false,
            activeMenuFrames: 2));
        Assert.True(VisualTestHarnessRules.CanTriggerGroupHubAction(
            actionId: "group-hub",
            menuReady: true,
            actionTriggered: false,
            activeMenuFrames: 3));
        Assert.False(VisualTestHarnessRules.CanTriggerGroupHubAction(
            actionId: "capture",
            menuReady: true,
            actionTriggered: false,
            activeMenuFrames: 3));
    }

    [Fact]
    public void GroupHubScenarioInvitationUsesTheExistingStoryStateSchema()
    {
        var invitation = VisualTestHarnessRules.CreateGroupHubInvitation(12);

        Assert.Empty(StoryStateValidation.Validate(invitation));
        Assert.Equal("story", invitation.Source);
        Assert.Equal(19, invitation.ExpiresTotalDays);
    }

    [Fact]
    public void EnabledEnvironmentAcceptsExplicitGroupMessageAction()
    {
        var options = VisualTestHarnessRules.Parse(
            new Dictionary<string, string?>
            {
                ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
                ["STARDEW_AI_NPC_VISUAL_ACTION"] = "group-message",
            });

        Assert.Equal("group-message", options.ActionId);
    }

    [Fact]
    public void EnabledEnvironmentAcceptsExplicitGroupSendAction()
    {
        var options = VisualTestHarnessRules.Parse(
            new Dictionary<string, string?>
            {
                ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
                ["STARDEW_AI_NPC_VISUAL_ACTION"] = "group-send",
            });

        Assert.Equal("group-send", options.ActionId);
        Assert.False(string.IsNullOrWhiteSpace(VisualTestHarnessRules.GroupSendPlayerMessage));
    }

    [Fact]
    public void EnabledEnvironmentAcceptsGroupFlowActions()
    {
        foreach (var action in new[] { "group-accept" })
        {
            var options = VisualTestHarnessRules.Parse(
                new Dictionary<string, string?>
                {
                    ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                    ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
                    ["STARDEW_AI_NPC_VISUAL_ACTION"] = action,
                });

            Assert.Equal(action, options.ActionId);
        }
    }

    [Fact]
    public void GroupFlowInvitationCanBeAcceptedThroughTheStoryStore()
    {
        // F9 全流程场景依赖“点击接受后 TrySetGroupInvitationStatus 能找到这张卡”。
        // 真机上曾因为测试邀约写在 SaveLoaded 之前、被存档状态覆盖而失败。
        var store = new StoryStateStore();
        var invitation = VisualTestHarnessRules.CreateGroupHubInvitation(12);
        store.Replace(store.State with
        {
            GroupDialogueInvitations = new[] { invitation },
        });

        Assert.True(store.TrySetGroupInvitationStatus(
            invitation.InvitationId,
            GroupInvitationStatus.Accepted));
        Assert.Equal(
            GroupInvitationStatus.Accepted,
            store.State.GroupDialogueInvitations.Single().Status);
    }

    [Fact]
    public void GroupSendScenarioUsesAThreePersonRosterMatchingItsInvitation()
    {
        var participants = VisualTestHarnessRules.CreateGroupSendParticipants();
        var invitation = VisualTestHarnessRules.CreateGroupSendInvitation(12);

        // 两人场在回合上限为 2 时必然都开口，三人场才看得出“每个人都有机会说话”。
        Assert.Equal(3, participants.Count);
        Assert.Equal(
            invitation.Participants,
            participants.Select(item => item.NpcId));
        Assert.Empty(StoryStateValidation.Validate(invitation));
        Assert.NotEqual(
            VisualTestHarnessRules.CreateGroupHubInvitation(12).InvitationId,
            invitation.InvitationId);
    }

    [Fact]
    public void GroupMessageScenarioProducesUsableTurnsAndOneHighlight()
    {
        var participants = VisualTestHarnessRules.CreateGroupMessageParticipants();
        var response = VisualTestHarnessRules.CreateGroupMessageResponse();
        var invitation = VisualTestHarnessRules.CreateGroupHubInvitation(12);

        Assert.Equal(2, participants.Count);
        Assert.Equal(
            invitation.Participants,
            participants.Select(item => item.NpcId));
        Assert.False(response.Fallback);
        Assert.Single(response.MemoryHighlights);

        var participantIds = participants
            .Select(item => item.NpcId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        Assert.NotEmpty(response.Turns);
        Assert.All(
            response.Turns,
            turn => Assert.True(GroupDialogueSessionRules.IsValidTurn(turn, participantIds)));

        var session = GroupDialogueSessionRules.ApplyResult(
            GroupDialogueSessionRules.Create(invitation),
            // 视觉测试场景里玩家没有说话（响应是直接排进菜单的），所以这里传 null：
            // 历史条数仍等于回合数，与「面板发言数 == 存档场次条数」那条证据行一致。
            playerMessage: null,
            response.Turns,
            response.Fallback);

        Assert.Equal(GroupInvitationStatus.Completed, session.Invitation.Status);
        Assert.Equal(response.Turns.Count, session.PublicHistory.Count);
        Assert.False(session.CanRetry);
    }

    [Fact]
    public void EnabledEnvironmentAcceptsExplicitWideBackBuffer()
    {
        var options = VisualTestHarnessRules.Parse(
            new Dictionary<string, string?>
            {
                ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
                ["STARDEW_AI_NPC_VISUAL_BACKBUFFER_WIDTH"] = "2560",
                ["STARDEW_AI_NPC_VISUAL_BACKBUFFER_HEIGHT"] = "1528",
            });

        Assert.Equal(2560, options.BackBufferWidth);
        Assert.Equal(1528, options.BackBufferHeight);
    }

    [Fact]
    public void ContentScenarioSeedsRepresentativeConversationAndKnownFriendship()
    {
        var scenario = VisualTestHarnessRules.GetScenarioContent(
            "chat-profile-strip-wide-content");

        Assert.Equal(5, scenario.FriendshipHearts);
        Assert.Contains(
            scenario.InitialMessages,
            message => message.Role == "npc" &&
                message.Content.Contains("今天的风", StringComparison.Ordinal));
        Assert.Contains(
            scenario.InitialMessages,
            message => message.Role == "player" &&
                message.Content.Contains("最近在整理", StringComparison.Ordinal));
        Assert.True(scenario.InitialMessages.Count >= 4);
    }

    [Fact]
    public void UnknownScenarioUsesEmptyConversationWithoutFriendshipOverride()
    {
        var scenario = VisualTestHarnessRules.GetScenarioContent("chat-empty");

        Assert.Empty(scenario.InitialMessages);
        Assert.Null(scenario.FriendshipHearts);
    }

    [Fact]
    public void ExplicitBackBufferRequiresBothPositiveDimensions()
    {
        Assert.Throws<ArgumentException>(() => VisualTestHarnessRules.Parse(
            new Dictionary<string, string?>
            {
                ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
                ["STARDEW_AI_NPC_VISUAL_BACKBUFFER_WIDTH"] = "2560",
            }));

        Assert.Throws<ArgumentException>(() => VisualTestHarnessRules.Parse(
            new Dictionary<string, string?>
            {
                ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
                ["STARDEW_AI_NPC_VISUAL_BACKBUFFER_WIDTH"] = "128",
                ["STARDEW_AI_NPC_VISUAL_BACKBUFFER_HEIGHT"] = "1528",
            }));
    }

    [Fact]
    public void UnsafeSaveNameFailsClosed()
    {
        Assert.Throws<ArgumentException>(() => VisualTestHarnessRules.Parse(
            new Dictionary<string, string?>
            {
                ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
                ["STARDEW_AI_NPC_VISUAL_SAVE_NAME"] = "..\\other-save",
                ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
            }));
    }

    [Fact]
    public void GameModeThreeWithLoadedWorldIsReadyWithoutSmapiWorldFlag()
    {
        Assert.True(VisualTestHarnessRules.IsGameReady(gameMode: 3, hasPlayer: true, hasLocation: true));
        Assert.False(VisualTestHarnessRules.IsGameReady(gameMode: 6, hasPlayer: true, hasLocation: true));
        Assert.False(VisualTestHarnessRules.IsGameReady(gameMode: 3, hasPlayer: false, hasLocation: true));
    }

    [Fact]
    public void GameReadyRequiresVanillaLoadedGameFlag()
    {
        Assert.False(VisualTestHarnessRules.IsGameReady(
            gameMode: 3,
            hasPlayer: true,
            hasLocation: true,
            hasLoadedGame: false));
        Assert.True(VisualTestHarnessRules.IsGameReady(
            gameMode: 3,
            hasPlayer: true,
            hasLocation: true,
            hasLoadedGame: true));
    }

    [Fact]
    public void MenuCannotOpenUntilWorldHasBeenStable()
    {
        Assert.False(VisualTestHarnessRules.CanOpenMenu(
            loadGateSatisfied: false,
            fadeClear: true,
            menuOpened: false,
            gameReady: true,
            ticks: 100,
            openAtTick: 90));
        Assert.True(VisualTestHarnessRules.CanOpenMenu(
            loadGateSatisfied: true,
            fadeClear: true,
            menuOpened: false,
            gameReady: true,
            ticks: 100,
            openAtTick: 90));
        Assert.False(VisualTestHarnessRules.CanOpenMenu(
            loadGateSatisfied: true,
            fadeClear: false,
            menuOpened: false,
            gameReady: true,
            ticks: 100,
            openAtTick: 90));
    }
}
