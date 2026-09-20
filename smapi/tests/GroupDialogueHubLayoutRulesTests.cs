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

        Assert.True(layout.CloseButton.Bottom <= layout.Panel.Bottom);
        Assert.True(layout.CloseButton.Right <= layout.Panel.Right);
    }

    /// <summary>
    /// 审计 #38：面板放置改用 <see cref="MenuPanelRules.CenteredInViewport"/> 之后，
    /// 多人对话中心的面板矩形必须与改动前逐值相同（边距由字面量 48 改为共享常量 ×2）。
    /// </summary>
    [Fact]
    public void Panel_rectangle_is_unchanged_after_the_shared_placement_refactor()
    {
        Assert.Equal(
            new Rectangle(100, 24, 1080, 672),
            GroupDialogueHubLayoutRules.Calculate(1280, 720).Panel);
        Assert.Equal(
            new Rectangle(100, 108, 1080, 680),
            GroupDialogueHubLayoutRules.Calculate(1280, 896).Panel);
    }
}
