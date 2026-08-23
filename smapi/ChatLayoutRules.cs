using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

public sealed record ChatDisplayMessage(string Role, string Content);

public sealed record ChatLayout(
    Rectangle Panel,
    Rectangle Header,
    Rectangle MessageArea,
    Rectangle InputBox,
    Rectangle SendButton,
    Rectangle TopicButton,
    Rectangle InventoryButton,
    Rectangle CloseButton);

public static class ChatLayoutRules
{
    private const int SafeMargin = 24;
    private const int MinimumPanelWidth = 760;
    private const int MinimumPanelHeight = 420;
    private const int FooterHeight = 112;
    private const int HeaderHeight = 92;
    private const int ActionGap = 8;

    public static ChatLayout Calculate(int viewportWidth, int viewportHeight)
    {
        if (viewportWidth <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(viewportWidth));
        }

        if (viewportHeight <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(viewportHeight));
        }

        var availableWidth = Math.Max(1, viewportWidth - (SafeMargin * 2));
        var availableHeight = Math.Max(1, viewportHeight - (SafeMargin * 2));
        var minimumWidth = Math.Min(MinimumPanelWidth, availableWidth);
        var minimumHeight = Math.Min(MinimumPanelHeight, availableHeight);
        var panelWidth = Math.Clamp(
            (int)Math.Round(viewportWidth * 0.68f),
            minimumWidth,
            availableWidth);
        var panelHeight = Math.Clamp(
            (int)Math.Round(viewportHeight * 0.55f),
            minimumHeight,
            availableHeight);
        var panel = new Rectangle(
            (viewportWidth - panelWidth) / 2,
            (viewportHeight - panelHeight) / 2,
            panelWidth,
            panelHeight);

        var header = new Rectangle(
            panel.X + SafeMargin,
            panel.Y + SafeMargin,
            panel.Width - (SafeMargin * 2),
            Math.Min(HeaderHeight, Math.Max(48, panel.Height / 4)));
        var footer = new Rectangle(
            panel.X + SafeMargin,
            panel.Bottom - SafeMargin - Math.Min(FooterHeight, Math.Max(72, panel.Height / 3)),
            panel.Width - (SafeMargin * 2),
            Math.Min(FooterHeight, Math.Max(72, panel.Height / 3)));
        var messageArea = new Rectangle(
            panel.X + SafeMargin,
            header.Bottom + ActionGap,
            panel.Width - (SafeMargin * 2),
            Math.Max(40, footer.Y - header.Bottom - (ActionGap * 2)));

        const int sendWidth = 96;
        const int topicWidth = 128;
        const int inventoryWidth = 104;
        const int closeWidth = 96;
        var closeButton = new Rectangle(
            footer.Right - closeWidth,
            footer.Y,
            closeWidth,
            footer.Height);
        var inventoryButton = new Rectangle(
            closeButton.X - ActionGap - inventoryWidth,
            footer.Y,
            inventoryWidth,
            footer.Height);
        var topicButton = new Rectangle(
            inventoryButton.X - ActionGap - topicWidth,
            footer.Y,
            topicWidth,
            footer.Height);
        var sendButton = new Rectangle(
            topicButton.X - ActionGap - sendWidth,
            footer.Y,
            sendWidth,
            footer.Height);
        var inputBox = new Rectangle(
            footer.X,
            footer.Y,
            Math.Max(120, sendButton.X - footer.X - ActionGap),
            footer.Height);

        return new ChatLayout(
            panel,
            header,
            messageArea,
            inputBox,
            sendButton,
            topicButton,
            inventoryButton,
            closeButton);
    }

    public static IReadOnlyList<ChatDisplayMessage> VisibleMessages(
        IEnumerable<ChatDisplayMessage> messages,
        int maximumCount)
    {
        ArgumentNullException.ThrowIfNull(messages);
        if (maximumCount <= 0)
        {
            return Array.Empty<ChatDisplayMessage>();
        }

        return messages
            .Where(message => message is not null && !string.IsNullOrWhiteSpace(message.Content))
            .TakeLast(maximumCount)
            .ToArray();
    }
}
