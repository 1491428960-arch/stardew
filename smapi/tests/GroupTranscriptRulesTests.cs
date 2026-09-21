using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 群聊面板的**显示时序**规则（2026-09-21 用户口径）：
/// 玩家发言立刻上屏、NPC 回复逐条出现、**对话进行中也能往上翻记录**。
///
/// 翻页这件事最容易出错的地方不是算术（那仍然只有
/// <see cref="GroupReadOnlyRules.VisibleWindow"/> 一份），而是**新消息进来时视口该不该动**：
/// 玩家翻上去之后若被新消息拽回底部，翻页等于没翻。下面把三种情况分开钉死。
/// </summary>
public sealed class GroupTranscriptRulesTests
{
    private const int MaxVisible = GroupDialogueLayoutRules.MaxVisibleMessages;

    /// <summary>把「面板看到的这一屏」翻译成一个便于断言的字符串，失败信息一眼能读。</summary>
    private static string Window(bool followLatest, int scrollStartIndex, int totalCount)
    {
        var (start, count) = GroupReadOnlyRules.VisibleWindow(
            totalCount,
            MaxVisible,
            GroupTranscriptRules.WindowStartIndex(followLatest, scrollStartIndex));
        return $"{start}+{count}";
    }

    [Fact]
    public void The_reveal_interval_sits_between_unnoticeable_and_annoying()
    {
        // 0.2 秒以下人眼分不出先后（等于没做），1 秒以上 4 条要多等 4 秒（会烦）。
        Assert.InRange(GroupTranscriptRules.TurnRevealIntervalSeconds, 0.25d, 0.8d);
    }

    [Fact]
    public void Fast_forward_is_almost_instant_but_not_a_jump()
    {
        // 「加速」与「跳过」是两件事：按住 Shift 时留一点间隔，让
        // 「这是几条不同的发言」仍然看得出来；一次到位那条路由鼠标点击消息区负责。
        Assert.InRange(GroupTranscriptRules.FastForwardIntervalSeconds, 0.01d, 0.15d);
        Assert.True(
            GroupTranscriptRules.FastForwardIntervalSeconds <
            GroupTranscriptRules.TurnRevealIntervalSeconds);
    }

    [Theory]
    [InlineData(false, true)]
    [InlineData(true, false)]
    public void A_read_only_transcript_is_never_played_back_turn_by_turn(
        bool readOnly,
        bool expected)
    {
        // 回看已经结束的那一场时一次看全（用户倾向），只有真实对话才逐条播。
        Assert.Equal(expected, GroupTranscriptRules.ShouldRevealOneByOne(readOnly));
    }

    // ── 情况一：玩家在看历史，新消息**不能**把他拽回底部 ────────────────────

    [Fact]
    public void A_new_message_does_not_drag_the_viewport_back_to_the_bottom()
    {
        const int scrolledFrom = 10;
        var before = Window(followLatest: false, scrolledFrom, totalCount: 34);
        Assert.Equal("10+10", before);

        // 视口外又来了 3 条（这一场变成 37 条）。
        var after = Window(followLatest: false, scrolledFrom, totalCount: 37);

        Assert.Equal(before, after);
    }

    [Fact]
    public void The_same_new_message_would_drag_a_following_viewport()
    {
        // 反例（防「新测试恒真」）：若还开着「跟随最新」，同一次新增就会把视口挪到末尾。
        // 两个结果不同，正说明「不拽回」是靠 followLatest 这个显式状态撑起来的，
        // 而不是碰巧算出来的。
        Assert.Equal("24+10", Window(followLatest: true, scrollStartIndex: 10, totalCount: 34));
        Assert.Equal("27+10", Window(followLatest: true, scrollStartIndex: 10, totalCount: 37));
    }

    // ── 情况二：玩家在底部，照常跟随 ────────────────────────────────────────

    [Fact]
    public void A_following_viewport_keeps_showing_the_newest_lines()
    {
        Assert.Equal("24+10", Window(followLatest: true, scrollStartIndex: 0, totalCount: 34));
        Assert.Equal("25+10", Window(followLatest: true, scrollStartIndex: 0, totalCount: 35));
    }

    // ── 情况三：自己发言 → 自动回到底部 ────────────────────────────────────

    [Fact]
    public void Speaking_again_puts_the_viewport_back_at_the_bottom()
    {
        // SendCurrentAsync 会把 followLatest 重新打开（他想看回复）。
        var (_, followLatest) = GroupTranscriptRules.Scroll(
            followLatest: true,
            scrollStartIndex: 10,
            direction: -1,
            totalCount: 34,
            maxVisible: MaxVisible);

        Assert.True(followLatest);
        Assert.Equal("24+10", Window(followLatest, scrollStartIndex: 10, totalCount: 34));
    }

    // ── 翻页本身 ───────────────────────────────────────────────────────────

    [Fact]
    public void Scrolling_up_from_the_bottom_stops_following()
    {
        var (start, followLatest) = GroupTranscriptRules.Scroll(
            followLatest: true,
            scrollStartIndex: 0,
            direction: 1,
            totalCount: 34,
            maxVisible: MaxVisible);

        Assert.Equal(23, start);
        Assert.False(followLatest);
    }

    [Fact]
    public void Scrolling_back_down_to_the_bottom_resumes_following()
    {
        var (start, followLatest) = GroupTranscriptRules.Scroll(
            followLatest: false,
            scrollStartIndex: 23,
            direction: -1,
            totalCount: 34,
            maxVisible: MaxVisible);

        Assert.Equal(24, start);
        Assert.True(followLatest);
    }

    [Fact]
    public void Scrolling_above_the_top_stops_at_the_first_line()
    {
        var (start, followLatest) = GroupTranscriptRules.Scroll(
            followLatest: false,
            scrollStartIndex: 0,
            direction: 1,
            totalCount: 34,
            maxVisible: MaxVisible);

        Assert.Equal(0, start);
        Assert.False(followLatest);
    }

    [Fact]
    public void A_transcript_that_fits_on_one_screen_has_nothing_to_scroll()
    {
        // 装得下时不接管滚轮（可发言时交回原版），且保持跟随。
        var (start, followLatest) = GroupTranscriptRules.Scroll(
            followLatest: false,
            scrollStartIndex: 5,
            direction: 1,
            totalCount: 6,
            maxVisible: MaxVisible);

        Assert.Equal(0, start);
        Assert.True(followLatest);
    }

    [Fact]
    public void A_zero_direction_wheel_event_changes_nothing()
    {
        var (_, followLatest) = GroupTranscriptRules.Scroll(
            followLatest: false,
            scrollStartIndex: 11,
            direction: 0,
            totalCount: 34,
            maxVisible: MaxVisible);

        Assert.True(followLatest);
    }

    [Fact]
    public void An_empty_transcript_is_scrollable_in_name_only()
    {
        var (start, followLatest) = GroupTranscriptRules.Scroll(
            followLatest: false,
            scrollStartIndex: 3,
            direction: 1,
            totalCount: 0,
            maxVisible: MaxVisible);

        Assert.Equal(0, start);
        Assert.True(followLatest);
    }

    // ── 提示行 ─────────────────────────────────────────────────────────────

    [Fact]
    public void The_hint_reports_the_visible_range_and_how_to_get_back()
    {
        var hint = GroupTranscriptRules.ChatScrollHintText(
            start: 10,
            count: 10,
            totalCount: 37,
            newMessageCount: 0);

        Assert.Equal("第 11–20 条 / 共 37 条；滚轮往上翻看更早的，End 回到底部", hint);
    }

    /// <summary>
    /// 玩家在看历史时来了新消息，**要提示**。理由：视口外的内容他看不见，
    /// 没有信号就不知道该不该翻回来——那等于把「翻页」做成了「看不见」。
    /// 提示落在**已有的那一行**（标题旁，放不下时回落到消息区下方的留白），
    /// 不覆盖任何气泡，所以不需要新开浮层。
    /// </summary>
    [Fact]
    public void New_lines_arriving_while_scrolled_are_announced()
    {
        var hint = GroupTranscriptRules.ChatScrollHintText(
            start: 10,
            count: 10,
            totalCount: 40,
            newMessageCount: 3);

        Assert.Equal(
            "第 11–20 条 / 共 40 条；↓ 下面还有 3 条新消息（End 或滚到底回到底部）",
            hint);
    }

    [Fact]
    public void An_empty_transcript_has_no_hint_to_show()
    {
        Assert.Equal(
            string.Empty,
            GroupTranscriptRules.ChatScrollHintText(0, 0, 0, 0));
    }

    [Theory]
    // 边界：起点落在末尾时 first/last 不能越界，也不能抛（与只读那份同一个理由）。
    [InlineData(36, 10, 37)]
    [InlineData(999, 10, 37)]
    [InlineData(-3, 10, 37)]
    public void The_hint_clamps_its_range_instead_of_throwing(int start, int count, int total)
    {
        var hint = GroupTranscriptRules.ChatScrollHintText(start, count, total, 0);

        Assert.StartsWith("第 ", hint, StringComparison.Ordinal);
        Assert.Contains($"共 {total} 条", hint, StringComparison.Ordinal);
    }
}
