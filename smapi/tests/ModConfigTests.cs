using StardewAI.NPC;
using StardewModdingAPI;
using StardewModdingAPI.Utilities;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ModConfigTests
{
    [Fact]
    public void Default_dialogue_key_is_F8()
    {
        var config = new ModConfig();

        Assert.Equal("F8", config.DialogueKey.ToString());
        Assert.True(config.DialogueKey.IsBound);
        Assert.Equal(SButton.F8, config.DialogueKey.Keybinds.Single().Buttons.Single());
        Assert.True(config.EnableDialogue);
        Assert.False(config.EnablePerformanceDiagnostics);
        Assert.Equal("http://127.0.0.1:5678", config.BridgeEndpoint);
        Assert.Equal(60, config.BridgeTimeoutSeconds);
    }

    [Fact]
    public void Default_group_dialogue_key_is_F9()
    {
        var config = new ModConfig();

        Assert.Equal(SButton.F9, config.GroupDialogueKey.Keybinds.Single().Buttons.Single());
    }

    [Fact]
    public void Group_dialogue_strategy_defaults_to_multi_turn()
    {
        var config = new ModConfig();

        Assert.Equal("multi_turn", config.GroupDialogueStrategy);
        Assert.Equal("multi_turn", config.Normalize().GroupDialogueStrategy);
    }

    [Theory]
    [InlineData("turn_based", "turn_based")]
    [InlineData("TURN_BASED", "turn_based")]
    [InlineData("multi_turn", "multi_turn")]
    [InlineData("fanout", "multi_turn")]
    [InlineData("", "multi_turn")]
    [InlineData("   ", "multi_turn")]
    public void Group_dialogue_strategy_normalizes_to_a_supported_value(
        string value,
        string expected)
    {
        var config = new ModConfig { GroupDialogueStrategy = value };

        Assert.Equal(expected, config.Normalize().GroupDialogueStrategy);
    }

    [Fact]
    public void Group_dialogue_key_cannot_share_the_single_dialogue_key()
    {
        var config = new ModConfig
        {
            DialogueKey = KeybindList.Parse("F9"),
            GroupDialogueKey = KeybindList.Parse("F9"),
        };

        var normalized = config.Normalize();

        Assert.Equal(SButton.F9, normalized.DialogueKey.Keybinds.Single().Buttons.Single());
        Assert.Equal(SButton.F10, normalized.GroupDialogueKey.Keybinds.Single().Buttons.Single());
    }

    [Fact]
    public void Valid_custom_dialogue_key_is_resolved()
    {
        var config = new ModConfig { DialogueKey = KeybindList.Parse("F9") };

        var normalized = config.Normalize();

        Assert.Equal(SButton.F9, normalized.DialogueKey.Keybinds.Single().Buttons.Single());
    }

    [Fact]
    public void Invalid_dialogue_key_falls_back_to_F8()
    {
        Assert.False(KeybindList.TryParse("not-a-button", out _, out _));

        var config = new ModConfig { DialogueKey = new KeybindList() };

        Assert.Equal(SButton.F8, config.Normalize().DialogueKey.Keybinds.Single().Buttons.Single());
    }

    [Fact]
    public void Invalid_endpoint_and_timeout_fall_back_to_safe_defaults()
    {
        var config = new ModConfig
        {
            BridgeEndpoint = "https://example.com/api",
            BridgeTimeoutSeconds = -1,
        };

        var normalized = config.Normalize();

        Assert.Equal("http://127.0.0.1:5678", normalized.BridgeEndpoint);
        Assert.Equal(60, normalized.BridgeTimeoutSeconds);
    }

    [Fact]
    public void Valid_endpoint_and_timeout_are_preserved()
    {
        var config = new ModConfig
        {
            BridgeEndpoint = "https://127.0.0.1:6000/base",
            BridgeTimeoutSeconds = 30,
        };

        var normalized = config.Normalize();

        Assert.Equal("https://127.0.0.1:6000/base", normalized.BridgeEndpoint);
        Assert.Equal(30, normalized.BridgeTimeoutSeconds);
    }

    [Fact]
    public void Reset_returns_a_new_default_config_without_mutating_current_config()
    {
        var config = new ModConfig { EnableDialogue = false, BridgeTimeoutSeconds = 60 };

        var reset = ModConfig.CreateDefault();

        Assert.False(config.EnableDialogue);
        Assert.Equal(60, config.BridgeTimeoutSeconds);
        Assert.True(reset.EnableDialogue);
        Assert.Equal(60, reset.BridgeTimeoutSeconds);
        Assert.True(reset.EnableHouseAccess);
        Assert.True(reset.AllowMixedBuildingAccess);
    }

    [Fact]
    public void Normalize_preserves_explicit_house_access_options()
    {
        var normalized = new ModConfig
        {
            EnableHouseAccess = true,
            AllowMixedBuildingAccess = true,
        }.Normalize();

        Assert.True(normalized.EnableHouseAccess);
        Assert.True(normalized.AllowMixedBuildingAccess);
    }

    [Fact]
    public void Normalize_preserves_performance_diagnostics_option()
    {
        var normalized = new ModConfig { EnablePerformanceDiagnostics = true }.Normalize();

        Assert.True(normalized.EnablePerformanceDiagnostics);
    }
}
