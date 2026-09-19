using Microsoft.Xna.Framework;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupDialogueHubLayoutRulesTests
{
    [Fact]
    public void Layout_recomputes_panel_position_when_ui_viewport_changes()
    {
        var tall = GroupDialogueHubLayoutRules.Calculate(1280, 896);
        var compact = GroupDialogueHubLayoutRules.Calculate(1280, 720);

        Assert.Equal(108, tall.Panel.Y);
        Assert.Equal(24, compact.Panel.Y);
        Assert.NotEqual(tall.Panel, compact.Panel);
    }

    [Fact]
    public void Layout_keeps_footer_controls_inside_panel()
    {
        var layout = GroupDialogueHubLayoutRules.Calculate(1280, 720);

        Assert.True(layout.FreeStartButton.Bottom <= layout.Panel.Bottom);
        Assert.True(layout.CloseButton.Bottom <= layout.Panel.Bottom);
        Assert.True(layout.FreeStartButton.Left >= layout.Panel.Left);
        Assert.True(layout.CloseButton.Right <= layout.Panel.Right);
    }
}
