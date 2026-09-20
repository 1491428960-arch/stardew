using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewModdingAPI;
using StardewValley;

namespace StardewAI.NPC;

/// <summary>
/// 角色气泡专用的面板纹理：<c>Maps\MenuTiles</c> 那块九宫格的**描边归一变体**，
/// 规则本身在 <see cref="NpcBubblePanelRules"/>（纯函数），这里只负责取像素、建纹理、持有它。
///
/// 为什么是**运行时生成**而不是打包一份素材：素材侧要多写一个 PNG、多一行
/// <c>EmbeddedResource</c>，还要跟网页侧那份产物保持同步；而这里只是把游戏自带的
/// 同一块贴图读出来跑一遍纯函数（零素材、零 csproj 改动），并且**自动跟随**
/// 内容包替换过的 <c>MenuTiles</c>。成本是一次 3600 像素的 <c>GetData</c>，只在启动时做一次。
///
/// ⚠ 创建时机：<c>Game1.graphics.GraphicsDevice</c> 在 <c>Entry()</c> 阶段常为 null，
/// 所以由 <c>ModEntry</c> 在 <c>GameLaunched</c> 里调用一次。拿不到就**回退到原图**
/// （观感与改前完全一致），只记一条警告，绝不抛异常打断绘制——
/// 取用处见 <see cref="ChatBubbleDrawing"/>。
/// </summary>
internal static class NpcBubblePanelTexture
{
    private static Texture2D? variant;
    private static bool creationAttempted;

    /// <summary>变体纹理；未创建或创建失败时为 null，调用方据此回退到原图。</summary>
    public static Texture2D? Variant => variant;

    /// <summary>变体纹理里的源矩形。</summary>
    public static Rectangle Source => NpcBubblePanelRules.VariantSource;

    /// <summary>
    /// 生成变体纹理。幂等：<c>GameLaunched</c> 只会调用一次，失败也不重试
    /// （重试只会在每帧的绘制路径上引入开销，而失败原因是启动期设备未就绪这类一次性情况）。
    /// </summary>
    public static void EnsureCreated(IMonitor monitor)
    {
        if (creationAttempted)
        {
            return;
        }

        creationAttempted = true;

        try
        {
            var device = Game1.graphics?.GraphicsDevice;
            var source = Game1.menuTexture;
            if (device is null || source is null)
            {
                monitor.Log(
                    "气泡面板纹理或图形设备尚未就绪，角色气泡退回原图绘制（边框保持改前观感）。",
                    LogLevel.Warn);
                return;
            }

            var pixels = new Color[NpcBubblePanelRules.Size * NpcBubblePanelRules.Size];
            source.GetData(0, NpcBubblePanelRules.MenuSource, pixels, 0, pixels.Length);

            var texture = new Texture2D(
                device,
                NpcBubblePanelRules.Size,
                NpcBubblePanelRules.Size);
            texture.SetData(NpcBubblePanelRules.NormalizeEdges(pixels));
            variant = texture;
        }
        catch (Exception exception)
        {
            monitor.Log(
                $"气泡面板纹理生成失败，角色气泡退回原图绘制：{exception.Message}",
                LogLevel.Warn);
        }
    }
}
