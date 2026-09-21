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
    /// <summary>
    /// 只读回看模式（2026-09-21）：这一场已经到期，界面上只准翻看、不准发言。
    /// 输入框、发送/重试、自动开场、键盘租约四处都看它（判据见 <see cref="GroupReadOnlyRules"/>）。
    /// </summary>
    private readonly bool readOnly;
    /// <summary>只读回看时的滚动起点；与 <see cref="followLatest"/> 一起决定这一屏画哪一段。</summary>
    private int scrollStartIndex;
    /// <summary>是否跟随最新一条。滚轮往上翻会关掉它，翻回底部或自己发言时自动打开。</summary>
    private bool followLatest = true;
    /// <summary>
    /// NPC 回复的逐条揭示队列（玩家自己那句**不走它**：那条要立刻上屏，见
    /// <see cref="RevealPlayerLine"/>）。间隔见 <see cref="GroupTranscriptRules.TurnRevealIntervalSeconds"/>。
    /// </summary>
    private readonly GroupTurnRevealQueue revealQueue = new();
    /// <summary>自己那句是否已经上屏。这一轮拿不到可用回复时要撤回，好让「画面 == 存档」重新成立。</summary>
    private bool playerLineRevealed;
    /// <summary>发言前的画面快照，撤回时用它还原。</summary>
    private List<GroupDialogueHistoryEntry>? preSendSnapshot;
    /// <summary>翻到历史里之后，视口外又来了几条（提示行靠它告诉玩家「下面还有东西」）。</summary>
    private int unseenCount;
    /// <summary>滚动产生的位置提示。<c>hint</c> 留给错误诊断，两者同时存在时诊断优先。</summary>
    private string scrollHint = string.Empty;
    /// <summary>
    /// 视觉测试专用：把排进来的响应**一次全部**揭示，不走逐条动画。
    /// 理由：视觉测试要的是稳定可复现的终态（证据行会比对「面板发言数 == 存档场次条数」），
    /// 而逐条是**给人看的时序**；播放本身由 <c>GroupTurnRevealQueue</c> 的单测覆盖。
    /// </summary>
    private bool revealImmediately;

    public GroupDialogueMenu(
        BridgeClient? bridgeClient,
        StoryStateStore storyStateStore,
        GroupDialogueInvitationRecord invitation,
        IReadOnlyList<GroupDialogueParticipant> participants,
        Action? onClosed = null,
        IReadOnlyList<GroupDialogueHistoryEntry>? initialHistory = null,
        bool readOnly = false)
        : base(0, 0, 1, 1)
    {
        this.bridgeClient = bridgeClient;
        this.storyStateStore = storyStateStore ?? throw new ArgumentNullException(nameof(storyStateStore));
        this.participants = participants ?? throw new ArgumentNullException(nameof(participants));
        this.onClosed = onClosed;
        this.readOnly = readOnly;
        // 续读 / 回看（2026-09-21）：存档里那一场的发言序列由调用方从回看档案取出交进来，
        // 于是「关掉菜单再打开」接的是同一场，而不是一片空白。
        var restored = (initialHistory ?? Array.Empty<GroupDialogueHistoryEntry>())
            .Where(entry => entry is not null && !string.IsNullOrWhiteSpace(entry.Content))
            .ToArray();
        session = GroupDialogueSessionRules.Create(invitation, restored);
        visibleMessages.AddRange(restored);
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
        keyboardSubscriberLease = new KeyboardSubscriberLease<IKeyboardSubscriber>(
            () => Game1.keyboardDispatcher.Subscriber,
            subscriber => Game1.keyboardDispatcher.Subscriber = subscriber);
        if (readOnly)
        {
            // 只读回看：**不获取键盘租约、也不把输入框设成焦点**。输入框在这个模式下
            // 根本不画（那个位置画的是一句说明），若仍抢走键盘，玩家打出来的字会进到一个
            // 看不见的框里，看起来像界面卡住。发送与回车两条路径另由
            // <see cref="SendCurrentAsync"/> 的闸门挡住，这里只是第一道。
            //
            // 说明写在 scrollHint 而不是 hint：hint 是**诊断级**的（画出来时压过一切），
            // 而这句说明在玩家一滚动时就该让位给位置提示——那正是改前
            // hint = ScrollHint() 覆盖它的行为。
            scrollHint = GroupReadOnlyRules.ReadOnlyHintText(restored.Length);
        }
        else
        {
            inputBox.OnEnterPressed += OnInputEnterPressed;
            keyboardSubscriberLease.Acquire(inputBox);
            inputBox.SelectMe();
        }
    }

    public GroupDialogueSession Session => session;

    /// <summary>诊断用：最近一次群聊请求里，成功带上自己游戏状态的参与者数量。</summary>
    internal int LastRequestStateCount { get; private set; }

    /// <summary>
    /// 视觉测试/诊断用：面板上（也即这一场）真正显示的发言。它与存档里的场次记录同源
    /// （都由 <see cref="GroupSessionRules.AppendTurn"/> 产出），用来核对「画面 = 存档」。
    /// </summary>
    internal IReadOnlyList<GroupDialogueHistoryEntry> VisibleMessages => visibleMessages;

    /// <summary>诊断用：最近一次群聊请求的参与者名单。</summary>
    internal IReadOnlyList<string> LastRequestParticipantIds { get; private set; } =
        Array.Empty<string>();

    /// <summary>诊断用：最近一次群聊请求的参与者快照（含各自 gameState）。</summary>
    internal IReadOnlyList<GroupDialogueParticipant> LastRequestParticipants { get; private set; } =
        Array.Empty<GroupDialogueParticipant>();

    /// <summary>诊断用：最近一次群聊响应的完整 JSON（含 warnings / providerCalls / usage）。</summary>
    internal string? LastResponseJson { get; private set; }

    /// <summary>诊断用：当前是不是只读回看模式（视觉测试据此核对按钮与输入区）。</summary>
    internal bool IsReadOnly => readOnly;

    /// <summary>诊断用：只读回看时这一屏从第几条开始画（跟随最新时就是最后一屏的起点）。</summary>
    internal int VisualTestScrollStartIndex => followLatest
        ? GroupReadOnlyRules.MaxScrollStart(visibleMessages.Count, GroupDialogueLayoutRules.MaxVisibleMessages)
        : scrollStartIndex;

    /// <summary>
    /// 实际画出来的提示行：<c>hint</c>（错误诊断／只读常驻说明）优先，
    /// 它为空时才让位给滚动位置提示——两者都要用同一行，但诊断信息更重要。
    /// </summary>
    internal string DisplayHint => string.IsNullOrWhiteSpace(hint) ? scrollHint : hint;

    /// <summary>诊断用：还有几条 NPC 回复没播完（退出时必须清零）。</summary>
    internal int PendingRevealCount => revealQueue.PendingCount;

    /// <summary>诊断用：这一屏从第几条开始画（可发言与只读共用同一条取值）。</summary>
    internal int VisibleWindowStart => GroupReadOnlyRules.VisibleWindow(
        visibleMessages.Count,
        GroupDialogueLayoutRules.MaxVisibleMessages,
        GroupTranscriptRules.WindowStartIndex(followLatest, scrollStartIndex)).Start;

    /// <summary>诊断用：是不是还在跟随最新（翻到历史里之后为 false）。</summary>
    internal bool IsFollowingLatest => followLatest;

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

        if (revealQueue.HasPending && layout.MessageArea.Contains(x, y))
        {
            // 点一下正在播放的消息区 = 剩下的立刻全部显示。玩家不想等动画时
            // 不该被迫等完——他点这一下就是「我看完了，都放出来」。
            revealQueue.SkipAll();
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

        if (key == Keys.End)
        {
            JumpToLatest();
            return;
        }

        if (key == Keys.PageUp && ScrollBy(1))
        {
            return;
        }

        if (key == Keys.PageDown && ScrollBy(-1))
        {
            return;
        }

        base.receiveKeyPress(key);
    }

    /// <summary>
    /// 只读回看与正常对话**共用**的翻页入口：滚轮、PageUp/PageDown 都走这里，
    /// 于是「一屏画哪一段」的算术永远只有 <see cref="GroupReadOnlyRules.VisibleWindow"/> 一份。
    ///
    /// 2026-09-21：改前这里只在只读模式翻页（<c>if (!readOnly) return;</c>），
    /// 正常对话时一屏装不下就再也看不到前面的——用户口径「群聊没有翻页功能，这个得加」。
    /// </summary>
    /// <returns>这一次滚轮/按键是否真的移动了视口。</returns>
    private bool ScrollBy(int direction)
    {
        var maxStart = GroupReadOnlyRules.MaxScrollStart(
            visibleMessages.Count,
            GroupDialogueLayoutRules.MaxVisibleMessages);
        if (direction == 0 || maxStart <= 0)
        {
            // 装得下一屏：没有可翻的，保持跟随。
            return false;
        }

        // 与原版一致：direction > 0 是往上滚 = 看更早的发言。
        var (start, follow) = GroupTranscriptRules.Scroll(
            followLatest,
            scrollStartIndex,
            direction,
            visibleMessages.Count,
            GroupDialogueLayoutRules.MaxVisibleMessages);
        scrollStartIndex = start;
        followLatest = follow;
        if (followLatest)
        {
            unseenCount = 0;
        }

        scrollHint = ScrollHint();
        return true;
    }

    /// <summary>
    /// 回到底部：End 键，以及滚轮一直往下滚（<see cref="GroupTranscriptRules.Scroll"/>
    /// 滚到底时会自己把 <c>followLatest</c> 打开）。**不跳过播放**——玩家按 End 是想看
    /// 最新的，之后新出现的那几条照常按节奏来，那正是他想要的。
    /// </summary>
    private void JumpToLatest()
    {
        followLatest = true;
        unseenCount = 0;
        // 回到底部就不再需要位置提示；只读那边退回它的常驻说明
        // （否则按一下 End 会把「这一场已经结束」那句一起抹掉）。
        scrollHint = readOnly
            ? GroupReadOnlyRules.ReadOnlyHintText(visibleMessages.Count)
            : string.Empty;
    }

    public override void receiveScrollWheelAction(int direction)
    {
        if (closed)
        {
            return;
        }

        if (!ScrollBy(direction) && !readOnly)
        {
            // 没接管（一屏装得下、或方向为 0）：可发言时交回原版，只读时本来就无事可做。
            base.receiveScrollWheelAction(direction);
        }
    }

    public override void update(GameTime time)
    {
        if (closed)
        {
            return;
        }

        // 刚开一场群聊时由 NPC 先起头：玩家接受邀约后还没说话，
        // 若等玩家先开口，邀约就起不到引导作用（2026-09-20 用户反馈）。
        // 只读回看**不自动开场**：那一场已经结束，这里一句都不该发出去。
        if (!readOnly && GroupDialogueSessionRules.ShouldOpenWithNpc(session, openingRequested))
        {
            openingRequested = true;
            _ = SendCurrentAsync(opening: true);
        }

        RevealPendingTurns(time);
        PumpPendingRequest();
        base.update(time);
    }

    /// <summary>
    /// 把队列里「到点」的 NPC 回合交给面板。间隔是
    /// <see cref="GroupTranscriptRules.TurnRevealIntervalSeconds"/>；只读回看不播
    /// （那一场一次性铺满，见 <see cref="GroupTranscriptRules.ShouldRevealOneByOne"/>）。
    ///
    /// **加速**：按住 Shift 时用 <see cref="GroupTranscriptRules.FastForwardIntervalSeconds"/>，
    /// 几乎立刻放完。之所以不用空格做这件事——空格会产生文本，于是会**同时**
    /// 触发加速并往输入框里塞一个空格；Shift 不产生任何文本，没有这个问题。
    /// </summary>
    private void RevealPendingTurns(GameTime time)
    {
        if (readOnly || !revealQueue.HasPending)
        {
            return;
        }

        var interval = IsFastForwarding()
            ? GroupTranscriptRules.FastForwardIntervalSeconds
            : GroupTranscriptRules.TurnRevealIntervalSeconds;
        AppendRevealedTurns(revealQueue.Advance(
            time.ElapsedGameTime.TotalSeconds,
            interval));
    }

    private static bool IsFastForwarding()
    {
        var keyboard = Keyboard.GetState();
        return keyboard.IsKeyDown(Keys.LeftShift) || keyboard.IsKeyDown(Keys.RightShift);
    }

    /// <summary>
    /// 把一批 NPC 回合接到面板上。
    ///
    /// **仍然走 <see cref="GroupSessionRules.AppendTurn"/>**，不自己往列表里塞：
    /// 裁剪上限、丢空条目、addressedTo 归一化都在那里，绕开它「面板 == 存档」
    /// 这条贯穿全篇的不变式当场就破了。分批调用与一次性调用的最终结果是逐条相同的
    /// （<c>AppendTurn</c> 对每一步都重做同一套规则），因此逐条播放不会改变最终画面。
    /// </summary>
    private void AppendRevealedTurns(IReadOnlyList<BridgeGroupTurn> turns)
    {
        if (turns.Count == 0)
        {
            return;
        }

        var spoken = GroupSessionRules.AppendTurn(visibleMessages, playerMessage: null, turns);
        visibleMessages.Clear();
        visibleMessages.AddRange(spoken);
        if (!followLatest)
        {
            // 玩家正在看历史：**不把他拽回底部**——拽回去等于翻页白翻，
            // 那正是用户口径里点名的第三种情况。只把「下面又来了几条」记下来，
            // 交给提示行告诉他该不该翻回来。
            unseenCount += turns.Count;
            scrollHint = ScrollHint();
        }
    }

    /// <summary>
    /// 玩家自己那句**立刻上屏**（与 F8 私聊同一条体验）。
    ///
    /// 改前玩家的话和 NPC 回复在同一批里追加（<c>PumpPendingRequest</c> 里一次
    /// <c>AppendTurn(…, pendingPlayerMessage, response.Turns)</c>），于是自己刚发的那句
    /// 要等十几秒响应回来才出现，中间那段时间面板像没反应。
    ///
    /// 先记一份快照：这一轮若拿不到可用回复就撤回（见 <see cref="RollBackPlayerLine"/>）。
    /// </summary>
    private void RevealPlayerLine(string? message, bool opening)
    {
        if (opening || string.IsNullOrWhiteSpace(message))
        {
            // 开场那一轮玩家一句话都没说；重试那一轮的文字早就上过屏了。
            return;
        }

        preSendSnapshot ??= new List<GroupDialogueHistoryEntry>(visibleMessages);
        var spoken = GroupSessionRules.AppendTurn(visibleMessages, message, turns: null);
        visibleMessages.Clear();
        visibleMessages.AddRange(spoken);
        playerLineRevealed = true;
        // 自己说话 = 想看回复：视口自动回到底部（用户口径里的第三种情况）。
        followLatest = true;
        unseenCount = 0;
        scrollHint = string.Empty;
    }

    /// <summary>
    /// 把「立刻上屏」的那句自己撤回来。这一轮既然没有可用回复，场上就等于什么都没发生
    /// ——存档那条路（<see cref="GroupSessionRules.Append"/>）在这种轮次里一条都不写，
    /// 面板若留着那句，「画面 == 存档」立刻不成立。撤回之后那句话仍在
    /// <c>pendingPlayerMessage</c> 里，重试成功时会补上。
    /// </summary>
    private void RollBackPlayerLine()
    {
        if (playerLineRevealed && preSendSnapshot is not null)
        {
            visibleMessages.Clear();
            visibleMessages.AddRange(preSendSnapshot);
        }

        playerLineRevealed = false;
        preSendSnapshot = null;
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
        var displayHint = DisplayHint;
        var hintWidth = string.IsNullOrWhiteSpace(displayHint)
            ? 0f
            : Game1.smallFont.MeasureString(displayHint).X;
        var hintNeedsBottomRow = MenuSkinRules.HintNeedsBottomRow(
            !string.IsNullOrWhiteSpace(displayHint),
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
        // 这一屏画哪一段：可发言与只读**共用同一条算术**（GroupReadOnlyRules.VisibleWindow），
        // 区别只在喂给它的起点——跟随最新时取一个必然被夹到末尾的值，翻页时取滚动位置。
        // 可发言时的「不拽回」是这条算术的自然结果：消息变多只会让 maxStart 变大，
        // 起点不动，视口因此停在原处（见 AppendRevealedTurns）。
        var window = GroupReadOnlyRules.VisibleWindow(
            visibleMessages.Count,
            GroupDialogueLayoutRules.MaxVisibleMessages,
            GroupTranscriptRules.WindowStartIndex(followLatest, scrollStartIndex));
        // 按发言人计次：边框构图随 occurrence 在三套布局间轮换（与回放页一致）。
        // 此前一律传 0，于是同一角色多次发言的构图固定不变。
        var seenBySpeaker = new Dictionary<string, int>(System.StringComparer.OrdinalIgnoreCase);
        foreach (var message in visibleMessages.Skip(window.Start).Take(window.Count))
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
        if (readOnly)
        {
            // 只读回看的输入区：**不画输入框**，同一个矩形里换成一句说明。
            // 三个选择里取这一个的理由：
            // · 隐藏输入框（整条空掉）会让面板像缺了一块，玩家看不出这里本来是什么；
            // · 把输入框画成灰的，读起来像「暂时不能打字，等会儿就行」，而这一场是**永久**
            //   结束了，语义是错的；
            // · 换成一行说明则位置不变、布局零改动，一句话讲清「为什么不能说话」。
            // 发送/重试留在原位但置灰（不是凭空消失）：灰色表达「原本能做的事现在不能做」，
            // 位置与命中区一个都没动，点击由 SendCurrentAsync 的闸门挡住。
            var placeholderVisual = MenuSkinRules.InputBoxVisual(layout.InputBox);
            b.DrawString(
                Game1.smallFont,
                GroupReadOnlyRules.InputPlaceholderText(session.Invitation.ExpiresTotalDays),
                new Vector2(
                    placeholderVisual.X + 12,
                    placeholderVisual.Center.Y - (Game1.smallFont.LineSpacing / 2f)),
                MenuSkinRules.InkSoft);
            MenuButtonDrawing.DrawButton(b, layout.SendButton, "发送", false, MenuSkinRules.PrimaryButtonTint);
            MenuButtonDrawing.DrawButton(b, layout.RetryButton, "重试", false, MenuSkinRules.SecondaryButtonTint);
        }
        else
        {
            MenuButtonDrawing.DrawButton(b, layout.SendButton, "发送", !sending, MenuSkinRules.PrimaryButtonTint);
            MenuButtonDrawing.DrawButton(b, layout.RetryButton, "重试", !sending && session.CanRetry, MenuSkinRules.SecondaryButtonTint);
            inputBox.Draw(b, drawShadow: true);
        }

        MenuButtonDrawing.DrawButton(b, layout.CloseButton, "关闭", true, MenuSkinRules.SecondaryButtonTint);
        if (hintNeedsBottomRow)
        {
            b.DrawString(
                Game1.smallFont,
                displayHint,
                new Vector2(messageArea.X + 12, messageArea.Y + bubbleAreaHeight + 4),
                MenuSkinRules.InkSoft);
        }
        else if (!string.IsNullOrWhiteSpace(displayHint))
        {
            b.DrawString(
                Game1.smallFont,
                displayHint,
                new Vector2(layout.ParticipantStrip.Right - hintWidth, layout.ParticipantStrip.Y + 5),
                MenuSkinRules.InkSoft);
        }

        drawMouse(b);
    }

    protected override void cleanupBeforeExit()
    {
        // **离开这个菜单之前，把没播完的一次性补上——绝不能丢。**
        // 按 Esc、点关闭、切场景、退回标题、退出存档，全都汇到这里。
        // 存档那条路本来就与播放无关（BridgeClient 一次性写完整场），所以丢的只会是
        // 画面；但画面一少，「面板发言数 == 存档场次条数」这条不变式当场就不成立
        // （视觉测试的证据行正是拿这两个数比对的）。
        AppendRevealedTurns(revealQueue.Drain());
        keyboardSubscriberLease.Release();
        cancellationSource.Cancel();
        pendingRequest.Clear();
        cancellationSource.Dispose();
        base.cleanupBeforeExit();
    }

    private Task SendCurrentAsync(bool retry = false, bool opening = false)
    {
        // 只读回看的闸门：发送按钮、回车、重试三条路径最后都汇到这里，判据只有
        // GroupReadOnlyRules.CanSpeak 一处（分散写三遍必然漏掉一处，那「只读」就是空话）。
        if (!GroupReadOnlyRules.CanSpeak(readOnly))
        {
            hint = GroupReadOnlyRules.InputPlaceholderText(session.Invitation.ExpiresTotalDays);
            return Task.CompletedTask;
        }

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
            "auto",
            // 场次身份：BridgeClient 用它把这一轮发言并进「这一场」（见 GroupSessionContext）。
            // 邀约卡 id 从一开始就唯一标识一场，重开同一张卡就是接着写同一场。
            new GroupSessionContext(
                session.Invitation.InvitationId,
                session.Invitation.Title,
                session.Invitation.Topic,
                CurrentDateLabel(),
                CurrentTotalDays()));
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
            return Task.CompletedTask;
        }

        // 玩家那句**立刻上屏**（与 F8 私聊同一条体验）。这一步在请求发出去之后立刻做，
        // 不等响应——改前它和 NPC 回复挤在同一批追加里，自己刚发的话要等十几秒才出现。
        // 拿不到可用回复时由 PumpPendingRequest 撤回（见 RollBackPlayerLine）。
        RevealPlayerLine(message, opening);

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
            RollBackPlayerLine();
            revealImmediately = false;
            hint = "请求失败，邀约仍可重试。";
            return;
        }

        LastResponseJson = System.Text.Json.JsonSerializer.Serialize(response);
        var next = GroupDialogueSessionRules.ApplyResult(session, response.Turns, response.Fallback);
        if (response.Fallback || next.Invitation.Status != GroupInvitationStatus.Completed)
        {
            // 这一轮没有可用回复：场上等于什么都没发生，把先上屏的那句自己撤回，
            // 好让「面板 == 存档」继续成立（存档在这种轮次里一条都不写）。
            RollBackPlayerLine();
            revealImmediately = false;
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

        // 面板上这一场显示的发言与存档里的场次记录**同源**：都由 GroupSessionRules.AppendTurn
        // 产出。只是现在**分两步揭示**——
        //
        // 1. 玩家那句：已经在 SendCurrentAsync 里立刻上屏（重试与视觉测试这两条不经过
        //    那里的路径在这里补上），顺序仍是玩家在前；
        // 2. NPC 回合：进逐条揭示队列，由 update 按间隔一条条接上（回看不播、
        //    视觉测试一次放完，见 GroupTranscriptRules.ShouldRevealOneByOne 与 revealImmediately）。
        //
        // 最终画面与改前**逐条相同**：AppendTurn 每一步都重做同一套裁剪与归一化规则。
        if (!playerLineRevealed && !string.IsNullOrWhiteSpace(pendingPlayerMessage))
        {
            RevealPlayerLine(pendingPlayerMessage, opening: false);
        }

        var turns = response.Turns ?? Array.Empty<BridgeGroupTurn>();
        if (GroupTranscriptRules.ShouldRevealOneByOne(readOnly) && !revealImmediately)
        {
            revealQueue.Enqueue(turns);
        }
        else
        {
            AppendRevealedTurns(turns);
        }

        pendingPlayerMessage = null;
        playerLineRevealed = false;
        preSendSnapshot = null;
        revealImmediately = false;
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
        var gameDate = CurrentDateLabel();
        foreach (var write in GroupMemoryRules.Plan(
                     participants.Select(item => item.NpcId),
                     highlights))
        {
            storyStateStore.RecordMemoryHighlight(write.NpcId, write.Content, gameDate);
        }
    }

    /// <summary>
    /// 当前游戏日期的人类可读写法（<c>秋 12</c>），场次抬头与长期记忆用的是同一个口径。
    /// 取不到日期（还没进世界）时返回空串，不抛异常。
    /// </summary>
    private static string CurrentDateLabel()
    {
        try
        {
            return $"{Game1.currentSeason} {Game1.dayOfMonth}";
        }
        catch
        {
            return string.Empty;
        }
    }

    /// <summary>当前游戏内总天数（场次记录里用来排序与排障）；取不到时记 0（未知）。</summary>
    private static int CurrentTotalDays()
    {
        try
        {
            return Game1.Date.TotalDays;
        }
        catch
        {
            return 0;
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
        if (!GroupReadOnlyRules.CanSpeak(readOnly))
        {
            // 只读回看里不该有「刚刚那一轮的回复」被排进来：视觉测试若在只读菜单上排队，
            // 说明场景本身拼错了，直接不给进（而不是让屏幕上的记录被改写）。
            return;
        }

        pendingPlayerMessage = string.IsNullOrWhiteSpace(playerMessage)
            ? null
            : playerMessage.Trim();
        sending = true;
        // 视觉测试要的是**稳定可复现的终态**（证据行会比对「面板发言数 == 存档场次条数」），
        // 逐条动画是给人看的时序，所以这条路径一次放完。真实路径仍逐条走，
        // 播放节奏本身由 GroupTurnRevealQueue 的单测覆盖。
        revealImmediately = true;
        RevealPlayerLine(pendingPlayerMessage, opening: false);
        pendingRequest.Start(Task.FromResult(response));
    }

    /// <summary>
    /// 视觉测试专用入口：像玩家一样填好输入框并点击“发送”。
    /// 它走的是 receiveLeftClick 的发送按钮分支，因此与手动点击完全同一条代码路径
    /// （只读回看时会被同一个闸门挡住，不会真的发出去）。
    /// </summary>
    internal void PressSendForVisualTest(string message)
    {
        inputBox.Text = message ?? string.Empty;
        if (!readOnly)
        {
            inputBox.SelectMe();
        }

        layout = CalculateLayout();
        receiveLeftClick(layout.SendButton.Center.X, layout.SendButton.Center.Y);
    }

    /// <summary>
    /// 滚动位置提示。只读与可发言共用同一段算术（<see cref="GroupReadOnlyRules.VisibleWindow"/>），
    /// 只有文案分两档：回看写「回看中」，对话中写「第 a–b 条 / 共 n 条」，
    /// 并在玩家看历史时附上「下面还有几条新消息」。
    /// </summary>
    private string ScrollHint()
    {
        var window = GroupReadOnlyRules.VisibleWindow(
            visibleMessages.Count,
            GroupDialogueLayoutRules.MaxVisibleMessages,
            GroupTranscriptRules.WindowStartIndex(followLatest, scrollStartIndex));
        return readOnly
            ? GroupReadOnlyRules.ScrollHintText(
                window.Start,
                window.Count,
                visibleMessages.Count)
            : GroupTranscriptRules.ChatScrollHintText(
                window.Start,
                window.Count,
                visibleMessages.Count,
                unseenCount);
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
