using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// F8 私聊名单的「预选」与「选中怎么动」规则（2026-09-21，B26 收尾时补）。
///
/// 与 <see cref="PrivateChatRosterRulesTests"/> 分工：那一份管名单**长什么样**
/// （排序、频道、容量、滚动切片），这一份管玩家打开名单之后**选中谁、怎么改**，
/// 以及「只有一位候选时不开列表」这条交互约定，还有「谁进得了名单」那条判据的边界。
/// </summary>
public sealed class PrivateChatRosterSelectionTests
{
    private static PrivateChatRosterSource Source(
        string npcId,
        bool isPresent,
        float distanceInTiles,
        bool isInteractionTarget = false)
    {
        return new PrivateChatRosterSource(
            npcId,
            $"{npcId} 的显示名",
            isPresent,
            distanceInTiles,
            isInteractionTarget);
    }

    private static IReadOnlyList<PrivateChatRosterEntry> Roster(
        params PrivateChatRosterSource[] sources)
    {
        return PrivateChatRosterRules.Build(sources);
    }

    // ── 预选：F8 改前那套自动选人规则，降级成「默认选中项」 ────────────────────

    [Fact]
    public void Preselects_the_nearest_npc_in_the_current_location()
    {
        var roster = Roster(
            Source("Emily", isPresent: true, distanceInTiles: 9f),
            Source("Abigail", isPresent: true, distanceInTiles: 1f),
            Source("Marnie", isPresent: true, distanceInTiles: 5f));

        Assert.Equal(
            "Abigail",
            roster[PrivateChatRosterRules.DefaultSelectedIndex(roster)].NpcId);
    }

    /// <summary>
    /// 「鼠标指向优先」是那条老规则的第一顺位，改成选人界面之后不能丢：
    /// 鼠标放在谁身上，打开名单就该预选谁——哪怕旁边还站着更近的人。
    /// </summary>
    [Fact]
    public void Preselects_the_npc_under_the_cursor_even_when_someone_else_is_closer()
    {
        var roster = Roster(
            Source("Abigail", isPresent: true, distanceInTiles: 1f),
            Source("Emily", isPresent: true, distanceInTiles: 6f, isInteractionTarget: true));

        Assert.Equal(
            "Emily",
            roster[PrivateChatRosterRules.DefaultSelectedIndex(roster)].NpcId);
    }

    /// <summary>
    /// 不在当前地点的角色不参与预选：预选一位「只能线上聊」的人没有意义，
    /// 而玩家真正想点的多半是站在眼前那位。
    /// </summary>
    [Fact]
    public void Preselection_ignores_npcs_outside_the_current_location()
    {
        var roster = Roster(
            Source("Pierre", isPresent: false, distanceInTiles: 0.5f),
            Source("Emily", isPresent: true, distanceInTiles: 7f));

        Assert.Equal(
            "Emily",
            roster[PrivateChatRosterRules.DefaultSelectedIndex(roster)].NpcId);
    }

    /// <summary>
    /// 当前地点一个人都没有时退回第 0 行：名单按名字排，第一行就是名字最靠前的那位，
    /// 不需要第二条兜底规则（不在同一地点的人距离一律取不到，本来就分不出远近）。
    /// </summary>
    [Fact]
    public void Falls_back_to_the_first_row_when_nobody_is_in_the_current_location()
    {
        var roster = Roster(
            Source("Abigail", isPresent: false, distanceInTiles: float.MaxValue),
            Source("Emily", isPresent: false, distanceInTiles: float.MaxValue));

        Assert.Equal(0, PrivateChatRosterRules.DefaultSelectedIndex(roster));
    }

    /// <summary>
    /// 排序改成按名字之后，「预选谁」与「谁排第一」彻底分家：最近的那位在名字序里
    /// 排在最后一行时，打开名单预选的仍然是他——玩家按回车进的是眼前这个人，
    /// 而不是名字最靠前的那位。
    /// </summary>
    [Fact]
    public void Preselection_is_independent_of_the_name_order_of_the_list()
    {
        var roster = Roster(
            Source("Abigail", isPresent: true, distanceInTiles: 20f),
            Source("Emily", isPresent: true, distanceInTiles: 15f),
            Source("Marnie", isPresent: true, distanceInTiles: 1f));

        Assert.Equal(
            new[] { "Abigail", "Emily", "Marnie" },
            roster.Select(entry => entry.NpcId));
        Assert.Equal(
            "Marnie",
            roster[PrivateChatRosterRules.DefaultSelectedIndex(roster)].NpcId);
    }

    [Fact]
    public void Preselection_skips_rows_with_unusable_distance()
    {
        var roster = Roster(
            Source("Abigail", isPresent: true, distanceInTiles: float.NaN),
            Source("Emily", isPresent: true, distanceInTiles: 4f));

        Assert.Equal(
            "Emily",
            roster[PrivateChatRosterRules.DefaultSelectedIndex(roster)].NpcId);
    }

    [Fact]
    public void Preselection_of_an_empty_roster_is_zero()
    {
        Assert.Equal(0, PrivateChatRosterRules.DefaultSelectedIndex(null));
        Assert.Equal(
            0,
            PrivateChatRosterRules.DefaultSelectedIndex(
                Array.Empty<PrivateChatRosterEntry>()));
    }

    // ── 选中怎么动：上下键／滚轮／翻页 ────────────────────────────────────────

    [Theory]
    [InlineData(0, 1, 1)]
    [InlineData(2, 1, 2)]
    [InlineData(0, -1, 0)]
    [InlineData(2, -1, 1)]
    [InlineData(1, 10, 2)]
    [InlineData(1, -10, 0)]
    public void Selection_moves_within_the_roster_and_stops_at_both_ends(
        int selectedIndex,
        int delta,
        int expected)
    {
        Assert.Equal(
            expected,
            PrivateChatRosterRules.MoveSelection(selectedIndex, delta, totalCount: 3));
    }

    /// <summary>
    /// **不循环**：名单可能有几十人，到头绕回另一头会让「一直按住下键」突然跳回顶部，
    /// 那是误操作来源。两端一律夹住。
    /// </summary>
    [Fact]
    public void Selection_does_not_wrap_around()
    {
        Assert.Equal(2, PrivateChatRosterRules.MoveSelection(2, 1, totalCount: 3));
        Assert.Equal(0, PrivateChatRosterRules.MoveSelection(0, -1, totalCount: 3));
    }

    [Fact]
    public void Page_down_moves_a_whole_screen_and_clamps_at_the_end()
    {
        // 12 人、一屏 5 行：从第 0 行翻一屏到第 5 行；已接近末尾时夹到最后一行。
        Assert.Equal(5, PrivateChatRosterRules.MoveSelection(0, 5, totalCount: 12));
        Assert.Equal(11, PrivateChatRosterRules.MoveSelection(8, 5, totalCount: 12));
    }

    [Fact]
    public void Selection_stays_at_zero_for_an_empty_roster()
    {
        Assert.Equal(0, PrivateChatRosterRules.MoveSelection(5, -1, totalCount: 0));
    }

    [Fact]
    public void Moving_the_selection_rejects_an_impossible_roster_size()
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => PrivateChatRosterRules.MoveSelection(0, 1, totalCount: -1));
    }

    /// <summary>
    /// 一路按「下键」走到底：每一步选中行都必须留在可视区内。
    /// 这条防的是「视口和选中行各滚各的」——那时玩家看得见的行不是回车会进的那位。
    /// </summary>
    [Fact]
    public void Walking_the_list_with_the_keyboard_keeps_the_selected_row_visible()
    {
        var roster = Roster(
            Enumerable.Range(0, 12)
                .Select(index => Source($"Npc{index:00}", false, float.MaxValue))
                .ToArray());
        const int capacity = 5;
        var start = 0;
        var selected = PrivateChatRosterRules.DefaultSelectedIndex(roster);

        for (var step = 0; step < roster.Count; step++)
        {
            selected = PrivateChatRosterRules.MoveSelection(selected, 1, roster.Count);
            start = PrivateChatRosterRules.ScrollTo(start, selected, roster.Count, capacity);
            Assert.InRange(selected, start, start + capacity - 1);
        }
    }

    // ── 只有一位候选时不开列表 ────────────────────────────────────────────────

    [Theory]
    [InlineData(0, false)]
    [InlineData(1, false)]
    [InlineData(2, true)]
    [InlineData(46, true)]
    public void The_roster_is_shown_only_when_there_is_a_choice(
        int entryCount,
        bool expected)
    {
        Assert.Equal(expected, PrivateChatRosterRules.ShouldShowRoster(entryCount));
    }

    [Fact]
    public void A_negative_roster_size_is_rejected()
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => PrivateChatRosterRules.ShouldShowRoster(-1));
    }

    // ── 判据边界：谁进得了名单 ────────────────────────────────────────────────

    /// <summary>
    /// 「游戏内第一次碰到过才解锁」这条口径的一段钉子：名单的输入**只有**存档里的好感度
    /// 记录（<see cref="KnownNpcResolver"/> 的那份 key 集合），没有第二条补人来源。
    /// </summary>
    [Fact]
    public void Roster_contains_exactly_the_npcs_with_a_friendship_record()
    {
        var known = KnownNpcResolver.Resolve(
            new[] { "Abigail", "Emily" },
            npcId => new KnownNpc(npcId, npcId));

        var roster = PrivateChatRosterRules.Build(
            known.Select(npc =>
                Source(npc.NpcId, isPresent: false, distanceInTiles: float.MaxValue)));

        Assert.Equal(new[] { "Abigail", "Emily" }, roster.Select(entry => entry.NpcId));
        Assert.DoesNotContain(roster, entry => entry.NpcId == "Sebastian");
    }

    /// <summary>
    /// 认识的边界之一：**认识 ≠ 此刻在同一地点**。好感度记录是「打过照面」的持久标志，
    /// 所以人在镇上的村民照样在名单里（只是走线上频道），不会因为建筑里没人就消失。
    /// </summary>
    [Fact]
    public void A_known_npc_stays_in_the_roster_while_being_somewhere_else()
    {
        var roster = Roster(Source("Abigail", isPresent: false, distanceInTiles: float.MaxValue));

        var entry = Assert.Single(roster);
        Assert.Equal(ConversationChannel.Remote, entry.Channel);
        Assert.False(entry.IsNearby);
        Assert.Equal("线上", entry.StatusLabel);
    }

    /// <summary>
    /// 认识的边界之二：新存档（一条好感度记录都没有）→ 名单为空，
    /// 于是 <c>ModEntry</c> 走「还没有认识的角色：先在镇上跟村民说说话」那条提示，
    /// 而不是弹一个空列表。名单随着在小镇上认识的人变多自然变长。
    /// </summary>
    [Fact]
    public void A_save_without_any_friendship_record_yields_an_empty_roster()
    {
        var known = KnownNpcResolver.Resolve(
            Array.Empty<string>(),
            npcId => new KnownNpc(npcId, npcId));

        var roster = PrivateChatRosterRules.Build(
            known.Select(npc => Source(npc.NpcId, isPresent: true, distanceInTiles: 1f)));

        Assert.Empty(roster);
        Assert.False(PrivateChatRosterRules.ShouldShowRoster(roster.Count));
    }

    /// <summary>
    /// 床边那个测试克隆体（<see cref="TestNpcPlacementRules.InternalName"/>）永远进不了名单：
    /// 它没有好感度记录，而好感度记录是唯一的解锁来源。这正是「克隆体抢走 F8 目标」
    /// 那个真实事故在名单时代的对应保障——它连候选都不是。
    /// </summary>
    [Fact]
    public void The_bedside_test_clone_never_reaches_the_roster()
    {
        var known = KnownNpcResolver.Resolve(
            new[] { "Abigail", TestNpcPlacementRules.InternalName },
            npcId => new KnownNpc(npcId, npcId));

        // 克隆体就贴在玩家身边（0.1 格、鼠标还指着它），照样进不来。
        var roster = PrivateChatRosterRules.Build(
            known.Select(npc => Source(
                npc.NpcId,
                isPresent: true,
                distanceInTiles: 0.1f,
                isInteractionTarget: true)));

        Assert.Equal(new[] { "Abigail" }, roster.Select(entry => entry.NpcId));
    }
}
