using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class PrivateChatRosterRulesTests
{
    private static PrivateChatRosterSource Source(
        string npcId,
        bool isPresent,
        float distanceInTiles)
    {
        return new PrivateChatRosterSource(npcId, npcId, isPresent, distanceInTiles);
    }

    [Fact]
    public void Nearby_rows_come_first_then_same_location_then_online()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Pierre", isPresent: false, distanceInTiles: float.MaxValue),
            Source("Emily", isPresent: true, distanceInTiles: 8f),
            Source("Abigail", isPresent: true, distanceInTiles: 1f),
            Source("Sebastian", isPresent: false, distanceInTiles: float.MaxValue),
        });

        Assert.Equal(
            new[] { "Abigail", "Emily", "Pierre", "Sebastian" },
            roster.Select(entry => entry.NpcId));
    }

    [Fact]
    public void Rows_inside_one_tier_are_sorted_by_distance()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Emily", isPresent: true, distanceInTiles: 8f),
            Source("Marnie", isPresent: true, distanceInTiles: 3f),
        });

        Assert.Equal(new[] { "Marnie", "Emily" }, roster.Select(entry => entry.NpcId));
    }

    [Fact]
    public void Unresolvable_distance_sinks_to_the_bottom_of_its_tier()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Marnie", isPresent: true, distanceInTiles: float.NaN),
            Source("Emily", isPresent: true, distanceInTiles: 8f),
        });

        // NaN 不该被当成 0 排到最前——那会让「不知道在哪」的角色插到看得见的人前面。
        Assert.Equal(new[] { "Emily", "Marnie" }, roster.Select(entry => entry.NpcId));
    }

    [Fact]
    public void Rows_without_ids_or_display_names_are_dropped_and_ids_are_deduplicated()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            new PrivateChatRosterSource("  ", "无名", false, float.MaxValue),
            new PrivateChatRosterSource("Abigail", "  ", false, float.MaxValue),
            Source("Emily", isPresent: false, distanceInTiles: float.MaxValue),
            Source("emily", isPresent: false, distanceInTiles: float.MaxValue),
        });

        Assert.Equal(new[] { "Emily" }, roster.Select(entry => entry.NpcId));
    }

    [Fact]
    public void Empty_input_yields_an_empty_roster()
    {
        Assert.Empty(PrivateChatRosterRules.Build(null));
        Assert.Empty(PrivateChatRosterRules.Build(Array.Empty<PrivateChatRosterSource>()));
    }

    [Theory]
    [InlineData(true, "face_to_face")]
    [InlineData(false, "remote")]
    public void Channel_follows_whether_the_npc_is_in_the_same_location(
        bool isPresent,
        string expectedChannel)
    {
        Assert.Equal(expectedChannel, PrivateChatRosterRules.ResolveChannel(isPresent));
    }

    /// <summary>
    /// 频道判据是「在不在同一地点」，**不是**距离：站在屋子另一头仍然是当面聊，
    /// 否则一次选址失误就会把玩家莫名其妙降级成线上聊天。
    /// </summary>
    [Fact]
    public void A_distant_but_present_npc_still_chats_face_to_face()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Emily", isPresent: true, distanceInTiles: 40f),
        });

        var entry = Assert.Single(roster);
        Assert.False(entry.IsNearby);
        Assert.Equal(ConversationChannel.FaceToFace, entry.Channel);
        Assert.Equal("同处一地", entry.StatusLabel);
    }

    [Theory]
    [InlineData(true, 0f, true)]
    [InlineData(true, 2.5f, true)]
    [InlineData(true, 2.6f, false)]
    [InlineData(true, float.NaN, false)]
    [InlineData(true, float.PositiveInfinity, false)]
    [InlineData(true, -1f, false)]
    [InlineData(false, 0.5f, false)]
    public void Nearby_reuses_the_face_to_face_repeat_chat_range(
        bool isPresent,
        float distanceInTiles,
        bool expected)
    {
        Assert.Equal(expected, PrivateChatRosterRules.IsNearby(isPresent, distanceInTiles));
    }

    [Fact]
    public void Status_label_tells_the_player_what_will_happen()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Abigail", isPresent: true, distanceInTiles: 1f),
            Source("Emily", isPresent: true, distanceInTiles: 9f),
            Source("Pierre", isPresent: false, distanceInTiles: float.MaxValue),
        });

        Assert.Equal(
            new[] { "身边", "同处一地", "线上" },
            roster.Select(entry => entry.StatusLabel));
    }

    [Fact]
    public void Visible_capacity_never_drops_below_one_row()
    {
        Assert.Equal(8, PrivateChatRosterRules.VisibleCapacity((8 * PrivateChatRosterRules.RowHeight) + 16));
        Assert.Equal(1, PrivateChatRosterRules.VisibleCapacity(0));
        Assert.Equal(1, PrivateChatRosterRules.VisibleCapacity(-100));
    }

    [Fact]
    public void Max_start_index_is_zero_while_everything_fits()
    {
        Assert.Equal(0, PrivateChatRosterRules.MaxStartIndex(5, 8));
        Assert.Equal(0, PrivateChatRosterRules.MaxStartIndex(8, 8));
        Assert.Equal(42, PrivateChatRosterRules.MaxStartIndex(50, 8));
    }

    [Theory]
    [InlineData(-1, 8)]
    [InlineData(5, 0)]
    [InlineData(5, -3)]
    public void Max_start_index_rejects_impossible_inputs(int total, int capacity)
    {
        Assert.Throws<ArgumentOutOfRangeException>(
            () => PrivateChatRosterRules.MaxStartIndex(total, capacity));
    }

    [Fact]
    public void Visible_entries_are_a_clamped_slice()
    {
        var roster = PrivateChatRosterRules.Build(
            Enumerable.Range(0, 10).Select(index => Source($"Npc{index:00}", false, float.MaxValue)));

        Assert.Equal(
            new[] { "Npc00", "Npc01", "Npc02" },
            PrivateChatRosterRules.VisibleEntries(roster, 0, 3).Select(entry => entry.NpcId));
        // 起始行越界时夹到最后一屏（10 行、3 行一屏 → 最大起始行 7）。
        Assert.Equal(
            new[] { "Npc07", "Npc08", "Npc09" },
            PrivateChatRosterRules.VisibleEntries(roster, 8, 3).Select(entry => entry.NpcId));
        Assert.Equal(
            new[] { "Npc07", "Npc08", "Npc09" },
            PrivateChatRosterRules.VisibleEntries(roster, 999, 3).Select(entry => entry.NpcId));
    }

    [Fact]
    public void Visible_entries_handle_empty_and_invalid_capacity()
    {
        Assert.Empty(PrivateChatRosterRules.VisibleEntries(null, 0, 3));
        Assert.Empty(PrivateChatRosterRules.VisibleEntries(
            Array.Empty<PrivateChatRosterEntry>(),
            0,
            3));
        Assert.Throws<ArgumentOutOfRangeException>(
            () => PrivateChatRosterRules.VisibleEntries(
                Array.Empty<PrivateChatRosterEntry>(),
                0,
                0));
    }

    [Theory]
    [InlineData(0, 0, 0)]
    // 目标行在视口下方：把它滚进来所需的最小起始行是 rowIndex - capacity + 1。
    [InlineData(0, 42, 33)]
    // 目标行在视口上方：起始行直接跟到它。
    [InlineData(3, 2, 2)]
    [InlineData(9, 42, 33)]
    // 起始行越界：夹到最大起始行（50 行、10 行一屏 → 40）。
    [InlineData(0, 999, 40)]
    public void Scroll_to_keeps_the_row_inside_the_viewport(
        int startIndex,
        int rowIndex,
        int expected)
    {
        Assert.Equal(
            expected,
            PrivateChatRosterRules.ScrollTo(startIndex, rowIndex, totalCount: 50, visibleCapacity: 10));
    }

    /// <summary>
    /// 「随着游戏中遇到 NPC 解锁」这条口径的钉子：名单建立在
    /// <see cref="KnownNpcResolver"/> 的解析结果上，而那份解析的输入就是存档里的
    /// 好感度记录——星露谷只在玩家真正跟某位村民说上话之后才建立记录。
    /// 将来若有人把名单换成「全部村民」之类的来源，这条测试会立刻报出来。
    /// </summary>
    [Fact]
    public void Roster_is_limited_to_npcs_the_player_has_already_met()
    {
        var friendshipKeys = new[]
        {
            "Abigail",
            "player",
            TestNpcPlacementRules.InternalName,
        };
        var known = KnownNpcResolver.Resolve(
            friendshipKeys,
            npcId => new KnownNpc(npcId, $"{npcId} 的显示名"));

        var roster = PrivateChatRosterRules.Build(
            known.Select(npc => new PrivateChatRosterSource(
                npc.NpcId,
                npc.DisplayName,
                IsPresent: false,
                DistanceInTiles: float.MaxValue)));

        Assert.Equal(new[] { "Abigail" }, roster.Select(entry => entry.NpcId));
        Assert.Equal("Abigail 的显示名", roster[0].DisplayName);
    }
}
