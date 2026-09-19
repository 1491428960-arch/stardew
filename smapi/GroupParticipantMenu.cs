using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;
using StardewValley.Menus;

namespace StardewAI.NPC;

public sealed class GroupParticipantMenu : IClickableMenu
{
    private readonly IReadOnlyList<GroupParticipantCandidate> candidates;
    private readonly BridgeClient? bridgeClient;
    private readonly StoryStateStore storyStateStore;
    private readonly Action? onClosed;
    private readonly Rectangle panel;
    private readonly Rectangle startButton;
    private readonly Rectangle closeButton;
    private readonly HashSet<string> selectedIds = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<Rectangle> candidateRows = new();
    private string hint = "请选择 2 到 3 名已经认识的 NPC；他们不需要在当前地图。";
    private bool closed;

    /// <summary>视觉测试/诊断用：候选行坐标（每帧 draw 时重建）。</summary>
    internal IReadOnlyList<Rectangle> VisualTestCandidateRows => candidateRows;

    /// <summary>视觉测试/诊断用：开始按钮与当前选中项。</summary>
    internal Rectangle VisualTestStartButton => startButton;

    internal IReadOnlyCollection<string> VisualTestSelectedIds => selectedIds;

    public GroupParticipantMenu(
        IReadOnlyList<GroupParticipantCandidate> candidates,
        BridgeClient? bridgeClient,
        StoryStateStore storyStateStore,
        Action? onClosed = null)
        : base(0, 0, 1, 1)
    {
        this.candidates = candidates
            .Where(candidate => candidate.HasFriendshipRecord &&
                                !string.IsNullOrWhiteSpace(candidate.NpcId) &&
                                !string.IsNullOrWhiteSpace(candidate.DisplayName))
            .GroupBy(candidate => candidate.NpcId.Trim(), StringComparer.OrdinalIgnoreCase)
            .Select(group => group.First())
            .OrderBy(candidate => candidate.NpcId, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        this.bridgeClient = bridgeClient;
        this.storyStateStore = storyStateStore ?? throw new ArgumentNullException(nameof(storyStateStore));
        this.onClosed = onClosed;

        var viewportSize = MenuViewportRules.PreferUiViewport(
            Game1.viewport.Width,
            Game1.viewport.Height,
            Game1.uiViewport.Width,
            Game1.uiViewport.Height);
        var panelWidth = Math.Min(900, Math.Max(620, viewportSize.X - 48));
        var panelHeight = Math.Min(640, Math.Max(420, viewportSize.Y - 48));
        panelWidth = Math.Min(panelWidth, Math.Max(1, viewportSize.X - 48));
        panelHeight = Math.Min(panelHeight, Math.Max(1, viewportSize.Y - 48));
        panel = new Rectangle(Math.Max(0, (viewportSize.X - panelWidth) / 2), Math.Max(0, (viewportSize.Y - panelHeight) / 2), panelWidth, panelHeight);
        xPositionOnScreen = panel.X;
        yPositionOnScreen = panel.Y;
        width = panel.Width;
        height = panel.Height;
        startButton = new Rectangle(panel.Center.X - 180, panel.Bottom - 78, 160, 56);
        closeButton = new Rectangle(panel.Center.X + 20, panel.Bottom - 78, 160, 56);
    }

    public override void receiveLeftClick(int x, int y, bool playSound = true)
    {
        if (closed)
        {
            return;
        }

        if (closeButton.Contains(x, y))
        {
            Close();
            return;
        }

        for (var index = 0; index < candidateRows.Count && index < candidates.Count; index++)
        {
            if (!candidateRows[index].Contains(x, y))
            {
                continue;
            }

            var candidate = candidates[index];
            if (!selectedIds.Add(candidate.NpcId))
            {
                selectedIds.Remove(candidate.NpcId);
            }
            hint = $"已选择 {selectedIds.Count} 人；选择 2 到 3 人后开始。";
            return;
        }

        if (startButton.Contains(x, y))
        {
            StartConversation();
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

        candidateRows.Clear();
        // 与线上多人对话中心一致：drawDialogueBox 会把自定义面板裁到原版
        // title-safe 区域，导致标题与候选行落到框外；这里改用九宫格纹理
        // 直接按 panel 矩形绘制，点击坐标不变。
        drawTextureBox(b, panel.X, panel.Y, panel.Width, panel.Height, Color.White);
        b.DrawString(Game1.smallFont, "选择群聊参与者", new Vector2(panel.X + 32, panel.Y + 24), Color.Black);
        var y = panel.Y + 96;
        foreach (var candidate in candidates.Take(8))
        {
            var row = new Rectangle(panel.X + 32, y, panel.Width - 64, 48);
            candidateRows.Add(row);
            var selected = selectedIds.Contains(candidate.NpcId);
            drawTextureBox(b, row.X, row.Y, row.Width, row.Height, selected ? new Color(224, 240, 228) : Color.White);
            // 中文字体的 Game1.smallFont 没有 ✓ / □ 字形（实测会渲染成 *），
            // 这里用 ASCII 方括号标记，保证任何语言下都能看清。
            b.DrawString(Game1.smallFont, selected ? "[x]" : "[ ]", new Vector2(row.X + 16, row.Y + 12), Color.Black);
            b.DrawString(Game1.smallFont, candidate.DisplayName, new Vector2(row.X + 52, row.Y + 12), Color.Black);
            y += 58;
        }

        if (candidates.Count == 0)
        {
            b.DrawString(Game1.smallFont, "没有可用的已认识 NPC。", new Vector2(panel.X + 40, y), Color.DarkSlateGray);
        }

        DrawButton(b, startButton, "开始群聊", selectedIds.Count is >= 2 and <= 3);
        DrawButton(b, closeButton, "返回", enabled: true);
        b.DrawString(Game1.smallFont, hint, new Vector2(panel.X + 32, panel.Bottom - 112), Color.Gray);
        drawMouse(b);
    }

    private void StartConversation()
    {
        if (selectedIds.Count is < 2 or > 3)
        {
            hint = "需要选择 2 到 3 名 NPC。";
            return;
        }

        var participants = candidates
            .Where(candidate => selectedIds.Contains(candidate.NpcId))
            .Select(candidate => new GroupDialogueParticipant(candidate.NpcId, candidate.DisplayName))
            .ToArray();
        var invitation = new GroupDialogueInvitationRecord
        {
            InvitationId = string.Empty,
            TemplateId = "neutral-public-topic",
            Participants = participants.Select(item => item.NpcId).ToArray(),
            ParticipantDisplayNames = participants.Select(item => item.DisplayName).ToArray(),
            Title = "自由群聊",
            Topic = string.Empty,
            Guidance = string.Empty,
            CreatedOn = string.Empty,
            ExpiresOn = string.Empty,
            CreatedTotalDays = 0,
            ExpiresTotalDays = 0,
            Source = "story",
            Status = GroupInvitationStatus.Accepted,
        };
        Game1.activeClickableMenu = new GroupDialogueMenu(
            bridgeClient,
            storyStateStore,
            invitation,
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

    private static void DrawButton(SpriteBatch b, Rectangle bounds, string label, bool enabled)
    {
        drawTextureBox(b, bounds.X, bounds.Y, bounds.Width, bounds.Height, enabled ? Color.White : Color.Gray);
        var size = Game1.smallFont.MeasureString(label);
        b.DrawString(Game1.smallFont, label, new Vector2(bounds.Center.X - size.X / 2f, bounds.Center.Y - size.Y / 2f), enabled ? Color.Black : Color.DimGray);
    }
}
