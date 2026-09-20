using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;

namespace StardewAI.NPC;

/// <summary>
/// 角色气泡的装饰边框：把 Bridge 回放页的 <c>characterFrameSvg</c> 复刻到游戏内。
///
/// 那份实现是**按气泡实际尺寸过程式生成**的（不是平铺图案）：细节元素摆在各边
/// 的比例位置上、自身尺寸固定，另有两个 32×32 大物件贴在边上，构图还随该角色
/// 的发言次序在三种布局间轮换。所以这里复刻算法，素材只提供「零件」
/// （assets/npc_bubble_frames.png：第 0 列细节造型，第 1/2 列大物件）。
///
/// 与源实现的唯一取舍：跳过 grapevine 在水平边上的额外卷须（影响极小，
/// 避免为一小段折线引入更多绘制分支）。
/// </summary>
internal static class NpcBubbleFrame
{
    /// <summary>边框相对气泡外扩的距离（源实现里的 pad）。</summary>
    public const int Pad = 14;

    private static readonly string[] OrganicKinds =
    {
        "vine", "grapevine", "laurel", "wheat", "crop", "leaf", "flower",
    };

    private static readonly string[] SwayingKinds = { "vine", "grapevine" };

    private static readonly Color OutlineColor = new(23, 31, 32);

    /// <summary>三种构图：每条边上细节元素的比例位置（照抄源实现的 layouts）。</summary>
    private static readonly float[][][] Layouts =
    {
        new[]
        {
            new[] { .08f, .14f, .23f, .72f },
            new[] { .34f, .42f, .83f, .91f },
            new[] { .68f },
            new[] { .22f, .31f },
        },
        new[]
        {
            new[] { .42f, .49f, .86f, .92f },
            new[] { .09f, .17f, .26f, .71f },
            new[] { .23f, .34f },
            new[] { .76f },
        },
        new[]
        {
            new[] { .09f, .18f, .78f, .86f, .92f },
            new[] { .24f, .32f, .59f },
            new[] { .72f, .81f },
            new[] { .29f },
        },
    };

    private static readonly float[] DetailScales = { 1f, .75f, 1.125f, .875f };

    /// <summary>
    /// 大物件的摆放（照抄源实现的 placements）：x 为小数时按气泡宽度换算，
    /// y 以气泡顶为基准、可为负（贴到上边缘之外）。
    /// </summary>
    private static (int Index, float X, float Y, float Size)[] PlacementsFor(
        int variant,
        int w,
        int h)
    {
        return variant switch
        {
            0 => new[] { (0, w - 35f, -2f, 40f), (1, 4f, h - 10f, 36f) },
            1 => new[]
            {
                (0, MathF.Round(w * .16f), 0f, 36f),
                (1, w - 34f, h - 12f, 40f),
            },
            _ => new[]
            {
                (1, MathF.Round(w * .56f), 0f, 36f),
                (0, MathF.Round(w * .12f), h - 12f, 40f),
            },
        };
    }

    /// <summary>边顺序与源实现一致：先画的在下层。</summary>
    private static readonly string[] Sides = { "top", "right", "bottom", "left" };

    /// <summary>
    /// 在气泡四周绘制装饰边框。<paramref name="occurrence"/> 是该角色本次会话里
    /// 第几次发言，用于在三种构图间轮换（与回放页语义一致）。
    /// </summary>
    public static void Draw(
        SpriteBatch b,
        Rectangle bubble,
        NpcBubbleStyle style,
        int occurrence)
    {
        ArgumentNullException.ThrowIfNull(b);
        ArgumentNullException.ThrowIfNull(style);

        var sheet = NpcBubbleStyle.FrameSheet;
        if (sheet is null || bubble.Width <= 0 || bubble.Height <= 0)
        {
            return;
        }

        var origin = new Vector2(bubble.X - Pad, bubble.Y - Pad);
        var w = bubble.Width;
        var h = bubble.Height;
        var kind = style.FrameKind;
        var organic = Array.IndexOf(OrganicKinds, kind) >= 0;
        var swaying = Array.IndexOf(SwayingKinds, kind) >= 0;
        var variant = VariantFor(kind, occurrence);
        var lineWidth = LineWidthFor(kind);
        var layout = Layouts[variant];

        for (var sideIndex = 0; sideIndex < Sides.Length; sideIndex++)
        {
            var side = Sides[sideIndex];
            var horizontal = side is "top" or "bottom";
            var length = horizontal ? w : h;

            // 1) 茎：沿边一条 2px 阶梯折线，先粗描边再画本体。
            var segments = BuildStem(side, w, h, organic, swaying, length);
            foreach (var segment in segments)
            {
                DrawSegment(b, origin, segment, lineWidth + 2f, OutlineColor);
            }

            foreach (var segment in segments)
            {
                DrawSegment(b, origin, segment, lineWidth, style.FrameLine);
            }

            if (organic || kind == "ribbon")
            {
                foreach (var segment in segments)
                {
                    DrawSegment(b, origin, segment, 1f, style.FrameHighlight);
                }
            }

            // 2) 细节零件：位置按比例、尺寸固定，organic 类带额外偏移与镜像。
            var positions = layout[sideIndex];
            for (var index = 0; index < positions.Length; index++)
            {
                var t = positions[index];
                var scale = DetailScales[(index + variant + (horizontal ? 0 : 1)) % 4];
                var point = EdgePoint(side, t, w, h, organic, swaying);
                var (dx, dy) = DetailOffset(kind, side, horizontal, index, organic);
                var size = (int)MathF.Round(NpcBubbleStyle.FrameCellSize * scale);
                var dest = new Rectangle(
                    (int)MathF.Round(origin.X + point.X + dx),
                    (int)MathF.Round(origin.Y + point.Y + dy),
                    size,
                    size);
                var flip = organic && (index + variant) % 2 == 1
                    ? SpriteEffects.FlipHorizontally
                    : SpriteEffects.None;
                b.Draw(sheet, dest, style.FrameSource(0), Color.White, 0f, Vector2.Zero, flip, 0f);
            }
        }

        // 3) 大物件：跨在边上，位置随 variant 变化。
        foreach (var (objectIndex, x, y, size) in PlacementsFor(variant, w, h))
        {
            var dest = new Rectangle(
                (int)MathF.Round(origin.X + x),
                (int)MathF.Round(origin.Y + y),
                (int)MathF.Round(size),
                (int)MathF.Round(size));
            b.Draw(sheet, dest, style.FrameSource(objectIndex + 1), Color.White);
        }
    }

    /// <summary>构造一条边的 2px 阶梯折线，交替水平/垂直走完整条边。</summary>
    private static List<(float X1, float Y1, float X2, float Y2)> BuildStem(
        string side,
        int w,
        int h,
        bool organic,
        bool swaying,
        int length)
    {
        var horizontal = side is "top" or "bottom";
        var count = Math.Max(2, (int)Math.Ceiling(length / 8f));
        var segments = new List<(float, float, float, float)>(count * 2);

        var previous = Pixel(EdgePoint(side, 0f, w, h, organic, swaying));
        for (var i = 1; i <= count; i++)
        {
            var next = Pixel(EdgePoint(side, i / (float)count, w, h, organic, swaying));
            if (horizontal)
            {
                segments.Add((previous.X, previous.Y, next.X, previous.Y));
                segments.Add((next.X, previous.Y, next.X, next.Y));
            }
            else
            {
                segments.Add((previous.X, previous.Y, previous.X, next.Y));
                segments.Add((previous.X, next.Y, next.X, next.Y));
            }

            previous = next;
        }

        return segments;
    }

    /// <summary>边上的参数点；organic 有弯曲，藤蔓类再叠一层摆动。</summary>
    private static Vector2 EdgePoint(
        string side,
        float t,
        int w,
        int h,
        bool organic,
        bool swaying)
    {
        var bend = organic ? MathF.Sin(MathF.PI * t) * 4f : 0f;
        var sway = swaying ? MathF.Sin(MathF.PI * t * 2f) * 2f : 0f;
        return side switch
        {
            "top" => new Vector2(Pad + (w * t), Pad - bend + sway),
            "bottom" => new Vector2(Pad + (w * t), Pad + h + bend + sway),
            "left" => new Vector2(Pad - bend, Pad + (h * t)),
            _ => new Vector2(Pad + w + bend, Pad + (h * t)),
        };
    }

    /// <summary>像素对齐：取整到偶数，保住源实现的 sprite 感阶梯。</summary>
    private static Vector2 Pixel(Vector2 point)
    {
        return new Vector2(
            MathF.Round(point.X / 2f) * 2f,
            MathF.Round(point.Y / 2f) * 2f);
    }

    /// <summary>细节零件相对边点的偏移（照抄源实现的分支）。</summary>
    private static (float X, float Y) DetailOffset(
        string kind,
        string side,
        bool horizontal,
        int index,
        bool organic)
    {
        if (organic)
        {
            var outward = index % 2 == 0 ? -1 : 1;
            var dx = horizontal ? -5f : side == "left" ? -10f : 0f;
            var dy = horizontal
                ? (side == "top" ? -8f : 0f) + (outward * 2f)
                : -5f;
            return (dx, dy);
        }

        return kind switch
        {
            "crystal" => (-4f, -6f),
            "arcane" => (-4f, -4f),
            "cable" => (-4f, -3f),
            "ribbon" => (-4f, -3f),
            "ore" => (-6f, -4f),
            "book" => (-5f, -5f),
            "wood" => (-3f, -6f),
            "wool" => (-6f, -4f),
            "fish" => (-5f, -5f),
            "slime" => (-5f, -3f),
            "stone" => (-5f, -5f),
            _ => (-4f, -3f),
        };
    }

    private static void DrawSegment(
        SpriteBatch b,
        Vector2 origin,
        (float X1, float Y1, float X2, float Y2) segment,
        float width,
        Color color)
    {
        var half = width / 2f;
        var x1 = origin.X + segment.X1;
        var y1 = origin.Y + segment.Y1;
        var x2 = origin.X + segment.X2;
        var y2 = origin.Y + segment.Y2;

        Rectangle dest;
        if (MathF.Abs(y1 - y2) < 0.01f)
        {
            dest = new Rectangle(
                (int)MathF.Round(MathF.Min(x1, x2) - half),
                (int)MathF.Round(y1 - half),
                (int)MathF.Round(MathF.Abs(x2 - x1) + width),
                (int)MathF.Round(width));
        }
        else
        {
            dest = new Rectangle(
                (int)MathF.Round(x1 - half),
                (int)MathF.Round(MathF.Min(y1, y2) - half),
                (int)MathF.Round(width),
                (int)MathF.Round(MathF.Abs(y2 - y1) + width));
        }

        b.Draw(Game1.staminaRect, dest, color);
    }

    /// <summary>与源实现一致：由 kind 的字符码之和与发言次序共同决定构图。</summary>
    private static int VariantFor(string kind, int occurrence)
    {
        var sum = 0;
        foreach (var ch in kind)
        {
            sum += ch;
        }

        return ((occurrence + sum) % 3 + 3) % 3;
    }

    private static float LineWidthFor(string kind)
    {
        return kind switch
        {
            "ribbon" or "wood" or "book" => 6f,
            "arcane" or "fish" => 2f,
            "slime" => 5f,
            _ => 3f,
        };
    }
}
