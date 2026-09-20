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

    /// <summary>相邻气泡之间的间距。</summary>
    public const int Gap = 8;

    /// <summary>换行时预留的安全边距。</summary>
    public const int SafetyMargin = 8;

    /// <summary>气泡最小宽度；内容再短也不会缩成一条。</summary>
    public const int MinWidth = 180;

    private static readonly Color PlayerBubble = new(226, 239, 246);
    private static readonly Color NpcFallbackBubble = new(239, 231, 244);

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
        bool isPlayer)
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
        // 玩家侧与未知角色沿用原本的浅色与黑字。
        var style = isPlayer ? null : NpcBubbleStyle.For(npcId);
        var showBadge = style is not null && NpcBubbleStyle.Sheet is not null;

        IClickableMenu.drawTextureBox(
            b,
            bounds.X,
            bounds.Y,
            bounds.Width,
            bounds.Height,
            isPlayer ? PlayerBubble : style?.Bubble ?? NpcFallbackBubble);

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
}
