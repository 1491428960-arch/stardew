using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;
using StardewValley.Menus;

namespace StardewAI.NPC;

/// <summary>
/// 私聊名单（B26：F8 之后先选人，再决定当面聊还是线上聊）。
///
/// 名单只列**已经认识**的角色（口径见 <see cref="PrivateChatRosterRules"/>），
/// 因此会随着在小镇上遇到的村民越来越多而变长。
///
/// 外壳沿用 F8 聊天窗／F9 群聊中心同一套皮肤
/// （<see cref="MenuSkinRules"/> + <see cref="MenuSkinDrawing"/> + <see cref="MenuButtonDrawing"/>），
/// 面板几何也与群聊中心共用一份规则，三个界面看起来像一家人。
///
/// 操作：上下键／滚轮移动选中行（选中的那一行始终留在可视区内），回车进入私聊，
/// Esc 取消，鼠标直接点某一行则等同「选中并回车」。打开时预选哪一行由
/// <see cref="PrivateChatRosterRules.DefaultSelectedIndex"/> 给出——也就是 F8 改前
/// 那套自动选人规则，只是不再替玩家拍板。
/// </summary>
public sealed class PrivateChatRosterMenu : IClickableMenu
{
    private readonly IReadOnlyList<PrivateChatRosterEntry> entries;
    private readonly Func<PrivateChatRosterEntry, bool> onSelected;
    private readonly Action? onClosed;
    private readonly List<Rectangle> rowAreas = new();
    private readonly List<PrivateChatRosterEntry> visibleRows = new();
    private Rectangle panel;
    private Rectangle listArea;
    private Rectangle closeButton;
    private int startIndex;
    private int selectedIndex;
    private int visibleCapacity = 1;
    private string hint = string.Empty;
    private bool closed;

    /// <summary>视觉测试/诊断用：当前可见行的矩形（每次绘制时重建）。</summary>
    internal IReadOnlyList<Rectangle> VisualTestRowAreas => rowAreas;

    /// <summary>视觉测试/诊断用：当前可见的名单行。</summary>
    internal IReadOnlyList<PrivateChatRosterEntry> VisualTestVisibleRows => visibleRows;

    /// <summary>视觉测试/诊断用：底部提示（能区分「共 N 位」与翻页状态）。</summary>
    internal string VisualTestHint => hint;

    /// <summary>视觉测试/诊断用：当前列表起始行。</summary>
    internal int VisualTestStartIndex => startIndex;

    /// <summary>视觉测试/诊断用：当前选中的是名单里的第几行（绝对下标）。</summary>
    internal int VisualTestSelectedIndex => selectedIndex;

    public PrivateChatRosterMenu(
        IReadOnlyList<PrivateChatRosterEntry> entries,
        Func<PrivateChatRosterEntry, bool> onSelected,
        Action? onClosed = null)
        : base(0, 0, 1, 1)
    {
        this.entries = entries ?? throw new ArgumentNullException(nameof(entries));
        this.onSelected = onSelected ?? throw new ArgumentNullException(nameof(onSelected));
        this.onClosed = onClosed;
        RefreshLayout();
        // 预选行由老规则给出，且必须一开始就在可视区里（鼠标指向的人可能排在后面）。
        selectedIndex = PrivateChatRosterRules.DefaultSelectedIndex(entries);
        startIndex = PrivateChatRosterRules.ScrollTo(
            startIndex,
            selectedIndex,
            entries.Count,
            visibleCapacity);
        UpdateScrollHint();
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

        for (var index = 0; index < rowAreas.Count && index < visibleRows.Count; index++)
        {
            if (!rowAreas[index].Contains(x, y))
            {
                continue;
            }

            // 鼠标点某一行 = 选中它并直接进去：先点一次选中、再回车确认是多余的一步。
            selectedIndex = startIndex + index;
            Select(visibleRows[index]);
            return;
        }

        base.receiveLeftClick(x, y, playSound);
    }

    public override void receiveScrollWheelAction(int direction)
    {
        if (closed || direction == 0)
        {
            return;
        }

        // 与聊天窗同向：向上滚 = 往名单前面走。
        // 滚轮也移动选中行（而不是只滚动视口）：这个界面只有「当前选中谁」一个状态，
        // 让它滚出屏幕外，玩家就看不见回车会进谁。
        MoveSelection(direction > 0 ? -1 : 1);
    }

    public override void receiveKeyPress(Microsoft.Xna.Framework.Input.Keys key)
    {
        if (key == Microsoft.Xna.Framework.Input.Keys.Escape)
        {
            Close();
            return;
        }

        switch (key)
        {
            case Microsoft.Xna.Framework.Input.Keys.Up:
                MoveSelection(-1);
                return;
            case Microsoft.Xna.Framework.Input.Keys.Down:
                MoveSelection(1);
                return;
            case Microsoft.Xna.Framework.Input.Keys.PageUp:
                MoveSelection(-visibleCapacity);
                return;
            case Microsoft.Xna.Framework.Input.Keys.PageDown:
                MoveSelection(visibleCapacity);
                return;
            case Microsoft.Xna.Framework.Input.Keys.Enter:
                ConfirmSelection();
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
        rowAreas.Clear();
        visibleRows.Clear();
        var visible = PrivateChatRosterRules.VisibleEntries(entries, startIndex, visibleCapacity);
        visibleRows.AddRange(visible);

        MenuSkinDrawing.DrawScrim(b);
        MenuSkinDrawing.DrawPanel(b, panel);
        // 标题带的状态字给出名单规模，让玩家一眼知道「解锁了多少人」。
        MenuSkinDrawing.DrawTitleBand(
            b,
            new Rectangle(panel.X, panel.Y, panel.Width, MenuSkinRules.HubTitleBandHeight),
            "私聊 · 选择对话对象",
            $"已认识 {entries.Count} 位",
            MenuSkinDrawing.AccentFor(visibleRows.Count > 0 ? visibleRows[0].NpcId : null));

        // 列表区凹槽：行浮在它上面，靠底色分档（与群聊列表同一处几何）。
        MenuSkinDrawing.DrawInset(b, listArea);

        for (var index = 0; index < visibleRows.Count; index++)
        {
            var entry = visibleRows[index];
            var isSelected = startIndex + index == selectedIndex;
            var row = new Rectangle(
                listArea.X + 8,
                listArea.Y + PrivateChatRosterRules.ListPadding + (index * PrivateChatRosterRules.RowHeight),
                Math.Max(1, listArea.Width - 16),
                PrivateChatRosterRules.RowHeight - 6);
            rowAreas.Add(row);
            // 选中态沿用既有那套「三层底色」语言：凹槽暗一档、卡片回到最亮。
            // 未选中的行压到次按钮那一档退后，选中的行留在最亮的一档——
            // 几何一行都没动，只靠明度差把「回车会进谁」标出来，不引入新颜色令牌。
            drawTextureBox(
                b,
                row.X,
                row.Y,
                row.Width,
                row.Height,
                isSelected ? MenuSkinRules.CardTint : MenuSkinRules.SecondaryButtonTint);

            // 行首一条角色强调色：与标题带、气泡、徽章同一个颜色来源，
            // 让玩家扫一眼就能认出是谁（而不是只靠读名字）；选中时加宽一倍。
            var accent = MenuSkinDrawing.AccentFor(entry.NpcId);
            b.Draw(
                Game1.fadeToBlackRect,
                new Rectangle(row.X + 8, row.Y + 12, isSelected ? 8 : 4, Math.Max(1, row.Height - 24)),
                accent);
            if (isSelected)
            {
                DrawSelectionFrame(b, row, accent);
            }

            b.DrawString(
                Game1.smallFont,
                entry.DisplayName,
                new Vector2(row.X + 28, row.Y + 12),
                MenuSkinRules.Ink);

            var status = entry.StatusLabel;
            var statusWidth = Game1.smallFont.MeasureString(status).X;
            b.DrawString(
                Game1.smallFont,
                status,
                new Vector2(row.Right - 18 - statusWidth, row.Y + 12),
                MenuSkinRules.InkSoft);
        }

        MenuButtonDrawing.DrawButton(
            b,
            closeButton,
            "关闭",
            enabled: true,
            tint: MenuSkinRules.SecondaryButtonTint);
        b.DrawString(Game1.smallFont, hint, new Vector2(panel.X + 32, panel.Bottom - 112), MenuSkinRules.InkSoft);
        drawMouse(b);
    }

    /// <summary>回车：把当前选中行交出去。</summary>
    private void ConfirmSelection()
    {
        if (selectedIndex < 0 || selectedIndex >= entries.Count)
        {
            return;
        }

        Select(entries[selectedIndex]);
    }

    private void Select(PrivateChatRosterEntry entry)
    {
        if (closed)
        {
            return;
        }

        // 与群聊中心接受邀约同一条路线：先让回调换上聊天菜单，再标记自己关闭。
        // 这里**不能**调 exitThisMenuNoSound —— 它会把刚设好的新菜单清成 null。
        //
        // 回调返回 false = 私聊没能打开（对话功能刚被关掉，或正处在亲吻动画里）。
        // 这时**不能**标记关闭：菜单已经挂在 Game1.activeClickableMenu 上，而 closed
        // 会让 draw 直接 return，连 Esc 都被 receiveKeyPress 第一行挡掉——
        // 玩家会卡在一个看不见的菜单里，只能退游戏。保持可见让他改选一位或按 Esc。
        if (!onSelected(entry))
        {
            hint = "现在打不开私聊：对话功能可能已关闭。可以换一位，或按 Esc 退出。";
            return;
        }

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

    private void MoveSelection(int delta)
    {
        if (entries.Count == 0)
        {
            return;
        }

        selectedIndex = PrivateChatRosterRules.MoveSelection(selectedIndex, delta, entries.Count);
        // 选中行永远留在可视区里：视口跟着选中行走，而不是两边各滚各的。
        startIndex = PrivateChatRosterRules.ScrollTo(
            startIndex,
            selectedIndex,
            entries.Count,
            visibleCapacity);
        UpdateScrollHint();
    }

    private void UpdateScrollHint()
    {
        if (entries.Count == 0)
        {
            hint = "还没有可以私聊的角色。";
            return;
        }

        var pages = Math.Max(1, (int)Math.Ceiling(entries.Count / (double)visibleCapacity));
        var page = Math.Min(pages, (startIndex / visibleCapacity) + 1);
        var progress = pages <= 1 ? string.Empty : $" · 第 {page}/{pages} 页";
        hint = $"共 {entries.Count} 位 · 上下键选择，回车开始聊天{progress}";
    }

    /// <summary>
    /// 选中行的描边：四条 2px 的角色强调色边。只靠明度差在低分辨率下不够醒目，
    /// 而强调色本就是这个角色的识别色（与行首色条、标题带同源）。
    /// </summary>
    private static void DrawSelectionFrame(SpriteBatch b, Rectangle row, Color accent)
    {
        const int thickness = 2;
        b.Draw(Game1.fadeToBlackRect, new Rectangle(row.X, row.Y, row.Width, thickness), accent);
        b.Draw(
            Game1.fadeToBlackRect,
            new Rectangle(row.X, row.Bottom - thickness, row.Width, thickness),
            accent);
        b.Draw(Game1.fadeToBlackRect, new Rectangle(row.X, row.Y, thickness, row.Height), accent);
        b.Draw(
            Game1.fadeToBlackRect,
            new Rectangle(row.Right - thickness, row.Y, thickness, row.Height),
            accent);
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
        listArea = MenuSkinRules.HubListArea(panel, closeButton);
        visibleCapacity = PrivateChatRosterRules.VisibleCapacity(listArea.Height);
        // 视口尺寸变化后两处下标都要收口：选中行先夹进合法范围（空名单返回 0），
        // 起始行再夹一次、并**跟着选中行走**——窗口或 UI 缩放变小之后，原来那一屏
        // 可能已经装不下选中的那一行了。
        selectedIndex = PrivateChatRosterRules.MoveSelection(selectedIndex, 0, entries.Count);
        startIndex = PrivateChatRosterRules.ScrollTo(
            ChatScrollRules.ClampStartIndex(
                startIndex,
                PrivateChatRosterRules.MaxStartIndex(entries.Count, visibleCapacity)),
            selectedIndex,
            entries.Count,
            visibleCapacity);
        xPositionOnScreen = panel.X;
        yPositionOnScreen = panel.Y;
        width = panel.Width;
        height = panel.Height;
    }
}
