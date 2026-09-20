using StardewAI.NPC;
using Microsoft.Xna.Framework;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 审计 #37：邀约卡按钮矩形此前算三遍（绘制局部字面量、点击类常量、视觉测试单独一份）。
/// 这里钉住收敛后的几何——期望值就是**改动前那三处各自的取值**。
/// </summary>
public sealed class GroupInvitationActionLayoutRulesTests
{
    private static readonly Rectangle Row = new(32, 94, 1016, 92);

    [Fact]
    public void Button_constants_match_the_literal_values_used_before()
    {
        Assert.Equal(64, GroupInvitationActionLayoutRules.ButtonWidth);
        Assert.Equal(6, GroupInvitationActionLayoutRules.ButtonGap);
        Assert.Equal(52, GroupInvitationActionLayoutRules.ButtonHeight);
        Assert.Equal(18, GroupInvitationActionLayoutRules.ButtonTopOffset);
    }

    [Fact]
    public void Action_row_starts_at_the_same_x_as_the_original_formula()
    {
        // 改前：row.Right - (64 * 3) - (6 * 2)
        Assert.Equal(Row.Right - 204, GroupInvitationActionLayoutRules.ActionRowX(Row));
    }

    [Fact]
    public void Three_buttons_reproduce_the_original_drawn_rectangles()
    {
        var actionX = Row.Right - 204;

        Assert.Equal(
            new Rectangle(actionX, Row.Y + 18, 64, 52),
            GroupInvitationActionLayoutRules.AcceptButton(Row));
        Assert.Equal(
            new Rectangle(actionX + 64 + 6, Row.Y + 18, 64, 52),
            GroupInvitationActionLayoutRules.DeferButton(Row));
        Assert.Equal(
            new Rectangle(actionX + ((64 + 6) * 2), Row.Y + 18, 64, 52),
            GroupInvitationActionLayoutRules.DismissButton(Row));
    }

    [Fact]
    public void Accept_hit_area_keeps_the_visual_test_rectangle_from_before()
    {
        // 视觉测试用的矩形：X 与按钮一致，纵向覆盖整行。
        var actionX = Row.Right - 204;

        Assert.Equal(
            new Rectangle(actionX, Row.Y, 64, Row.Height),
            GroupInvitationActionLayoutRules.AcceptHitArea(Row));
    }

    [Fact]
    public void Drawn_buttons_do_not_overlap_each_other_and_stay_inside_the_row()
    {
        var accept = GroupInvitationActionLayoutRules.AcceptButton(Row);
        var defer = GroupInvitationActionLayoutRules.DeferButton(Row);
        var dismiss = GroupInvitationActionLayoutRules.DismissButton(Row);

        Assert.False(accept.Intersects(defer));
        Assert.False(defer.Intersects(dismiss));
        Assert.True(accept.Left >= Row.Left);
        Assert.True(dismiss.Right <= Row.Right);
    }

    [Theory]
    // 三个按钮各自的判定区间（改前的 pointerX switch 逐字重写）
    [InlineData(-1, GroupInvitationStatus.Accepted)]
    [InlineData(0, GroupInvitationStatus.Accepted)]
    [InlineData(63, GroupInvitationStatus.Accepted)]
    // 落在按钮之间的间隙：改前的 switch 落到 default 分支，仍是 Accepted
    [InlineData(64, GroupInvitationStatus.Accepted)]
    [InlineData(69, GroupInvitationStatus.Accepted)]
    [InlineData(70, GroupInvitationStatus.Deferred)]
    [InlineData(139, GroupInvitationStatus.Deferred)]
    [InlineData(140, GroupInvitationStatus.Dismissed)]
    [InlineData(400, GroupInvitationStatus.Dismissed)]
    public void Pointer_action_matches_the_original_thresholds(
        int offsetFromActionRow,
        GroupInvitationStatus expected)
    {
        var pointerX = GroupInvitationActionLayoutRules.ActionRowX(Row) + offsetFromActionRow;

        Assert.Equal(
            expected,
            GroupInvitationActionLayoutRules.ResolvePointerAction(Row, pointerX));
    }

    [Fact]
    public void Pointer_action_thresholds_agree_with_the_drawn_button_rectangles()
    {
        var accept = GroupInvitationActionLayoutRules.AcceptButton(Row);
        var defer = GroupInvitationActionLayoutRules.DeferButton(Row);
        var dismiss = GroupInvitationActionLayoutRules.DismissButton(Row);

        Assert.Equal(
            GroupInvitationStatus.Accepted,
            GroupInvitationActionLayoutRules.ResolvePointerAction(Row, accept.Center.X));
        Assert.Equal(
            GroupInvitationStatus.Deferred,
            GroupInvitationActionLayoutRules.ResolvePointerAction(Row, defer.Center.X));
        Assert.Equal(
            GroupInvitationStatus.Dismissed,
            GroupInvitationActionLayoutRules.ResolvePointerAction(Row, dismiss.Center.X));
    }
}
