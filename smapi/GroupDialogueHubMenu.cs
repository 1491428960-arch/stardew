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

    private const int ActionButtonWidth = 64;
    private const int ActionButtonGap = 6;

    /// <summary>
    /// 邀约卡上“接受”按钮的矩形。坐标定义与 <see cref="HandleInvitationClick"/>
    /// 共用同一组常量，避免视觉测试另算一份而漂移。
    /// </summary>
    internal static Rectangle VisualTestAcceptButton(Rectangle row)
    {
        var actionX = row.Right - (ActionButtonWidth * 3) - (ActionButtonGap * 2);
        return new Rectangle(actionX, row.Y, ActionButtonWidth, row.Height);
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
        visibleInvitations = storyStateStore.State.GroupDialogueInvitations
            .Where(invitation =>
                invitation.Status is not GroupInvitationStatus.Expired and
                    not GroupInvitationStatus.Dismissed and
                    not GroupInvitationStatus.Completed &&
                !GroupInvitationRules.IsExpired(
                    CurrentTotalDays(),
                    invitation.CreatedTotalDays,
                    invitation.ExpiresTotalDays))
            .OrderByDescending(invitation => invitation.CreatedTotalDays)
            .Take(GroupInvitationRules.MaxVisibleInvitations)
            .ToList();
    }

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
        drawTextureBox(
            b,
            panel.X,
            panel.Y,
            panel.Width,
            panel.Height,
            Color.White);
        b.DrawString(
            Game1.smallFont,
            "线上多人对话",
            new Vector2(panel.X + 32, panel.Y + 24),
            Color.Black);

        var y = panel.Y + 94;
        if (visibleInvitations.Count == 0)
        {
            b.DrawString(Game1.smallFont, "目前没有未处理的邀约卡。", new Vector2(panel.X + 40, y), Color.DarkSlateGray);
        }
        else
        {
            foreach (var invitation in visibleInvitations)
            {
                var row = new Rectangle(panel.X + 32, y, panel.Width - 64, 92);
                invitationRows.Add(row);
                drawTextureBox(
                    b,
                    row.X,
                    row.Y,
                    row.Width,
                    row.Height,
                    Color.White);
                var names = string.Join("、", invitation.ParticipantDisplayNames);
                b.DrawString(Game1.smallFont, $"{invitation.Title} · {names}", new Vector2(row.X + 18, row.Y + 14), Color.Black);
                b.DrawString(Game1.smallFont, $"主题：{invitation.Topic}", new Vector2(row.X + 18, row.Y + 42), Color.DarkSlateGray);
                b.DrawString(Game1.smallFont, $"状态：{FormatStatus(invitation.Status)} · 到期第 {invitation.ExpiresTotalDays} 天", new Vector2(row.X + 18, row.Y + 66), Color.DimGray);
                var actionWidth = 64;
                var actionGap = 6;
                var actionX = row.Right - (actionWidth * 3) - (actionGap * 2);
                MenuButtonDrawing.DrawButton(b, new Rectangle(actionX, row.Y + 18, actionWidth, 52), "接受", true);
                MenuButtonDrawing.DrawButton(b, new Rectangle(actionX + actionWidth + actionGap, row.Y + 18, actionWidth, 52), "稍后", true);
                MenuButtonDrawing.DrawButton(b, new Rectangle(actionX + ((actionWidth + actionGap) * 2), row.Y + 18, actionWidth, 52), "忽略", true);
                y += 104;
            }
        }

        MenuButtonDrawing.DrawButton(b, closeButton, "关闭", enabled: true);
        b.DrawString(Game1.smallFont, hint, new Vector2(panel.X + 32, panel.Bottom - 112), Color.Gray);
        drawMouse(b);
    }

    private void HandleInvitationClick(GroupDialogueInvitationRecord invitation, Rectangle row, int pointerX)
    {
        var actionWidth = ActionButtonWidth;
        var actionGap = ActionButtonGap;
        var actionX = row.Right - (actionWidth * 3) - (actionGap * 2);
        var status = pointerX switch
        {
            _ when pointerX >= actionX && pointerX < actionX + actionWidth => GroupInvitationStatus.Accepted,
            _ when pointerX >= actionX + actionWidth + actionGap && pointerX < actionX + ((actionWidth + actionGap) * 2) => GroupInvitationStatus.Deferred,
            _ when pointerX >= actionX + ((actionWidth + actionGap) * 2) => GroupInvitationStatus.Dismissed,
            _ => GroupInvitationStatus.Accepted,
        };
        if (pointerX < actionX)
        {
            status = GroupInvitationStatus.Accepted;
        }
        if (status is GroupInvitationStatus.Deferred or GroupInvitationStatus.Dismissed)
        {
            if (storyStateStore.TrySetGroupInvitationStatus(invitation.InvitationId, status))
            {
                visibleInvitations.Remove(invitation);
                hint = status == GroupInvitationStatus.Deferred ? "已暂缓这张邀约卡。" : "已忽略这张邀约卡。";
            }
            return;
        }

        if (!storyStateStore.TrySetGroupInvitationStatus(invitation.InvitationId, GroupInvitationStatus.Accepted))
        {
            hint = "这张邀约卡已经失效，请重新打开多人对话中心。";
            return;
        }

        var participants = invitation.Participants
            .Select((npcId, index) => new GroupDialogueParticipant(
                npcId,
                invitation.ParticipantDisplayNames.ElementAtOrDefault(index) ?? npcId))
            .ToArray();
        Game1.activeClickableMenu = new GroupDialogueMenu(
            bridgeClient,
            storyStateStore,
            invitation with { Status = GroupInvitationStatus.Accepted },
            participants,
            Close);
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
            _ => status.ToString(),
        };
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
