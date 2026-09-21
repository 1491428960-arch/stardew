using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;
using StardewValley.Menus;

namespace StardewAI.NPC;

/// <summary>
/// 聊天气泡的统一绘制：私聊（F8，<see cref="ChatInputMenu"/>）与
/// 群聊（F9，<see cref="GroupDialogueMenu"/>）共用这一份逻辑。
///
/// 2026-09-20：此前两处各画各的——F8 有气泡与角色配色，F9 只有一行
/// <c>"{发言人}：{内容}"</c> 的纯文本，长句既不换行也会溢出面板。
/// 抽到这里以后，气泡尺寸、换行宽度、角色配色、图标徽章、文字颜色
/// 都只有一处定义，两个界面不会再各自漂移。
/// </summary>
internal static class ChatBubbleDrawing
{
    /// <summary>气泡内边距。</summary>
    public const int Padding = 12;

    /// <summary>正文行间额外间距。</summary>
    public const int LineSpacing = 4;

    /// <summary>
    /// 相邻气泡之间的间距。要容得下装饰边框向外扩的 <see cref="NpcBubbleFrame.Pad"/>，
    /// 否则相邻气泡的藤蔓/物件会叠在一起。
    /// </summary>
    public const int Gap = NpcBubbleFrame.Pad + 6;

    /// <summary>换行时预留的安全边距。</summary>
    public const int SafetyMargin = 8;

    /// <summary>气泡最小宽度；内容再短也不会缩成一条。</summary>
    public const int MinWidth = 180;

    /// <summary>
    /// 未着色面板纹理（<c>Maps\MenuTilesUncolored</c>）里的九宫格源区。
    /// 它是 <c>Maps\MenuTiles</c> 的去色版：alpha 轮廓逐像素相同，
    /// 只是底板色区从 #fdbc6e 换成了近白，因此可以拿设计色反推后直接染色。
    /// </summary>
    private static readonly Rectangle PanelSource = new(0, 256, 60, 60);

    /// <summary>
    /// 未着色面板底板区的基准色（实测：九宫格拉伸区的主色，占四成面积）。
    /// 该区另有三个近邻色 255 / 240 / 239，用 248 反推时它们的偏差在 8 个色阶以内。
    /// </summary>
    private static readonly Color PanelBase = new(248, 248, 248);

    /// <summary>玩家气泡设计色：浅蓝。</summary>
    private static readonly Color PlayerBubbleDesign = new(226, 239, 246);

    /// <summary>NPC 兜底气泡设计色：浅紫（角色没有专属配色时）。</summary>
    private static readonly Color NpcFallbackBubbleDesign = new(239, 231, 244);

    /// <summary>玩家气泡实际交给绘制接口的 tint。</summary>
    private static readonly Color PlayerBubbleTint = ToPanelTint(PlayerBubbleDesign);

    /// <summary>NPC 兜底气泡实际交给绘制接口的 tint。</summary>
    private static readonly Color NpcFallbackBubbleTint = ToPanelTint(NpcFallbackBubbleDesign);

    /// <summary>深色角色气泡上的正文色；黑字在深底上不可读。</summary>
    private static readonly Color DarkBubbleText = new(243, 240, 252);

    /// <summary>由气泡可用宽度推出正文换行宽度。</summary>
    public static int ContentWidth(int availableWidth)
    {
        return Math.Max(80, availableWidth - (Padding * 2) - SafetyMargin);
    }

    /// <summary>气泡在给定行数下需要的高度。</summary>
    public static int MeasureHeight(int lineCount)
    {
        if (lineCount <= 0)
        {
            lineCount = 1;
        }

        return (Padding * 2)
            + Game1.smallFont.LineSpacing
            + LineSpacing
            + (lineCount * Game1.smallFont.LineSpacing)
            + ((lineCount - 1) * LineSpacing);
    }

    /// <summary>
    /// 分节线（群聊场次抬头）的上下留白。它没有气泡底板，只比一行字多一点呼吸空间。
    /// </summary>
    public const int DividerPadding = 8;

    /// <summary>分节线左右两条发丝线与居中文字之间留的空。</summary>
    public const int DividerLineGap = 10;

    /// <summary>
    /// 分节线占用的高度。**必须与实际绘制用同一个算式**：F8 的滚动窗口是按高度算出来的
    /// （<c>ChatInputMenu.DrawMessages</c> 的 <c>SelectLatestThatFit</c>），
    /// 两处不一致就会出现「算得下、画到一半被切断」。
    /// </summary>
    public static int MeasureDividerHeight(int lineCount)
    {
        return lineCount <= 0
            ? 0
            : (DividerPadding * 2) + (lineCount * Game1.smallFont.LineSpacing);
    }

    /// <summary>
    /// 画一条**分节线**：左右各一段发丝线、中间一行（或几行）说明文字。
    /// 用来在 F8 的时间线里标出「这里开始是一整场群聊」以及**当时都有谁在**
    /// （见 <see cref="GroupSessionRules"/>）——它不是谁说的话，所以不走气泡那套配色。
    /// 返回它占用的高度。
    /// </summary>
    public static int DrawDivider(
        SpriteBatch b,
        int left,
        int right,
        int y,
        IReadOnlyList<string> lines)
    {
        ArgumentNullException.ThrowIfNull(b);
        if (lines is null || lines.Count == 0)
        {
            return 0;
        }

        var lineSpacing = Game1.smallFont.LineSpacing;
        var height = MeasureDividerHeight(lines.Count);
        var available = Math.Max(1, right - left);
        var textTop = y + DividerPadding;
        var ruleY = textTop + (lineSpacing / 2);
        var textY = textTop;
        foreach (var line in lines)
        {
            var textWidth = (int)Math.Ceiling(Game1.smallFont.MeasureString(line).X);
            var textLeft = left + Math.Max(0, (available - textWidth) / 2);
            var ruleWidth = Math.Max(0, textLeft - DividerLineGap - left);
            if (ruleWidth > 0)
            {
                b.Draw(
                    Game1.fadeToBlackRect,
                    new Rectangle(left, ruleY, ruleWidth, 1),
                    MenuSkinRules.RuleColor);
                b.Draw(
                    Game1.fadeToBlackRect,
                    new Rectangle(right - ruleWidth, ruleY, ruleWidth, 1),
                    MenuSkinRules.RuleColor);
            }

            b.DrawString(
                Game1.smallFont,
                line,
                new Vector2(textLeft, textY),
                MenuSkinRules.InkSoft);
            textY += lineSpacing;
        }

        return height;
    }

    /// <summary>
    /// 一条**显示消息**在消息区里占的高度：普通消息按气泡算，分节线（
    /// <see cref="ChatHistoryRules.SessionRole"/>）按它自己的算式算。
    /// F8 的滚动窗口（哪些消息放得下）与实际绘制都走这一个函数，
    /// 免得两处各算一遍、出现「算得下但画到一半被切」。
    /// </summary>
    public static int MeasureMessage(string? role, IReadOnlyList<string> lines)
    {
        ArgumentNullException.ThrowIfNull(lines);
        return string.Equals(role, ChatHistoryRules.SessionRole, StringComparison.Ordinal)
            ? MeasureDividerHeight(lines.Count)
            : MeasureHeight(lines.Count);
    }

    /// <summary>
    /// 在 [<paramref name="left"/>, <paramref name="right"/>] 之间画一个气泡，返回它占用的高度。
    /// 玩家侧靠右对齐，NPC 侧靠左并使用角色专属底色与图标徽章。
    /// </summary>
    public static int Draw(
        SpriteBatch b,
        int left,
        int right,
        int y,
        string speaker,
        IReadOnlyList<string> lines,
        string? npcId,
        bool isPlayer,
        int occurrence = 0)
    {
        ArgumentNullException.ThrowIfNull(b);
        if (lines is null || lines.Count == 0)
        {
            return 0;
        }

        var availableWidth = Math.Max(MinWidth, right - left);
        var textWidth = 0f;
        foreach (var line in lines)
        {
            textWidth = Math.Max(textWidth, Game1.smallFont.MeasureString(line).X);
        }

        var width = Math.Clamp(
            (int)Math.Ceiling(textWidth + (Padding * 2)),
            Math.Min(MinWidth, availableWidth),
            availableWidth);
        var height = MeasureHeight(lines.Count);
        var bounds = new Rectangle(
            isPlayer ? right - width : left,
            y,
            width,
            height);

        // 角色视觉：NPC 侧使用角色专属底色 + 图标徽章 + 特征色。
        // 玩家侧与未知角色走未着色面板，底色回到设计色而不被木质纹理乘偏。
        var style = isPlayer ? null : NpcBubbleStyle.For(npcId);
        var showBadge = style is not null && NpcBubbleStyle.Sheet is not null;

        if (isPlayer)
        {
            DrawPanel(b, bounds, PlayerBubbleDesign, PlayerBubbleTint);
        }
        else if (style is not null)
        {
            DrawNpcPanel(b, bounds, style);
        }
        else
        {
            DrawPanel(b, bounds, NpcFallbackBubbleDesign, NpcFallbackBubbleTint);
        }

        // 装饰边框贴在气泡外侧一圈；画在底色之后、文字之前。
        if (style is not null)
        {
            NpcBubbleFrame.Draw(b, bounds, style, occurrence);
        }

        var textLeft = bounds.X + Padding;
        var speakerLeft = textLeft;
        if (showBadge)
        {
            b.Draw(
                NpcBubbleStyle.Sheet!,
                new Rectangle(textLeft, bounds.Y + Padding, NpcBubbleStyle.CellSize, NpcBubbleStyle.CellSize),
                style!.SheetSource,
                Color.White);
            speakerLeft = textLeft + NpcBubbleStyle.CellSize + 6;
        }

        b.DrawString(
            Game1.smallFont,
            speaker,
            new Vector2(speakerLeft, bounds.Y + Padding),
            isPlayer ? Color.DarkSlateBlue : style?.Accent ?? Color.DarkMagenta);

        var bodyColor = isPlayer || style is null ? Color.Black : DarkBubbleText;
        var lineY = bounds.Y + Padding + Game1.smallFont.LineSpacing + LineSpacing;
        foreach (var line in lines)
        {
            b.DrawString(Game1.smallFont, line, new Vector2(textLeft, lineY), bodyColor);
            lineY += Game1.smallFont.LineSpacing + LineSpacing;
        }

        return height;
    }

    /// <summary>
    /// 把设计色反推成面板 tint。面板最终色 = 纹理色 × tint ÷ 255（逐通道），
    /// 所以 tint = 设计色 × 255 ÷ <see cref="PanelBase"/>，回乘即还原设计色。
    ///
    /// 这一步非做不可：彩色 MenuTiles 的基色是 #fdbc6e，蓝紫通道只有 188 / 110，
    /// 而玩家气泡的浅蓝、兜底气泡的浅紫在 G / B 上都高于基色（最高要 570），
    /// 乘法最多只能到 1.0 倍，那些颜色根本乘不出来。换成近白的未着色面板后，
    /// 两个设计色的反推值分别为 (232,246,253) 与 (246,238,251)，全部落在界内。
    /// </summary>
    private static Color ToPanelTint(Color design)
    {
        return new Color(
            Math.Min(255, (int)Math.Round(design.R * 255.0 / PanelBase.R)),
            Math.Min(255, (int)Math.Round(design.G * 255.0 / PanelBase.G)),
            Math.Min(255, (int)Math.Round(design.B * 255.0 / PanelBase.B)));
    }

    /// <summary>
    /// 角色专属底色的气泡底。tint（<see cref="NpcBubbleStyle.Bubble"/>）仍按彩色 MenuTiles
    /// 的填充基色 <c>#fdbc6e</c> 反推过，所以纹理与 tint 依旧是配套的一对——
    /// 换的只是**纹理**：<see cref="NpcBubblePanelTexture"/> 那份变体把高饱和的红橙描边
    /// 归一成了填充基色的暗版本，于是描边随 tint 与填充同比例变暗，不再是紫红底旁边
    /// 那一圈突兀的橙红（详见 <see cref="NpcBubblePanelRules"/>）。
    /// 变体拿不到（图形设备或贴图未就绪）时退回原图，观感与改前完全一致。
    /// </summary>
    private static void DrawNpcPanel(SpriteBatch b, Rectangle bounds, NpcBubbleStyle style)
    {
        var variant = NpcBubblePanelTexture.Variant;
        if (variant is null)
        {
            IClickableMenu.drawTextureBox(
                b, bounds.X, bounds.Y, bounds.Width, bounds.Height, style.Bubble);
            return;
        }

        IClickableMenu.drawTextureBox(
            b,
            variant,
            NpcBubblePanelTexture.Source,
            bounds.X,
            bounds.Y,
            bounds.Width,
            bounds.Height,
            style.Bubble);
    }

    /// <summary>
    /// 用未着色面板画气泡底：保留九宫格木框纹理，同时让底色回到设计色。
    /// 极端情况下拿不到未着色面板时退回纯色底——颜色依旧准确，只是失去木框纹理。
    /// </summary>
    private static void DrawPanel(SpriteBatch b, Rectangle bounds, Color design, Color tint)
    {
        var panel = Game1.uncoloredMenuTexture;
        if (panel is null)
        {
            b.Draw(Game1.staminaRect, bounds, design);
            return;
        }

        IClickableMenu.drawTextureBox(
            b,
            panel,
            PanelSource,
            bounds.X,
            bounds.Y,
            bounds.Width,
            bounds.Height,
            tint);
    }
}
