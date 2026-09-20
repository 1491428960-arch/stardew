using StardewAI.NPC;
using Microsoft.Xna.Framework;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupDialogueLayoutRulesTests
{
    [Fact]
    public void Layout_rejects_non_positive_viewport()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => GroupDialogueLayoutRules.Calculate(0, 720));
        Assert.Throws<ArgumentOutOfRangeException>(() => GroupDialogueLayoutRules.Calculate(1280, 0));
    }

    /// <summary>
    /// 审计 #36：群聊消息窗口的条数上限有一个名字了，数值与行为不变。
    /// </summary>
    [Fact]
    public void Visible_message_window_keeps_the_previous_hard_coded_limit()
    {
        Assert.Equal(10, GroupDialogueLayoutRules.MaxVisibleMessages);
    }

    /// <summary>
    /// 审计 #38：面板放置改用 <see cref="MenuPanelRules.CenteredInViewport"/> 之后，
    /// 群聊面板矩形必须与改动前逐值相同。
    /// </summary>
    [Fact]
    public void Panel_rectangle_is_unchanged_after_the_shared_placement_refactor()
    {
        // 改前算式：宽 = min(1120, max(680, 1280-48))，再夹到 1280-48
        //           高 = min(720, max(430, 720-48))，再夹到 720-48
        //           原点 = (max(0,…), max(0,…))
        Assert.Equal(
            new Rectangle(80, 24, 1120, 672),
            GroupDialogueLayoutRules.Calculate(1280, 720).Panel);
    }
}
