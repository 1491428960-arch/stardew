using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ChatScrollRulesTests
{
    [Fact]
    public void ClampStartIndex_keeps_position_inside_history_range()
    {
        Assert.Equal(0, ChatScrollRules.ClampStartIndex(-2, maxStartIndex: 4));
        Assert.Equal(3, ChatScrollRules.ClampStartIndex(3, maxStartIndex: 4));
        Assert.Equal(4, ChatScrollRules.ClampStartIndex(9, maxStartIndex: 4));
    }

    [Fact]
    public void MoveStartIndex_uses_scroll_direction_and_clamps_at_edges()
    {
        Assert.Equal(0, ChatScrollRules.MoveStartIndex(2, delta: -5, maxStartIndex: 4));
        Assert.Equal(4, ChatScrollRules.MoveStartIndex(2, delta: 5, maxStartIndex: 4));
        Assert.Equal(1, ChatScrollRules.MoveStartIndex(2, delta: -1, maxStartIndex: 4));
    }
}
