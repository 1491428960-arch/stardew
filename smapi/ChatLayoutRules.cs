using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

/// <summary>
/// 消息区里的一条内容。前两个字段是面板一直在用的「角色 + 文本」；
/// 后三个是 2026-09-21 加群聊场次时补的**可选**字段，老调用点（只传两个参数）不受影响。
/// </summary>
/// <param name="Role">见 <see cref="ChatHistoryRules"/> 的 PlayerRole／NpcRole／SessionRole。</param>
/// <param name="Content">显示的原文；分节线（<see cref="ChatHistoryRules.SessionRole"/>）放抬头文字。</param>
/// <param name="Sequence">
/// 回看档案里的发生序号（<see cref="BridgeClient"/> 的单调计数器）。私聊条目与群聊场次共用同一个
/// 序号空间，F8 靠它把两者并成一条时间线；<c>null</c> 表示这条来自老档案（没有序号），排在有序号的那批之前。
/// **它只服务显示**，永远不进任何发给模型的请求。
/// </param>
/// <param name="SpeakerId">发言角色的 id（用于取角色配色与徽章）；玩家发言为 <c>"player"</c>。</param>
/// <param name="SpeakerName">气泡抬头显示的名字；为 null 时退回当前私聊对象的显示名。</param>
public sealed record ChatDisplayMessage(
    string Role,
    string Content,
    int? Sequence = null,
    string? SpeakerId = null,
    string? SpeakerName = null);

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
    private const int SafeMargin = MenuPanelRules.SafeMargin;
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
        var panel = MenuPanelRules.CenteredInViewport(
            viewportWidth,
            viewportHeight,
            panelWidth,
            panelHeight,
            floorOriginAtZero: false);

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

    /// <summary>
    /// 消息区**该显示哪些消息**的唯一过滤实现（2026-09-20 语义层审计 #36）。
    ///
    /// 此前同一段「丢掉 null 与纯空白内容」的过滤在本类与
    /// <see cref="ChatInputMenu"/> 的绘制里各写一份，本方法又零调用、成了死规则；
    /// 现在绘制侧也走这里，过滤只此一处。
    /// </summary>
    public static IReadOnlyList<ChatDisplayMessage> VisibleMessages(
        IEnumerable<ChatDisplayMessage> messages)
    {
        ArgumentNullException.ThrowIfNull(messages);

        return FilterVisible(messages).ToArray();
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

        return FilterVisible(messages).TakeLast(maximumCount).ToArray();
    }

    private static IEnumerable<ChatDisplayMessage> FilterVisible(
        IEnumerable<ChatDisplayMessage> messages)
    {
        return messages.Where(message =>
            message is not null && !string.IsNullOrWhiteSpace(message.Content));
    }

    /// <summary>
    /// 私聊标题带是否画「和 X 聊聊」。
    ///
    /// 2026-09-20 外壳重构：此前这里返回 <c>false</c>，于是算得出 92px 高的 header
    /// 什么都不画，面板顶部留一条空白——那是「看着脏」的主要来源。
    /// 现在与 F9／群聊中心共用 <see cref="MenuSkinDrawing.DrawTitleBand"/> 的那一套
    /// （强调色竖条 + 标题 + 状态 + 发丝分隔线）。
    /// </summary>
    public static bool ShouldDrawHeaderTitle() => true;

    /// <summary>私聊标题带是否画右侧的好感度状态字（与标题同一行，走次级文字色）。</summary>
    public static bool ShouldDrawHeaderStatus() => true;

    public static bool ShouldDrawFriendshipMeter(int? hearts) => hearts.HasValue;
}
