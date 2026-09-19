using Microsoft.Xna.Framework;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// <c>ChatScrollRules</c> 的边界：滚动位置必须被夹在合法区间内，
/// 且 <c>MoveStartIndex</c> 要能吃下加法的整数溢出——实现里刻意用 <c>long</c> 中转后再夹回
/// <c>int</c> 范围，但原有的两条测试只覆盖了常规路径。
/// </summary>
public sealed class ChatScrollRulesEdgeTests
{
    [Theory]
    [InlineData(-1)]
    [InlineData(-100)]
    public void Negative_max_start_index_is_rejected(int maxStartIndex)
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => ChatScrollRules.ClampStartIndex(0, maxStartIndex));
        Assert.Throws<ArgumentOutOfRangeException>(
            () => ChatScrollRules.MoveStartIndex(0, 1, maxStartIndex));
    }

    [Fact]
    public void Zero_max_start_index_pins_to_the_only_position()
    {
        // 历史为空时只有位置 0 合法。
        Assert.Equal(0, ChatScrollRules.ClampStartIndex(5, 0));
        Assert.Equal(0, ChatScrollRules.MoveStartIndex(5, -3, 0));
        Assert.Equal(0, ChatScrollRules.MoveStartIndex(5, 3, 0));
    }

    [Fact]
    public void Move_start_index_survives_integer_overflow()
    {
        // 往上滚到 int.MaxValue 再加、往下滚到 int.MinValue 再减：都不应抛异常，
        // 结果仍要被夹回合法区间。
        Assert.Equal(10, ChatScrollRules.MoveStartIndex(int.MaxValue, 5, 10));
        Assert.Equal(0, ChatScrollRules.MoveStartIndex(int.MinValue, -5, 10));
    }

    [Fact]
    public void Move_start_index_with_zero_delta_keeps_the_clamped_position()
    {
        Assert.Equal(3, ChatScrollRules.MoveStartIndex(3, 0, 10));
        Assert.Equal(10, ChatScrollRules.MoveStartIndex(99, 0, 10));
    }
}

/// <summary>
/// <c>MenuViewportRules.PreferUiViewport</c> 的边界：UI 视口要**宽高都为正**才会被采用，
/// 只有一边有效时必须回退到游戏视口；两者都不可用时抛错，而不是返回 (0, 0)。
/// </summary>
public sealed class MenuViewportRulesEdgeTests
{
    [Theory]
    [InlineData(0, 720)]
    [InlineData(1280, 0)]
    [InlineData(-1, 720)]
    [InlineData(1280, -1)]
    [InlineData(0, 0)]
    public void Partially_valid_ui_viewport_falls_back_to_the_game_viewport(
        int uiWidth,
        int uiHeight)
    {
        var size = MenuViewportRules.PreferUiViewport(1920, 1080, uiWidth, uiHeight);

        Assert.Equal(new Point(1920, 1080), size);
    }

    [Fact]
    public void Ui_viewport_wins_when_both_dimensions_are_positive()
    {
        var size = MenuViewportRules.PreferUiViewport(1920, 1080, 1280, 720);

        Assert.Equal(new Point(1280, 720), size);
    }

    [Theory]
    [InlineData(0, 1080)]
    [InlineData(1920, 0)]
    [InlineData(-1, -1)]
    [InlineData(0, 0)]
    public void Throws_when_neither_viewport_is_usable(int gameWidth, int gameHeight)
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => MenuViewportRules.PreferUiViewport(gameWidth, gameHeight, 0, 0));
    }
}
