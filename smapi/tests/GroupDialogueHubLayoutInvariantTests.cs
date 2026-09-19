using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 群聊中心（F9 入口菜单）布局的几何不变量。
///
/// 已有的 <c>GroupDialogueHubLayoutRulesTests</c> 只覆盖 1280×720 一个视口，
/// 这里补上跨视口的不变量与小视口的已知限制，思路与
/// <c>GroupDialogueLayoutInvariantTests</c> 一致：不钉像素，只钉必须成立的关系。
/// </summary>
public sealed class GroupDialogueHubLayoutInvariantTests
{
    /// <summary>布局充裕、两个底部按钮应当互不重叠的视口。</summary>
    public static TheoryData<int, int> RoomyViewports => new()
    {
        { 1280, 720 },
        { 1920, 1080 },
        { 2560, 1440 },
        { 3840, 2160 },
    };

    /// <summary>从极小到两种长条，只要求“不崩且尺寸合法”。</summary>
    public static TheoryData<int, int> AllViewports => new()
    {
        { 320, 240 },
        { 640, 480 },
        { 1280, 720 },
        { 1920, 1080 },
        { 3840, 2160 },
        { 800, 2000 },
        { 2000, 600 },
    };

    [Theory]
    [MemberData(nameof(AllViewports))]
    public void Panel_stays_inside_the_viewport_and_is_centred(int width, int height)
    {
        var layout = GroupDialogueHubLayoutRules.Calculate(width, height);
        var panel = layout.Panel;

        Assert.True(panel.Left >= 0, $"面板越出左边界: {panel}");
        Assert.True(panel.Top >= 0, $"面板越出上边界: {panel}");
        Assert.True(panel.Right <= width, $"面板越出右边界: {panel}");
        Assert.True(panel.Bottom <= height, $"面板越出下边界: {panel}");
        Assert.Equal((width - panel.Width) / 2, panel.X);
        Assert.Equal((height - panel.Height) / 2, panel.Y);
    }

    [Theory]
    [MemberData(nameof(AllViewports))]
    public void Every_rectangle_has_a_positive_size(int width, int height)
    {
        var layout = GroupDialogueHubLayoutRules.Calculate(width, height);

        foreach (var rectangle in new[] { layout.Panel, layout.FreeStartButton, layout.CloseButton })
        {
            Assert.True(rectangle.Width >= 1, $"宽度非法: {rectangle}");
            Assert.True(rectangle.Height >= 1, $"高度非法: {rectangle}");
        }
    }

    [Theory]
    [MemberData(nameof(RoomyViewports))]
    public void Footer_buttons_are_inside_the_panel_and_do_not_overlap(int width, int height)
    {
        var layout = GroupDialogueHubLayoutRules.Calculate(width, height);

        Assert.True(layout.FreeStartButton.Left >= layout.Panel.Left);
        Assert.True(layout.CloseButton.Right <= layout.Panel.Right);
        Assert.True(layout.FreeStartButton.Bottom <= layout.Panel.Bottom);
        Assert.True(layout.CloseButton.Bottom <= layout.Panel.Bottom);
        Assert.True(
            layout.FreeStartButton.Right <= layout.CloseButton.Left,
            $"两个按钮重叠: freeStart={layout.FreeStartButton}, close={layout.CloseButton}");
        // 同一行、同一高度
        Assert.Equal(layout.FreeStartButton.Y, layout.CloseButton.Y);
        Assert.Equal(layout.FreeStartButton.Height, layout.CloseButton.Height);
    }

    [Fact]
    public void Narrow_viewports_overlap_the_two_buttons_which_is_a_known_limitation()
    {
        // 放下“左侧 220 + 右侧 148 + 各自边距”需要面板宽度 ≥ 432，
        // 而 320 宽时面板只有 272（被裁到视口内），两个按钮必然重叠。
        // 若这条断言开始失败，说明布局已改善，请更新本契约。
        var layout = GroupDialogueHubLayoutRules.Calculate(320, 240);

        Assert.True(
            layout.FreeStartButton.Right > layout.CloseButton.Left,
            "窄视口下按钮不再重叠，说明布局逻辑变了，请更新本测试");
    }

    [Fact]
    public void Very_short_viewports_place_the_buttons_above_the_panel_which_is_a_known_limitation()
    {
        // 400×120 时面板高度被裁到 72，而按钮行的 y 固定取 panel.Bottom - 76，
        // 于是整行落到面板顶边之上——与上一条同源，都是小视口退化。
        // 若这条开始失败，说明小视口布局已改善，请更新本契约。
        var layout = GroupDialogueHubLayoutRules.Calculate(400, 120);

        Assert.True(
            layout.FreeStartButton.Top < layout.Panel.Top,
            "极矮视口下按钮不再越出面板，说明布局逻辑变了，请更新本测试");
    }
}
