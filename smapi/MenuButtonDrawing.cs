using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;
using StardewValley.Menus;

namespace StardewAI.NPC;

/// <summary>
/// 菜单按钮的统一绘制。
///
/// 2026-09-20（系统性排查第 2 处）：这段绘制逻辑此前在四个菜单里各写了一份——
/// `GroupDialogueHubMenu`、`GroupDialogueMenu`、`InventoryItemPicker` 三份
/// **一字不差**，`ChatInputMenu` 多一个 `tint` 参数。改其中一处必然漏掉另外几处，
/// 于是抽到这里，四个菜单改为调用。
/// </summary>
internal static class MenuButtonDrawing
{
    /// <summary>默认底色为白（等价于此前的 Color.White 版本）。</summary>
    public static void DrawButton(SpriteBatch b, Rectangle bounds, string label, bool enabled) =>
        DrawButton(b, bounds, label, enabled, Color.White);

    public static void DrawButton(
        SpriteBatch b,
        Rectangle bounds,
        string label,
        bool enabled,
        Color tint)
    {
        IClickableMenu.drawTextureBox(b, bounds.X, bounds.Y, bounds.Width, bounds.Height, enabled ? tint : Color.Gray);
        var size = Game1.smallFont.MeasureString(label);
        b.DrawString(
            Game1.smallFont,
            label,
            new Vector2(bounds.Center.X - size.X / 2f, bounds.Center.Y - size.Y / 2f),
            enabled ? Color.Black : Color.DimGray);
    }
}
