using StardewAI.NPC;
using Microsoft.Xna.Framework;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 审计 #38：四个菜单的面板放置规则收敛到一处之后的等价性与边界。
/// </summary>
public sealed class MenuPanelRulesTests
{
    [Fact]
    public void Safe_margin_matches_the_value_every_menu_used_before()
    {
        Assert.Equal(24, MenuPanelRules.SafeMargin);
    }

    [Fact]
    public void Panel_is_centred_without_floating_point_rounding()
    {
        Assert.Equal(
            new Rectangle(240, 60, 800, 600),
            MenuPanelRules.CenteredInViewport(1280, 720, 800, 600, floorOriginAtZero: false));
    }

    [Fact]
    public void Odd_remainders_are_truncated_towards_zero_like_the_original_integer_division()
    {
        // (1281 - 800) / 2 == 240（整数除法，改前也是这个结果）
        Assert.Equal(
            new Rectangle(240, 60, 800, 600),
            MenuPanelRules.CenteredInViewport(1281, 721, 800, 600, floorOriginAtZero: false));
    }

    [Fact]
    public void Floor_origin_mode_clamps_a_panel_larger_than_the_viewport()
    {
        Assert.Equal(
            new Rectangle(0, 0, 300, 300),
            MenuPanelRules.CenteredInViewport(100, 100, 300, 300, floorOriginAtZero: true));
    }

    [Fact]
    public void Non_floored_mode_keeps_the_negative_origin_of_the_chat_and_inventory_menus()
    {
        // 私聊与物品选择器改前不做 Max(0, …)，极小视口下的负原点必须原样保留。
        Assert.Equal(
            new Rectangle(-100, -100, 300, 300),
            MenuPanelRules.CenteredInViewport(100, 100, 300, 300, floorOriginAtZero: false));
    }

    [Theory]
    [InlineData(0, 720, "viewportWidth")]
    [InlineData(-1, 720, "viewportWidth")]
    [InlineData(1280, 0, "viewportHeight")]
    [InlineData(1280, -5, "viewportHeight")]
    public void Non_positive_viewports_are_rejected_with_the_original_parameter_name(
        int width,
        int height,
        string expectedParameter)
    {
        var exception = Assert.Throws<ArgumentOutOfRangeException>(
            () => MenuPanelRules.CenteredInViewport(width, height, 800, 600, floorOriginAtZero: true));

        Assert.Equal(expectedParameter, exception.ParamName);
    }
}
