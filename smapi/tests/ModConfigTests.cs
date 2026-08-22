using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ModConfigTests
{
    [Fact]
    public void Default_dialogue_key_is_F8()
    {
        var config = new ModConfig();

        Assert.Equal("F8", config.DialogueKey);
        Assert.Equal(TestButton.F8, ModConfig.ParseDialogueKey(config.DialogueKey, TestButton.F8));
    }

    [Fact]
    public void Valid_custom_dialogue_key_is_resolved()
    {
        var config = new ModConfig { DialogueKey = "F9" };

        Assert.Equal(TestButton.F9, ModConfig.ParseDialogueKey(config.DialogueKey, TestButton.F8));
    }

    [Fact]
    public void Invalid_dialogue_key_falls_back_to_F8()
    {
        var config = new ModConfig { DialogueKey = "not-a-button" };

        Assert.Equal(TestButton.F8, ModConfig.ParseDialogueKey(config.DialogueKey, TestButton.F8));
    }

    private enum TestButton
    {
        F8,
        F9,
    }
}
