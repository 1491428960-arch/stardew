using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// <c>ChatTextLayoutRules</c> 的边界。三条规则各自都带“调用方保证不了时怎么办”的设计决策，
/// 但原有的 3 条测试只覆盖了三段顺利路径（正常换行、加省略号、保留最新消息）。
/// </summary>
public sealed class ChatTextLayoutEdgeTests
{
    private static float ByLength(string value) => value.Length;

    [Fact]
    public void Wrap_keeps_a_character_wider_than_the_limit_on_its_own_line()
    {
        // 单个字符就超过宽度时既不能丢字、也不能死循环：让它独占一行。
        var lines = ChatTextLayoutRules.Wrap("甲乙", maxWidth: 1, _ => 10f);

        Assert.Equal(new[] { "甲", "乙" }, lines);
    }

    [Fact]
    public void Wrap_normalises_crlf_and_preserves_empty_paragraphs()
    {
        var lines = ChatTextLayoutRules.Wrap("甲\r\n乙\n\n丙", maxWidth: 10, ByLength);

        Assert.Equal(new[] { "甲", "乙", "", "丙" }, lines);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public void Wrap_rejects_non_positive_width(int maxWidth)
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => ChatTextLayoutRules.Wrap("甲", maxWidth, ByLength));
    }

    [Fact]
    public void Wrap_rejects_null_text_and_measure()
    {
        Assert.Throws<ArgumentNullException>(() => ChatTextLayoutRules.Wrap(null!, 10, ByLength));
        Assert.Throws<ArgumentNullException>(() => ChatTextLayoutRules.Wrap("甲", 10, null!));
    }

    [Fact]
    public void Fit_returns_the_lines_untouched_when_they_already_fit()
    {
        var lines = new[] { "一", "二" };

        var fitted = ChatTextLayoutRules.Fit(lines, maxLines: 2, maxWidth: 10, ByLength);

        Assert.Equal(lines, fitted);
    }

    [Fact]
    public void Fit_drops_the_ellipsis_when_even_it_is_too_wide()
    {
        // 省略号自己就量不下时，最后一行只能留空，而不是突破宽度限制。
        var fitted = ChatTextLayoutRules.Fit(
            new[] { "长", "长" },
            maxLines: 1,
            maxWidth: 1,
            _ => 2f,
            ellipsis: "…");

        Assert.Equal(new[] { "" }, fitted);
    }

    [Fact]
    public void Fit_rejects_empty_ellipsis()
    {
        Assert.Throws<ArgumentException>(
            () => ChatTextLayoutRules.Fit(new[] { "一" }, 1, 10, ByLength, ellipsis: ""));
    }

    [Fact]
    public void SelectLatestThatFit_always_keeps_the_newest_item_even_if_it_overflows()
    {
        // 最新一条即使超出可用高度也要保留——调用方会再用 Fit 压缩它，
        // 否则玩家会看不到自己刚发出或刚收到的那句。
        var selected = ChatTextLayoutRules.SelectLatestThatFit(
            new[] { "旧", "新" },
            maxItems: 5,
            availableHeight: 3,
            gap: 0,
            _ => 100);

        Assert.Equal(new[] { "新" }, selected);
    }

    [Fact]
    public void SelectLatestThatFit_stops_before_exceeding_the_budget()
    {
        // 最新 5、上一条 5+2=7，合计 12 超过可用高度 10，所以只能放最新一条。
        var selected = ChatTextLayoutRules.SelectLatestThatFit(
            new[] { "A", "B", "C" },
            maxItems: 5,
            availableHeight: 10,
            gap: 2,
            _ => 5);

        Assert.Equal(new[] { "C" }, selected);
    }

    [Fact]
    public void SelectLatestThatFit_respects_max_items_and_returns_chronological_order()
    {
        var selected = ChatTextLayoutRules.SelectLatestThatFit(
            new[] { "A", "B", "C" },
            maxItems: 2,
            availableHeight: 100,
            gap: 0,
            _ => 1);

        Assert.Equal(new[] { "B", "C" }, selected);
    }

    [Fact]
    public void SelectLatestThatFit_rejects_non_positive_measured_height()
    {
        Assert.Throws<ArgumentException>(
            () => ChatTextLayoutRules.SelectLatestThatFit(new[] { "A" }, 1, 10, 0, _ => 0));
    }

    [Fact]
    public void SelectLatestThatFit_rejects_negative_gap()
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => ChatTextLayoutRules.SelectLatestThatFit(new[] { "A" }, 1, 10, gap: -1, _ => 1));
    }
}
