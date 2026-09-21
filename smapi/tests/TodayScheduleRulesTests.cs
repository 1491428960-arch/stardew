using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// L2b 当日日程投影规则。
///
/// 三件事分开验：
/// ① **整理**（排序 / 合并 / 去重 / 限长 / 限条数）—— 决定模型看到哪几段；
/// ② **本地化**（`GameLocation.DisplayName` 的委托）—— 取不到时必须回退原名，
///    不能因为本地化失败就整张卡丢掉；
/// ③ **降级**（null / 空 / 脏数据 / 枚举抛异常）—— 方向必须是「没有日程」，
///    不能是「错的日程」，也不能让异常冒到调用方。
/// </summary>
public sealed class TodayScheduleRulesTests
{
    private static KeyValuePair<int, string?> Entry(int time, string? location) =>
        new(time, location);

    private static int[] Times(IReadOnlyList<TodayScheduleEntry> entries) =>
        entries.Select(item => item.Time).ToArray();

    private static string[] Locations(IReadOnlyList<TodayScheduleEntry> entries) =>
        entries.Select(item => item.Location).ToArray();

    // --- 整理 -----------------------------------------------------------------

    [Fact]
    public void Project_sorts_a_dictionary_ordered_schedule()
    {
        // `NPC.Schedule` 是 Dictionary，迭代顺序不保证；游戏内实测出现过
        // 先吐 1900 再吐 900 的情况，直接透传会让「今日安排」倒着讲。
        var result = TodayScheduleRules.Project(new[]
        {
            Entry(1900, "Saloon"),
            Entry(900, "SeedShop"),
            Entry(1300, "Town"),
        });

        Assert.Equal(new[] { 900, 1300, 1900 }, Times(result));
    }

    [Fact]
    public void Project_merges_consecutive_stays_in_the_same_location()
    {
        // `900 葡萄园 / 1200 葡萄园 / 1400 酒窖` 说的是「从 9 点起一直在葡萄园」，
        // 压成两段而不是三段——否则模型会把同一件事讲两遍。
        var result = TodayScheduleRules.Project(new[]
        {
            Entry(900, "葡萄园"),
            Entry(1200, "葡萄园"),
            Entry(1400, "酒窖"),
        });

        Assert.Equal(new[] { 900, 1400 }, Times(result));
        Assert.Equal(new[] { "葡萄园", "酒窖" }, Locations(result));
    }

    [Fact]
    public void Project_keeps_the_first_entry_when_two_share_a_time()
    {
        var result = TodayScheduleRules.Project(new[]
        {
            Entry(900, "SeedShop"),
            Entry(900, "Town"),
        });

        Assert.Equal(new[] { 900 }, Times(result));
        Assert.Equal(new[] { "SeedShop" }, Locations(result));
    }

    [Fact]
    public void Project_does_not_merge_the_same_location_across_a_gap()
    {
        // 中间去别处又回来，是两段真实行程，不能合并。
        var result = TodayScheduleRules.Project(new[]
        {
            Entry(900, "SeedShop"),
            Entry(1200, "Town"),
            Entry(1500, "SeedShop"),
        });

        Assert.Equal(new[] { 900, 1200, 1500 }, Times(result));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-100)]
    [InlineData(599)]
    [InlineData(760)]   // 分钟位非法：星露谷的 timeOfDay 没有 7:60
    [InlineData(2601)]
    [InlineData(9900)]
    public void Project_drops_uninterpretable_times(int invalidTime)
    {
        var result = TodayScheduleRules.Project(new[]
        {
            Entry(invalidTime, "Town"),
            Entry(900, "SeedShop"),
        });

        Assert.Equal(new[] { 900 }, Times(result));
    }

    [Fact]
    public void Project_keeps_the_boundary_times()
    {
        // 600 是清晨开始、2400 是午夜 0:00、2600 是次日 2:00——两端都必须保留，
        // 否则「夜里在哪」这一段会整段消失。
        var result = TodayScheduleRules.Project(new[]
        {
            Entry(600, "Farm"),
            Entry(2400, "SeedShop"),
            Entry(2600, "SeedShop"),
        });

        Assert.Equal(new[] { 600, 2400 }, Times(result));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Project_drops_entries_without_a_location(string? location)
    {
        var result = TodayScheduleRules.Project(new[]
        {
            Entry(900, location),
            Entry(1200, "Town"),
        });

        Assert.Equal(new[] { 1200 }, Times(result));
    }

    [Fact]
    public void Project_trims_location_whitespace()
    {
        var result = TodayScheduleRules.Project(new[] { Entry(900, "  Town  ") });

        Assert.Equal(new[] { "Town" }, Locations(result));
    }

    [Fact]
    public void Project_caps_entries_to_keep_the_request_body_bounded()
    {
        // 整点时刻（600/700/…/2600）全是合法值，共 21 段——异常数据下确有可能。
        var schedule = Enumerable.Range(0, 21)
            .Select(index => Entry(600 + index * 100, $"Loc{index}"))
            .ToArray();

        var result = TodayScheduleRules.Project(schedule);

        Assert.Equal(TodayScheduleRules.MaxEntries, result.Count);
        Assert.Equal(12, TodayScheduleRules.MaxEntries);
    }

    [Fact]
    public void Project_truncates_an_absurd_location_name()
    {
        // 异常数据里出现过整段对白被当成地点名；截断而不是丢弃，
        // 因为这一条至少还是「今天某一时段在某处」。
        var result = TodayScheduleRules.Project(new[]
        {
            Entry(900, new string('长', 200)),
        });

        Assert.Single(result);
        Assert.Equal(TodayScheduleRules.MaxLocationLength, result[0].Location.Length);
    }

    // --- 本地化 ---------------------------------------------------------------

    [Fact]
    public void Project_uses_the_localized_name_when_available()
    {
        var result = TodayScheduleRules.Project(
            new[] { Entry(900, "Town") },
            name => name == "Town" ? "鹈鹕镇" : null);

        Assert.Equal(new[] { "鹈鹕镇" }, Locations(result));
    }

    [Fact]
    public void Project_falls_back_to_the_identifier_when_localization_returns_null()
    {
        // 未加载的自定义地点、未解析的 `Strings\Locations:` token 都走这条路：
        // 给标识符（`Town`）比给一个空地点或整条丢掉更有用。
        var result = TodayScheduleRules.Project(
            new[] { Entry(900, "Town") },
            _ => null);

        Assert.Equal(new[] { "Town" }, Locations(result));
    }

    [Fact]
    public void Project_survives_a_throwing_localizer()
    {
        // 本地化是游戏侧调用（`Game1.getLocationFromName`），自定义内容下有真实的
        // 抛异常可能；它不该把整张日程卡带走，也不该冒到调用方。
        var result = TodayScheduleRules.Project(
            new[] { Entry(900, "Town"), Entry(1400, "Farm") },
            _ => throw new InvalidOperationException("boom"));

        Assert.Equal(new[] { "Town", "Farm" }, Locations(result));
    }

    [Fact]
    public void Project_without_a_localizer_keeps_identifiers()
    {
        var result = TodayScheduleRules.Project(new[] { Entry(900, "Town") });

        Assert.Equal(new[] { "Town" }, Locations(result));
    }

    // --- `bed` → 语义标记 -----------------------------------------------------

    [Theory]
    [InlineData("bed", "home")]
    [InlineData("BED", "home")]
    [InlineData(" bed ", "home")]
    [InlineData("Town", "Town")]
    [InlineData(" 葡萄园 ", "葡萄园")]
    [InlineData(null, null)]
    [InlineData("", null)]
    [InlineData("   ", null)]
    public void NormalizeLocationName_maps_bed_to_the_home_marker(
        string? raw,
        string? expected)
    {
        // `bed` 是「回家睡觉」，语义由游戏数据确定——转成标记是翻译不是猜测。
        // 离线实测：婚姻日程里 `bed` 占 11/21，所以这是「配偶的一天」的主干路径。
        Assert.Equal(expected, TodayScheduleRules.NormalizeLocationName(raw));
    }

    [Fact]
    public void Project_passes_the_home_marker_through_untouched()
    {
        var result = TodayScheduleRules.Project(
            new[] { Entry(2100, TodayScheduleRules.HomeLocationMarker) },
            name => name == "Town" ? "鹈鹕镇" : null);

        Assert.Equal(new[] { "home" }, Locations(result));
    }

    // --- 降级路径 -------------------------------------------------------------

    [Fact]
    public void Project_returns_empty_for_null_or_empty_schedule()
    {
        Assert.Empty(TodayScheduleRules.Project(null));
        Assert.Empty(TodayScheduleRules.Project(Array.Empty<KeyValuePair<int, string?>>()));
    }

    [Fact]
    public void Project_returns_empty_when_every_entry_is_unusable()
    {
        // 全部不合法 → 空列表 → Bridge 侧不发卡（退化成「今天还没定下安排」），
        // 而不是发一张只有标题的空卡。
        var result = TodayScheduleRules.Project(new[]
        {
            Entry(0, "Town"),
            Entry(760, "Farm"),
            Entry(900, null),
            Entry(1200, "  "),
        });

        Assert.Empty(result);
    }

    [Fact]
    public void Project_returns_empty_when_enumeration_throws()
    {
        // 自定义 NPC 的惰性集合可能在枚举中途抛异常。这里用迭代器模拟。
        static IEnumerable<KeyValuePair<int, string?>> Throwing()
        {
            yield return Entry(900, "Town");
            throw new InvalidOperationException("lazy schedule failed");
        }

        Assert.Empty(TodayScheduleRules.Project(Throwing()));
    }

    [Fact]
    public void Project_never_throws_on_hostile_input()
    {
        var result = TodayScheduleRules.Project(new[]
        {
            Entry(int.MinValue, "Town"),
            Entry(int.MaxValue, "Town"),
            Entry(900, "\u0000\u0001"),
        });

        Assert.NotNull(result);
    }

    // --- 时刻判定与 Bridge 侧同尺子 -------------------------------------------

    [Theory]
    [InlineData(600, true)]
    [InlineData(1250, true)]
    [InlineData(2400, true)]
    [InlineData(2600, true)]
    [InlineData(599, false)]
    [InlineData(2601, false)]
    [InlineData(760, false)]
    [InlineData(0, false)]
    public void IsValidTime_matches_the_bridge_range(int time, bool expected)
    {
        // 契约：Bridge 侧 `scene.py::time_of_day_label` 用同一把尺子
        // （600–2600 且分钟位 ≤ 59）。两边不同步会让「合法的被丢掉」或
        // 「非法的进了 prompt」，所以这里把边界钉住。
        Assert.Equal(expected, TodayScheduleRules.IsValidTime(time));
    }
}
