using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Microsoft.Xna.Framework.Input;
using StardewValley;
using StardewValley.Menus;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

/// <summary>
/// 使用 Stardew Valley 原生菜单资源绘制的聊天界面。
/// </summary>
public class ChatInputMenu : IClickableMenu
{
    private const int MessagePadding = 12;
    private const int PortraitSize = 64;
    private const int BubblePadding = ChatBubbleDrawing.Padding;
    private const int BubbleSafetyMargin = ChatBubbleDrawing.SafetyMargin;
    private const int BubbleGap = ChatBubbleDrawing.Gap;
    private const int MessageLineSpacing = ChatBubbleDrawing.LineSpacing;
    private const int ScrollBarWidth = 12;
    private const int ScrollBarGap = 8;
    private const int ScrollBarMinThumb = 24;
    private const int ScrollPageStep = 3;

    private readonly StardewNpc npc;
    private readonly ConversationService conversationService;
    private readonly StoryStateStore storyStateStore;
    private readonly Action<bool> onClosed;
    private readonly int? friendshipHeartsOverride;
    private readonly string conversationChannel;
    private readonly bool openedFromPrivateChatRoster;
    private readonly Action? onReturnToRoster;
    private readonly CancellationTokenSource cancellationSource = new();
    private readonly List<ChatDisplayMessage> messages = new();
    private readonly KeyboardSubscriberLease<IKeyboardSubscriber> keyboardSubscriberLease;
    private readonly TextBox inputBox;
    private readonly TaskResultPump<ConversationTurnResult> pendingRequest = new();
    private readonly ShareFriendshipLedger shareFriendshipLedger;
    private ChatLayout layout;
    private Rectangle scrollBarTrack = Rectangle.Empty;
    private Rectangle scrollBarThumb = Rectangle.Empty;
    private string uiHint = "输入一句话，或者让她先找个话题。";
    private ItemConversationSelection? pendingGiftSelection;
    private int scrollMaxStartIndex;
    private int scrollStartIndex;
    private bool sending;
    private bool closed;
    private bool hasValuableRelationshipRepair;
    private string? pendingPlayerMessage;
    private bool followLatest = true;

    public ChatInputMenu(
        StardewNpc npc,
        ConversationService conversationService,
        StoryStateStore storyStateStore,
        Action<bool> onClosed,
        IReadOnlyList<ChatDisplayMessage>? initialMessages = null,
        int? friendshipHeartsOverride = null,
        string conversationChannel = ConversationChannel.Remote,
        bool openedFromPrivateChatRoster = false,
        Action? onReturnToRoster = null,
        ShareFriendshipLedger? shareFriendshipLedger = null)
        : base(0, 0, 1, 1)
    {
        this.npc = npc ?? throw new ArgumentNullException(nameof(npc));
        this.conversationService = conversationService ??
            throw new ArgumentNullException(nameof(conversationService));
        this.storyStateStore = storyStateStore ??
            throw new ArgumentNullException(nameof(storyStateStore));
        this.shareFriendshipLedger = shareFriendshipLedger ?? new ShareFriendshipLedger();
        this.onClosed = onClosed ?? throw new ArgumentNullException(nameof(onClosed));
        this.friendshipHeartsOverride = friendshipHeartsOverride;
        this.openedFromPrivateChatRoster = openedFromPrivateChatRoster;
        this.onReturnToRoster = onReturnToRoster;
        this.conversationChannel = string.Equals(
            conversationChannel,
            ConversationChannel.FaceToFace,
            StringComparison.Ordinal)
            ? ConversationChannel.FaceToFace
            : ConversationChannel.Remote;

        if (initialMessages is { Count: > 0 })
        {
            messages.AddRange(initialMessages);
            uiHint = string.Empty;
        }

        layout = ChatLayoutRules.Calculate(Game1.viewport.Width, Game1.viewport.Height);
        xPositionOnScreen = layout.Panel.X;
        yPositionOnScreen = layout.Panel.Y;
        width = layout.Panel.Width;
        height = layout.Panel.Height;

        inputBox = new TextBox(
            Game1.content.Load<Texture2D>("LooseSprites\\textBox"),
            null,
            Game1.smallFont,
            Color.Black)
        {
            Text = string.Empty,
        };
        // 输入框的绘制矩形只有一处定义（MenuSkinRules.InputBoxVisual）；
        // 命中判定用的是 layout.InputBox，两者互不影响。
        UpdateInputBoxBounds();
        inputBox.OnEnterPressed += OnInputEnterPressed;
        keyboardSubscriberLease = new KeyboardSubscriberLease<IKeyboardSubscriber>(
            () => Game1.keyboardDispatcher.Subscriber,
            subscriber => Game1.keyboardDispatcher.Subscriber = subscriber);
        keyboardSubscriberLease.Acquire(inputBox);
        inputBox.SelectMe();
    }

    public IReadOnlyList<ChatDisplayMessage> Messages => messages;

    public string InputText
    {
        get => inputBox.Text;
        set => inputBox.Text = value ?? string.Empty;
    }

    public bool IsSending => sending;

    public string UiHint => uiHint;

    /// <summary>
    /// 本次会话的频道（<see cref="ConversationChannel"/> 里的取值）。
    ///
    /// 关闭回调只有 <c>Action&lt;bool&gt;</c>，频道没有随回调传出去，所以协调器要在
    /// 窗口还挂在 <c>Game1.activeClickableMenu</c> 上时自己读这里——判定「刚关掉的是
    /// 哪条频道的会话」不能依赖状态字段的副作用（那条回调并不是每条退出路径都会调）。
    /// </summary>
    public string ChatChannel => conversationChannel;

    /// <summary>
    /// 这次会话是不是**从私聊名单（F8）打开的**——只影响「关掉之后要不要问一句
    /// 要继续聊聊吗」，不参与其它按频道分叉的行为（送礼、亲吻、当面描述都不看它）。
    ///
    /// 2026-09-21（用户口径「F8 一律不算当面：不管人在不在旁边，F8 打开的一律当线上，
    /// 退出永不弹续聊窗；想当面续聊就走过去按交互键」）：F8 打开的人若正好站在续聊距离内，
    /// 走的是面对面频道，于是退出时会弹出那句提问——用户要的是把这句去掉，
    /// 又不想连带丢掉「站在旁边的人还能送礼」这类靠频道区分的语义。
    /// 所以来源标记**单独**挂在窗口上，而不是让名单把频道改成 <c>remote</c>。
    ///
    /// 标记跟着**窗口对象**走（而不是协调器上的一个字段）：聊天窗中途被背包选择器顶掉、
    /// 取消后回到同一个窗口时它仍在，退出时照旧不弹。
    /// </summary>
    public bool OpenedFromPrivateChatRoster => openedFromPrivateChatRoster;

    protected StardewNpc Npc => npc;

    protected ConversationService Service => conversationService;

    protected StoryStateStore StateStore => storyStateStore;

    public override void receiveLeftClick(int x, int y, bool playSound = true)
    {
        if (closed)
        {
            return;
        }

        if (layout.CloseButton.Contains(x, y))
        {
            Close();
            return;
        }

        if (scrollBarTrack.Contains(x, y) && scrollMaxStartIndex > 0)
        {
            SetScrollFromPointer(y);
            return;
        }

        if (layout.SendButton.Contains(x, y))
        {
            _ = SendCurrentAsync();
            return;
        }

        if (layout.TopicButton.Contains(x, y))
        {
            _ = RequestTopicAsync();
            return;
        }

        if (layout.InventoryButton.Contains(x, y))
        {
            OpenInventoryPicker();
            return;
        }

        if (layout.InputBox.Contains(x, y))
        {
            inputBox.SelectMe();
            return;
        }

        base.receiveLeftClick(x, y, playSound);
    }

    public override void receiveKeyPress(Keys key)
    {
        if (key == Keys.Escape)
        {
            Close();
            return;
        }

        if (key == Keys.PageUp)
        {
            MoveScroll(-ScrollPageStep);
            return;
        }

        if (key == Keys.PageDown)
        {
            MoveScroll(ScrollPageStep);
            return;
        }

        if (key == Keys.Home)
        {
            scrollStartIndex = 0;
            followLatest = false;
            return;
        }

        if (key == Keys.End)
        {
            JumpToLatest();
            return;
        }

        base.receiveKeyPress(key);
    }

    public override void receiveScrollWheelAction(int direction)
    {
        if (closed || direction == 0)
        {
            return;
        }

        MoveScroll(direction > 0 ? -1 : 1);
    }

    public override void update(GameTime time)
    {
        if (closed)
        {
            return;
        }

        PumpPendingRequest();
        base.update(time);
    }

    protected override void cleanupBeforeExit()
    {
        CleanupKeyboardSubscriber();
        cancellationSource.Cancel();
        pendingRequest.Clear();
        cancellationSource.Dispose();
        base.cleanupBeforeExit();
    }

    public override void draw(SpriteBatch b)
    {
        if (closed)
        {
            return;
        }

        // Some Stardew menu states can render while skipping the regular
        // IClickableMenu.update callback. Poll here as a second safe point so
        // a completed request is never left showing “正在思考……”.
        PumpPendingRequest();
        layout = ChatLayoutRules.Calculate(Game1.viewport.Width, Game1.viewport.Height);
        xPositionOnScreen = layout.Panel.X;
        yPositionOnScreen = layout.Panel.Y;
        width = layout.Panel.Width;
        height = layout.Panel.Height;
        UpdateInputBoxBounds();

        DrawBackdrop(b);
        // 面板与 F9／群聊中心走同一条调用（20px 九宫格 + 白 tint + 投影）。
        // 改前这里是 Game1.drawDialogueBox 的 64px 切法且没有投影，
        // 与另外两个界面不是一套画法——面板矩形本身不变。
        MenuSkinDrawing.DrawPanel(b, layout.Panel);
        // 内容区凹槽（含右侧角色卡）画在气泡与角色卡之前，气泡于是「浮」在凹槽上。
        MenuSkinDrawing.DrawInset(b, layout.MessageArea);
        DrawHeader(b);
        DrawMessages(b);
        DrawFooter(b);
        drawMouse(b);
    }

    protected virtual void Close()
    {
        if (closed)
        {
            return;
        }

        closed = true;
        CleanupKeyboardSubscriber();
        cancellationSource.Cancel();
        onClosed(hasValuableRelationshipRepair);

        // 从 F8 名单打开的这一层：Esc 只退一层，回名单，而不是一路退回游戏
        // （用户口径 2026-09-26：「按 esc 退回上级界面而不是彻底退出」）。
        //
        // 顺序不能反：exitThisMenu 会把 activeClickableMenu 清成 null，
        // 回调必须在它之后才装得上。这一层来自名单（openedFromPrivateChatRoster），
        // 所以退出时不会弹「要不要继续聊聊」（见 ShouldOfferContinuationAfterExit）。
        //
        // 名单由回调**重开**而不是复用旧实例：聊了这几轮之后，未读标记、
        // 谁在附近、好感度都可能变了，旧实例拿的是打开那一刻的快照。
        var returnToRoster = openedFromPrivateChatRoster && onReturnToRoster is not null;
        exitThisMenu();
        if (returnToRoster)
        {
            onReturnToRoster!();
        }
    }

    protected virtual Task SendCurrentAsync()
    {
        if (sending)
        {
            return Task.CompletedTask;
        }

        var message = inputBox.Text.Trim();
        if (message.Length == 0)
        {
            uiHint = "先写点什么吧。";
            return Task.CompletedTask;
        }

        inputBox.Text = string.Empty;
        AddMessage(new ChatDisplayMessage("player", message));
        return SendAsync(message, ConversationIntent.Chat);
    }

    protected virtual Task RequestTopicAsync()
    {
        if (sending)
        {
            return Task.CompletedTask;
        }

        return SendAsync(null, ConversationIntent.Topic);
    }

    private Task SendAsync(
        string? message,
        string intent,
        ItemConversationContext? itemContext = null)
    {
        sending = true;
        uiHint = "正在思考……";
        pendingPlayerMessage = intent == ConversationIntent.Chat
            ? message
            : null;

        try
        {
            var state = GameStateCollector.Collect(npc);
            var request = intent == ConversationIntent.Topic
                ? conversationService.RequestTopicAsync(
                    state,
                    cancellationSource.Token,
                    conversationChannel)
                : conversationService.SendAsync(
                    state,
                    message ?? string.Empty,
                    cancellationSource.Token,
                    itemContext,
                    conversationChannel);
            pendingRequest.Start(request);
        }
        catch (Exception exception)
        {
            ApplyRequestError(exception);
            sending = false;
        }

        return Task.CompletedTask;
    }

    private void PumpPendingRequest()
    {
        if (!pendingRequest.TryTakeCompleted(out var result, out var error))
        {
            return;
        }

        if (error is not null)
        {
            ApplyRequestError(error);
        }
        else
        {
            ApplyResponse(result);
        }

        sending = false;
    }

    private void ApplyRequestError(Exception exception)
    {
        pendingPlayerMessage = null;
        if (closed)
        {
            return;
        }

        if (exception is OperationCanceledException)
        {
            uiHint = "对话已取消。";
            return;
        }

        AddMessage(new ChatDisplayMessage("npc", "刚才没听清，我们稍后再聊吧。"));
        uiHint = "暂时联系不上她，可以重试或结束。";
    }

    private void ApplyResponse(ConversationTurnResult result)
    {
        if (closed)
        {
            return;
        }

        if (ChatSessionRules.IsValuableRelationshipRepair(
                result,
                pendingPlayerMessage,
                storyStateStore.RelationshipSnapshotFor(npc.Name)))
        {
            hasValuableRelationshipRepair = true;
        }
        pendingPlayerMessage = null;

        var reply = result.Fallback
            ? "暂时联系不上她，可以稍后重试。"
            : NormalizeReply(result.Reply);
        AddMessage(new ChatDisplayMessage("npc", reply));
        uiHint = result.Fallback
            ? "暂时联系不上她，可以重试或结束。"
            : "";
    }

    private void OnInputEnterPressed(TextBox sender)
    {
        _ = sender;
        _ = SendCurrentAsync();
    }

    private void OpenInventoryPicker()
    {
        if (sending || closed)
        {
            return;
        }

        SuspendInput();
        Game1.activeClickableMenu = new InventoryItemPicker(
            npc,
            OnItemSelected,
            OnItemPickerCanceled);
    }

    private void OnItemPickerCanceled()
    {
        Game1.activeClickableMenu = this;
        ResumeInput();
    }

    private void OnItemSelected(ItemConversationSelection selection)
    {
        Game1.activeClickableMenu = this;
        ResumeInput();

        if (selection.Action == ItemInteractionAction.Gift)
        {
            // 线上频道（人不在同一地点）不接赠送：原版收礼是当场把东西递过去，
            // 隔着地图触发既怪，也越过 remote 频道「不写成已经见面」的边界。
            // 分享与展示不受影响。判定本身在规则层（ItemInteractionRules.CanGift）。
            if (!ItemInteractionRules.CanGift(conversationChannel))
            {
                uiHint = $"{npc.displayName} 不在身边，礼物留到见面再送吧。";
                return;
            }

            pendingGiftSelection = selection;
            OfferGiftConfirmation(selection);
            return;
        }

        var friendshipAwarded = 0;
        if (selection.Action == ItemInteractionAction.Share &&
            !TryCommitShare(selection, out friendshipAwarded))
        {
            uiHint = "这件物品现在无法分享，背包里可能已经没有了。";
            return;
        }

        AddItemMessage(selection);
        _ = SendItemAsync(
            selection,
            selection.Action == ItemInteractionAction.Share ? friendshipAwarded : null);
    }

    private void OfferGiftConfirmation(ItemConversationSelection selection)
    {
        if (Game1.currentLocation is null)
        {
            pendingGiftSelection = null;
            uiHint = "当前地点无法完成赠送。";
            return;
        }

        SuspendInput();
        var responses = new[]
        {
            new Response("gift_confirm", "确定赠送"),
            new Response("gift_cancel", "先不送了"),
        };
        Game1.currentLocation.createQuestionDialogue(
            $"要把 {selection.Snapshot.DisplayName} 送给 {npc.displayName} 吗？",
            responses,
            (farmer, answer) => HandleGiftConfirmation(answer),
            npc);
    }

    private void HandleGiftConfirmation(string answer)
    {
        var selection = pendingGiftSelection;
        pendingGiftSelection = null;
        Game1.activeClickableMenu = this;
        ResumeInput();
        if (selection is null || !string.Equals(answer, "gift_confirm", StringComparison.Ordinal))
        {
            uiHint = "这次先不送了。";
            return;
        }

        if (!VanillaGiftHandler.TryGive(npc, selection.Item, Game1.player))
        {
            uiHint = "这件物品现在没法送出去。";
            return;
        }

        AddItemMessage(selection);
        _ = SendItemAsync(selection);
    }

    private void AddItemMessage(ItemConversationSelection selection)
    {
        var action = selection.Action switch
        {
            ItemInteractionAction.Display => "展示",
            ItemInteractionAction.Share => "分享",
            ItemInteractionAction.Gift => "送出",
            _ => "拿出",
        };
        AddMessage(new ChatDisplayMessage(
            "player",
            $"（{action}了 {selection.Snapshot.DisplayName}）"));
    }

    private async Task SendItemAsync(
        ItemConversationSelection selection,
        int? friendshipAwarded = null)
    {
        var message = ItemInteractionRules.DescribeItemAction(
            selection.Action,
            selection.Snapshot.DisplayName);
        await SendAsync(
            message,
            ConversationIntent.Item,
            selection.ToConversationContext(friendshipAwarded)).ConfigureAwait(true);
    }

    private bool TryCommitShare(
        ItemConversationSelection selection,
        out int friendshipAwarded)
    {
        friendshipAwarded = 0;
        var preview = ItemInteractionRules.CreatePreview(
            selection.Snapshot,
            selection.Action);
        if (!preview.ConsumesItem ||
            !VanillaGiftHandler.TryConsumeOne(selection.Item, Game1.player))
        {
            return false;
        }

        friendshipAwarded = VanillaGiftHandler.TryAwardShareFriendship(
            npc,
            Game1.player,
            shareFriendshipLedger,
            Game1.Date.TotalDays);
        return true;
    }

    private string NormalizeReply(string reply)
    {
        var normalized = string.IsNullOrWhiteSpace(reply)
            ? "……"
            : reply.Trim();
        var prefixes = new[]
        {
            npc.displayName + ":",
            npc.Name + ":",
            npc.displayName + "：",
            npc.Name + "：",
        };
        foreach (var prefix in prefixes.Where(prefix => !string.IsNullOrWhiteSpace(prefix)))
        {
            if (normalized.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                return normalized[prefix.Length..].TrimStart();
            }
        }

        return normalized;
    }

    private void AddMessage(ChatDisplayMessage message)
    {
        messages.Add(message);
        followLatest = true;
    }

    private void MoveScroll(int delta)
    {
        if (scrollMaxStartIndex <= 0)
        {
            return;
        }

        followLatest = false;
        scrollStartIndex = ChatScrollRules.MoveStartIndex(
            scrollStartIndex,
            delta,
            scrollMaxStartIndex);
        if (scrollStartIndex == scrollMaxStartIndex)
        {
            followLatest = true;
        }
    }

    private void JumpToLatest()
    {
        scrollStartIndex = scrollMaxStartIndex;
        followLatest = true;
    }

    private void SetScrollFromPointer(int pointerY)
    {
        if (scrollBarTrack == Rectangle.Empty || scrollBarThumb == Rectangle.Empty ||
            scrollMaxStartIndex <= 0)
        {
            return;
        }

        var travel = Math.Max(0, scrollBarTrack.Height - scrollBarThumb.Height);
        var relative = Math.Clamp(
            pointerY - scrollBarTrack.Y - (scrollBarThumb.Height / 2),
            0,
            travel);
        scrollStartIndex = travel == 0
            ? scrollMaxStartIndex
            : (int)Math.Round(scrollMaxStartIndex * (relative / (double)travel));
        followLatest = scrollStartIndex == scrollMaxStartIndex;
    }

    private void DrawBackdrop(SpriteBatch b)
    {
        // 遮罩强度与 F9／群聊中心统一（MenuSkinRules.ScrimAlpha）；改前这里是 0.42f，
        // 而另外两个界面完全没有遮罩。
        MenuSkinDrawing.DrawScrim(b);
    }

    private void DrawHeader(SpriteBatch b)
    {
        if (!ChatLayoutRules.ShouldDrawHeaderTitle())
        {
            return;
        }

        var relationship = GetFriendshipHearts() is { } hearts
            ? $"好感度 {hearts} 心"
            : "好感度未知";
        // 标题带：角色强调色竖条 + 「和 X 聊聊」+ 好感度 + 发丝分隔线。
        // 强调色与气泡、徽章同一个来源；状态字走次级文字色。
        MenuSkinDrawing.DrawTitleBand(
            b,
            layout.Header,
            $"和 {npc.displayName} 聊聊",
            ChatLayoutRules.ShouldDrawHeaderStatus() ? relationship : null,
            MenuSkinDrawing.AccentFor(npc.Name));
    }

    private void DrawMessages(SpriteBatch b)
    {
        var area = layout.ConversationArea;
        // 「哪些消息可见」只有一份实现（ChatLayoutRules.VisibleMessages），
        // 不再在这里另写一次同样的过滤条件。
        var history = ChatLayoutRules.VisibleMessages(messages);
        var maxWidth = Math.Max(
            80,
            area.Width
                - (MessagePadding * 2)
                - ScrollBarWidth
                - ScrollBarGap);
        var contentWidth = Math.Max(
            80,
            maxWidth - (BubblePadding * 2) - BubbleSafetyMargin);
        var measure = (string value) => Game1.smallFont.MeasureString(value).X;
        var lineHeight = Game1.smallFont.LineSpacing + MessageLineSpacing;
        var fixedHeight = (BubblePadding * 2)
            + Game1.smallFont.LineSpacing
            + MessageLineSpacing;
        var availableHeight = Math.Max(
            1,
            area.Height - (MessagePadding * 2) - BubbleSafetyMargin);
        var latestWindow = ChatTextLayoutRules.SelectLatestThatFit(
            history,
            history.Count == 0 ? 1 : history.Count,
            availableHeight,
            BubbleGap,
            message =>
            {
                var lines = ChatTextLayoutRules.Wrap(message.Content, contentWidth, measure);
                return ChatBubbleDrawing.MeasureMessage(message.Role, lines);
            });
        scrollMaxStartIndex = Math.Max(0, history.Count - latestWindow.Count);
        if (followLatest)
        {
            scrollStartIndex = scrollMaxStartIndex;
        }

        scrollStartIndex = ChatScrollRules.ClampStartIndex(
            scrollStartIndex,
            scrollMaxStartIndex);
        var y = area.Y + MessagePadding;
        foreach (var message in history.Skip(scrollStartIndex))
        {
            var isPlayer = message.Role == ChatHistoryRules.PlayerRole;
            var isDivider = string.Equals(
                message.Role,
                ChatHistoryRules.SessionRole,
                StringComparison.Ordinal);
            // 发言人与配色都取自这一条自己（群聊场次里会有别的 NPC 与玩家本人），
            // 只有老式私聊消息没有携带发言人，才退回当前私聊对象。
            var speaker = isPlayer
                ? "你"
                : message.SpeakerName ?? npc.displayName;
            var bubbleNpcId = message.SpeakerId ?? npc.Name;
            var lines = ChatTextLayoutRules.Wrap(message.Content, contentWidth, measure);
            if (lines.Count == 0)
            {
                continue;
            }

            if (isDivider)
            {
                // 分节线不是谁说的话：它标出「这里开始是一整场群聊」以及当时都有谁在
                // （见 GroupSessionRules.ToTimeline），所以不走气泡那套配色与对齐。
                var dividerHeight = ChatBubbleDrawing.MeasureDividerHeight(lines.Count);
                if (y + dividerHeight > area.Bottom - MessagePadding)
                {
                    break;
                }

                y += ChatBubbleDrawing.DrawDivider(
                    b,
                    area.X + MessagePadding,
                    area.Right - MessagePadding,
                    y,
                    lines) + BubbleGap;
                continue;
            }

            var remainingHeight = area.Bottom - MessagePadding - BubbleSafetyMargin - y;
            var maxLineCount = (remainingHeight - fixedHeight + MessageLineSpacing) / lineHeight;
            if (maxLineCount <= 0)
            {
                break;
            }

            lines = ChatTextLayoutRules.Fit(
                lines,
                maxLineCount,
                contentWidth,
                measure);

            var bubbleHeight = ChatBubbleDrawing.MeasureHeight(lines.Count);
            if (y + bubbleHeight > area.Bottom - MessagePadding)
            {
                break;
            }

            // 气泡的尺寸、换行宽度、角色配色、图标徽章与文字颜色统一由
            // ChatBubbleDrawing 决定——F9 群聊走的是同一份逻辑，不再各写一套。
            var drawnHeight = ChatBubbleDrawing.Draw(
                b,
                area.X + MessagePadding,
                area.Right - MessagePadding,
                y,
                speaker,
                lines,
                bubbleNpcId,
                isPlayer);

            y += drawnHeight + BubbleGap;
        }

        UpdateScrollBar(
            area,
            history.Count,
            Math.Max(1, latestWindow.Count),
            scrollStartIndex);
        DrawScrollBar(b);

        if (!string.IsNullOrWhiteSpace(uiHint) && y < area.Bottom - MessagePadding)
        {
            // 提示行文字色与 F9 群聊、Hub 同源：三处都用 MenuSkinRules.InkSoft（次级文字档）。
            b.DrawString(
                Game1.smallFont,
                uiHint,
                new Vector2(area.X + MessagePadding, y),
                MenuSkinRules.InkSoft);
        }

        DrawProfile(b);
    }

    private void UpdateScrollBar(
        Rectangle area,
        int itemCount,
        int visibleCount,
        int startIndex)
    {
        if (itemCount <= 0 || scrollMaxStartIndex <= 0)
        {
            scrollBarTrack = Rectangle.Empty;
            scrollBarThumb = Rectangle.Empty;
            return;
        }

        var trackHeight = Math.Max(1, area.Height - (MessagePadding * 2));
        scrollBarTrack = new Rectangle(
            area.Right - MessagePadding - ScrollBarWidth,
            area.Y + MessagePadding,
            ScrollBarWidth,
            trackHeight);
        var thumbHeight = Math.Clamp(
            (int)Math.Round(trackHeight * (visibleCount / (double)itemCount)),
            Math.Min(ScrollBarMinThumb, trackHeight),
            trackHeight);
        var thumbTravel = trackHeight - thumbHeight;
        var thumbFraction = scrollMaxStartIndex == 0
            ? 0d
            : startIndex / (double)scrollMaxStartIndex;
        var thumbY = scrollBarTrack.Y + (int)Math.Round(thumbTravel * thumbFraction);
        scrollBarThumb = new Rectangle(
            scrollBarTrack.X,
            thumbY,
            scrollBarTrack.Width,
            thumbHeight);
    }

    private void DrawScrollBar(SpriteBatch b)
    {
        if (scrollBarTrack == Rectangle.Empty)
        {
            return;
        }

        b.Draw(
            Game1.fadeToBlackRect,
            scrollBarTrack,
            new Color(205, 190, 167) * 0.72f);
        b.Draw(
            Game1.fadeToBlackRect,
            scrollBarThumb,
            followLatest
                ? new Color(120, 84, 56)
                : new Color(154, 112, 76));
    }

    private void DrawFooter(SpriteBatch b)
    {
        // 输入区做成凹槽，输入框（48px）在其中垂直居中。
        MenuSkinDrawing.DrawInset(b, layout.InputBox);
        // 按钮两档 tint：主按钮白（发送），其余退到暗一档的暖色。
        // 改前这里是四种几乎分不清的淡色（淡绿/淡紫/淡蓝/淡粉），在橙底上只留下偏色。
        MenuButtonDrawing.DrawButton(b, layout.SendButton, "发送", enabled: !sending, tint: MenuSkinRules.PrimaryButtonTint);
        MenuButtonDrawing.DrawButton(b, layout.TopicButton, "找话题", enabled: !sending, tint: MenuSkinRules.SecondaryButtonTint);
        MenuButtonDrawing.DrawButton(b, layout.InventoryButton, "物品", enabled: !sending, tint: MenuSkinRules.SecondaryButtonTint);
        MenuButtonDrawing.DrawButton(b, layout.CloseButton, "结束", enabled: true, tint: MenuSkinRules.SecondaryButtonTint);
        inputBox.Draw(b, drawShadow: true);
    }

    private void DrawProfile(SpriteBatch b)
    {
        if (layout.ProfilePanel == Rectangle.Empty)
        {
            return;
        }

        var panel = layout.ProfilePanel;
        // 角色卡回到白 tint：它之所以现在看不出层次，是因为底层（消息区）原本也是白 tint；
        // 有了上面那层凹槽之后自动分层，卡片自身不需要换颜色。
        drawTextureBox(
            b,
            panel.X,
            panel.Y,
            panel.Width,
            panel.Height,
            MenuSkinRules.CardTint);

        // 头像改走**游戏原版对话框的同一条肖像路径**（规则见 NpcPortraitRules）：
        // 贴图直接取 NPC.Portrait，源矩形按原版 DialogueBox.drawPortrait 的口径
        // （Game1.getSourceRectForStandardTileSheet(tex, $neutral 帧, 64, 64)，越界回落 (0,0,64,64)）。
        // 因此这里显示的就是「实际对话」里那张图，Portraits/<NPC> 一类的美化包
        // （Content Patcher 的替换结果）不需要额外适配就会跟着生效。
        // 改前是自己拼的 new Rectangle(0, 0, 64, 64)：标准贴图上与 $neutral 恰好同帧，
        // 但少了原版的越界判定，贴图布局非标准时会取到贴图外的区域。
        // 立绘位的位置与尺寸（PortraitSize = 64×64）保持改前不变。
        var portrait = NpcPortraitRules.TryResolvePortrait(npc);
        var portraitFrame = new Rectangle(
            panel.X + MessagePadding,
            panel.Y + ((panel.Height - PortraitSize) / 2),
            PortraitSize,
            PortraitSize);
        // 白描边底板无论有没有头像都画：它本来就是这块立绘位的「现在的观感」，
        // 拿不到肖像时至少留下一个空位，而不是一个看不见的洞。
        drawTextureBox(
            b,
            portraitFrame.X - 6,
            portraitFrame.Y - 6,
            portraitFrame.Width + 12,
            portraitFrame.Height + 12,
            Color.White);
        if (portrait is not null)
        {
            // 原版把 64×64 源帧画进 256×256 立绘位（scale 4f）；F8 的位子只有 64×64，
            // 所以按 1:1 落图 —— 取图来源与帧序号与原版一致，只有显示尺寸不同。
            b.Draw(
                portrait,
                portraitFrame,
                NpcPortraitRules.ResolveSourceRect(portrait.Width, portrait.Height),
                Color.White);
        }

        var infoX = portraitFrame.Right + MessagePadding;
        var infoY = panel.Y + 22;
        b.DrawString(
            Game1.smallFont,
            npc.displayName,
            new Vector2(infoX, infoY),
            Color.Black);

        var hearts = GetFriendshipHearts();
        var relationship = hearts is { } value ? $"好感度 {value} 心" : "好感度未知";
        b.DrawString(
            Game1.smallFont,
            relationship,
            new Vector2(infoX, infoY + 28),
            MenuSkinRules.InkSoft);

        if (ChatLayoutRules.ShouldDrawFriendshipMeter(hearts))
        {
            var meter = new Rectangle(
                infoX,
                panel.Bottom - MessagePadding - 10,
                panel.Right - infoX - MessagePadding,
                10);
            b.Draw(Game1.fadeToBlackRect, meter, new Color(206, 195, 180));
            if (hearts is { } friendshipHearts && meter.Width > 0)
            {
                var filledWidth = (int)Math.Round(
                    meter.Width * Math.Clamp(friendshipHearts / 10f, 0f, 1f));
                if (filledWidth > 0)
                {
                    b.Draw(Game1.fadeToBlackRect, new Rectangle(meter.X, meter.Y, filledWidth, meter.Height), new Color(181, 137, 191));
                }
            }
        }
    }

    private int? GetFriendshipHearts()
    {
        return friendshipHeartsOverride ?? GameStateCollector.Collect(npc).FriendshipHearts;
    }

    private void UpdateInputBoxBounds()
    {
        // 只动 TextBox 的**绘制**矩形：48px 高、在输入区里居中。
        // receiveLeftClick 仍走 layout.InputBox.Contains，点击范围不变。
        var visual = MenuSkinRules.InputBoxVisual(layout.InputBox);
        inputBox.X = visual.X;
        inputBox.Y = visual.Y;
        inputBox.Width = visual.Width;
        inputBox.Height = visual.Height;
    }

    private void CleanupKeyboardSubscriber()
    {
        keyboardSubscriberLease.Release();
    }

    private void SuspendInput()
    {
        keyboardSubscriberLease.Suspend();
    }

    private void ResumeInput()
    {
        if (!closed)
        {
            keyboardSubscriberLease.Resume();
            if (ReferenceEquals(Game1.keyboardDispatcher.Subscriber, inputBox))
            {
                inputBox.SelectMe();
            }
        }
    }
}
