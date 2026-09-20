using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

public sealed record GroupDialogueLayout(
    Rectangle Panel,
    Rectangle Header,
    Rectangle ParticipantStrip,
    Rectangle MessageArea,
    Rectangle InputBox,
    Rectangle SendButton,
    Rectangle RetryButton,
    Rectangle CloseButton);

public static class GroupDialogueLayoutRules
{
    private const int SafeMargin = MenuPanelRules.SafeMargin;
    private const int FooterHeight = 104;
    private const int HeaderHeight = 118;
    private const int ActionGap = 8;

    /// <summary>
    /// 消息区一次最多画几条历史消息。与私聊侧按高度取窗口（
    /// <see cref="ChatTextLayoutRules.SelectLatestThatFit"/>）不同，群聊用固定条数上限。
    /// 抽成常量只是让这个「显示哪些消息」的口径有个名字，数值与行为不变
    /// （2026-09-20 语义层审计 #36）。
    /// </summary>
    public const int MaxVisibleMessages = 10;

    public static GroupDialogueLayout Calculate(int viewportWidth, int viewportHeight)
    {
        var panelWidth = Math.Min(1120, Math.Max(680, viewportWidth - (SafeMargin * 2)));
        var panelHeight = Math.Min(720, Math.Max(430, viewportHeight - (SafeMargin * 2)));
        panelWidth = Math.Min(panelWidth, Math.Max(1, viewportWidth - (SafeMargin * 2)));
        panelHeight = Math.Min(panelHeight, Math.Max(1, viewportHeight - (SafeMargin * 2)));
        var panel = MenuPanelRules.CenteredInViewport(
            viewportWidth,
            viewportHeight,
            panelWidth,
            panelHeight,
            floorOriginAtZero: true);
        var header = new Rectangle(panel.X, panel.Y, panel.Width, Math.Min(HeaderHeight, panel.Height));
        var footerY = Math.Max(header.Bottom, panel.Bottom - Math.Min(FooterHeight, panel.Height));
        var footer = new Rectangle(panel.X + 20, footerY, Math.Max(1, panel.Width - 40), Math.Max(1, panel.Bottom - footerY));
        var participantStrip = new Rectangle(
            header.X + 20,
            header.Bottom - 48,
            Math.Max(1, header.Width - 40),
            Math.Min(32, Math.Max(1, header.Height - 20)));
        var messageArea = new Rectangle(
            panel.X + 20,
            header.Bottom,
            Math.Max(1, panel.Width - 40),
            Math.Max(1, footer.Y - header.Bottom - 12));

        var closeWidth = 88;
        var retryWidth = 88;
        var sendWidth = 88;
        var closeButton = new Rectangle(footer.Right - closeWidth, footer.Y, closeWidth, footer.Height);
        var retryButton = new Rectangle(closeButton.X - ActionGap - retryWidth, footer.Y, retryWidth, footer.Height);
        var sendButton = new Rectangle(retryButton.X - ActionGap - sendWidth, footer.Y, sendWidth, footer.Height);
        var inputBox = new Rectangle(
            footer.X,
            footer.Y,
            Math.Max(120, sendButton.X - footer.X - ActionGap),
            footer.Height);

        return new GroupDialogueLayout(
            panel,
            header,
            participantStrip,
            messageArea,
            inputBox,
            sendButton,
            retryButton,
            closeButton);
    }
}
