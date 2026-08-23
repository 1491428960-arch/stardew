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
    private const int MessagePadding = 16;
    private const int PortraitSize = 64;
    private const int MessageLineSpacing = 4;
    private const int MaxMessageCount = 24;

    private readonly StardewNpc npc;
    private readonly ConversationService conversationService;
    private readonly StoryStateStore storyStateStore;
    private readonly Action onClosed;
    private readonly CancellationTokenSource cancellationSource = new();
    private readonly List<ChatDisplayMessage> messages = new();
    private readonly IKeyboardSubscriber? previousKeyboardSubscriber;
    private readonly TextBox inputBox;
    private ChatLayout layout;
    private string uiHint = "输入一句话，或者让她先找个话题。";
    private bool sending;
    private bool closed;

    public ChatInputMenu(
        StardewNpc npc,
        ConversationService conversationService,
        StoryStateStore storyStateStore,
        Action onClosed)
        : base(0, 0, 1, 1)
    {
        this.npc = npc ?? throw new ArgumentNullException(nameof(npc));
        this.conversationService = conversationService ??
            throw new ArgumentNullException(nameof(conversationService));
        this.storyStateStore = storyStateStore ??
            throw new ArgumentNullException(nameof(storyStateStore));
        this.onClosed = onClosed;

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
        inputBox.SelectMe();

        previousKeyboardSubscriber = Game1.keyboardDispatcher.Subscriber;
        Game1.keyboardDispatcher.Subscriber = inputBox;
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
            uiHint = "背包选择将在下一阶段启用。";
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

        base.receiveKeyPress(key);
    }

    public override void update(GameTime time)
    {
        if (closed)
        {
            return;
        }

        inputBox.Update();
        base.update(time);
    }

    protected override void cleanupBeforeExit()
    {
        CleanupKeyboardSubscriber();
        cancellationSource.Cancel();
        cancellationSource.Dispose();
        base.cleanupBeforeExit();
    }

    public override void draw(SpriteBatch b)
    {
        if (closed)
        {
            return;
        }

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

    protected virtual async Task SendCurrentAsync()
    {
        if (sending)
        {
            return;
        }

        var message = inputBox.Text.Trim();
        if (message.Length == 0)
        {
            uiHint = "先写点什么吧。";
            return;
        }

        inputBox.Text = string.Empty;
        messages.Add(new ChatDisplayMessage("player", message));
        TrimMessages();
        await SendAsync(message, ConversationIntent.Chat).ConfigureAwait(true);
    }

    protected virtual async Task RequestTopicAsync()
    {
        if (sending)
        {
            return;
        }

        await SendAsync(null, ConversationIntent.Topic).ConfigureAwait(true);
    }

    private async Task SendAsync(string? message, string intent)
    {
        sending = true;
        uiHint = "正在思考……";

        try
        {
            var state = GameStateCollector.Collect(npc);
            var result = intent == ConversationIntent.Topic
                ? await conversationService.RequestTopicAsync(
                    state,
                    cancellationSource.Token).ConfigureAwait(true)
                : await conversationService.SendAsync(
                    state,
                    message ?? string.Empty,
                    cancellationSource.Token).ConfigureAwait(true);

            var reply = result.Fallback
                ? "暂时联系不上她，可以稍后重试。"
                : NormalizeReply(result.Reply);
            messages.Add(new ChatDisplayMessage("npc", reply));
            TrimMessages();
            uiHint = result.Fallback
                ? "暂时联系不上她，可以重试或结束。"
                : "";
        }
        catch (OperationCanceledException)
        {
            if (!closed)
            {
                uiHint = "对话已取消。";
            }
        }
        catch (Exception)
        {
            messages.Add(new ChatDisplayMessage("npc", "刚才没听清，我们稍后再聊吧。"));
            TrimMessages();
            uiHint = "暂时联系不上她，可以重试或结束。";
        }
        finally
        {
            sending = false;
        }
    }

    private void OnInputEnterPressed(TextBox sender)
    {
        _ = sender;
        _ = SendCurrentAsync();
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

    private void TrimMessages()
    {
        if (messages.Count > MaxMessageCount)
        {
            messages.RemoveRange(0, messages.Count - MaxMessageCount);
        }
    }

    private void DrawBackdrop(SpriteBatch b)
    {
        var viewport = Game1.viewport;
        b.Draw(
            Game1.fadeToBlackRect,
            new Rectangle(0, 0, viewport.Width, viewport.Height),
            Color.Black * 0.35f);
    }

    private void DrawHeader(SpriteBatch b)
    {
        var portrait = npc.Portrait;
        if (portrait is not null)
        {
            b.Draw(
                portrait,
                new Rectangle(
                    layout.Header.X,
                    layout.Header.Y,
                    PortraitSize,
                    PortraitSize),
                new Rectangle(0, 0, PortraitSize, PortraitSize),
                Color.White);
        }

        var title = $"和 {npc.displayName} 聊聊";
        b.DrawString(
            Game1.dialogueFont,
            title,
            new Vector2(layout.Header.X + PortraitSize + MessagePadding, layout.Header.Y + 8),
            Color.Black);
        var relationship = GameStateCollector.Collect(npc).FriendshipHearts is { } hearts
            ? $"好感度：{hearts} 心"
            : "好感度：未知";
        b.DrawString(
            Game1.smallFont,
            relationship,
            new Vector2(layout.Header.X + PortraitSize + MessagePadding, layout.Header.Y + 48),
            Color.DarkSlateGray);
    }

    private void DrawMessages(SpriteBatch b)
    {
        var visible = ChatLayoutRules.VisibleMessages(messages, MaxMessageCount);
        var y = layout.MessageArea.Y + MessagePadding;
        var maxWidth = layout.MessageArea.Width - (MessagePadding * 2);
        foreach (var message in visible)
        {
            var speaker = message.Role == "player" ? "你" : npc.displayName;
            var color = message.Role == "player" ? Color.DarkSlateBlue : Color.Black;
            foreach (var line in WrapText($"{speaker}：{message.Content}", maxWidth))
            {
                if (y + Game1.smallFont.LineSpacing > layout.MessageArea.Bottom - MessagePadding)
                {
                    return;
                }

                b.DrawString(Game1.smallFont, line, new Vector2(layout.MessageArea.X + MessagePadding, y), color);
                y += Game1.smallFont.LineSpacing + MessageLineSpacing;
            }
        }

        if (!string.IsNullOrWhiteSpace(uiHint) && y < layout.MessageArea.Bottom - MessagePadding)
        {
            b.DrawString(
                Game1.smallFont,
                uiHint,
                new Vector2(layout.MessageArea.X + MessagePadding, y),
                Color.Gray);
        }
    }

    private void DrawFooter(SpriteBatch b)
    {
        DrawButton(b, layout.SendButton, "发送", enabled: !sending);
        DrawButton(b, layout.TopicButton, "找话题", enabled: !sending);
        DrawButton(b, layout.InventoryButton, "物品", enabled: false);
        DrawButton(b, layout.CloseButton, "结束", enabled: true);
        inputBox.Draw(b, drawShadow: true);
    }

    private static void DrawButton(SpriteBatch b, Rectangle bounds, string label, bool enabled)
    {
        drawTextureBox(b, bounds.X, bounds.Y, bounds.Width, bounds.Height, enabled ? Color.White : Color.Gray);
        var size = Game1.smallFont.MeasureString(label);
        b.DrawString(
            Game1.smallFont,
            label,
            new Vector2(bounds.Center.X - size.X / 2f, bounds.Center.Y - size.Y / 2f),
            enabled ? Color.Black : Color.DimGray);
    }

    private static IEnumerable<string> WrapText(string text, int maxWidth)
    {
        if (string.IsNullOrEmpty(text))
        {
            yield break;
        }

        var current = string.Empty;
        foreach (var character in text)
        {
            var candidate = current + character;
            if (current.Length > 0 && Game1.smallFont.MeasureString(candidate).X > maxWidth)
            {
                yield return current;
                current = character.ToString();
            }
            else
            {
                current = candidate;
            }
        }

        if (current.Length > 0)
        {
            yield return current;
        }
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
        if (ReferenceEquals(Game1.keyboardDispatcher.Subscriber, inputBox))
        {
            Game1.keyboardDispatcher.Subscriber = previousKeyboardSubscriber;
        }
    }
}
