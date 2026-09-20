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
        Assert.True(layout.ConversationArea.Width >= 240);
        Assert.True(layout.ProfilePanel.Width >= 120);
        Assert.False(layout.ConversationArea.Intersects(layout.ProfilePanel));
        Assert.False(layout.SendButton.Intersects(layout.TopicButton));
        Assert.False(layout.TopicButton.Intersects(layout.InventoryButton));
        Assert.False(layout.InventoryButton.Intersects(layout.CloseButton));
        Assert.True(layout.InputBox.Width >= 120);
    }

    [Fact]
    public void ProfilePanelUsesCompactHorizontalGeometry()
    {
        var layout = ChatLayoutRules.Calculate(1280, 720);

        Assert.Equal(280, layout.ProfilePanel.Width);
        Assert.InRange(layout.ProfilePanel.Height, 96, 128);
        Assert.True(layout.ProfilePanel.Height < layout.MessageArea.Height);
        Assert.False(layout.ConversationArea.Intersects(layout.ProfilePanel));
    }

    [Theory]
    [InlineData(null, false)]
    [InlineData(0, true)]
    [InlineData(5, true)]
    public void FriendshipMeterOnlyDrawsWhenHeartsAreKnown(int? hearts, bool expected)
    {
        Assert.Equal(expected, ChatLayoutRules.ShouldDrawFriendshipMeter(hearts));
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

    /// <summary>
    /// 审计 #36：绘制路径不再自带一份过滤条件，而是调用这里的无上限重载。
    /// </summary>
    [Fact]
    public void VisibleMessagesWithoutALimitKeepsEveryNonBlankEntryInOrder()
    {
        var messages = new ChatDisplayMessage?[]
        {
            new("npc", "第一条"),
            null,
            new("player", " "),
            new("npc", "第二条"),
            new("player", "\t\n"),
            new("npc", "第三条"),
        };

        var visible = ChatLayoutRules.VisibleMessages(messages!);

        Assert.Equal(
            new[] { "第一条", "第二条", "第三条" },
            visible.Select(message => message.Content).ToArray());
    }

    [Fact]
    public void VisibleMessagesWithoutALimitReturnsNothingForAnEmptyHistory()
    {
        Assert.Empty(ChatLayoutRules.VisibleMessages(Array.Empty<ChatDisplayMessage>()));
        Assert.Empty(ChatLayoutRules.VisibleMessages(
            new[] { new ChatDisplayMessage("npc", "   ") }));
    }

    [Fact]
    public void VisibleMessagesWithANonPositiveLimitStillValidatesItsInput()
    {
        Assert.Empty(ChatLayoutRules.VisibleMessages(
            new[] { new ChatDisplayMessage("npc", "第一条") },
            0));

        Assert.Throws<ArgumentNullException>(
            () => ChatLayoutRules.VisibleMessages(null!, 3));
        Assert.Throws<ArgumentNullException>(
            () => ChatLayoutRules.VisibleMessages((IEnumerable<ChatDisplayMessage>)null!));
    }

    /// <summary>
    /// 审计 #38：面板放置改用 <see cref="MenuPanelRules.CenteredInViewport"/> 之后，
    /// 私聊面板矩形必须与改动前逐值相同。
    /// </summary>
    [Fact]
    public void Panel_rectangle_is_unchanged_after_the_shared_placement_refactor()
    {
        // 改前算式：宽 = clamp(round(1280*0.68), min(760, 1232), 1232) = 870
        //           高 = clamp(round(720*0.55), min(420, 672), 672) = 420
        //           原点 = ((1280-870)/2, (720-420)/2)
        Assert.Equal(new Rectangle(205, 150, 870, 420), ChatLayoutRules.Calculate(1280, 720).Panel);
    }

    [Fact]
    public void CompactViewportKeepsInputAndActionsSeparated()
    {
        var layout = ChatLayoutRules.Calculate(640, 480);

        Assert.True(layout.InputBox.Width >= 120);
        Assert.False(layout.InputBox.Intersects(layout.SendButton));
        Assert.False(layout.SendButton.Intersects(layout.TopicButton));
        Assert.False(layout.TopicButton.Intersects(layout.InventoryButton));
        Assert.False(layout.InventoryButton.Intersects(layout.CloseButton));
    }

    [Fact]
    public void VeryNarrowViewportHidesProfilePanelInsteadOfOverlappingConversation()
    {
        var layout = ChatLayoutRules.Calculate(480, 320);

        Assert.Equal(Rectangle.Empty, layout.ProfilePanel);
        Assert.Equal(layout.MessageArea, layout.ConversationArea);
    }

    [Fact]
    public void VeryNarrowViewportKeepsInputAndActionsSeparated()
    {
        var layout = ChatLayoutRules.Calculate(480, 320);

        Assert.False(layout.InputBox.Intersects(layout.SendButton));
        Assert.False(layout.SendButton.Intersects(layout.TopicButton));
        Assert.False(layout.TopicButton.Intersects(layout.InventoryButton));
        Assert.False(layout.InventoryButton.Intersects(layout.CloseButton));
    }

    [Fact]
    public void CalculateRejectsNonPositiveViewport()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => ChatLayoutRules.Calculate(0, 720));
        Assert.Throws<ArgumentOutOfRangeException>(() => ChatLayoutRules.Calculate(1280, 0));
    }

    [Fact]
    public void HeaderDoesNotDrawTitle()
    {
        Assert.False(ChatLayoutRules.ShouldDrawHeaderTitle());
    }

    [Fact]
    public void HeaderDoesNotDrawStatus()
    {
        Assert.False(ChatLayoutRules.ShouldDrawHeaderStatus());
    }
}
