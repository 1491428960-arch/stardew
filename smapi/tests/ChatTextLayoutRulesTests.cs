using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ChatTextLayoutRulesTests
{
    [Fact]
    public void Wrap_splits_lines_and_respects_measured_width()
    {
        static float Measure(string value) => value.Length;

        var lines = ChatTextLayoutRules.Wrap(
            "甲乙丙丁戊\n己庚辛壬癸",
            maxWidth: 4,
            Measure);

        Assert.Equal(new[] { "甲乙丙丁", "戊", "己庚辛壬", "癸" }, lines);
        Assert.All(lines, line => Assert.True(Measure(line) <= 4));
    }

    [Fact]
    public void Fit_adds_ellipsis_without_exceeding_line_limit_or_width()
    {
        static float Measure(string value) => value.Length;

        var fitted = ChatTextLayoutRules.Fit(
            new[] { "第一行", "第二行", "第三行" },
            maxLines: 2,
            maxWidth: 3,
            Measure);

        Assert.Equal(new[] { "第一行", "第二…" }, fitted);
        Assert.All(fitted, line => Assert.True(Measure(line) <= 4));
    }

    [Fact]
    public void SelectLatestThatFit_keeps_newest_messages_when_old_bubbles_fill_area()
    {
        var selected = ChatTextLayoutRules.SelectLatestThatFit(
            new[] { "旧回复", "中间回复", "最新回复" },
            maxItems: 3,
            availableHeight: 22,
            gap: 2,
            item => item switch
            {
                "旧回复" => 14,
                "中间回复" => 9,
                _ => 8,
            });

        Assert.Equal(new[] { "中间回复", "最新回复" }, selected);
    }
}
