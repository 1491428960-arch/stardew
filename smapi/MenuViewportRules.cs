using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

public static class MenuViewportRules
{
    public static Point PreferUiViewport(
        int viewportWidth,
        int viewportHeight,
        int uiViewportWidth,
        int uiViewportHeight)
    {
        if (uiViewportWidth > 0 && uiViewportHeight > 0)
        {
            return new Point(uiViewportWidth, uiViewportHeight);
        }

        if (viewportWidth > 0 && viewportHeight > 0)
        {
            return new Point(viewportWidth, viewportHeight);
        }

        throw new ArgumentOutOfRangeException(
            nameof(viewportWidth),
            "游戏视口和 UI 视口都必须提供正数尺寸。\n");
    }
}
