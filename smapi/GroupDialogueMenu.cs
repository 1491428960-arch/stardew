using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Microsoft.Xna.Framework.Input;
using StardewValley;
using StardewValley.Menus;

namespace StardewAI.NPC;

public sealed class GroupDialogueMenu : IClickableMenu
{
    private readonly BridgeClient? bridgeClient;
    private readonly StoryStateStore storyStateStore;
    private readonly IReadOnlyList<GroupDialogueParticipant> participants;
    private readonly Action? onClosed;
    private readonly CancellationTokenSource cancellationSource = new();
    private readonly TaskResultPump<BridgeGroupDialogueResponse> pendingRequest = new();
    private readonly KeyboardSubscriberLease<IKeyboardSubscriber> keyboardSubscriberLease;
    private readonly TextBox inputBox;
    private readonly Dictionary<string, string> displayNames;
    private readonly List<GroupDialogueHistoryEntry> visibleMessages = new();
    private GroupDialogueSession session;
    private GroupDialogueLayout layout;
    private string hint = "线上群聊不会传送 NPC，也不会改变他们的日程。";
    private string? pendingPlayerMessage;
    private bool sending;
    private bool closed;

    public GroupDialogueMenu(
        BridgeClient? bridgeClient,
        StoryStateStore storyStateStore,
        GroupDialogueInvitationRecord invitation,
        IReadOnlyList<GroupDialogueParticipant> participants,
        Action? onClosed = null)
        : base(0, 0, 1, 1)
    {
        this.bridgeClient = bridgeClient;
        this.storyStateStore = storyStateStore ?? throw new ArgumentNullException(nameof(storyStateStore));
        this.participants = participants ?? throw new ArgumentNullException(nameof(participants));
        this.onClosed = onClosed;
        session = GroupDialogueSessionRules.Create(invitation);
        displayNames = participants.ToDictionary(item => item.NpcId, item => item.DisplayName, StringComparer.OrdinalIgnoreCase);

        layout = CalculateLayout();
        xPositionOnScreen = layout.Panel.X;
        yPositionOnScreen = layout.Panel.Y;
        width = layout.Panel.Width;
        height = layout.Panel.Height;

        inputBox = new TextBox(Game1.content.Load<Texture2D>("LooseSprites\\textBox"), null, Game1.smallFont, Color.Black)
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

    public GroupDialogueSession Session => session;

    /// <summary>诊断用：最近一次群聊请求里，成功带上自己游戏状态的参与者数量。</summary>
    internal int LastRequestStateCount { get; private set; }

    /// <summary>诊断用：最近一次群聊请求的参与者名单。</summary>
    internal IReadOnlyList<string> LastRequestParticipantIds { get; private set; } =
        Array.Empty<string>();

    /// <summary>诊断用：最近一次群聊请求的参与者快照（含各自 gameState）。</summary>
    internal IReadOnlyList<GroupDialogueParticipant> LastRequestParticipants { get; private set; } =
        Array.Empty<GroupDialogueParticipant>();

    /// <summary>诊断用：最近一次群聊响应的完整 JSON（含 warnings / providerCalls / usage）。</summary>
    internal string? LastResponseJson { get; private set; }

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

        if (layout.RetryButton.Contains(x, y) && session.CanRetry)
        {
            _ = SendCurrentAsync(retry: true);
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

        PumpPendingRequest();
        base.update(time);
    }

    public override void draw(SpriteBatch b)
    {
        if (closed)
        {
            return;
        }

        PumpPendingRequest();
        layout = CalculateLayout();
        xPositionOnScreen = layout.Panel.X;
        yPositionOnScreen = layout.Panel.Y;
        width = layout.Panel.Width;
        height = layout.Panel.Height;
        inputBox.X = layout.InputBox.X;
        inputBox.Y = layout.InputBox.Y;
        inputBox.Width = layout.InputBox.Width;
        inputBox.Height = layout.InputBox.Height;

        // 与线上多人对话中心一致：Game1.drawDialogueBox 仍会把自定义面板裁到
        // 原版 title-safe 区域，导致标题与参与者行落到框外；这里用九宫格纹理
        // 直接按 layout 的矩形绘制，按钮与点击坐标保持不变。
        drawTextureBox(
            b,
            layout.Panel.X,
            layout.Panel.Y,
            layout.Panel.Width,
            layout.Panel.Height,
            Color.White);
        b.DrawString(Game1.smallFont, "线上多人对话", new Vector2(layout.Header.X + 12, layout.Header.Y + 10), Color.Black);
        b.DrawString(Game1.smallFont, string.Join("、", participants.Select(item => item.DisplayName)), new Vector2(layout.ParticipantStrip.X, layout.ParticipantStrip.Y), Color.DarkSlateGray);

        var y = layout.MessageArea.Y + 12;
        foreach (var message in visibleMessages.TakeLast(10))
        {
            var speaker = message.SpeakerType == "player"
                ? "玩家"
                : displayNames.GetValueOrDefault(message.SpeakerId, message.SpeakerId);
            b.DrawString(Game1.smallFont, $"{speaker}：{message.Content}", new Vector2(layout.MessageArea.X + 12, y), message.SpeakerType == "player" ? Color.DarkSlateBlue : Color.Black);
            y += Game1.smallFont.LineSpacing + 8;
            if (y > layout.MessageArea.Bottom - Game1.smallFont.LineSpacing)
            {
                break;
            }
        }

        DrawButton(b, layout.SendButton, "发送", !sending);
        DrawButton(b, layout.RetryButton, "重试", !sending && session.CanRetry);
        DrawButton(b, layout.CloseButton, "关闭", true);
        inputBox.Draw(b, drawShadow: true);
        b.DrawString(Game1.smallFont, hint, new Vector2(layout.MessageArea.X + 12, layout.MessageArea.Bottom - 28), Color.Gray);
        drawMouse(b);
    }

    protected override void cleanupBeforeExit()
    {
        keyboardSubscriberLease.Release();
        cancellationSource.Cancel();
        pendingRequest.Clear();
        cancellationSource.Dispose();
        base.cleanupBeforeExit();
    }

    private Task SendCurrentAsync(bool retry = false)
    {
        if (sending || closed || bridgeClient is null)
        {
            if (bridgeClient is null)
            {
                hint = "Bridge 当前不可用；邀约仍保留，可以稍后重试。";
            }
            return Task.CompletedTask;
        }

        var message = inputBox.Text.Trim();
        if (!retry && message.Length == 0)
        {
            hint = "先写点什么吧。";
            return Task.CompletedTask;
        }

        inputBox.Text = string.Empty;
        sending = true;
        if (!retry)
        {
            pendingPlayerMessage = message;
        }
        hint = "正在等待线上回复……";
        var activeSpeakerNpcId = participants[0].NpcId;
        // 每个参与者带各自的状态：非发言人也需要正确的阶段与好感，不能串用首位的状态。
        var participantsWithState = GroupDialogueStateRules.ResolveParticipantStates(
            participants,
            npcId =>
            {
                // 线上群聊不要求 NPC 在场；解析失败时保持未知，不能误报成空事件列表。
                var npc = Game1.getCharacterFromName(npcId);
                return npc is null ? null : GameStateCollector.Collect(npc);
            });
        var gameState = participantsWithState
            .FirstOrDefault(item => string.Equals(
                item.NpcId,
                activeSpeakerNpcId,
                StringComparison.OrdinalIgnoreCase))
            ?.GameState;
        // 诊断证据：请求里每个参与者是否带上了各自的状态。
        LastRequestParticipants = participantsWithState;
        LastRequestParticipantIds = participantsWithState
            .Select(item => item.NpcId)
            .ToArray();
        LastRequestStateCount = participantsWithState
            .Count(item => item.GameState is not null);
        var request = new GroupDialogueRequest(
            retry ? "请继续回应刚才的群聊话题。" : message,
            participantsWithState,
            string.IsNullOrWhiteSpace(session.Invitation.Topic) ? null : session.Invitation.Topic,
            string.IsNullOrWhiteSpace(session.Invitation.Guidance) ? null : session.Invitation.Guidance,
            session.PublicHistory,
            activeSpeakerNpcId,
            gameState,
            Array.Empty<string>(),
            null,
            "auto");
        try
        {
            pendingRequest.Start(bridgeClient.SendGroupAsync(request, cancellationSource.Token));
        }
        catch (Exception exception)
        {
            sending = false;
            hint = $"请求未发出：{exception.GetType().Name}。";
        }

        return Task.CompletedTask;
    }

    private void PumpPendingRequest()
    {
        if (!pendingRequest.TryTakeCompleted(out var response, out var error))
        {
            return;
        }

        sending = false;
        if (error is not null)
        {
            hint = "请求失败，邀约仍可重试。";
            return;
        }

        LastResponseJson = System.Text.Json.JsonSerializer.Serialize(response);
        var next = GroupDialogueSessionRules.ApplyResult(session, response.Turns, response.Fallback);
        if (response.Fallback || next.Invitation.Status != GroupInvitationStatus.Completed)
        {
            session = next;
            hint = "这次没有可用回复，公开历史未写入，可以重试。";
            return;
        }

        if (!string.IsNullOrWhiteSpace(pendingPlayerMessage))
        {
            visibleMessages.Add(new GroupDialogueHistoryEntry(
                "player",
                "player",
                pendingPlayerMessage.Trim()));
        }
        visibleMessages.AddRange(next.PublicHistory.Skip(session.PublicHistory.Count));
        pendingPlayerMessage = null;
        session = next;
        if (!string.IsNullOrWhiteSpace(session.Invitation.InvitationId))
        {
            storyStateStore.TrySetGroupInvitationStatus(
                session.Invitation.InvitationId,
                GroupInvitationStatus.Completed);
        }
        // Bridge 只挑出值得长期记住的事实或约定；这些是玩家当着所有人说的，
        // 在场的每个 NPC 各记一条，闲聊不会出现在这里。
        ApplyMemoryHighlights(response.MemoryHighlights);
        hint = string.Empty;
    }

    /// <summary>
    /// 把高亮写进长期记忆。写入计划由 <see cref="GroupMemoryRules"/> 给出，
    /// 生产路径与视觉测试路径共用同一段逻辑。
    /// </summary>
    internal void ApplyMemoryHighlights(IReadOnlyList<string>? highlights)
    {
        var gameDate = $"{Game1.currentSeason} {Game1.dayOfMonth}";
        foreach (var write in GroupMemoryRules.Plan(
                     participants.Select(item => item.NpcId),
                     highlights))
        {
            storyStateStore.RecordMemoryHighlight(write.NpcId, write.Content, gameDate);
        }
    }

    /// <summary>
    /// 视觉测试专用入口：把一条已经拿到的响应交给同一个 pendingRequest 管线，
    /// 让后续 update/draw 的 <see cref="PumpPendingRequest"/> 走与真实 Bridge
    /// 响应完全相同的成功分支，而不是让测试另走一条旁路。
    /// </summary>
    internal void QueueResponseForVisualTest(
        BridgeGroupDialogueResponse response,
        string? playerMessage)
    {
        ArgumentNullException.ThrowIfNull(response);
        pendingPlayerMessage = string.IsNullOrWhiteSpace(playerMessage)
            ? null
            : playerMessage.Trim();
        sending = true;
        pendingRequest.Start(Task.FromResult(response));
    }

    /// <summary>
    /// 视觉测试专用入口：像玩家一样填好输入框并点击“发送”。
    /// 它走的是 receiveLeftClick 的发送按钮分支，因此与手动点击完全同一条代码路径。
    /// </summary>
    internal void PressSendForVisualTest(string message)
    {
        inputBox.Text = message ?? string.Empty;
        inputBox.SelectMe();
        layout = CalculateLayout();
        receiveLeftClick(layout.SendButton.Center.X, layout.SendButton.Center.Y);
    }

    private void OnInputEnterPressed(TextBox sender)
    {
        _ = sender;
        _ = SendCurrentAsync();
    }

    private void Close()
    {
        if (closed)
        {
            return;
        }

        closed = true;
        keyboardSubscriberLease.Release();
        cancellationSource.Cancel();
        onClosed?.Invoke();
        exitThisMenu();
    }

    private static void DrawButton(SpriteBatch b, Rectangle bounds, string label, bool enabled)
    {
        drawTextureBox(b, bounds.X, bounds.Y, bounds.Width, bounds.Height, enabled ? Color.White : Color.Gray);
        var size = Game1.smallFont.MeasureString(label);
        b.DrawString(Game1.smallFont, label, new Vector2(bounds.Center.X - size.X / 2f, bounds.Center.Y - size.Y / 2f), enabled ? Color.Black : Color.DimGray);
    }

    private static GroupDialogueLayout CalculateLayout()
    {
        var viewportSize = MenuViewportRules.PreferUiViewport(
            Game1.viewport.Width,
            Game1.viewport.Height,
            Game1.uiViewport.Width,
            Game1.uiViewport.Height);
        return GroupDialogueLayoutRules.Calculate(viewportSize.X, viewportSize.Y);
    }
}
