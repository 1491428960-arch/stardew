using Microsoft.Xna.Framework;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ChatLayoutRulesTests
{
    [Theory]
    [InlineData(1280, 720)]
    [InlineData(1920, 1080)]
    [InlineData(2560, 1440)]
    public void LayoutFitsViewportAndKeepsActionButtonsSeparated(int viewportWidth, int viewportHeight)
    {
        var layout = ChatLayoutRules.Calculate(viewportWidth, viewportHeight);

        Assert.InRange((float)layout.Panel.Width, viewportWidth * 0.60f, viewportWidth * 0.72f);
        Assert.InRange((float)layout.Panel.Height, viewportHeight * 0.48f, viewportHeight * 0.62f);
        Assert.True(layout.Panel.Left >= 24);
        Assert.True(layout.Panel.Right <= viewportWidth - 24);
        Assert.False(layout.SendButton.Intersects(layout.TopicButton));
        Assert.False(layout.TopicButton.Intersects(layout.InventoryButton));
        Assert.False(layout.InventoryButton.Intersects(layout.CloseButton));
    }

    [Fact]
    public void VisibleMessagesDropsBlankEntriesAndKeepsNewestItems()
    {
        var messages = new[]
        {
            new ChatDisplayMessage("npc", "第一条"),
            new ChatDisplayMessage("player", " "),
            new ChatDisplayMessage("npc", "第二条"),
            new ChatDisplayMessage("player", "第三条"),
        };

        var visible = ChatLayoutRules.VisibleMessages(messages, 2);

        Assert.Equal(
            new[] { "第二条", "第三条" },
            visible.Select(message => message.Content).ToArray());
    }

    [Fact]
    public void CalculateRejectsNonPositiveViewport()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => ChatLayoutRules.Calculate(0, 720));
        Assert.Throws<ArgumentOutOfRangeException>(() => ChatLayoutRules.Calculate(1280, 0));
    }
}
