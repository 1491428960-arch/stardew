using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

/// <summary>
/// 菜单面板的**唯一**放置规则。
///
/// 2026-09-20（语义层审计 #38）：四个菜单（私聊、群聊、多人对话中心、物品选择器）
/// 此前各自写一份「按视口居中放面板」的算式，边距两处用常量、两处用字面量 48，
/// 面板尺寸的推导也各写一遍。这里先把**共用的两件事**收敛：
/// ① 安全边距 <see cref="SafeMargin"/>；② 面板居中的落点。
/// 各菜单自己的尺寸推导（比例式 vs 上限式）保持不变——那是各自的设计，不是重复判定。
/// </summary>
public static class MenuPanelRules
{
    /// <summary>面板与视口边缘之间的安全边距（左右/上下各一份）。</summary>
    public const int SafeMargin = 24;

    /// <summary>
    /// 面板按视口居中。
    ///
    /// <paramref name="floorOriginAtZero"/> 保留两处调用方的原有差异，逐字等价：
    /// 群聊与多人对话中心把面板原点下限夹到 0，私聊与物品选择器不夹
    /// （它们的面板宽度已被夹到 ≤ 视口宽度，实际不会出现负原点）。
    /// </summary>
    public static Rectangle CenteredInViewport(
        int viewportWidth,
        int viewportHeight,
        int panelWidth,
        int panelHeight,
        bool floorOriginAtZero)
    {
        if (viewportWidth <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(viewportWidth));
        }

        if (viewportHeight <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(viewportHeight));
        }

        var x = (viewportWidth - panelWidth) / 2;
        var y = (viewportHeight - panelHeight) / 2;
        if (floorOriginAtZero)
        {
            x = Math.Max(0, x);
            y = Math.Max(0, y);
        }

        return new Rectangle(x, y, panelWidth, panelHeight);
    }
}
