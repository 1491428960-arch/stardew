using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

/// <summary>
/// F8 角色卡头像的取图规则：与游戏**原版对话框**走同一条肖像路径，
/// 因此头像与「实际对话」看到的那张完全一致，并自动跟随
/// <c>Portraits/&lt;NPC&gt;</c> 一类美化包（Content Patcher 的替换结果就落在
/// <see cref="StardewNpc.Portrait"/> 这个贴图上，不需要我们自己拼图）。
///
/// 原版路径（Stardew Valley 1.6 反编译实证，
/// <c>StardewValley.Menus.DialogueBox::drawPortrait(SpriteBatch)</c>）：
/// <code>
/// Texture2D texture = this.characterDialogue.overridePortrait ?? speaker.Portrait;
/// Rectangle sourceRect = Game1.getSourceRectForStandardTileSheet(
///     texture, this.characterDialogue.getPortraitIndex(), 64, 64);
/// if (!texture.Bounds.Contains(sourceRect))
///     sourceRect = new Rectangle(0, 0, 64, 64);
/// b.Draw(texture, position, sourceRect, Color.White, 0f, Vector2.Zero, 4f, SpriteEffects.None, 0.88f);
/// </code>
/// 其中 <c>Dialogue.getPortraitIndex()</c> 把情绪串映射成帧序号
/// （<c>$neutral</c>→0、<c>$h</c>→1、<c>$s</c>→2、<c>$u</c>→3、<c>$l</c>→4、<c>$a</c>→5，
/// <c>$&lt;数字&gt;</c> 直接取该数字，其余回落 0）。
///
/// 本菜单没有 <c>Dialogue</c> 对象（消息来自 AI 而不是原版对白表），情绪无从谈起，
/// 所以固定取 <c>$neutral</c> 那一帧，即 <see cref="NeutralPortraitIndex"/>。
///
/// ⚠ 原版把 64×64 的源帧画进 **256×256** 的立绘位（<c>scale: 4f</c>）；
/// F8 的立绘位是 64×64（见 <c>ChatInputMenu.PortraitSize</c>），所以这里按 1:1 落图。
/// 两处的**取图来源与帧序号**一致，「显示多大」不同。
///
/// 本类只放**纯取帧几何 + 一次带护栏的贴图解析**（几何部分可单元测试），
/// 真正落到 <c>SpriteBatch</c> 的绘制仍在 <see cref="ChatInputMenu"/>。
/// </summary>
public static class NpcPortraitRules
{
    /// <summary>
    /// 原版肖像贴图的单帧边长。原版调用是
    /// <c>Game1.getSourceRectForStandardTileSheet(texture, index, 64, 64)</c>，
    /// 与 <c>ChatInputMenu.PortraitSize</c> 数值相同但含义不同：这里是**源帧**尺寸。
    /// </summary>
    public const int FrameSize = 64;

    /// <summary>原版 <c>$neutral</c> 情绪对应的帧序号（<c>Dialogue.getPortraitIndex()</c> 的返回值）。</summary>
    public const int NeutralPortraitIndex = 0;

    /// <summary>
    /// 取 NPC 的肖像贴图，并复刻原版对「越界帧」的兜底。
    /// 拿不到时返回 <c>null</c>（**不抛异常**），由调用方退回到不带头像的绘制。
    ///
    /// 三种拿不到的情况：
    /// <list type="number">
    /// <item>NPC 本身为空（调用方没有可聊对象）；</item>
    /// <item><c>Game1.graphics.GraphicsDevice</c> 未就绪 —— <c>NPC.Portrait</c> 是懒加载属性，
    /// 首次读取会走 <c>ChooseAppearance → content.Load&lt;Texture2D&gt;</c>，而建纹理必须有图形设备
    /// （本项目在 <c>Entry()</c> 阶段建纹理踩过这个坑，所以这里先挡一道）；</item>
    /// <item>贴图加载失败 —— 原版 <c>NPC.TryLoadPortraits</c> 内部会吞异常并把 <c>portrait</c>
    /// 留成 <c>null</c>，但内容包异常时仍可能把异常抛穿，这里一并兜住，保证菜单不崩。</item>
    /// </list>
    /// </summary>
    public static Texture2D? TryResolvePortrait(StardewNpc? npc)
    {
        if (npc is null)
        {
            return null;
        }

        if (Game1.graphics?.GraphicsDevice is null)
        {
            return null;
        }

        try
        {
            return npc.Portrait;
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// <summary>
    /// 复刻原版 <c>DialogueBox.drawPortrait</c> 的取帧：先按
    /// <c>Game1.getSourceRectForStandardTileSheet(texture, index, 64, 64)</c> 算源矩形，
    /// 再用 <c>texture.Bounds.Contains(sourceRect)</c> 判越界，越界就回落到 <c>(0, 0, 64, 64)</c>。
    ///
    /// 换成宽高入参是为了让这段判定可以脱离 <c>GraphicsDevice</c> 做单元测试；
    /// 判定结果与对真实 <c>Texture2D</c> 调用原版方法逐字等价。
    /// </summary>
    public static Rectangle ResolveSourceRect(
        int textureWidth,
        int textureHeight,
        int portraitIndex = NeutralPortraitIndex)
    {
        if (textureWidth <= 0 || textureHeight <= 0)
        {
            return FallbackSourceRect();
        }

        var frame = GetStandardTileSheetRect(textureWidth, portraitIndex);
        // 等价于 texture.Bounds.Contains(frame)：Bounds 是 (0, 0, Width, Height)。
        return textureWidth >= frame.Right && textureHeight >= frame.Bottom
            ? frame
            : FallbackSourceRect();
    }

    /// <summary>原版越界兜底用的源矩形。</summary>
    public static Rectangle FallbackSourceRect()
    {
        return new Rectangle(0, 0, FrameSize, FrameSize);
    }

    /// <summary>
    /// 逐字复刻 <c>Game1.getSourceRectForStandardTileSheet(Texture2D, int, int, int)</c> 的算法
    /// （反编译实证）：帧沿贴图横向排布，放不下就按贴图宽度换到下一行。
    /// </summary>
    public static Rectangle GetStandardTileSheetRect(int textureWidth, int tilePosition)
    {
        return new Rectangle(
            tilePosition * FrameSize % textureWidth,
            tilePosition * FrameSize / textureWidth * FrameSize,
            FrameSize,
            FrameSize);
    }
}
