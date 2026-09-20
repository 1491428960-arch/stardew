using Microsoft.Xna.Framework;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// F8 角色卡头像的取帧规则（<see cref="NpcPortraitRules"/>）。
///
/// 这些用例钉住的是**原版口径**：源矩形必须等于
/// <c>Game1.getSourceRectForStandardTileSheet(texture, $neutral, 64, 64)</c>，
/// 越界时必须回落到 <c>(0, 0, 64, 64)</c> —— 与
/// <c>DialogueBox.drawPortrait</c> 逐字一致。
/// 期望值全部手算自原版公式 <c>x = i*64 % W</c>、<c>y = i*64 / W * 64</c>。
/// </summary>
public sealed class NpcPortraitRulesTests
{
    [Fact]
    public void Frame_geometry_matches_the_vanilla_constants()
    {
        Assert.Equal(64, NpcPortraitRules.FrameSize);
        // Dialogue.getPortraitIndex(): $neutral -> 0。F8 没有 Dialogue，
        // 固定用这一帧，等于「实际对话」用普通语气说话时的那张。
        Assert.Equal(0, NpcPortraitRules.NeutralPortraitIndex);
    }

    /// <summary>
    /// 标准四帧贴图（384×64，原版 NPC 的常见布局）取 $neutral 帧 = 改前硬编码的同一块。
    /// 这条用例同时是「标准贴图上观感不变」的证据：改动只补上原版的越界判定与解析。
    /// </summary>
    [Fact]
    public void Standard_sheet_keeps_the_rect_that_was_previously_hardcoded()
    {
        var rect = NpcPortraitRules.ResolveSourceRect(384, 64);

        Assert.Equal(new Rectangle(0, 0, 64, 64), rect);
    }

    [Fact]
    public void Single_frame_sheet_keeps_the_whole_texture()
    {
        Assert.Equal(
            new Rectangle(0, 0, 64, 64),
            NpcPortraitRules.ResolveSourceRect(64, 64));
    }

    /// <summary>
    /// 多行贴图按原版公式换行：索引 5 落在第 3 行第 2 列 → (64,128)。
    /// 改前的硬编码矩形永远只会取左上角，取不到这一帧。
    /// </summary>
    [Fact]
    public void Frames_wrap_to_the_next_row_like_the_vanilla_helper()
    {
        Assert.Equal(
            new Rectangle(64, 128, 64, 64),
            NpcPortraitRules.ResolveSourceRect(128, 192, portraitIndex: 5));
    }

    /// <summary>
    /// 索引超出贴图高度时原版会回落到左上角那一帧；不能把贴图外的矩形交给 SpriteBatch。
    /// 手算：i=10、W=384 → x=640%384=256、y=640/384*64=64，底边 128 &gt; 64，越界。
    /// </summary>
    [Fact]
    public void Out_of_bounds_frame_falls_back_to_the_first_frame()
    {
        Assert.Equal(
            new Rectangle(0, 0, 64, 64),
            NpcPortraitRules.ResolveSourceRect(384, 64, portraitIndex: 10));
    }

    /// <summary>两行贴图上取到第二行同样越界（128×128 装不下 y=128 的第二行）。</summary>
    [Fact]
    public void Second_row_frame_on_a_too_short_sheet_falls_back()
    {
        Assert.Equal(
            new Rectangle(0, 0, 64, 64),
            NpcPortraitRules.ResolveSourceRect(128, 128, portraitIndex: 5));
    }

    /// <summary>
    /// 贴图比一帧还小时同样回落，且不能抛异常（原版公式里 texture.Width 是除数）。
    /// 手算：i=1、W=32 → x=64%32=0、y=64/32*64=128，底边 192 &gt; 32，越界。
    /// </summary>
    [Theory]
    [InlineData(32, 32, 1)]
    [InlineData(0, 0, 0)]
    [InlineData(-8, -8, 0)]
    public void Degenerate_texture_sizes_fall_back_instead_of_throwing(
        int textureWidth,
        int textureHeight,
        int portraitIndex)
    {
        Assert.Equal(
            new Rectangle(0, 0, 64, 64),
            NpcPortraitRules.ResolveSourceRect(textureWidth, textureHeight, portraitIndex));
    }

    [Theory]
    [InlineData(384, 0, 0, 0)]
    [InlineData(384, 1, 64, 0)]
    [InlineData(384, 5, 320, 0)]
    [InlineData(384, 6, 0, 64)]
    [InlineData(128, 5, 64, 128)]
    public void Tile_sheet_layout_matches_the_vanilla_formula(
        int textureWidth,
        int tilePosition,
        int expectedX,
        int expectedY)
    {
        Assert.Equal(
            new Rectangle(expectedX, expectedY, 64, 64),
            NpcPortraitRules.GetStandardTileSheetRect(textureWidth, tilePosition));
    }

    /// <summary>没有可聊对象时直接返回 null，不去碰 NPC.Portrait（避免触发内容加载）。</summary>
    [Fact]
    public void Missing_npc_yields_no_portrait_instead_of_throwing()
    {
        Assert.Null(NpcPortraitRules.TryResolvePortrait(null));
    }
}
