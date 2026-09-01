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
    private const int BubblePadding = 12;
    private const int BubbleSafetyMargin = 8;
    private const int BubbleGap = 8;
    private const int MessageLineSpacing = 4;
    private const int ScrollBarWidth = 12;
    private const int ScrollBarGap = 8;
    private const int ScrollBarMinThumb = 24;
    private const int ScrollPageStep = 3;

    private readonly StardewNpc npc;
    private readonly ConversationService conversationService;
    private readonly StoryStateStore storyStateStore;
    private readonly Action onClosed;
    private readonly int? friendshipHeartsOverride;
    private readonly CancellationTokenSource cancellationSource = new();
    private readonly List<ChatDisplayMessage> messages = new();
    private readonly KeyboardSubscriberLease<IKeyboardSubscriber> keyboardSubscriberLease;
    private readonly TextBox inputBox;
    private readonly TaskResultPump<ConversationTurnResult> pendingRequest = new();
    private ChatLayout layout;
    private Rectangle scrollBarTrack = Rectangle.Empty;
    private Rectangle scrollBarThumb = Rectangle.Empty;
    private string uiHint = "输入一句话，或者让她先找个话题。";
    private ItemConversationSelection? pendingGiftSelection;
    private int scrollMaxStartIndex;
    private int scrollStartIndex;
    private bool sending;
    private bool closed;
    private bool followLatest = true;

    public ChatInputMenu(
        StardewNpc npc,
        ConversationService conversationService,
        StoryStateStore storyStateStore,
        Action onClosed,
        IReadOnlyList<ChatDisplayMessage>? initialMessages = null,
        int? friendshipHeartsOverride = null)
        : base(0, 0, 1, 1)
    {
        this.npc = npc ?? throw new ArgumentNullException(nameof(npc));
        this.conversationService = conversationService ??
            throw new ArgumentNullException(nameof(conversationService));
        this.storyStateStore = storyStateStore ??
            throw new ArgumentNullException(nameof(storyStateStore));
        this.onClosed = onClosed;
        this.friendshipHeartsOverride = friendshipHeartsOverride;

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
            X = layout.InputBox.X,
            Y = layout.InputBox.Y,
            Width = layout.InputBox.Width,
            Height = layout.InputBox.Height,
            Text = string.Empty,
        };
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
        Game1.drawDialogueBox(
            layout.Panel.X,
            layout.Panel.Y,
            layout.Panel.Width,
            layout.Panel.Height,
            speaker: false,
            drawOnlyBox: true);
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
        onClosed?.Invoke();
        exitThisMenu();
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

        try
        {
            var state = GameStateCollector.Collect(npc);
            var request = intent == ConversationIntent.Topic
                ? conversationService.RequestTopicAsync(
                    state,
                    cancellationSource.Token)
                : conversationService.SendAsync(
                    state,
                    message ?? string.Empty,
                    cancellationSource.Token,
                    itemContext);
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
            pendingGiftSelection = selection;
            OfferGiftConfirmation(selection);
            return;
        }

        AddItemMessage(selection);
        _ = SendItemAsync(selection);
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

    private async Task SendItemAsync(ItemConversationSelection selection)
    {
        var message = selection.Action switch
        {
            ItemInteractionAction.Display => $"我想给你看看这个：{selection.Snapshot.DisplayName}。",
            ItemInteractionAction.Share => $"我们一起分享这个：{selection.Snapshot.DisplayName}。",
            ItemInteractionAction.Gift => $"我把{selection.Snapshot.DisplayName}送给你。",
            _ => $"我拿出了{selection.Snapshot.DisplayName}。",
        };
        await SendAsync(
            message,
            ConversationIntent.Item,
            selection.ToConversationContext()).ConfigureAwait(true);
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
        var viewport = Game1.viewport;
        b.Draw(
            Game1.fadeToBlackRect,
            new Rectangle(0, 0, viewport.Width, viewport.Height),
            Color.Black * 0.42f);
    }

    private void DrawHeader(SpriteBatch b)
    {
        var title = $"和 {npc.displayName} 聊聊";
        if (ChatLayoutRules.ShouldDrawHeaderTitle())
        {
            b.DrawString(
                Game1.dialogueFont,
                title,
                new Vector2(layout.Header.X + MessagePadding, layout.Header.Y + 8),
                Color.Black);
        }
        if (ChatLayoutRules.ShouldDrawHeaderStatus())
        {
            var relationship = GetFriendshipHearts() is { } hearts
                ? $"原版好感度 · {hearts} 心"
                : "原版好感度 · 未知";
            b.DrawString(
                Game1.smallFont,
                relationship,
                new Vector2(layout.Header.X + MessagePadding, layout.Header.Y + 48),
                Color.DarkSlateGray);
        }
    }

    private void DrawMessages(SpriteBatch b)
    {
        var area = layout.ConversationArea;
        var history = messages
            .Where(message => message is not null && !string.IsNullOrWhiteSpace(message.Content))
            .ToArray();
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
            history.Length == 0 ? 1 : history.Length,
            availableHeight,
            BubbleGap,
            message =>
            {
                var lineCount = ChatTextLayoutRules.Wrap(message.Content, contentWidth, measure).Count;
                return fixedHeight
                    + (lineCount * Game1.smallFont.LineSpacing)
                    + ((lineCount - 1) * MessageLineSpacing);
            });
        scrollMaxStartIndex = Math.Max(0, history.Length - latestWindow.Count);
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
            var isPlayer = message.Role == "player";
            var speaker = isPlayer ? "你" : npc.displayName;
            var lines = ChatTextLayoutRules.Wrap(message.Content, contentWidth, measure);
            if (lines.Count == 0)
            {
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

            var textWidth = lines.Max(line => measure(line));
            var bubbleWidth = Math.Clamp(
                (int)Math.Ceiling(textWidth + (BubblePadding * 2)),
                Math.Min(180, maxWidth),
                maxWidth);
            var bubbleHeight = (BubblePadding * 2)
                + Game1.smallFont.LineSpacing
                + MessageLineSpacing
                + (lines.Count * Game1.smallFont.LineSpacing)
                + ((lines.Count - 1) * MessageLineSpacing);
            if (y + bubbleHeight > area.Bottom - MessagePadding)
            {
                break;
            }

            var bubbleX = isPlayer
                ? area.Right - MessagePadding - bubbleWidth
                : area.X + MessagePadding;
            var bubble = new Rectangle(bubbleX, y, bubbleWidth, bubbleHeight);
            drawTextureBox(
                b,
                bubble.X,
                bubble.Y,
                bubble.Width,
                bubble.Height,
                isPlayer ? new Color(226, 239, 246) : new Color(239, 231, 244));

            var speakerColor = isPlayer ? Color.DarkSlateBlue : Color.DarkMagenta;
            b.DrawString(
                Game1.smallFont,
                speaker,
                new Vector2(bubble.X + BubblePadding, bubble.Y + BubblePadding),
                speakerColor);
            var lineY = bubble.Y + BubblePadding + Game1.smallFont.LineSpacing + MessageLineSpacing;
            foreach (var line in lines)
            {
                b.DrawString(
                    Game1.smallFont,
                    line,
                    new Vector2(bubble.X + BubblePadding, lineY),
                    Color.Black);
                lineY += Game1.smallFont.LineSpacing + MessageLineSpacing;
            }

            y += bubbleHeight + BubbleGap;
        }

        UpdateScrollBar(
            area,
            history.Length,
            Math.Max(1, latestWindow.Count),
            scrollStartIndex);
        DrawScrollBar(b);

        if (!string.IsNullOrWhiteSpace(uiHint) && y < area.Bottom - MessagePadding)
        {
            b.DrawString(
                Game1.smallFont,
                uiHint,
                new Vector2(area.X + MessagePadding, y),
                Color.Gray);
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
        DrawButton(b, layout.SendButton, "发送", enabled: !sending, tint: new Color(235, 246, 236));
        DrawButton(b, layout.TopicButton, "找话题", enabled: !sending, tint: new Color(239, 231, 244));
        DrawButton(b, layout.InventoryButton, "物品", enabled: !sending, tint: new Color(235, 240, 246));
        DrawButton(b, layout.CloseButton, "结束", enabled: true, tint: new Color(247, 232, 227));
        inputBox.Draw(b, drawShadow: true);
    }

    private void DrawProfile(SpriteBatch b)
    {
        if (layout.ProfilePanel == Rectangle.Empty)
        {
            return;
        }

        var panel = layout.ProfilePanel;
        drawTextureBox(
            b,
            panel.X,
            panel.Y,
            panel.Width,
            panel.Height,
            new Color(248, 240, 224));

        var portrait = npc.Portrait;
        var portraitFrame = new Rectangle(
            panel.X + MessagePadding,
            panel.Y + ((panel.Height - PortraitSize) / 2),
            PortraitSize,
            PortraitSize);
        if (portrait is not null)
        {
            drawTextureBox(
                b,
                portraitFrame.X - 6,
                portraitFrame.Y - 6,
                portraitFrame.Width + 12,
                portraitFrame.Height + 12,
                Color.White);
            b.Draw(
                portrait,
                portraitFrame,
                new Rectangle(0, 0, PortraitSize, PortraitSize),
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
            Color.DarkSlateGray);

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

    private static void DrawButton(
        SpriteBatch b,
        Rectangle bounds,
        string label,
        bool enabled,
        Color tint)
    {
        drawTextureBox(b, bounds.X, bounds.Y, bounds.Width, bounds.Height, enabled ? tint : Color.Gray);
        var size = Game1.smallFont.MeasureString(label);
        b.DrawString(
            Game1.smallFont,
            label,
            new Vector2(bounds.Center.X - size.X / 2f, bounds.Center.Y - size.Y / 2f),
            enabled ? Color.Black : Color.DimGray);
    }

    private void UpdateInputBoxBounds()
    {
        inputBox.X = layout.InputBox.X;
        inputBox.Y = layout.InputBox.Y;
        inputBox.Width = layout.InputBox.Width;
        inputBox.Height = layout.InputBox.Height;
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
