using Microsoft.Xna.Framework;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class MenuViewportRulesTests
{
    [Fact]
    public void PreferUiViewport_uses_ui_coordinates_when_back_buffer_viewport_differs()
    {
        var size = MenuViewportRules.PreferUiViewport(
            viewportWidth: 1280,
            viewportHeight: 896,
            uiViewportWidth: 1280,
            uiViewportHeight: 720);

        Assert.Equal(new Point(1280, 720), size);
    }

    [Fact]
    public void PreferUiViewport_falls_back_to_game_viewport_when_ui_viewport_is_unavailable()
    {
        var size = MenuViewportRules.PreferUiViewport(
            viewportWidth: 1280,
            viewportHeight: 720,
            uiViewportWidth: 0,
            uiViewportHeight: 0);

        Assert.Equal(new Point(1280, 720), size);
    }
}
