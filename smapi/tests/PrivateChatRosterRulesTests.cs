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

    /// <summary>显示名与 ID 不同的行：排序看的是玩家**看到的名字**，不是内部 ID。</summary>
    private static PrivateChatRosterSource Named(string npcId, string displayName)
    {
        return new PrivateChatRosterSource(
            npcId,
            displayName,
            IsPresent: false,
            DistanceInTiles: float.MaxValue);
    }

    private static string StatusOf(
        IReadOnlyList<PrivateChatRosterEntry> roster,
        string npcId)
    {
        return roster.Single(entry => entry.NpcId == npcId).StatusLabel;
    }

    // ── 排序口径：按名字（2026-09-21 用户反馈「排序按首字母排吧」之后定稿） ────────

    /// <summary>
    /// 排序**只看名字**。这条用例特意把「在场／远近」与名字序**反着摆**：
    /// 若哪天有人把「身边 → 同处一地 → 线上」那套分档排回来，它会立刻报出来。
    /// </summary>
    [Fact]
    public void Rows_are_ordered_by_name_rather_than_by_status_or_distance()
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
        // 状态仍在**每一行**上标着：排序变了，玩家点之前照样知道会发生什么。
        Assert.Equal(
            new[] { "身边", "同处一地", "线上", "线上" },
            roster.Select(entry => entry.StatusLabel));
    }

    /// <summary>
    /// 距离与在场**不再挪动任何一行**：同一批人，远近／在场怎么变，名字序都是同一份。
    /// （距离仍然决定「身边」标记与打开时的预选行，那两处各有自己的用例。）
    /// </summary>
    [Fact]
    public void Distance_and_presence_no_longer_move_a_row()
    {
        var allClose = PrivateChatRosterRules.Build(new[]
        {
            Source("Marnie", isPresent: true, distanceInTiles: 0.1f),
            Source("Emily", isPresent: true, distanceInTiles: 0.5f),
        });
        var allFar = PrivateChatRosterRules.Build(new[]
        {
            Source("Marnie", isPresent: true, distanceInTiles: float.NaN),
            Source("Emily", isPresent: false, distanceInTiles: float.MaxValue),
        });

        Assert.Equal(new[] { "Emily", "Marnie" }, allClose.Select(entry => entry.NpcId));
        // 距离取不到（NaN）的人也一样按名字排，不再被挪到列表末尾。
        Assert.Equal(new[] { "Emily", "Marnie" }, allFar.Select(entry => entry.NpcId));
        Assert.Equal("身边", StatusOf(allClose, "Marnie"));
        Assert.Equal("线上", StatusOf(allFar, "Emily"));
    }

    /// <summary>
    /// 中文名字按**拼音**排，而不是按 Unicode 码位排。
    ///
    /// 口径来源：.NET 5+ 在 Windows 上用 ICU，而 ICU 里中文（<c>zh</c>／<c>zh-CN</c>）
    /// 的默认排序规则就是拼音序——项目里没有、也不需要自带一份拼音表。
    /// 这四个人名的**码位序恰好是拼音序的完全倒序**（乔 U+4E54 &lt; 塞 U+585E &lt; 艾 U+827E
    /// &lt; 阿 U+963F），所以这条用例同时钉住了「不是码位序」。
    /// </summary>
    [Fact]
    public void Chinese_names_are_ordered_by_pinyin_rather_than_by_code_point()
    {
        Assert.True(
            PrivateChatRosterRules.UsesPinyinNameOrder,
            "这台机器上的中文排序不是拼音序（取不到 zh-CN 数据，或 ICU 的中文排序数据不全）："
            + "名单里的中文已退化——下面几条断言会跟着失守。");

        var roster = PrivateChatRosterRules.Build(new[]
        {
            Named("Sebastian", "塞巴斯蒂安"),
            Named("George", "乔治"),
            Named("Emily", "艾米丽"),
            Named("Abigail", "阿比盖尔"),
        });

        Assert.Equal(
            new[] { "阿比盖尔", "艾米丽", "乔治", "塞巴斯蒂安" },
            roster.Select(entry => entry.DisplayName));
    }

    /// <summary>
    /// 「首字母」不是**只**比首字母：同一批人的全拼还要接着比下去——
    /// 塞(sai) &lt; 桑(sang) &lt; 山(shan) &lt; 威(wei) &lt; 谢(xie)。
    /// 这正是玩家翻中文名单时预期的顺序。
    /// </summary>
    [Fact]
    public void Names_sharing_an_initial_are_ordered_by_the_full_pinyin_syllable()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Named("Shane", "谢恩"),
            Named("Sam", "山姆"),
            Named("Willy", "威利"),
            Named("Sandy", "桑迪"),
            Named("Sebastian", "塞巴斯蒂安"),
        });

        Assert.Equal(
            new[] { "塞巴斯蒂安", "桑迪", "山姆", "威利", "谢恩" },
            roster.Select(entry => entry.DisplayName));
    }

    /// <summary>
    /// 拉丁字母的名字仍按字母序，且**大小写不敏感**；显示名完全相同时按 ID 兜底——
    /// 同一份输入永远得到同一份顺序，玩家能记住谁在哪一行。
    /// </summary>
    [Fact]
    public void Latin_names_stay_alphabetical_and_ties_fall_back_to_the_npc_id()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Named("Emily", "emily"),
            Named("Abigail", "Emily"),
            Named("Pierre", "Pierre"),
        });

        // 「Emily」与「emily」名字序相等 → 按 ID 兜底：Abigail 在前。
        Assert.Equal(
            new[] { "Abigail", "Emily", "Pierre" },
            roster.Select(entry => entry.NpcId));
    }

    /// <summary>
    /// 中英混排的边界：两种文字**各自内部仍然有序**。它不钉「谁在前谁在后」——
    /// 跨文字的先后由 ICU 的中文排序规则决定（实测汉字在前、拉丁在后），
    /// 名单里绝大多数是中文名，这条只在装了英文名 NPC 的 mod 存档里看得见。
    /// </summary>
    [Fact]
    public void Chinese_and_latin_names_keep_their_own_order_when_mixed()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Named("Rasmodia", "Rasmodia"),
            Named("Emily", "艾米丽"),
            Named("Abigail", "阿比盖尔"),
            Named("Marnie", "Marnie"),
        });

        var names = roster.Select(entry => entry.DisplayName).ToArray();

        Assert.Equal(
            new[] { "阿比盖尔", "艾米丽" },
            names.Where(name => name is "阿比盖尔" or "艾米丽"));
        Assert.Equal(
            new[] { "Marnie", "Rasmodia" },
            names.Where(name => name is "Marnie" or "Rasmodia"));
    }

    /// <summary>
    /// 兜底口径本身也可查：拿不到中文排序数据时给的是**序数比较**——顺序依旧稳定，
    /// 只是中文退化成码位序（这正是「退化」的含义，不是我们想要的名单顺序）。
    /// 真机上这条分支取不到（ICU 在），所以它必须能被单独钉住。
    /// </summary>
    [Fact]
    public void Missing_culture_data_falls_back_to_an_ordinal_comparer()
    {
        var comparer = PrivateChatRosterRules.CreateNameOrderComparer(null);

        Assert.Equal(0, comparer.Compare("Emily", "emily"));
        Assert.True(comparer.Compare("Abigail", "Emily") < 0);
        Assert.True(comparer.Compare("乔治", "阿比盖尔") < 0);
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

        // 排序改成按名字之后，状态不再决定行序，所以这里**按 ID 点名取状态**，
        // 不再依赖「谁排在第几行」——三种状态各钉一条。
        Assert.Equal("身边", StatusOf(roster, "Abigail"));
        Assert.Equal("同处一地", StatusOf(roster, "Emily"));
        Assert.Equal("线上", StatusOf(roster, "Pierre"));
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
