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
    // 整场只自动开场一次；由 GroupDialogueSessionRules.ShouldOpenWithNpc 判定时机。
    private bool openingRequested;

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
            Text = string.Empty,
        };
        // 与 F8 同源：输入框的绘制矩形只有 MenuSkinRules.InputBoxVisual 一处定义，
        // 命中判定继续用 layout.InputBox。
        UpdateInputBoxBounds();
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

        // 刚开一场群聊时由 NPC 先起头：玩家接受邀约后还没说话，
        // 若等玩家先开口，邀约就起不到引导作用（2026-09-20 用户反馈）。
        if (GroupDialogueSessionRules.ShouldOpenWithNpc(session, openingRequested))
        {
            openingRequested = true;
            _ = SendCurrentAsync(opening: true);
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
        UpdateInputBoxBounds();

        // 遮罩与 F8／群聊中心统一（改前这里完全没有遮罩，三个界面「浮在画面上的高度」不一致）。
        MenuSkinDrawing.DrawScrim(b);
        // 与线上多人对话中心一致：Game1.drawDialogueBox 仍会把自定义面板裁到
        // 原版 title-safe 区域，导致标题与参与者行落到框外；这里用九宫格纹理
        // 直接按 layout 的矩形绘制，按钮与点击坐标保持不变。
        MenuSkinDrawing.DrawPanel(b, layout.Panel);

        // 标题带（竖条 + 标题 + 发丝分隔线），强调色取第一位参与者的角色色。
        var participantNames = string.Join("、", participants.Select(item => item.DisplayName));
        MenuSkinDrawing.DrawTitleBand(
            b,
            layout.Header,
            "线上多人对话",
            null,
            MenuSkinDrawing.AccentFor(participants.Count > 0 ? participants[0].NpcId : null));
        b.DrawString(Game1.smallFont, participantNames, new Vector2(layout.ParticipantStrip.X, layout.ParticipantStrip.Y), MenuSkinRules.InkSoft);

        // 提示行放哪：**短提示**（正常态）放 header 右侧、与参与者条同一行 —— 气泡区零损失；
        // **长提示**（"无可用回复(fb=… n=… spk=[…])" 那种排障串）放不下 header，就回落到
        // 消息区下方。这一条是本次唯一动了气泡可用高度的分支，且只在长提示时才触发；
        // 提示行与气泡不接收点击，两个分支都不改任何命中区。
        // 提示为空（群聊成功回复后会清空）时按「没有东西要放」处理，不占底部留白。
        var namesWidth = Game1.smallFont.MeasureString(participantNames).X;
        var hintWidth = string.IsNullOrWhiteSpace(hint)
            ? 0f
            : Game1.smallFont.MeasureString(hint).X;
        var hintNeedsBottomRow = MenuSkinRules.HintNeedsBottomRow(
            !string.IsNullOrWhiteSpace(hint),
            layout.ParticipantStrip.Width,
            namesWidth,
            hintWidth);

        var messageArea = layout.MessageArea;
        var bubbleAreaHeight = MenuSkinRules.MessageBubbleAreaHeight(messageArea.Height, hintInHeader: !hintNeedsBottomRow);
        // 内容区凹槽：气泡浮在它上面（画在气泡之前）。
        MenuSkinDrawing.DrawInset(
            b,
            new Rectangle(messageArea.X, messageArea.Y, messageArea.Width, bubbleAreaHeight));

        // 与 F8 私聊共用 ChatBubbleDrawing：换行宽度、角色配色、图标徽章
        // 只有一处定义。此前这里是一行 "{发言人}：{内容}" 纯文本，长句既不
        // 换行又会溢出面板。
        var bubbleLeft = messageArea.X + 12;
        var bubbleRight = messageArea.Right - 12;
        var contentWidth = ChatBubbleDrawing.ContentWidth(bubbleRight - bubbleLeft);
        var measure = (string value) => Game1.smallFont.MeasureString(value).X;
        var y = messageArea.Y + 12;
        // 按发言人计次：边框构图随 occurrence 在三套布局间轮换（与回放页一致）。
        // 此前一律传 0，于是同一角色多次发言的构图固定不变。
        var seenBySpeaker = new Dictionary<string, int>(System.StringComparer.OrdinalIgnoreCase);
        foreach (var message in visibleMessages.TakeLast(GroupDialogueLayoutRules.MaxVisibleMessages))
        {
            var speakerKey = message.SpeakerId ?? string.Empty;
            var occurrence = seenBySpeaker.TryGetValue(speakerKey, out var seen) ? seen : 0;
            seenBySpeaker[speakerKey] = occurrence + 1;
            var isPlayer = message.SpeakerType == "player";
            // 名单里查得到就用显示名，查不到退回 ID 本身。
            // 与改前的 displayNames.GetValueOrDefault(message.SpeakerId, message.SpeakerId) 同义；
            // 换成 TryGetValue 只为消掉 Dictionary<string,string> 与 <string?,string?> 之间的
            // 可空性推断警告，取值不变。
            var speaker = isPlayer
                ? "玩家"
                : displayNames.TryGetValue(speakerKey, out var displayName)
                    ? displayName
                    : speakerKey;
            var lines = ChatTextLayoutRules.Wrap(
                message.Content ?? string.Empty,
                contentWidth,
                measure);
            if (lines.Count == 0)
            {
                continue;
            }

            var drawnHeight = ChatBubbleDrawing.Draw(
                b,
                bubbleLeft,
                bubbleRight,
                y,
                speaker,
                lines,
                message.SpeakerId,
                isPlayer,
                occurrence);

            y += drawnHeight + ChatBubbleDrawing.Gap;
            if (y > messageArea.Y + bubbleAreaHeight - Game1.smallFont.LineSpacing)
            {
                break;
            }
        }

        // 输入区凹槽 + 按钮两档 tint（发送=主，重试/关闭=次）。
        MenuSkinDrawing.DrawInset(b, layout.InputBox);
        MenuButtonDrawing.DrawButton(b, layout.SendButton, "发送", !sending, MenuSkinRules.PrimaryButtonTint);
        MenuButtonDrawing.DrawButton(b, layout.RetryButton, "重试", !sending && session.CanRetry, MenuSkinRules.SecondaryButtonTint);
        MenuButtonDrawing.DrawButton(b, layout.CloseButton, "关闭", true, MenuSkinRules.SecondaryButtonTint);
        inputBox.Draw(b, drawShadow: true);
        if (hintNeedsBottomRow)
        {
            b.DrawString(
                Game1.smallFont,
                hint,
                new Vector2(messageArea.X + 12, messageArea.Y + bubbleAreaHeight + 4),
                MenuSkinRules.InkSoft);
        }
        else if (!string.IsNullOrWhiteSpace(hint))
        {
            b.DrawString(
                Game1.smallFont,
                hint,
                new Vector2(layout.ParticipantStrip.Right - hintWidth, layout.ParticipantStrip.Y + 5),
                MenuSkinRules.InkSoft);
        }

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

    private Task SendCurrentAsync(bool retry = false, bool opening = false)
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
        // opening：玩家一句话都没说，由 NPC 起头——Bridge 侧把空消息当作开场语义。
        if (!retry && !opening && message.Length == 0)
        {
            hint = "先写点什么吧。";
            return Task.CompletedTask;
        }

        inputBox.Text = string.Empty;
        sending = true;
        if (!retry && !opening)
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
            opening
                ? string.Empty
                : retry
                    ? "请继续回应刚才的群聊话题。"
                    : message,
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
            pendingRequest.Start(bridgeClient.SendGroupAsync(
                request,
                cancellationSource.Token,
                allowEmptyMessage: opening));
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
            // 排障辅助（2026-09-20 起常驻）：把失败的关键事实压成一行放进 hint，
            // 它直接画在菜单上、玩家可见，不需要额外的日志管线。
            // 之所以保留而不是用完就删——「无可用回复」本身是异常情况，而这串信息
            // 上一次直接把排查从“反复猜测”变成了“一眼看出”（当时缺 warn 字段，
            // 正是它藏着 "bridge: message empty" 这个真正的原因）。
            var diag = string.Join(
                " ",
                $"fb={response.Fallback}",
                $"n={response.Turns.Count}",
                $"spk=[{string.Join("|", response.Turns.Select(t => t.SpeakerNpcId))}]",
                $"len=[{string.Join("|", response.Turns.Select(t => (t.Content ?? string.Empty).Length))}]",
                $"add=[{string.Join("|", response.Turns.Select(t => (t.AddressedTo?.Count ?? 0)))}]",
                $"warn=[{string.Join("|", response.Warnings)}]",
                $"roster=[{string.Join("|", session.Invitation.Participants)}]");
            hint = $"无可用回复({diag})。可以重试。";
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

    private static GroupDialogueLayout CalculateLayout()
    {
        var viewportSize = MenuViewportRules.PreferUiViewport(
            Game1.viewport.Width,
            Game1.viewport.Height,
            Game1.uiViewport.Width,
            Game1.uiViewport.Height);
        return GroupDialogueLayoutRules.Calculate(viewportSize.X, viewportSize.Y);
    }

    /// <summary>
    /// 输入框的**绘制**矩形：48px 高、在输入区里居中（<see cref="MenuSkinRules.InputBoxVisual"/>）。
    /// <c>receiveLeftClick</c> 仍走 <c>layout.InputBox.Contains</c>，点击范围不受影响。
    /// </summary>
    private void UpdateInputBoxBounds()
    {
        var visual = MenuSkinRules.InputBoxVisual(layout.InputBox);
        inputBox.X = visual.X;
        inputBox.Y = visual.Y;
        inputBox.Width = visual.Width;
        inputBox.Height = visual.Height;
    }
}
