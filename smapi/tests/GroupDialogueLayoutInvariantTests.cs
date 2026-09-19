using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 群聊菜单布局的几何不变量。
///
/// <c>GroupDialogueLayoutRules.Calculate</c> 决定面板、消息区与三个按钮的实际坐标，
/// 但此前只测了“非法视口抛异常”一条，79 行的布局计算**没有任何覆盖**。
/// 这里不钉死具体像素（那会变得又脆又难维护），而是钉住**任何视口下都必须成立的关系**，
/// 并把小视口下的已知限制写成可检测的契约。
/// </summary>
public sealed class GroupDialogueLayoutInvariantTests
{
    /// <summary>布局充裕、按钮应当严格排列的视口。</summary>
    public static TheoryData<int, int> RoomyViewports => new()
    {
        { 1280, 720 },
        { 1920, 1080 },
        { 2560, 1440 },
        { 3840, 2160 },
    };

    /// <summary>从极小到竖长条、横长条，只要求“不崩且尺寸合法”。</summary>
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
        var layout = GroupDialogueLayoutRules.Calculate(width, height);
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
        var layout = GroupDialogueLayoutRules.Calculate(width, height);

        var rectangles = new[]
        {
            layout.Panel,
            layout.Header,
            layout.ParticipantStrip,
            layout.MessageArea,
            layout.InputBox,
            layout.SendButton,
            layout.RetryButton,
            layout.CloseButton,
        };

        foreach (var rectangle in rectangles)
        {
            Assert.True(rectangle.Width >= 1, $"宽度非法: {rectangle}");
            Assert.True(rectangle.Height >= 1, $"高度非法: {rectangle}");
        }
    }

    [Theory]
    [MemberData(nameof(AllViewports))]
    public void Header_message_area_and_footer_are_stacked_inside_the_panel(int width, int height)
    {
        var layout = GroupDialogueLayoutRules.Calculate(width, height);

        // 头部贴住面板顶部、与面板同宽
        Assert.Equal(layout.Panel.Top, layout.Header.Top);
        Assert.Equal(layout.Panel.Left, layout.Header.Left);
        Assert.Equal(layout.Panel.Width, layout.Header.Width);
        // 消息区紧接头部下方
        Assert.Equal(layout.Header.Bottom, layout.MessageArea.Top);
        // 输入框在面板内部
        Assert.True(layout.InputBox.Left >= layout.Panel.Left);
        Assert.True(layout.InputBox.Right <= layout.Panel.Right);
        Assert.True(layout.InputBox.Bottom <= layout.Panel.Bottom);
    }

    [Theory]
    [MemberData(nameof(RoomyViewports))]
    public void Action_buttons_are_right_aligned_and_ordered(int width, int height)
    {
        var layout = GroupDialogueLayoutRules.Calculate(width, height);

        // 关闭贴右边界，重试在它左边，发送再往左，彼此留出间隔。
        // 不钉死具体内边距（纯视觉微调不该让测试失败），只要求“贴右但留出边”。
        Assert.True(layout.CloseButton.Right <= layout.Panel.Right);
        Assert.True(layout.CloseButton.Right > layout.Panel.Right - 80);
        Assert.True(layout.RetryButton.Right < layout.CloseButton.Left);
        Assert.True(layout.SendButton.Right < layout.RetryButton.Left);
        // 三个按钮同高、同排
        Assert.Equal(layout.CloseButton.Y, layout.RetryButton.Y);
        Assert.Equal(layout.CloseButton.Y, layout.SendButton.Y);
        Assert.Equal(layout.CloseButton.Height, layout.SendButton.Height);
        // 输入框在发送按钮左侧，不与它重叠
        Assert.True(layout.InputBox.Right <= layout.SendButton.Left);
    }

    [Theory]
    // 只在布局充裕的视口下要求“不重叠”：极端小视口里消息区会被压到 1 像素高、
    // 与按钮行同高（见文末的已知限制测试）。
    [MemberData(nameof(RoomyViewports))]
    public void Message_area_never_overlaps_the_footer(int width, int height)
    {
        var layout = GroupDialogueLayoutRules.Calculate(width, height);

        Assert.True(
            layout.MessageArea.Bottom <= layout.RetryButton.Top,
            $"消息区与按钮行重叠: messageArea={layout.MessageArea}, retry={layout.RetryButton}");
    }

    [Fact]
    public void Tiny_viewports_overflow_the_footer_which_is_a_known_limitation()
    {
        // 320×240 下面板只有 272 宽，而三个 88 宽的按钮加间隔需要 280——
        // 发送按钮因此被排到面板左边界之外，输入框也会与它重叠；
        // 同时消息区高度被压到下限 1 像素，与按钮行同高。
        // 这些都不是崩溃（尺寸仍为正、面板仍居中），属于已知限制。
        // 若下面两条断言开始失败，说明小视口布局已被改善，请更新本测试。
        var layout = GroupDialogueLayoutRules.Calculate(320, 240);

        Assert.True(
            layout.SendButton.Left < layout.Panel.Left,
            "小视口下按钮已不再溢出，说明布局逻辑变了，请更新这条契约");
        Assert.True(layout.InputBox.Right > layout.SendButton.Left);
        Assert.Equal(1, layout.MessageArea.Height);
    }
}
