using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

public sealed record ChatDisplayMessage(string Role, string Content);

public sealed record ChatLayout(
    Rectangle Panel,
    Rectangle Header,
    Rectangle MessageArea,
    Rectangle ConversationArea,
    Rectangle ProfilePanel,
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
    private const int ProfileWidth = 280;
    private const int ProfileHeight = 112;
    private const int MinimumConversationWidth = 240;

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

        var showProfile = messageArea.Width >=
            MinimumConversationWidth + ProfileWidth + ActionGap;
        var profilePanel = showProfile
            ? new Rectangle(
                messageArea.Right - ProfileWidth,
                messageArea.Y,
                ProfileWidth,
                Math.Min(ProfileHeight, messageArea.Height))
            : Rectangle.Empty;
        var conversationArea = new Rectangle(
            messageArea.X,
            messageArea.Y,
            showProfile
                ? messageArea.Width - ProfileWidth - ActionGap
                : messageArea.Width,
            messageArea.Height);

        var compactActions = footer.Width < 600;
        var veryCompactActions = footer.Width < 420;
        var buttonGap = veryCompactActions
            ? 4
            : compactActions
                ? 6
                : ActionGap;
        var sendWidth = veryCompactActions ? 56 : compactActions ? 72 : 96;
        var topicWidth = veryCompactActions ? 72 : compactActions ? 96 : 128;
        var inventoryWidth = veryCompactActions ? 62 : compactActions ? 84 : 104;
        var closeWidth = veryCompactActions ? 56 : compactActions ? 72 : 96;
        var closeButton = new Rectangle(
            footer.Right - closeWidth,
            footer.Y,
            closeWidth,
            footer.Height);
        var inventoryButton = new Rectangle(
            closeButton.X - buttonGap - inventoryWidth,
            footer.Y,
            inventoryWidth,
            footer.Height);
        var topicButton = new Rectangle(
            inventoryButton.X - buttonGap - topicWidth,
            footer.Y,
            topicWidth,
            footer.Height);
        var sendButton = new Rectangle(
            topicButton.X - buttonGap - sendWidth,
            footer.Y,
            sendWidth,
            footer.Height);
        var inputBox = new Rectangle(
            footer.X,
            footer.Y,
            Math.Max(120, sendButton.X - footer.X - buttonGap),
            footer.Height);

        return new ChatLayout(
            panel,
            header,
            messageArea,
            conversationArea,
            profilePanel,
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

    public static bool ShouldDrawHeaderTitle() => false;

    public static bool ShouldDrawHeaderStatus() => false;

    public static bool ShouldDrawFriendshipMeter(int? hearts) => hearts.HasValue;
}
