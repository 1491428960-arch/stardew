using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// F9 群聊翻页的两处修正（2026-09-21 用户口径「画面装不下的那一段翻不动」）：
///
/// 1. **「一屏」从固定 10 条改成按高度算出来的容量**——
///    改前门槛是 11 条，而 720p 下 84px 单行气泡加 20px 间距只画得下 4 条，
///    于是 5～10 条这一段画面已经装不下、滚轮与 PageUp/PageDown 却全部返回 false；
/// 2. **PageUp/PageDown 改为翻一屏**（改前一次只滚 1 条，与 F8 私聊的翻页键不是一回事）。
///
/// 容量算术本身不在群聊里另写一套：调的是私聊（F8）在用的
/// <see cref="ChatTextLayoutRules.SelectLatestThatFit"/>，高度也用同一套气泡度量。
/// 这里钉住的因此只有两件事：**换算口径对不对**、**翻页门槛与步长跟不跟着它走**。
/// </summary>
public sealed class GroupDialoguePagingTests
{
    /// <summary>
    /// 单行气泡实测高度：<c>Padding*2(24) + 发言人行(28) + 行距(4) + 正文行(28)</c>。
    /// 测试不能取 <c>Game1.smallFont</c>（要 Game1 才构造得出来），所以用实测值；
    /// 与 <c>ui_preview_page.py</c> 记录的「bubble-f9.png 三个单行气泡同为 84px」互相印证。
    /// </summary>
    private const int SingleLineBubbleHeight = 84;

    /// <summary>两行正文的气泡高度（84 + 28 + 4）。</summary>
    private const int TwoLineBubbleHeight = 116;

    /// <summary>三行正文的气泡高度（116 + 28 + 4）。</summary>
    private const int ThreeLineBubbleHeight = 148;

    /// <summary>720p 下的消息区高度（<see cref="GroupDialogueLayoutRules.Calculate"/> 实算）。</summary>
    private const int MessageArea720p = 438;

    /// <summary>1080p / 1440p 下的消息区高度。</summary>
    private const int MessageArea1080p = 486;

    private const int MaxVisible = GroupDialogueLayoutRules.MaxVisibleMessages;

    /// <summary>菜单里的真实调用链：消息区高度 → 气泡区高度 → 容量。</summary>
    private static int Capacity(int messageAreaHeight, params int[] messageHeights) =>
        GroupDialogueLayoutRules.VisibleCapacity(
            GroupDialogueLayoutRules.CapacityBubbleAreaHeight(messageAreaHeight),
            messageHeights,
            MaxVisible);

    /// <summary>
    /// 菜单里 <c>ScrollBy</c> 的纯算术部分：返回「这一次按键有没有移动视口」与新的视口起点。
    /// </summary>
    private static (bool Moved, int Start, bool FollowLatest) Press(
        int totalCount,
        int capacity,
        bool followLatest,
        int scrollStartIndex,
        int direction,
        int step)
    {
        var maxStart = GroupReadOnlyRules.MaxScrollStart(totalCount, capacity);
        if (direction == 0 || maxStart <= 0)
        {
            return (false, 0, true);
        }

        var (start, followLatestAfter) = GroupTranscriptRules.Scroll(
            followLatest,
            scrollStartIndex,
            direction,
            totalCount,
            capacity,
            step);
        return (true, start, followLatestAfter);
    }

    // ── 一、容量＝按高度算，不再是固定 10 条 ────────────────────────────────

    [Fact]
    public void A_single_line_bubble_screen_holds_four_messages_not_ten()
    {
        // 改前写死 10 条；按像素算，720p 与 1080p 都只画得下 4 条。
        var heights = Enumerable.Repeat(SingleLineBubbleHeight, 20).ToArray();

        Assert.Equal(4, Capacity(MessageArea720p, heights));
        Assert.Equal(4, Capacity(MessageArea1080p, heights));
    }

    [Fact]
    public void Taller_bubbles_shrink_the_screen_the_same_way_the_old_code_could_not()
    {
        // 长回复换行占两行 / 三行时，一屏分别是 3 条与 2 条——
        // 这正是「固定 10 条」最离谱的地方：内容越长，装得下的越少，门槛却一动不动。
        Assert.Equal(3, Capacity(MessageArea720p, Enumerable.Repeat(TwoLineBubbleHeight, 20).ToArray()));
        Assert.Equal(2, Capacity(MessageArea720p, Enumerable.Repeat(ThreeLineBubbleHeight, 20).ToArray()));
    }

    [Fact]
    public void The_fixed_ten_still_caps_the_capacity_on_a_tall_screen()
    {
        // 高度足够多时回到 MaxVisibleMessages 这个上限：它是**上限**，不再冒充「一屏」。
        Assert.Equal(MaxVisible, Capacity(4096, Enumerable.Repeat(SingleLineBubbleHeight, 40).ToArray()));
    }

    [Fact]
    public void The_capacity_is_never_smaller_than_one()
    {
        // 一条消息都没有、或消息区被压到 1 像素：容量是 1 而不是 0。
        // （0 会让「只有一条」的场次也变成可滚动，那是改前没有的行为。）
        Assert.Equal(1, Capacity(MessageArea720p));
        Assert.Equal(1, Capacity(1, Enumerable.Repeat(SingleLineBubbleHeight, 10).ToArray()));
    }

    [Fact]
    public void Messages_that_draw_nothing_do_not_eat_into_the_capacity()
    {
        // 空内容的消息在 draw 里被 continue 掉、不占高度，容量算术必须同样跳过它们。
        var withEmpty = new[] { 0, 0, 0, SingleLineBubbleHeight, SingleLineBubbleHeight, SingleLineBubbleHeight, SingleLineBubbleHeight };

        Assert.Equal(4, Capacity(MessageArea720p, withEmpty));
    }

    [Theory]
    [InlineData(MessageArea720p)]
    [InlineData(MessageArea1080p)]
    [InlineData(240)]
    public void The_capacity_always_fits_inside_the_bubble_area(int messageAreaHeight)
    {
        // 不变式（这条是「算得下就一定画得下」的保证）：
        // 容量条气泡加上它们之间的间距，再加顶部内缩，不超过气泡区高度。
        // 前提是「有得选」——容量为 1 时首条与 F8 一样无条件保留，
        // 见 A_bubble_area_too_short_for_even_one_bubble_keeps_the_newest_line。
        var bubbleAreaHeight = GroupDialogueLayoutRules.CapacityBubbleAreaHeight(messageAreaHeight);
        var heights = Enumerable.Repeat(SingleLineBubbleHeight, 12).ToArray();
        var capacity = GroupDialogueLayoutRules.VisibleCapacity(bubbleAreaHeight, heights, MaxVisible);
        Assert.True(capacity > 1, $"这条视口下已经没得选（容量 {capacity}），不属于本条不变式的范围");
        var used = (capacity * SingleLineBubbleHeight)
            + ((capacity - 1) * GroupDialogueLayoutRules.BubbleGap);

        Assert.True(
            GroupDialogueLayoutRules.MessageInset + used <= bubbleAreaHeight,
            $"容量 {capacity} 条占 {used}px，加内缩后超出气泡区 {bubbleAreaHeight}px");
    }

    [Fact]
    public void A_bubble_area_too_short_for_even_one_bubble_keeps_the_newest_line()
    {
        // 极端退化视口（气泡区连一个气泡都放不下）：容量是 1，而那一条
        // **无条件保留**——这是 SelectLatestThatFit 的既有契约（F8 私聊也靠它），
        // 宁可压掉一点也不能一条都不画。上面那条不变式因此只对容量 > 1 成立。
        var bubbleAreaHeight = GroupDialogueLayoutRules.CapacityBubbleAreaHeight(1);
        var capacity = GroupDialogueLayoutRules.VisibleCapacity(
            bubbleAreaHeight,
            new[] { SingleLineBubbleHeight, SingleLineBubbleHeight },
            MaxVisible);

        Assert.Equal(1, capacity);
    }

    // ── 二、翻页门槛跟着容量走（用户清单：4 / 6 / 8 / 10 条）──────────────

    /// <summary>
    /// 这一场到底有几条被画面挡在外面 —— 也就是「玩家有没有东西可翻」。
    /// </summary>
    private static int HiddenCount(int totalCount, int capacity)
    {
        var (_, count) = GroupReadOnlyRules.VisibleWindow(
            totalCount,
            capacity,
            GroupTranscriptRules.WindowStartIndex(followLatest: true, scrollStartIndex: 0));
        return totalCount - count;
    }

    [Theory]
    // 条数, 改前（固定 10 条）能否翻, 改后能否翻, 改后被挡在外面的条数
    [InlineData(4, false, false, 0)]
    [InlineData(5, false, true, 1)]
    [InlineData(6, false, true, 2)]
    [InlineData(8, false, true, 4)]
    [InlineData(10, false, true, 6)]
    [InlineData(11, true, true, 7)]
    [InlineData(20, true, true, 16)]
    public void The_paging_gate_follows_the_pixel_capacity_not_a_fixed_ten(
        int totalCount,
        bool couldPageBefore,
        bool canPageNow,
        int hiddenAfter)
    {
        // 改前的门槛：MaxScrollStart(count, 10) —— 11 条以上才接管滚轮/翻页键。
        var beforeMoved = Press(totalCount, MaxVisible, followLatest: true, 0, 1, 1).Moved;
        Assert.Equal(couldPageBefore, beforeMoved);

        // 改后：门槛由实测容量（720p 下 4 条）决定。
        var capacity = Capacity(MessageArea720p, Enumerable.Repeat(SingleLineBubbleHeight, totalCount).ToArray());
        Assert.Equal(4, capacity);

        var (moved, _, _) = Press(totalCount, capacity, followLatest: true, 0, 1, capacity);
        Assert.Equal(canPageNow, moved);
        Assert.Equal(hiddenAfter, HiddenCount(totalCount, capacity));

        // 4 条是「一屏正好装下」：不动是**正确**结果（没有东西被挡住），
        // 而不是改前那种「明明被挡住却翻不动」。这一点用 hiddenAfter == 0 钉住。
        if (!canPageNow)
        {
            Assert.Equal(0, hiddenAfter);
        }
    }

    [Fact]
    public void The_five_to_ten_band_is_exactly_what_used_to_be_stuck()
    {
        // 用户现场：5～10 条时画面已经装不下（4 条以上全被切），翻页却全部返回 false。
        // 这一段每一条现在都必须能翻，且翻一次就能看到被挡住的那些。
        var capacity = Capacity(MessageArea720p, Enumerable.Repeat(SingleLineBubbleHeight, 10).ToArray());

        for (var totalCount = 5; totalCount <= 10; totalCount++)
        {
            var (moved, start, followLatest) = Press(totalCount, capacity, followLatest: true, 0, 1, capacity);

            Assert.True(moved, $"{totalCount} 条时仍然翻不动");
            Assert.False(followLatest);
            Assert.Equal(Math.Max(0, totalCount - capacity - capacity), start);
            // 翻过之后能看到的那一段，起点比原来更早（确实往上走了）。
            Assert.True(start < GroupReadOnlyRules.MaxScrollStart(totalCount, capacity));
        }
    }

    // ── 三、PageUp/PageDown 翻一屏，滚轮仍然逐条 ───────────────────────────

    [Fact]
    public void A_page_key_moves_a_whole_screen_while_the_wheel_moves_one_line()
    {
        const int totalCount = 20;
        var capacity = Capacity(MessageArea720p, Enumerable.Repeat(SingleLineBubbleHeight, totalCount).ToArray());

        // 从底部起：PageUp 一次翻一屏（20 条 → maxStart 16 → 12）。
        var page = Press(totalCount, capacity, followLatest: true, 0, 1, capacity);
        Assert.True(page.Moved);
        Assert.Equal(12, page.Start);

        // 滚轮一次只走一条（16 → 15），与 F8 私聊一致。
        var wheel = Press(totalCount, capacity, followLatest: true, 0, 1, 1);
        Assert.True(wheel.Moved);
        Assert.Equal(15, wheel.Start);
    }

    [Fact]
    public void Paging_up_four_times_reaches_the_first_line_and_stops()
    {
        const int totalCount = 20;
        var capacity = Capacity(MessageArea720p, Enumerable.Repeat(SingleLineBubbleHeight, totalCount).ToArray());
        var start = GroupReadOnlyRules.MaxScrollStart(totalCount, capacity);
        var expected = new[] { 12, 8, 4, 0, 0 };

        foreach (var want in expected)
        {
            var (moved, next, _) = Press(totalCount, capacity, followLatest: false, start, 1, capacity);
            Assert.True(moved, $"从 {start} 往上翻一屏应当仍然接管（page-up 返回 true）");
            Assert.Equal(want, next);
            start = next;
        }
    }

    [Fact]
    public void Paging_back_down_returns_to_following_the_latest()
    {
        const int totalCount = 20;
        var capacity = Capacity(MessageArea720p, Enumerable.Repeat(SingleLineBubbleHeight, totalCount).ToArray());

        var (moved, start, followLatest) = Press(totalCount, capacity, followLatest: false, scrollStartIndex: 0, direction: -1, step: capacity);

        Assert.True(moved);
        Assert.Equal(Math.Min(capacity, GroupReadOnlyRules.MaxScrollStart(totalCount, capacity)), start);
        Assert.False(followLatest);

        // 一直翻到底 → 恢复跟随（与逐条滚动同一个收尾）。
        var bottom = GroupReadOnlyRules.MaxScrollStart(totalCount, capacity);
        var (_, finalStart, finalFollow) = Press(totalCount, capacity, followLatest: false, scrollStartIndex: bottom - capacity, direction: -1, step: capacity);
        Assert.Equal(bottom, finalStart);
        Assert.True(finalFollow);
    }

    [Theory]
    // 步长 0 / 负数不能让 PageUp/PageDown 变成「按了没反应」——
    // 那正是这一次要修掉的现象，不能从参数上再放进来。
    [InlineData(0)]
    [InlineData(-5)]
    public void A_non_positive_step_is_treated_as_one_line(int step)
    {
        var (moved, start, _) = Press(20, 4, followLatest: true, 0, 1, step);

        Assert.True(moved);
        Assert.Equal(15, start);
    }

    [Fact]
    public void The_page_step_is_the_measured_capacity_not_a_hard_coded_three()
    {
        // 容量是算出来的，步长就必须与它同源；照抄 F8 的常量 3 会在
        // 「一屏 4 条」的屏幕上留下一条永远翻不到的重叠。
        var capacity = Capacity(MessageArea720p, Enumerable.Repeat(SingleLineBubbleHeight, 20).ToArray());
        var (_, start, _) = Press(20, capacity, followLatest: true, 0, 1, capacity);

        Assert.Equal(GroupReadOnlyRules.MaxScrollStart(20, capacity) - capacity, start);
    }

    // ── 四、只读回看不回归 ────────────────────────────────────────────────

    [Fact]
    public void A_read_only_transcript_still_pages_through_the_same_arithmetic()
    {
        // 只读回看与正常对话共用 ScrollBy/draw 与同一条窗口算术；容量改成算出来的之后，
        // 只读侧跟着一起能翻（改前 11 条以上才动），而不是被改坏。
        const int totalCount = 8;
        var capacity = Capacity(MessageArea720p, Enumerable.Repeat(SingleLineBubbleHeight, totalCount).ToArray());

        var (alwaysVisible, count) = GroupReadOnlyRules.VisibleWindow(
            totalCount,
            capacity,
            GroupTranscriptRules.WindowStartIndex(followLatest: true, scrollStartIndex: 0));
        Assert.Equal(totalCount - capacity, alwaysVisible);
        Assert.Equal(capacity, count);

        var (moved, start, _) = Press(totalCount, capacity, followLatest: true, 0, 1, capacity);
        Assert.True(moved);
        Assert.Equal(0, start);

        // 回到最新：起点回到最后一屏，只读提示行的范围与实际窗口一致。
        var (backStart, backCount) = GroupReadOnlyRules.VisibleWindow(
            totalCount,
            capacity,
            GroupTranscriptRules.WindowStartIndex(followLatest: true, scrollStartIndex: 0));
        var hint = GroupReadOnlyRules.ScrollHintText(backStart, backCount, totalCount);
        Assert.Contains($"第 {backStart + 1}–{totalCount} 条", hint);
        Assert.Contains($"共 {totalCount} 条", hint);
    }

    [Fact]
    public void A_read_only_session_that_fits_on_one_screen_is_left_alone()
    {
        // 原契约不变：装得下一屏就不接管（maxStart == 0）。只读模式下这正是
        // 「一场很短的邀约，点进去看完就完了，滚轮不该有任何反应」。
        const int totalCount = 4;
        var capacity = Capacity(MessageArea720p, Enumerable.Repeat(SingleLineBubbleHeight, totalCount).ToArray());

        Assert.Equal(0, GroupReadOnlyRules.MaxScrollStart(totalCount, capacity));
        var (moved, _, followLatest) = Press(totalCount, capacity, followLatest: false, 0, 1, capacity);
        Assert.False(moved);
        Assert.True(followLatest);
    }

    [Theory]
    // MaxScrollStart 的契约（≥ 0、不足一屏为 0）在换成真实容量之后逐条不变。
    [InlineData(0, 0)]
    [InlineData(-3, 0)]
    [InlineData(4, 0)]
    [InlineData(5, 1)]
    [InlineData(20, 16)]
    public void Max_scroll_start_keeps_its_contract_with_the_measured_capacity(
        int totalCount,
        int expected)
    {
        Assert.Equal(expected, GroupReadOnlyRules.MaxScrollStart(totalCount, 4));
    }
}
