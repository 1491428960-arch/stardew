using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

/// <summary>
/// 邀约卡上「接受 / 稍后 / 忽略」三个按钮的**唯一**几何定义。
///
/// 2026-09-20（语义层审计 #37）：同一个按钮此前算三遍——绘制用方法内的局部字面量
/// （64/6/18/52），点击用类常量（<c>ActionButtonWidth</c>/<c>ActionButtonGap</c>），
/// 视觉测试又用一份 <c>VisualTestAcceptButton</c>；于是「同一个按钮」存在多个矩形。
/// 现在三处共用这里的函数：矩形数值与改前逐字相同，只是不再各算一份。
/// </summary>
public static class GroupInvitationActionLayoutRules
{
    public const int ButtonWidth = 64;
    public const int ButtonGap = 6;
    public const int ButtonHeight = 52;
    public const int ButtonTopOffset = 18;

    /// <summary>三个按钮那一排的起始 X（即「接受」按钮的左边界）。</summary>
    public static int ActionRowX(Rectangle row)
    {
        return row.Right - (ButtonWidth * 3) - (ButtonGap * 2);
    }

    public static Rectangle AcceptButton(Rectangle row) => ButtonAt(row, index: 0);

    public static Rectangle DeferButton(Rectangle row) => ButtonAt(row, index: 1);

    public static Rectangle DismissButton(Rectangle row) => ButtonAt(row, index: 2);

    /// <summary>
    /// 「接受」按钮的命中区：X 与绘制一致，纵向覆盖整行。
    /// 视觉测试用它取点击坐标；纵向范围保持改前的 row.Height（点击判定只看 X）。
    /// </summary>
    public static Rectangle AcceptHitArea(Rectangle row)
    {
        return new Rectangle(ActionRowX(row), row.Y, ButtonWidth, row.Height);
    }

    /// <summary>
    /// 行内点击落在哪个按钮上。判定区间与绘制矩形同源，不再各写一套阈值。
    /// </summary>
    public static GroupInvitationStatus ResolvePointerAction(Rectangle row, int pointerX)
    {
        var actionX = ActionRowX(row);
        return pointerX switch
        {
            _ when pointerX >= actionX && pointerX < actionX + ButtonWidth =>
                GroupInvitationStatus.Accepted,
            _ when pointerX >= actionX + ButtonWidth + ButtonGap &&
                pointerX < actionX + ((ButtonWidth + ButtonGap) * 2) =>
                GroupInvitationStatus.Deferred,
            _ when pointerX >= actionX + ((ButtonWidth + ButtonGap) * 2) =>
                GroupInvitationStatus.Dismissed,
            _ => GroupInvitationStatus.Accepted,
        };
    }

    private static Rectangle ButtonAt(Rectangle row, int index)
    {
        return new Rectangle(
            ActionRowX(row) + ((ButtonWidth + ButtonGap) * index),
            row.Y + ButtonTopOffset,
            ButtonWidth,
            ButtonHeight);
    }
}
