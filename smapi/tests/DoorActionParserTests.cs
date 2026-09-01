using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class DoorActionParserTests
{
    [Fact]
    public void Parses_locked_door_warp_with_optional_resident_requirement()
    {
        var parsed = DoorActionParser.TryParse(
            "LockedDoorWarp 5 9 FishShop 900 1700 Willy 500",
            out var action);

        Assert.True(parsed);
        Assert.NotNull(action);
        Assert.Equal(5, action.DestinationX);
        Assert.Equal(9, action.DestinationY);
        Assert.Equal("FishShop", action.TargetLocationName);
        Assert.Equal(900, action.OpenTime);
        Assert.Equal(1700, action.CloseTime);
        Assert.Equal("Willy", action.RequiredNpcId);
        Assert.Equal(500, action.MinimumFriendship);
    }

    [Fact]
    public void Parses_locked_door_warp_without_optional_requirement()
    {
        var parsed = DoorActionParser.TryParse(
            "LockedDoorWarp 20 41 Custom_AndyHouse 800 2200",
            out var action);

        Assert.True(parsed);
        Assert.NotNull(action);
        Assert.Null(action.RequiredNpcId);
        Assert.Null(action.MinimumFriendship);
    }

    [Theory]
    [InlineData("")]
    [InlineData("Warp 5 9 FishShop 900 1700")]
    [InlineData("LockedDoorWarp 5 9 FishShop")]
    [InlineData("LockedDoorWarp x 9 FishShop 900 1700")]
    [InlineData("LockedDoorWarp 5 9 FishShop 900 1700 Willy nope")]
    public void Rejects_invalid_door_actions_without_throwing(
        string actionText)
    {
        Assert.False(DoorActionParser.TryParse(actionText, out var action));
        Assert.Null(action);
    }

    [Fact]
    public void Parses_and_relaxes_the_actual_perform_action_token_array()
    {
        var tokens = new[]
        {
            "LockedDoorWarp", "5", "9", "WizardHouse",
            "900", "2300", "Wizard", "500",
        };

        Assert.True(DoorActionParser.TryParse(tokens, out var action));
        Assert.NotNull(action);
        Assert.Equal("WizardHouse", action.TargetLocationName);

        Assert.True(DoorActionParser.RelaxResidentialGate(tokens));
        Assert.Equal("600", tokens[4]);
        Assert.Equal("2600", tokens[5]);
        Assert.Equal(string.Empty, tokens[6]);
        Assert.Equal("0", tokens[7]);
        Assert.Equal(new[] { "5", "9", "WizardHouse" }, tokens[1..4]);
    }

    [Theory]
    [InlineData("LockedDoorWarp", true)]
    [InlineData("Warp", true)]
    [InlineData("ConditionalDoor", true)]
    [InlineData("OpenDoor", true)]
    [InlineData("Shop", false)]
    public void Door_and_warp_actions_are_selected_for_path_diagnostics(
        string actionName,
        bool expected)
    {
        Assert.Equal(expected, DoorActionParser.IsDoorOrWarpAction(actionName));
    }
}
