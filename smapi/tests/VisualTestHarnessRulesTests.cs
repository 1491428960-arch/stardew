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
        Assert.Null(options.BackBufferWidth);
        Assert.Null(options.BackBufferHeight);
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
