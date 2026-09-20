using Microsoft.Xna.Framework;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 2026-09-20 外壳重构：三个聊天界面共用的设计令牌与纯几何。
///
/// 契约的权威来源是浏览器侧定稿的设计稿
/// <c>bridge/src/stardew_ai_bridge/ui_preview_redesign_page.py</c>——断言里逐个写明了
/// 它对应的页面常量，改数值时应当先改设计稿。
/// </summary>
public sealed class MenuSkinRulesTests
{
    // ── 设计令牌：三层底色与两档按钮 tint ──────────────────────────────────

    [Fact]
    public void Panel_and_card_are_the_brightest_tint()
    {
        // 页面：SKIN.panel / SKIN.card = [255,255,255]
        Assert.Equal(new Color(255, 255, 255), MenuSkinRules.PanelTint);
        Assert.Equal(new Color(255, 255, 255), MenuSkinRules.CardTint);
    }

    [Fact]
    public void Inset_is_one_step_darker_than_the_panel()
    {
        // 页面：SKIN.inset = [232,228,224]；tint 是乘法，所以凹槽只能比面板暗。
        Assert.Equal(new Color(232, 228, 224), MenuSkinRules.InsetTint);
        Assert.True(MenuSkinRules.InsetTint.R < MenuSkinRules.PanelTint.R);
        Assert.True(MenuSkinRules.InsetTint.G < MenuSkinRules.PanelTint.G);
        Assert.True(MenuSkinRules.InsetTint.B < MenuSkinRules.PanelTint.B);
    }

    [Fact]
    public void Buttons_collapse_to_two_tints_primary_brightest()
    {
        // 页面：SKIN.btnPrimary = 白、SKIN.btnSecondary = [238,226,208]；
        // 禁用档沿用 MenuButtonDrawing 里的 Color.Gray。
        Assert.Equal(new Color(255, 255, 255), MenuSkinRules.PrimaryButtonTint);
        Assert.Equal(new Color(238, 226, 208), MenuSkinRules.SecondaryButtonTint);
        Assert.True(MenuSkinRules.SecondaryButtonTint.R <= MenuSkinRules.PrimaryButtonTint.R);
        Assert.True(MenuSkinRules.SecondaryButtonTint.G <= MenuSkinRules.PrimaryButtonTint.G);
        Assert.True(MenuSkinRules.SecondaryButtonTint.B <= MenuSkinRules.PrimaryButtonTint.B);
    }

    [Fact]
    public void Text_collapses_to_black_and_dimgray()
    {
        // 页面：SKIN.ink = GAME_BLACK、SKIN.inkSoft = DIM_GRAY(105,105,105)。
        // DarkSlateGray(47,79,79) 偏青，压在暖橙面板上发灰发脏，不再使用。
        Assert.Equal(Color.Black, MenuSkinRules.Ink);
        Assert.Equal(Color.DimGray, MenuSkinRules.InkSoft);
        Assert.NotEqual(Color.DarkSlateGray, MenuSkinRules.InkSoft);
    }

    [Fact]
    public void Scrim_is_uniform_and_lighter_than_the_old_chat_only_value()
    {
        // 页面「四、我的推荐」的默认值（SKIN.scrim）；F8 原本是 0.42f，F9／中心是 0。
        Assert.InRange(MenuSkinRules.ScrimAlpha, 0.20f, 0.32f);
        Assert.True(MenuSkinRules.ScrimAlpha < 0.42f);
    }

    [Fact]
    public void Rule_colour_is_the_original_brown_at_partial_alpha()
    {
        // 页面：SKIN.rule = [150,96,48]、ruleAlpha = 0.55。
        // Color * float 预乘进通道，所以逐通道等于 round(通道 × 0.55 × 255 / 255)。
        Assert.Equal(new Color(150, 96, 48) * 0.55f, MenuSkinRules.RuleColor);
        Assert.True(MenuSkinRules.RuleColor.A < 255);
    }

    // ── 标题带几何 ────────────────────────────────────────────────────────

    /// <summary>F8 在 1280×720 下的 header（见 ChatLayoutRulesTests 里钉住的面板矩形）。</summary>
    private static readonly Rectangle ChatHeader = ChatLayoutRules.Calculate(1280, 720).Header;

    [Fact]
    public void Title_bar_hugs_the_header_corner()
    {
        // 页面 titleBand：barX = header.x + 12、barY = header.y + 12、4 × 20
        var bar = MenuSkinRules.TitleBar(ChatHeader);

        Assert.Equal(new Rectangle(ChatHeader.X + 12, ChatHeader.Y + 12, 4, 20), bar);
        Assert.True(ChatHeader.Contains(bar), "竖条必须落在 header 内");
    }

    [Fact]
    public void Title_text_sits_after_the_bar_and_status_follows_the_measured_title()
    {
        // 页面 titleBand：title 在 (barX + 12, barY - 3)，status 在 (… + ceil(titleWidth) + 16, barY - 1)
        var titlePosition = MenuSkinRules.TitleTextPosition(ChatHeader);
        var bar = MenuSkinRules.TitleBar(ChatHeader);

        Assert.Equal(bar.X + 12, (int)titlePosition.X);
        Assert.Equal(bar.Y - 3, (int)titlePosition.Y);

        var statusPosition = MenuSkinRules.StatusTextPosition(ChatHeader, titleWidth: 120.4f);
        Assert.Equal(bar.X + 12 + 121 + 16, (int)statusPosition.X);
        Assert.Equal(bar.Y - 1, (int)statusPosition.Y);
        Assert.True(statusPosition.X > titlePosition.X);
    }

    [Fact]
    public void Status_width_rounds_the_title_up_like_the_reference_page()
    {
        // 页面用 Math.ceil(measureText(title))，不是一个含糊的取整：
        // 120.1 → 121（比整数值多 1），119.9 → 120（与整数值同）。
        var exact = MenuSkinRules.StatusTextPosition(ChatHeader, 120f);
        var justAbove = MenuSkinRules.StatusTextPosition(ChatHeader, 120.1f);
        var justBelow = MenuSkinRules.StatusTextPosition(ChatHeader, 119.9f);

        Assert.Equal(exact.X + 1, justAbove.X);
        Assert.Equal(exact.X, justBelow.X);
    }

    [Fact]
    public void Hairline_rule_spans_the_header_above_its_bottom_edge()
    {
        // 页面 titleBand：分隔线 = { x: header.x + 12, y: header.y + h - 14, w: header.w - 24, h: 2 }
        var rule = MenuSkinRules.TitleRule(ChatHeader);

        Assert.Equal(ChatHeader.X + 12, rule.X);
        Assert.Equal(ChatHeader.Bottom - 14, rule.Y);
        Assert.Equal(ChatHeader.Width - 24, rule.Width);
        Assert.Equal(2, rule.Height);
        Assert.True(rule.Bottom <= ChatHeader.Bottom, "分隔线不能越出 header");
    }

    [Fact]
    public void Hairline_rule_still_has_a_positive_width_for_a_degenerate_header()
    {
        var rule = MenuSkinRules.TitleRule(new Rectangle(0, 0, 10, 20));

        Assert.True(rule.Width >= 1);
    }

    // ── 输入框：绘制矩形与命中区分离 ──────────────────────────────────────

    [Fact]
    public void Chat_input_box_visual_rectangle_matches_the_reference_page()
    {
        // 1280×720 → layout.InputBox = (229, 434, 366, 112)
        // 页面 textBoxDesign：x = well.x + 12、y = well.y + trunc((well.h - 48) / 2)、w = well.w - 24、h = 48
        var layout = ChatLayoutRules.Calculate(1280, 720);

        Assert.Equal(new Rectangle(229, 434, 366, 112), layout.InputBox);
        Assert.Equal(new Rectangle(241, 466, 342, 48), MenuSkinRules.InputBoxVisual(layout.InputBox));
    }

    [Fact]
    public void Group_input_box_visual_rectangle_is_centred_in_a_taller_footer()
    {
        // 1280×720 → layout.InputBox = (100, 592, 792, 104)：footer 高 104，(104-48)/2 = 28
        var layout = GroupDialogueLayoutRules.Calculate(1280, 720);

        Assert.Equal(new Rectangle(100, 592, 792, 104), layout.InputBox);
        Assert.Equal(new Rectangle(112, 620, 768, 48), MenuSkinRules.InputBoxVisual(layout.InputBox));
    }

    /// <summary>
    /// 这一条是本次改动里唯一可能碰到点击的地方，必须钉死：
    /// <see cref="MenuSkinRules.InputBoxVisual"/> 只产出**绘制**矩形，
    /// 命中判定用的 <c>layout.InputBox</c> 一个像素都没动。
    /// </summary>
    [Theory]
    [InlineData(1280, 720)]
    [InlineData(1920, 1080)]
    [InlineData(1024, 600)]
    [InlineData(640, 480)]
    public void Visual_input_rect_never_replaces_the_hit_area(int width, int height)
    {
        var chat = ChatLayoutRules.Calculate(width, height);
        var chatVisual = MenuSkinRules.InputBoxVisual(chat.InputBox);

        // 视觉矩形始终内含于命中区（因此「点得到的地方」只会多、不会少），
        // 而且高度恒为贴图高度 48。
        Assert.Equal(MenuSkinRules.InputBoxHeight, chatVisual.Height);
        Assert.True(chat.InputBox.Contains(chatVisual), $"私聊视觉输入框越出命中区: {chatVisual} ⊄ {chat.InputBox}");

        var group = GroupDialogueLayoutRules.Calculate(width, height);
        var groupVisual = MenuSkinRules.InputBoxVisual(group.InputBox);
        Assert.Equal(MenuSkinRules.InputBoxHeight, groupVisual.Height);
        Assert.True(group.InputBox.Contains(groupVisual), $"群聊视觉输入框越出命中区: {groupVisual} ⊄ {group.InputBox}");
    }

    /// <summary>
    /// 视觉输入框的**可达**宽度下限。用真实布局（而不是手搓的窄矩形）来断言：
    /// 两个布局给出命中区宽 ≥ 120（<c>ChatLayoutRules</c> 与 <c>GroupDialogueLayoutRules</c>
    /// 里的 <c>Math.Max(120, …)</c>），视觉矩形再左右各缩
    /// <see cref="MenuSkinRules.InputBoxHorizontalInset"/> → 视觉宽恒 ≥ 96。
    ///
    /// 原来这条用手拼一个 40 宽的输入框去撞 <see cref="MenuSkinRules.InputBoxMinimumWidth"/>：
    /// 40 宽在现有几何下拼不出来，命中的只是那条不可达的防呆分支，绿得与行为无关。
    /// </summary>
    [Fact]
    public void Visual_input_rect_keeps_a_usable_minimum_width()
    {
        const int layoutFloor = 120;   // 两处布局的 Math.Max(120, …)
        var minimum = layoutFloor - (MenuSkinRules.InputBoxHorizontalInset * 2);

        foreach (var (width, height) in new[] { (1280, 720), (1920, 1080), (1024, 600), (640, 480) })
        {
            var chat = MenuSkinRules.InputBoxVisual(ChatLayoutRules.Calculate(width, height).InputBox);
            var group = MenuSkinRules.InputBoxVisual(GroupDialogueLayoutRules.Calculate(width, height).InputBox);

            Assert.Equal(MenuSkinRules.InputBoxHeight, chat.Height);
            Assert.Equal(MenuSkinRules.InputBoxHeight, group.Height);
            Assert.True(chat.Width >= minimum, $"{width}×{height} 私聊视觉输入框过窄：{chat.Width} < {minimum}");
            Assert.True(group.Width >= minimum, $"{width}×{height} 群聊视觉输入框过窄：{group.Width} < {minimum}");
        }

        // MenuSkinRules.InputBoxMinimumWidth = 80 是**防呆**下限而不是布局下限（96 > 80），
        // Math.Max(80, …) 的 80 分支在现有几何下取不到。保留它的理由与代价：
        // 消除这条不可达分支必须把布局下限降到 104 以下，而布局下限就是命中区宽度 ——
        // 三个界面的点击判定都吃 layout.InputBox，所以不动，只在这里钉住它仍然生效。
        var degenerate = MenuSkinRules.InputBoxVisual(new Rectangle(0, 0, 40, 112));

        Assert.Equal(MenuSkinRules.InputBoxMinimumWidth, degenerate.Width);
        Assert.Equal(MenuSkinRules.InputBoxHeight, degenerate.Height);
    }

    [Fact]
    public void Input_box_height_is_the_texture_height_that_removes_the_dark_band()
    {
        // 那条深色带的成因是 TextBox.Draw 把源矩形高度写成 Height，
        // H > 48 时采样被 clamp 到 192×48 贴图的末行。48 即 1:1。
        Assert.Equal(48, MenuSkinRules.InputBoxHeight);
        Assert.Equal(12, MenuSkinRules.InputBoxHorizontalInset);
    }

    // ── F9 提示行与气泡区 ─────────────────────────────────────────────────

    [Fact]
    public void Short_hint_fits_the_header_and_costs_the_bubble_area_nothing()
    {
        var layout = GroupDialogueLayoutRules.Calculate(1280, 720);

        // 参与者条宽 1080、名单占 120 → 剩 936
        Assert.True(MenuSkinRules.HintFitsHeader(layout.ParticipantStrip.Width, 120f, 936f));
        Assert.False(MenuSkinRules.HintFitsHeader(layout.ParticipantStrip.Width, 120f, 937f));

        Assert.Equal(layout.MessageArea.Height, MenuSkinRules.MessageBubbleAreaHeight(layout.MessageArea.Height, hintInHeader: true));
    }

    [Fact]
    public void Long_hint_falls_back_below_and_shrinks_the_bubble_area()
    {
        // 页面：bubbleAreaH = max(60, area.h - 30)
        Assert.Equal(408, MenuSkinRules.MessageBubbleAreaHeight(438, hintInHeader: false));
        Assert.Equal(MenuSkinRules.MessageAreaMinimumHeight, MenuSkinRules.MessageBubbleAreaHeight(70, hintInHeader: false));
    }

    [Fact]
    public void Bubble_area_never_grows_beyond_the_message_area_it_lives_in()
    {
        // 退化视口：消息区比下限还矮时不能反过来变高（凹槽会被画出消息区）。
        Assert.Equal(20, MenuSkinRules.MessageBubbleAreaHeight(20, hintInHeader: false));
        Assert.Equal(20, MenuSkinRules.MessageBubbleAreaHeight(20, hintInHeader: true));
    }

    [Fact]
    public void Header_hint_space_matches_the_reference_page_formula()
    {
        // 页面：headerHintSpace = participantStrip.w - namesWidth - 24
        Assert.Equal(936f, MenuSkinRules.HeaderHintSpace(1080, 120f));
    }

    [Fact]
    public void Missing_hint_does_not_reserve_the_bottom_row()
    {
        // 群聊成功收到回复后 hint 会被清空（GroupDialogueMenu 的 hint = string.Empty），
        // 也就是正常对话中提示大部分时间是空的——这种常态不能白白少掉 30px 气泡区。
        // 这是与设计稿页面的一处有意差异，页面上的示例提示恒非空。
        Assert.False(MenuSkinRules.HintNeedsBottomRow(hasHint: false, 1080, 120f, 0f));
        Assert.Equal(
            438,
            MenuSkinRules.MessageBubbleAreaHeight(438, hintInHeader: true));
    }

    [Fact]
    public void Short_hint_goes_to_the_header_only_the_long_one_takes_the_bottom_row()
    {
        Assert.False(MenuSkinRules.HintNeedsBottomRow(hasHint: true, 1080, 120f, 936f));
        Assert.True(MenuSkinRules.HintNeedsBottomRow(hasHint: true, 1080, 120f, 937f));
    }

    // ── 群聊中心：标题带与列表凹槽 ────────────────────────────────────────

    [Fact]
    public void Hub_list_inset_matches_the_reference_page_geometry()
    {
        // 1280×720 → panel = (100, 24, 1080, 672)、closeButton = (1000, 620, 148, 56)
        // 页面：{ x: panel.x + 24, y: panel.y + 74, w: panel.w - 48, h: listBottom - listTop }
        //       listBottom = closeButton.y - 44
        var layout = GroupDialogueHubLayoutRules.Calculate(1280, 720);

        Assert.Equal(new Rectangle(100, 24, 1080, 672), layout.Panel);
        Assert.Equal(new Rectangle(1000, 620, 148, 56), layout.CloseButton);
        Assert.Equal(new Rectangle(124, 98, 1032, 478), MenuSkinRules.HubListArea(layout.Panel, layout.CloseButton));
    }

    [Fact]
    public void Hub_list_inset_never_collapses_on_a_tiny_panel()
    {
        var area = MenuSkinRules.HubListArea(
            new Rectangle(0, 0, 40, 30),
            new Rectangle(0, 0, 10, 10));

        Assert.True(area.Width >= 1);
        Assert.True(area.Height >= MenuSkinRules.HubListMinimumHeight);
    }

    [Fact]
    public void Hub_card_second_row_ends_inside_the_card()
    {
        // 卡片高 92、九宫格 slice 20 → 下内沿 = 72。
        // 第二行文字底 = 44 + 单行行高（28）= 72，正好落在内沿上；
        // 改前的第三行在 +66、文字底 +94，比卡片还低 2px，会被下边框切断。
        Assert.Equal(44, MenuSkinRules.HubCardSecondRowOffset);
        Assert.True(MenuSkinRules.HubCardSecondRowOffset + 28 <= 92 - 20);
        Assert.Equal(74, MenuSkinRules.HubTitleBandHeight);
    }
}
