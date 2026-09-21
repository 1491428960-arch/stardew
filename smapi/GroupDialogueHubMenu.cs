using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;
using StardewValley.Menus;

namespace StardewAI.NPC;

public sealed class GroupDialogueHubMenu : IClickableMenu
{
    private readonly StoryStateStore storyStateStore;
    private readonly BridgeClient? bridgeClient;
    private readonly Func<IReadOnlyList<GroupParticipantCandidate>> participantProvider;
    private readonly Action? onClosed;
    private Rectangle panel;
    private readonly List<GroupDialogueInvitationRecord> visibleInvitations;
    private readonly List<Rectangle> invitationRows = new();
    private Rectangle closeButton;
    private string hint = "选择一张邀约卡参与群聊。";
    private bool closed;

    internal GroupDialogueHubLayout VisualTestLayout =>
        new(panel, closeButton);

    /// <summary>视觉测试/诊断用：邀约卡行坐标（每帧 draw 时重建）。</summary>
    internal IReadOnlyList<Rectangle> VisualTestInvitationRows => invitationRows;

    /// <summary>视觉测试/诊断用：当前列表首张邀约卡的 ID。</summary>
    internal string? VisualTestPendingInvitationId =>
        visibleInvitations.Count > 0 ? visibleInvitations[0].InvitationId : null;

    /// <summary>视觉测试/诊断用：当前提示文本（能区分“已暂缓/已忽略/已失效”）。</summary>
    internal string VisualTestHint => hint;

    /// <summary>
    /// 邀约卡上“接受”按钮的矩形。几何定义与 <see cref="HandleInvitationClick"/>、
    /// 绘制共用 <see cref="GroupInvitationActionLayoutRules"/>，不再各算一份。
    /// </summary>
    internal static Rectangle VisualTestAcceptButton(Rectangle row)
    {
        return GroupInvitationActionLayoutRules.AcceptHitArea(row);
    }

    public GroupDialogueHubMenu(
        StoryStateStore storyStateStore,
        BridgeClient? bridgeClient,
        Func<IReadOnlyList<GroupParticipantCandidate>> participantProvider,
        Action? onClosed = null)
        : base(0, 0, 1, 1)
    {
        this.storyStateStore = storyStateStore ?? throw new ArgumentNullException(nameof(storyStateStore));
        this.bridgeClient = bridgeClient;
        this.participantProvider = participantProvider ?? throw new ArgumentNullException(nameof(participantProvider));
        this.onClosed = onClosed;

        RefreshLayout();
        // 保留哪些卡、按什么顺序排，判据全在 GroupInvitationRules 里（纯函数，可单测）：
        // 已聊过（有存档场次）的卡一律留着 —— 到期之后它是只读回看的入口；
        // 没聊过的卡沿用旧规则，到期即消失。
        visibleInvitations = storyStateStore.State.GroupDialogueInvitations
            .Where(invitation => GroupInvitationRules.ShouldShowInHub(
                invitation,
                CurrentTotalDays(),
                HasArchivedSession(invitation)))
            // 先按「聊过 / 没聊过」分档，档内新的在前：这样已聊过的卡不会把新邀约挤出这一屏。
            .OrderBy(invitation => GroupInvitationRules.HubSortTier(HasArchivedSession(invitation)))
            .ThenByDescending(invitation => invitation.CreatedTotalDays)
            .Take(GroupInvitationRules.MaxVisibleInvitations)
            .ToList();
    }

    /// <summary>这一场在回看档案里有没有记录（决定它还能不能被打开、打开是续聊还是回看）。</summary>
    private bool HasArchivedSession(GroupDialogueInvitationRecord invitation)
    {
        return bridgeClient?.GroupSession(invitation.InvitationId) is not null;
    }

    /// <summary>这张卡点进去是只读回看还是能接着聊（到期日之后就不能再发言了）。</summary>
    private static bool IsReadOnly(GroupDialogueInvitationRecord invitation)
    {
        return GroupInvitationRules.IsReadOnly(CurrentTotalDays(), invitation);
    }

    /// <summary>视觉测试/诊断用：当前列表里每张卡的主按钮文案（「接受」「继续」「回看」）。</summary>
    internal IReadOnlyList<string> VisualTestPrimaryActionLabels =>
        visibleInvitations
            .Select(invitation => GroupInvitationRules.PrimaryActionLabel(
                HasArchivedSession(invitation),
                IsReadOnly(invitation)))
            .ToArray();

    public override void receiveLeftClick(int x, int y, bool playSound = true)
    {
        if (closed)
        {
            return;
        }

        RefreshLayout();
        if (closeButton.Contains(x, y))
        {
            Close();
            return;
        }

        for (var index = 0; index < invitationRows.Count && index < visibleInvitations.Count; index++)
        {
            if (!invitationRows[index].Contains(x, y))
            {
                continue;
            }

            HandleInvitationClick(visibleInvitations[index], invitationRows[index], x);
            return;
        }

        base.receiveLeftClick(x, y, playSound);
    }

    public override void receiveKeyPress(Microsoft.Xna.Framework.Input.Keys key)
    {
        if (key == Microsoft.Xna.Framework.Input.Keys.Escape)
        {
            Close();
            return;
        }

        base.receiveKeyPress(key);
    }

    public override void draw(SpriteBatch b)
    {
        if (closed)
        {
            return;
        }

        RefreshLayout();
        invitationRows.Clear();
        // 遮罩与 F8／F9 统一（改前这里没有遮罩）。
        MenuSkinDrawing.DrawScrim(b);
        MenuSkinDrawing.DrawPanel(b, panel);

        // 标题带：强调色取第一张邀约卡的第一位参与者，与卡片是同一套角色色。
        var accentSource = visibleInvitations.Count > 0
            ? visibleInvitations[0].Participants.FirstOrDefault()
            : null;
        MenuSkinDrawing.DrawTitleBand(
            b,
            new Rectangle(panel.X, panel.Y, panel.Width, MenuSkinRules.HubTitleBandHeight),
            "线上多人对话",
            null,
            MenuSkinDrawing.AccentFor(accentSource));

        // 列表区凹槽：卡片浮在它上面，靠底色分档分层（卡片自身的 tint 不动）。
        // 画在卡片之前。
        MenuSkinDrawing.DrawInset(b, MenuSkinRules.HubListArea(panel, closeButton));

        var y = panel.Y + 94;
        if (visibleInvitations.Count == 0)
        {
            b.DrawString(Game1.smallFont, "目前没有未处理的邀约卡。", new Vector2(panel.X + 40, y), MenuSkinRules.InkSoft);
        }
        else
        {
            foreach (var invitation in visibleInvitations)
            {
                var row = new Rectangle(panel.X + 32, y, panel.Width - 64, 92);
                invitationRows.Add(row);
                var hasSession = HasArchivedSession(invitation);
                var readOnly = IsReadOnly(invitation);
                drawTextureBox(
                    b,
                    row.X,
                    row.Y,
                    row.Width,
                    row.Height,
                    MenuSkinRules.CardTint);
                var names = string.Join("、", invitation.ParticipantDisplayNames);
                b.DrawString(Game1.smallFont, $"{invitation.Title} · {names}", new Vector2(row.X + 18, row.Y + 14), MenuSkinRules.Ink);
                // 三行并两行：原来第三行在 +66、文字底 +94，比卡片本身（92）还低 2px，
                // 直接被下边框切断（九宫格 slice 20 → 下内沿 = 92 − 20 = 72）。
                // 主题与状态并到 +44 后，文字底正好 +72，不出框，而卡片矩形与
                // 三个按钮的命中区一个都没动。
                b.DrawString(
                    Game1.smallFont,
                    $"主题：{invitation.Topic} · {FormatStatus(invitation.Status)} · {FormatDeadline(invitation, readOnly)}",
                    new Vector2(row.X + 18, row.Y + MenuSkinRules.HubCardSecondRowOffset),
                    MenuSkinRules.InkSoft);
                // 按钮矩形与点击判定同源：GroupInvitationActionLayoutRules。
                // 两档 tint：接受=主按钮，稍后/忽略=次按钮。
                // 文案三档（接受／继续／回看）由 GroupInvitationRules 给出：
                // 已聊过的那张卡接的是同一场（历史从存档回来）；到期之后同一张卡只能回看。
                MenuButtonDrawing.DrawButton(
                    b,
                    GroupInvitationActionLayoutRules.AcceptButton(row),
                    GroupInvitationRules.PrimaryActionLabel(hasSession, readOnly),
                    true,
                    MenuSkinRules.PrimaryButtonTint);
                MenuButtonDrawing.DrawButton(b, GroupInvitationActionLayoutRules.DeferButton(row), "稍后", true, MenuSkinRules.SecondaryButtonTint);
                MenuButtonDrawing.DrawButton(b, GroupInvitationActionLayoutRules.DismissButton(row), "忽略", true, MenuSkinRules.SecondaryButtonTint);
                y += 104;
            }
        }

        MenuButtonDrawing.DrawButton(b, closeButton, "关闭", enabled: true, tint: MenuSkinRules.SecondaryButtonTint);
        // 提示行文字色与 F9 群聊、F8 私聊同源：都用 MenuSkinRules.InkSoft。
        b.DrawString(Game1.smallFont, hint, new Vector2(panel.X + 32, panel.Bottom - 112), MenuSkinRules.InkSoft);
        drawMouse(b);
    }

    private void HandleInvitationClick(GroupDialogueInvitationRecord invitation, Rectangle row, int pointerX)
    {
        // 与绘制同一份几何：pointerX 落在哪个按钮上由规则类判定。
        var status = GroupInvitationActionLayoutRules.ResolvePointerAction(row, pointerX);
        if (status is GroupInvitationStatus.Deferred or GroupInvitationStatus.Dismissed)
        {
            if (storyStateStore.TrySetGroupInvitationStatus(invitation.InvitationId, status))
            {
                visibleInvitations.Remove(invitation);
                hint = status == GroupInvitationStatus.Deferred ? "已暂缓这张邀约卡。" : "已忽略这张邀约卡。";
            }
            return;
        }

        var readOnly = IsReadOnly(invitation);
        // 只读的卡**不改状态**：那一场已经结束，把 Completed 改回 Accepted 会让日切
        // 把它当成「进行中」并过期掉，玩家下次进来这个记录入口就没了
        // （GroupDialogueCoordinator.ExpireInvitations 会动 Accepted，不动 Completed）。
        if (!readOnly &&
            !storyStateStore.TrySetGroupInvitationStatus(invitation.InvitationId, GroupInvitationStatus.Accepted))
        {
            hint = "这张邀约卡已经失效，请重新打开多人对话中心。";
            return;
        }

        var participants = invitation.Participants
            .Select((npcId, index) => new GroupDialogueParticipant(
                npcId,
                invitation.ParticipantDisplayNames.ElementAtOrDefault(index) ?? npcId))
            .ToArray();
        // 续读 / 回看：这一场在回看档案里的发言序列交给菜单，于是重开同一张卡接的是同一场
        // （PublicHistory 与面板气泡都从这里回来），而不是一片空白。
        var restored = bridgeClient?.GroupSession(invitation.InvitationId)?.Lines;
        Game1.activeClickableMenu = new GroupDialogueMenu(
            bridgeClient,
            storyStateStore,
            readOnly ? invitation : invitation with { Status = GroupInvitationStatus.Accepted },
            participants,
            Close,
            restored,
            readOnly: readOnly);
        closed = true;
    }

    private void Close()
    {
        if (closed)
        {
            return;
        }

        closed = true;
        onClosed?.Invoke();
        exitThisMenuNoSound();
    }


    private void RefreshLayout()
    {
        var viewportSize = MenuViewportRules.PreferUiViewport(
            Game1.viewport.Width,
            Game1.viewport.Height,
            Game1.uiViewport.Width,
            Game1.uiViewport.Height);
        var layout = GroupDialogueHubLayoutRules.Calculate(viewportSize.X, viewportSize.Y);
        panel = layout.Panel;
        closeButton = layout.CloseButton;
        xPositionOnScreen = panel.X;
        yPositionOnScreen = panel.Y;
        width = panel.Width;
        height = panel.Height;
    }

    private static string FormatStatus(GroupInvitationStatus status)
    {
        return status switch
        {
            GroupInvitationStatus.Unread => "未读",
            GroupInvitationStatus.Deferred => "稍后处理",
            GroupInvitationStatus.Accepted => "进行中",
            // 已聊过的卡会留在列表里（有场次记录时），文案要跟着有——否则会露出英文枚举名。
            GroupInvitationStatus.Completed => "已聊过",
            _ => status.ToString(),
        };
    }

    /// <summary>
    /// 状态行里那截日期。到期之后写「已到期，只能回看」而不是一个日子：
    /// 玩家看到的应该是**为什么按钮变成「回看」**，而不是自己去做减法。
    /// </summary>
    private static string FormatDeadline(GroupDialogueInvitationRecord invitation, bool readOnly)
    {
        return readOnly ? "已到期，只能回看" : $"到期第 {invitation.ExpiresTotalDays} 天";
    }

    private static int CurrentTotalDays()
    {
        try
        {
            return Game1.Date.TotalDays;
        }
        catch
        {
            return int.MaxValue;
        }
    }
}
