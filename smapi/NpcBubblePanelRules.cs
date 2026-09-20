using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

/// <summary>
/// 角色气泡底图的**描边色相归一**规则（纯函数，无游戏依赖，可单元测试）。
///
/// 背景（2026-09-21 用户反馈「气泡边上围一圈红色的边太奇怪了」）：
/// 气泡底走 <c>IClickableMenu.drawTextureBox</c> 的**乘法着色**
/// （<c>最终色 = 纹理色 × tint ÷ 255</c>），而 <c>Maps\MenuTiles (0,256,60,60)</c>
/// 这块九宫格**自带的描边是红橙色** <c>(177,78,5)</c>——饱和度 0.97、B 通道只有 5。
/// 白 tint 下面板与按钮看着是木框本色，没问题；可角色气泡的 tint 是紫红／靛蓝这类深色，
/// 描边乘完 B 通道仍是 <c>5 × t ÷ 255 ≈ 2</c>，「紫红底色」旁边就围了一圈**橙红**的边。
///
/// 修法：只把**高饱和的描边像素**换成「填充基准色的暗版本」，逐像素保留相对亮度——
///
///     新描边 = 填充基准色 × (亮度(p) ÷ 亮度(填充基准色))
///
/// 于是对**任意** tint 都有「描边最终色 = 填充最终色 × 同一比例」，边框成为底色的暗版本；
/// 四档明暗、圆角形状、木框质感一个像素不动。填充像素（饱和度 ≈0.55，与描边的 0.97
/// 两档分明）**逐像素原样保留**，所以 <see cref="NpcBubbleStyle.Bubble"/> 那套按填充基色
/// 反推出来的 tint 依旧成立，46 个角色的配色一处都不用改。
///
/// ⚠ 本规则与 <c>scripts/build_bubble_texture.py</c>／bridge 侧
/// <c>npc_bubble_texture.py</c> **同源同公式**：那边把结果生成成网页预览用的 PNG 变体，
/// 这边在运行时对游戏自带的同一块贴图做同一件事（零素材，见
/// <see cref="NpcBubblePanelTexture"/>）。改一处必须同步另一处——四个代表映射
/// <c>(133,54,5)→(92,68,40)</c>、<c>(177,78,5)→(127,94,55)</c>、
/// <c>(250,147,5)→(206,153,90)</c>、<c>(220,123,5)→(177,131,77)</c> 由测试钉住。
/// </summary>
public static class NpcBubblePanelRules
{
    /// <summary>气泡九宫格的边长（源裁剪就是 60×60，slice 20）。</summary>
    public const int Size = 60;

    /// <summary>
    /// 气泡九宫格在 <c>Game1.menuTexture</c> 里的源矩形：与
    /// <c>IClickableMenu.drawTextureBox(b, x, y, w, h, color)</c> 内部用的那块完全一致。
    /// </summary>
    public static readonly Rectangle MenuSource = new(0, 256, Size, Size);

    /// <summary>
    /// 归一变体纹理**自身**的源矩形。变体是独立的一张 60×60，坐标从 <c>(0,0)</c> 起算，
    /// 不能直接复用 <see cref="MenuSource"/>。
    /// </summary>
    public static readonly Rectangle VariantSource = new(0, 0, Size, Size);

    /// <summary>
    /// 填充基准色 <c>#fdbc6e</c>：九宫格中心块（被拉伸的那块）的主色，
    /// 与 <c>stardew_ai_bridge.npc_bubble_tint::BUBBLE_TEX_BASE</c> 同源（Python 侧的唯一定义处；
    /// C# 不能 import Python，此处是跨语言复刻，改一处必须同步另一处）。
    /// </summary>
    public static readonly Color FillBase = new(253, 188, 110);

    /// <summary>描边判定阈值：描边实测饱和度 ≈0.97、填充 ≈0.55，取两档中间。</summary>
    public const float EdgeSaturation = 0.75f;

    /// <summary>饱和度 <c>(max−min)/max</c>；纯黑（max=0）视为 0。</summary>
    public static float Saturation(Color color)
    {
        var max = Math.Max(color.R, Math.Max(color.G, color.B));
        if (max == 0)
        {
            return 0f;
        }

        var min = Math.Min(color.R, Math.Min(color.G, color.B));
        return (max - min) / (float)max;
    }

    /// <summary>
    /// Rec.601 亮度。游戏与浏览器都在 sRGB 直通道上做乘法，
    /// 所以这里只取比值、不做伽马校正——那正是「乘完仍然同比例」成立的原因。
    /// </summary>
    public static float Luminance(Color color) =>
        (0.299f * color.R) + (0.587f * color.G) + (0.114f * color.B);

    /// <summary>这个像素是不是贴图自带的红橙描边（高饱和）；透明像素不算。</summary>
    public static bool IsEdge(Color color) =>
        color.A != 0 && Saturation(color) >= EdgeSaturation;

    /// <summary>
    /// 把描边像素换成「<see cref="FillBase"/> 的暗版本」，其余像素原样返回。
    /// 亮度比例照抄，所以新旧描边在任意 tint 下都与填充保持同一个比例。
    /// </summary>
    public static Color NormalizeEdge(Color color)
    {
        if (!IsEdge(color))
        {
            return color;
        }

        var scale = Luminance(color) / Luminance(FillBase);
        return new Color(
            ScaleChannel(FillBase.R, scale),
            ScaleChannel(FillBase.G, scale),
            ScaleChannel(FillBase.B, scale),
            color.A);
    }

    /// <summary>批量版本（整块贴图逐像素）。返回新数组，不改动入参。</summary>
    public static Color[] NormalizeEdges(Color[] pixels)
    {
        ArgumentNullException.ThrowIfNull(pixels);
        var normalized = new Color[pixels.Length];
        for (var index = 0; index < pixels.Length; index++)
        {
            normalized[index] = NormalizeEdge(pixels[index]);
        }

        return normalized;
    }

    /// <summary>
    /// 单通道取值：<c>round(基准通道 × 比例)</c>、夹到 0~255。
    /// 用 <see cref="Math.Round(double)"/> 的默认口径（四舍六入五成双），与 Python 侧的
    /// <c>round()</c> 一致，四个代表映射才能逐值对上。
    /// </summary>
    private static int ScaleChannel(byte channel, float scale) =>
        Math.Clamp((int)Math.Round(channel * (double)scale), 0, 255);
}
