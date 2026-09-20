using StardewAI.NPC;
using Microsoft.Xna.Framework;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 气泡底图描边归一：与网页侧变体逐值同源，以及「描边随 tint 与填充同比例」这个目的本身。
/// 背景见 <see cref="NpcBubblePanelRules"/> 的类注释。
/// </summary>
public sealed class NpcBubblePanelRulesTests
{
    [Fact]
    public void Source_rectangles_point_at_the_bubble_nine_slice()
    {
        // 游戏贴图里是 (0,256,60,60)；变体是独立一张 60×60，坐标从原点起。
        Assert.Equal(new Rectangle(0, 256, 60, 60), NpcBubblePanelRules.MenuSource);
        Assert.Equal(new Rectangle(0, 0, 60, 60), NpcBubblePanelRules.VariantSource);
        Assert.Equal(60, NpcBubblePanelRules.Size);
    }

    [Fact]
    public void Fill_base_matches_the_export_script_constant()
    {
        // 与 bridge 的 npc_bubble_tint.py::BUBBLE_TEX_BASE 同源，改一处必须同步另一处。
        Assert.Equal(new Color(253, 188, 110), NpcBubblePanelRules.FillBase);
    }

    [Theory]
    [InlineData(177, 78, 5)]    // 主描边
    [InlineData(133, 54, 5)]    // 最深一档
    [InlineData(250, 147, 5)]   // 最亮一档
    [InlineData(220, 123, 5)]   // 内档
    public void Edge_pixels_are_recognised_by_saturation(int r, int g, int b)
    {
        Assert.True(NpcBubblePanelRules.IsEdge(new Color(r, g, b)));
    }

    [Theory]
    [InlineData(253, 188, 110)]  // 填充主色
    [InlineData(255, 197, 118)]  // 填充近邻色
    [InlineData(245, 181, 111)]
    [InlineData(245, 181, 101)]
    public void Fill_pixels_are_not_edges(int r, int g, int b)
    {
        Assert.False(NpcBubblePanelRules.IsEdge(new Color(r, g, b)));
    }

    [Theory]
    [InlineData(133, 54, 5, 92, 68, 40)]
    [InlineData(177, 78, 5, 127, 94, 55)]
    [InlineData(250, 147, 5, 206, 153, 90)]
    [InlineData(220, 123, 5, 177, 131, 77)]
    public void Edge_pixels_map_to_the_same_values_as_the_web_side_variant(
        int r,
        int g,
        int b,
        int expectedR,
        int expectedG,
        int expectedB)
    {
        // 这四个映射是 bridge 侧 npc_bubble_texture.py 记录在案的产物值；
        // C# 侧对同一像素必须算出同一结果，否则两边皮肤会分叉。
        Assert.Equal(
            new Color(expectedR, expectedG, expectedB),
            NpcBubblePanelRules.NormalizeEdge(new Color(r, g, b)));
    }

    [Fact]
    public void Fill_and_transparent_pixels_are_returned_untouched()
    {
        var fill = new Color(255, 197, 118);
        var transparent = new Color(0, 0, 0, 0);

        Assert.Equal(fill, NpcBubblePanelRules.NormalizeEdge(fill));
        Assert.Equal(transparent, NpcBubblePanelRules.NormalizeEdge(transparent));
    }

    [Fact]
    public void Edge_alpha_is_preserved()
    {
        var translucentEdge = new Color(177, 78, 5, 128);

        Assert.Equal(128, NpcBubblePanelRules.NormalizeEdge(translucentEdge).A);
    }

    [Fact]
    public void Normalized_edges_keep_the_same_channel_ratio_to_the_fill()
    {
        // 这次改动的目的就是这一条：对任意 tint 都有
        // 「描边最终色 = 填充最终色 × 同一比例」，边框才是底色的暗版本而不是一圈橙红。
        // 比例只取决于纹理像素，与 tint 无关，所以直接比纹理值即可。
        var edges = new[]
        {
            new[] { 133, 54, 5 },
            new[] { 177, 78, 5 },
            new[] { 250, 147, 5 },
            new[] { 220, 123, 5 },
        };

        var worstBefore = 0f;
        var worstAfter = 0f;
        foreach (var edge in edges)
        {
            var color = new Color(edge[0], edge[1], edge[2]);
            worstBefore = Math.Max(worstBefore, Spread(color));
            worstAfter = Math.Max(worstAfter, Spread(NpcBubblePanelRules.NormalizeEdge(color)));
        }

        Assert.True(worstBefore > 0.6f, $"改前应当明显偏色，实测三通道比例极差 {worstBefore}");
        Assert.True(worstAfter <= 0.02f, $"归一后应当收敛到同比例，实测三通道比例极差 {worstAfter}");
    }

    [Fact]
    public void NormalizeEdges_returns_a_new_array_and_keeps_the_input_intact()
    {
        var pixels = new[]
        {
            new Color(177, 78, 5),
            new Color(253, 188, 110),
            new Color(0, 0, 0, 0),
        };

        var normalized = NpcBubblePanelRules.NormalizeEdges(pixels);

        Assert.Equal(pixels.Length, normalized.Length);
        Assert.Equal(new Color(127, 94, 55), normalized[0]);
        Assert.Equal(pixels[1], normalized[1]);
        Assert.Equal(pixels[2], normalized[2]);
        Assert.Equal(new Color(177, 78, 5), pixels[0]);
    }

    [Fact]
    public void NormalizeEdges_rejects_a_missing_array()
    {
        Assert.Throws<ArgumentNullException>(() => NpcBubblePanelRules.NormalizeEdges(null!));
    }

    [Fact]
    public void Saturation_and_luminance_follow_the_reference_formulas()
    {
        // 饱和度 (max−min)/max；(133,54,5) → 128/133。
        Assert.Equal(128f / 133f, NpcBubblePanelRules.Saturation(new Color(133, 54, 5)), 5);

        // Rec.601：0.299R + 0.587G + 0.114B。
        Assert.Equal(
            99.279f,
            NpcBubblePanelRules.Luminance(new Color(177, 78, 5)),
            3);
    }

    /// <summary>描边相对填充的三通道比例极差：0 = 三通道同比例（纯粹的明暗差）。</summary>
    private static float Spread(Color edge)
    {
        var fill = NpcBubblePanelRules.FillBase;
        var ratios = new[]
        {
            edge.R / (float)fill.R,
            edge.G / (float)fill.G,
            edge.B / (float)fill.B,
        };

        return ratios.Max() - ratios.Min();
    }
}
