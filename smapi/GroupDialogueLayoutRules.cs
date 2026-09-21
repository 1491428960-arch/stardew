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
    /// 消息区一次最多画几条历史消息。**这是上限，不再是「一屏」本身**：
    /// 真正画得下几条由 <see cref="VisibleCapacity"/> 按气泡区高度算出来
    /// （2026-09-21 修正，见那里的说明）。
    /// </summary>
    public const int MaxVisibleMessages = 10;

    /// <summary>
    /// 消息内容区相对消息区四边的内缩：首条气泡的顶边与气泡左右边界都用它。
    /// 抽成常量是为了让**容量**与**绘制**共用同一个留白——两处各写一个 12，
    /// 就会出现「算得下、画到一半被切断」。
    /// </summary>
    public const int MessageInset = 12;

    /// <summary>
    /// 相邻气泡之间的间距，与 <see cref="ChatBubbleDrawing.Gap"/> 是**同一个值**
    /// 而不是各写一遍：容量算术要用它，而 <c>ChatBubbleDrawing</c> 是 internal、
    /// 测试够不到，所以在这里给一个公开别名。
    /// </summary>
    public const int BubbleGap = ChatBubbleDrawing.Gap;

    /// <summary>
    /// 一屏**真正画得下**的条数。
    ///
    /// **为什么要算而不是写死**（2026-09-21 用户口径）：改前这里是固定 10 条，
    /// 而 720p 下 84px 的单行气泡加 20px 间距只画得下 4 条——于是 5～10 条这一段
    /// 画面已经装不下（第 5 条起被 <c>draw</c> 的 break 切掉），翻页门槛
    /// （11 条）却还没到，滚轮与 PageUp/PageDown 全部返回 false。
    /// 用户看到的现象就是「翻不动」。
    ///
    /// 算术**不在**这里另写一套：直接调私聊（F8）在用的
    /// <see cref="ChatTextLayoutRules.SelectLatestThatFit"/>，每条的高度也由调用方
    /// 用 F8 同一个 <c>ChatBubbleDrawing.MeasureMessage</c> 量出来。这里只做两件事：
    /// 把气泡区高度换算成「装得下的气泡总高」，以及只取尾部若干条来量。
    /// </summary>
    /// <param name="bubbleAreaHeight">气泡区高度（<see cref="MenuSkinRules.MessageBubbleAreaHeight"/>）。</param>
    /// <param name="messageHeights">
    /// 每条消息的高度，按时间顺序；非正值表示这一条根本不画（空内容），
    /// 不参与算术（<see cref="ChatTextLayoutRules.SelectLatestThatFit"/> 对高度 ≤ 0 会抛）。
    /// </param>
    /// <param name="maxVisible">条数上限（<see cref="MaxVisibleMessages"/>）。</param>
    /// <returns>至少 1、至多 <paramref name="maxVisible"/>。</returns>
    public static int VisibleCapacity(
        int bubbleAreaHeight,
        IReadOnlyList<int> messageHeights,
        int maxVisible)
    {
        ArgumentNullException.ThrowIfNull(messageHeights);
        if (maxVisible <= 0)
        {
            return 1;
        }

        // 换算：绘制从气泡区顶部内缩 MessageInset 起画，于是「n 条气泡 + n-1 个间距」
        // 只要不超过 bubbleAreaHeight - MessageInset，就一定能完整画在区内。
        // （draw 的 break 判据比这更宽松——它允许最后一条的下一个起点落到
        //   底部再上留一个行高——所以按这里算出来的容量**永远画得下**，不会溢出。）
        var availableHeight = Math.Max(1, bubbleAreaHeight - MessageInset);

        // 从末尾往前取：容量本来就封顶在 maxVisible，更早的消息不可能改变
        // 「最新的这一屏装得下几条」，多量几百条只是白费。
        var heights = new List<int>(Math.Min(messageHeights.Count, maxVisible));
        for (var index = messageHeights.Count - 1;
             index >= 0 && heights.Count < maxVisible;
             index--)
        {
            var height = messageHeights[index];
            if (height > 0)
            {
                heights.Add(height);
            }
        }

        if (heights.Count == 0)
        {
            // 一条都还没有：给 1 而不是 0。GroupReadOnlyRules.MaxScrollStart 拿它做减法，
            // 0 会让「只有一条」的场次也变成可滚动（那是改前没有的行为）。
            return 1;
        }

        heights.Reverse();
        var fit = ChatTextLayoutRules.SelectLatestThatFit(
            heights,
            heights.Count,
            availableHeight,
            BubbleGap,
            height => height);
        return Math.Max(1, Math.Min(maxVisible, fit.Count));
    }

    /// <summary>
    /// 算容量时用的气泡区高度：**按最坏情况**取（假设提示行落到底部、
    /// 吃掉 <see cref="MenuSkinRules.HintFallbackReserve"/> 那一行）。
    ///
    /// 理由：提示行落不落底部取决于那句提示有多长，而提示内容会在滚动前后变化——
    /// 若容量跟着它抖动，玩家翻一次页「一屏」就从 4 条变 3 条。宁可少算一条，
    /// 也不能让「翻一屏」的步长随提示文字变化；而且这条口径与 draw 实际用的
    /// 气泡区高度要么相等、要么更小，永远不会算出画不下的窗口。
    /// </summary>
    public static int CapacityBubbleAreaHeight(int messageAreaHeight) =>
        MenuSkinRules.MessageBubbleAreaHeight(messageAreaHeight, hintInHeader: false);

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
