using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 群聊**只读回看**模式的规则（2026-09-21 用户口径：邀约到期后「不能继续聊，
/// 但可以点进去看记录」）。
///
/// 菜单本身要 Game1 才能构造，单元测试造不出来，所以「能不能发言」「这一屏画哪一段」
/// 全部下沉到 <see cref="GroupReadOnlyRules"/>；菜单里对这两件事只有一处调用点
/// （<c>GroupDialogueMenu.SendCurrentAsync</c> 的闸门与 <c>draw</c> 的窗口）。
/// </summary>
public sealed class GroupReadOnlyRulesTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Only_the_writable_mode_accepts_speaking(bool readOnly)
    {
        // 发送按钮、回车、重试三条路径共用这一个判据。
        Assert.Equal(!readOnly, GroupReadOnlyRules.CanSpeak(readOnly));
    }

    [Fact]
    public void A_read_only_session_rejects_every_speaking_entry_point()
    {
        // 「只读模式不能发言」：这是玩家能感知的那条不变式，判据上钉死。
        Assert.False(GroupReadOnlyRules.CanSpeak(readOnly: true));
    }

    [Fact]
    public void A_short_session_shows_every_line()
    {
        var (start, count) = GroupReadOnlyRules.VisibleWindow(totalCount: 6, maxVisible: 10, startIndex: 0);

        Assert.Equal(0, start);
        Assert.Equal(6, count);
    }

    [Fact]
    public void Following_the_latest_matches_the_take_last_behaviour()
    {
        // 可发言时这个面板一直是「最后 10 条」；只读模式的默认（跟随最新）
        // 必须与改前的 TakeLast(MaxVisibleMessages) 逐条一致。
        var (start, count) = GroupReadOnlyRules.VisibleWindow(
            totalCount: 34,
            maxVisible: 10,
            startIndex: int.MaxValue);

        Assert.Equal(24, start);
        Assert.Equal(10, count);
    }

    [Fact]
    public void Scrolling_up_shows_earlier_lines()
    {
        var (start, count) = GroupReadOnlyRules.VisibleWindow(totalCount: 34, maxVisible: 10, startIndex: 11);

        Assert.Equal(11, start);
        Assert.Equal(10, count);
    }

    [Theory]
    // 越界的起点一律夹回合法区间，绝不抛异常（存档里的场次可以很短、也可以被手改）。
    [InlineData(-5, 0)]
    [InlineData(0, 0)]
    [InlineData(24, 24)]
    [InlineData(999, 24)]
    [InlineData(int.MaxValue, 24)]
    public void The_visible_window_clamps_any_start_index(int requested, int expectedStart)
    {
        var (start, count) = GroupReadOnlyRules.VisibleWindow(34, 10, requested);

        Assert.Equal(expectedStart, start);
        Assert.Equal(10, count);
    }

    [Theory]
    [InlineData(0, 0)]
    [InlineData(-3, 0)]
    [InlineData(4, 0)]
    [InlineData(34, 24)]
    public void Max_scroll_start_never_goes_negative(int totalCount, int expected)
    {
        Assert.Equal(expected, GroupReadOnlyRules.MaxScrollStart(totalCount, 10));
    }

    [Fact]
    public void An_empty_session_draws_nothing()
    {
        Assert.Equal((0, 0), GroupReadOnlyRules.VisibleWindow(0, 10, 0));
        Assert.Equal((0, 0), GroupReadOnlyRules.VisibleWindow(5, 0, 0));
    }

    [Fact]
    public void The_input_placeholder_says_why_speaking_is_off()
    {
        // 只读的输入区画的不是输入框，而是这一行：它必须交代**原因**（这一场到期了），
        // 而不是只写「不能发言」。
        var withDeadline = GroupReadOnlyRules.InputPlaceholderText(27);
        Assert.Contains("27", withDeadline);
        Assert.Contains("只能回看", withDeadline);

        // 拿不到到期日时也要有一句能读的话，不能露出空串。
        var withoutDeadline = GroupReadOnlyRules.InputPlaceholderText(0);
        Assert.Contains("只能回看", withoutDeadline);
    }

    [Fact]
    public void The_read_only_hint_reports_how_many_lines_are_archived()
    {
        Assert.Contains("12", GroupReadOnlyRules.ReadOnlyHintText(12));
        Assert.Contains("不能再发言", GroupReadOnlyRules.ReadOnlyHintText(12));
        Assert.Contains("回看模式", GroupReadOnlyRules.ReadOnlyHintText(0));
    }

    [Fact]
    public void The_scroll_hint_reports_the_visible_slice()
    {
        var hint = GroupReadOnlyRules.ScrollHintText(start: 10, count: 10, totalCount: 34);

        Assert.Contains("第 11–20 条", hint);
        Assert.Contains("共 34 条", hint);
    }

    [Theory]
    // 起点落在末尾（或越界）时不能算出「第 35–34 条」这种反过来的区间。
    [InlineData(34, 10, 34)]
    [InlineData(999, 10, 34)]
    [InlineData(-4, 10, 34)]
    public void The_scroll_hint_survives_a_start_index_at_the_edge(
        int start,
        int count,
        int totalCount)
    {
        var hint = GroupReadOnlyRules.ScrollHintText(start, count, totalCount);

        Assert.Contains($"共 {totalCount} 条", hint);
        Assert.DoesNotContain("第 0 条", hint);
    }

    [Fact]
    public void The_scroll_hint_falls_back_when_there_is_nothing_archived()
    {
        Assert.Equal(
            GroupReadOnlyRules.ReadOnlyHintText(0),
            GroupReadOnlyRules.ScrollHintText(0, 0, 0));
    }

    [Fact]
    public void The_card_button_label_is_two_characters_like_the_other_states()
    {
        // 卡片按钮只有 64px 宽，「继续」「接受」都是两个字；「回看」也必须是两个字，
        // 否则会顶到按钮边框上（四个字的「查看记录」就会）。
        Assert.Equal(2, GroupReadOnlyRules.ActionLabel.Length);
    }
}
