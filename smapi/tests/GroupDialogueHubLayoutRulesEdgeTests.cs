using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// <c>GroupDialogueHubLayoutRules.Calculate</c> 的入参校验与面板尺寸上限。
/// 几何不变量（面板在视口内、居中、正尺寸、按钮不重叠、窄视口重叠的已知限制）
/// 已由 <c>GroupDialogueHubLayoutInvariantTests</c> 跨视口覆盖，
/// 这里只补它没有碰的两件事：非正视口必须抛出，以及面板不随显示器无限放大。
/// </summary>
public sealed class GroupDialogueHubLayoutRulesEdgeTests
{
    [Theory]
    [InlineData(0, 720)]
    [InlineData(-1, 720)]
    [InlineData(int.MinValue, int.MaxValue)]
    public void Calculate_rejects_a_non_positive_viewport_width(int width, int height)
    {
        var exception = Assert.Throws<ArgumentOutOfRangeException>(
            () => GroupDialogueHubLayoutRules.Calculate(width, height));

        Assert.Equal("viewportWidth", exception.ParamName);
    }

    [Theory]
    [InlineData(1280, 0)]
    [InlineData(1280, -1)]
    public void Calculate_rejects_a_non_positive_viewport_height(int width, int height)
    {
        var exception = Assert.Throws<ArgumentOutOfRangeException>(
            () => GroupDialogueHubLayoutRules.Calculate(width, height));

        Assert.Equal("viewportHeight", exception.ParamName);
    }

    [Theory]
    [InlineData(1920, 1080)]
    [InlineData(3840, 2160)]
    public void Panel_keeps_its_maximum_size_on_large_viewports(int width, int height)
    {
        // 上限 1080×680 是设计约束：超宽屏上面板不铺满视口，
        // 否则文本行宽与两个底部按钮的位置会随显示器漂移，视觉基线就失去意义。
        var panel = GroupDialogueHubLayoutRules.Calculate(width, height).Panel;

        Assert.Equal(1080, panel.Width);
        Assert.Equal(680, panel.Height);
    }
}
