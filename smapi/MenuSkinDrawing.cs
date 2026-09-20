using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;
using StardewValley.Menus;

namespace StardewAI.NPC;

/// <summary>
/// 三个聊天界面（F8 私聊、F9 群聊、群聊中心）共用的**外壳绘制**。
///
/// 与 <see cref="MenuSkinRules"/> 的分工：那边是数值与纯几何（可单元测试），
/// 这边是落到 <c>SpriteBatch</c> 的几步绘制。抽出来的理由和
/// <see cref="MenuButtonDrawing"/>／<see cref="ChatBubbleDrawing"/> 一样——
/// 「同一个东西在三个菜单里各画一份」正是三个界面逐渐长得不像的直接原因。
///
/// 视觉基准与常量来源见 <see cref="MenuSkinRules"/> 的类注释。
/// </summary>
internal static class MenuSkinDrawing
{
    /// <summary>角色查不到时用的强调色（设计稿里的系统默认紫）。</summary>
    private static readonly Color DefaultAccent = new(176, 146, 242);

    /// <summary>
    /// <c>Maps\MenuTiles</c> 里那块规整的九宫格素材：<c>(0,256,60,60)</c>，slice 20。
    ///
    /// 这也是 <c>IClickableMenu.drawTextureBox(b, x, y, w, h, color)</c> 内部用的源矩形
    /// （贴图就是 <c>Game1.menuTexture</c>）——三个界面的面板、凹槽、卡片、按钮全都走这一块，
    /// 只靠 tint 分档。注意 <c>(0,0,256,256)</c> 那块**不是**九宫格素材，
    /// 而是一整张画好的对话框图形，按 64px 切会整片错位（F8 改前走的
    /// <c>Game1.drawDialogueBox</c> 用的是 64px 那一套切法）。
    /// </summary>
    private static readonly Rectangle MenuTextureSource = new(0, 256, 60, 60);

    /// <summary>
    /// 面板：20px 九宫格（<c>Maps\MenuTiles (0,256,60,60)</c>）+ 白 tint + 投影。
    ///
    /// 改前 F8 走的是 <c>Game1.drawDialogueBox</c>——那是同一张贴图里**另一套切法**
    /// （64px 九宫格、中心块还另有 <c>(x+28, y+28)</c> 偏移）且不画投影；
    /// F9 与群聊中心走 <c>drawTextureBox</c>。两套九宫格的描边厚度与色阶不同，
    /// 这正是「F8 与 F9 看着不是一套」的直接来源。统一到这一条调用后与气泡、按钮同族。
    /// </summary>
    public static void DrawPanel(SpriteBatch b, Rectangle bounds) =>
        IClickableMenu.drawTextureBox(
            b,
            bounds.X,
            bounds.Y,
            bounds.Width,
            bounds.Height,
            MenuSkinRules.PanelTint);

    /// <summary>
    /// 内容区凹槽：同一个源矩形，只换 tint 并**关掉投影**。
    /// 凹陷的纸面不该有影子——只有浮起来的东西（面板、卡片、按钮）才投影，
    /// 这是层级读起来干净的关键。
    ///
    /// ⚠ 这里的游戏版本没有 <c>drawTextureBox(b, x, y, w, h, color, scale, drawShadow)</c>
    /// 这个重载，只有 6 参数版与带 <c>texture + sourceRect</c> 的 11 参数版，
    /// 所以要显式给出源矩形才能关掉投影。源矩形与 6 参数版内部用的**同一个**
    /// （见 <see cref="MenuTextureSource"/>）。
    /// </summary>
    public static void DrawInset(SpriteBatch b, Rectangle bounds) =>
        IClickableMenu.drawTextureBox(
            b,
            Game1.menuTexture,
            MenuTextureSource,
            bounds.X,
            bounds.Y,
            bounds.Width,
            bounds.Height,
            MenuSkinRules.InsetTint,
            1f,
            drawShadow: false);

    /// <summary>整屏遮罩。三个界面用同一句、同一个强度（写法与 F8 原有的 <c>DrawBackdrop</c> 相同）。</summary>
    public static void DrawScrim(SpriteBatch b)
    {
        var viewport = Game1.viewport;
        b.Draw(
            Game1.fadeToBlackRect,
            new Rectangle(0, 0, viewport.Width, viewport.Height),
            Color.Black * MenuSkinRules.ScrimAlpha);
    }

    /// <summary>
    /// 标题带：角色强调色竖条 + 标题 +（可选）右侧状态字 + 发丝分隔线。
    ///
    /// 改前 F8 的 header 算得出 92px 高却**什么都不画**（两个开关都是 false），
    /// 面板顶部留一条空白，是「看着脏」的主要来源；F9 与中心的标题则各画在
    /// 自己的位置上、彼此不成套。现在三处共用这一句。
    /// </summary>
    public static void DrawTitleBand(
        SpriteBatch b,
        Rectangle header,
        string title,
        string? status,
        Color accent)
    {
        b.Draw(Game1.fadeToBlackRect, MenuSkinRules.TitleBar(header), accent);
        var titlePosition = MenuSkinRules.TitleTextPosition(header);
        b.DrawString(Game1.smallFont, title, titlePosition, MenuSkinRules.Ink);
        if (!string.IsNullOrEmpty(status))
        {
            var titleWidth = Game1.smallFont.MeasureString(title).X;
            b.DrawString(
                Game1.smallFont,
                status,
                MenuSkinRules.StatusTextPosition(header, titleWidth),
                MenuSkinRules.InkSoft);
        }

        b.Draw(Game1.fadeToBlackRect, MenuSkinRules.TitleRule(header), MenuSkinRules.RuleColor);
    }

    /// <summary>角色强调色（气泡与徽章用的是同一份来源）；查不到角色时退回默认紫。</summary>
    public static Color AccentFor(string? npcId) =>
        NpcBubbleStyle.For(npcId)?.Accent ?? DefaultAccent;
}
