using System.Collections;
using System.Globalization;
using System.Reflection;
using System.Text.Json.Serialization;
using StardewValley;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

public sealed class NpcGameState
{
    [JsonPropertyName("npcId")]
    public string? NpcId { get; init; }

    [JsonPropertyName("displayName")]
    public string? DisplayName { get; init; }

    [JsonPropertyName("gender")]
    public string? Gender { get; init; }

    [JsonPropertyName("location")]
    public string? Location { get; init; }

    [JsonPropertyName("season")]
    public string? Season { get; init; }

    [JsonPropertyName("date")]
    public string? Date { get; init; }

    [JsonPropertyName("weather")]
    public string? Weather { get; init; }

    [JsonPropertyName("time")]
    public int? Time { get; init; }

    [JsonPropertyName("friendship")]
    public int? Friendship { get; init; }

    [JsonPropertyName("friendshipHearts")]
    public int? FriendshipHearts { get; init; }

    [JsonPropertyName("relationship")]
    public string? Relationship { get; init; }

    [JsonPropertyName("marriageStatus")]
    public string? MarriageStatus { get; init; }

    [JsonPropertyName("childrenCount")]
    public int? ChildrenCount { get; init; }

    /// <summary>
    /// 这个 NPC 是否与玩家同住（配偶或室友）。
    /// </summary>
    /// <remarks>
    /// **语义边界（务必按注释使用）**：它回答的是「**住处**」，不是「**行踪**」。
    /// 星露谷里配偶 NPC 白天照样按自己的日程外出上班、开店、钓鱼，只在夜里回屋；
    /// 因此这个标记**不能**被下游解读成「他/她此刻在家」，也**不能**用来推断
    /// 「刚从家里出来」。Bridge 侧的 <c>daily_context</c> 卡就是按这个口径写
    /// instruction 的。
    /// <para>
    /// 三态：<c>true</c> = 同住、<c>false</c> = 玩家已婚/有室友但不是这个 NPC、
    /// <c>null</c> = 读不到 <c>Game1.player.spouse</c>（未知，不要当成 false）。
    /// </para>
    /// </remarks>
    [JsonPropertyName("livesWithPlayer")]
    public bool? LivesWithPlayer { get; init; }

    /// <summary>
    /// 今日日程的投影（时刻 + 已本地化地点名），取不到时为**空列表**。
    /// </summary>
    /// <remarks>
    /// 这是**快照**：它在请求发出的那一刻从 <c>NPC.Schedule</c> 读出，
    /// 而游戏里的日程会因天气、节日、事件和自定义 NPC 的延迟加载而变。
    /// Bridge 侧会把它再压成 2–3 条「今日安排」；压缩失败或数据为空时
    /// 那张卡根本不出现——失效方向是「退化成没有日程」，不是「给出错的地点」。
    /// </remarks>
    [JsonPropertyName("todaySchedule")]
    public IReadOnlyList<TodayScheduleEntry> TodaySchedule { get; init; } =
        Array.Empty<TodayScheduleEntry>();

    [JsonPropertyName("completedEventIds")]
    public IReadOnlyList<string> CompletedEventIds { get; init; } = Array.Empty<string>();

    [JsonPropertyName("sourceMods")]
    public IReadOnlyList<string> SourceMods { get; init; } = Array.Empty<string>();

    /// <summary>
    /// **玩家的**性别（<c>Male</c> / <c>Female</c>），读不到时为 <c>null</c>。
    /// </summary>
    /// <remarks>
    /// <para>
    /// ⚠ **这是本 DTO 里唯一的玩家字段** —— 其余每个字段都是「关于这个 NPC 的」。
    /// 往这里继续堆玩家信息之前，先考虑是不是该另起一个容器（例如
    /// <c>PlayerContext</c>），别让 <c>NpcGameState</c> 慢慢变成一个「场景快照」。
    /// </para>
    /// <para>
    /// **唯一用途是称呼**：Bridge 侧把它渲染进 <c>mod_overlay</c> 卡、紧挨
    /// <c>addressing</c>，让「按玩家性别：男「小伙子」，女「小姑娘」」这个条件有依据。
    /// 它**不参与任何门控、分支或检索**，也不要拿它去推断别的玩家属性。
    /// </para>
    /// <para>
    /// ⚠ **发布顺序**：Bridge 侧的 <c>ApiModel</c> 是 <c>extra="forbid"</c>，
    /// 所以「新 DLL + 旧 Bridge」会 **422 → 退化成兜底回复**。**必须先发 Bridge、再发 DLL**。
    /// （反方向安全：旧 DLL 不发这个字段时 Bridge 收到 <c>null</c>，与今天的行为一致。）
    /// </para>
    /// </remarks>
    [JsonPropertyName("playerGender")]
    public string? PlayerGender { get; init; }

    [JsonPropertyName("warnings")]
    public IReadOnlyList<string> Warnings { get; init; } = Array.Empty<string>();
}

public sealed record RuntimeNpcState(
    string? NpcId,
    string? DisplayName,
    string? Gender,
    string? Location,
    int? Friendship,
    string? Relationship);

public sealed record RuntimeStoryState(
    string? MarriageStatus = null,
    int? ChildrenCount = null,
    IReadOnlyList<string>? CompletedEventIds = null,
    bool? LivesWithPlayer = null,
    IReadOnlyList<TodayScheduleEntry>? TodaySchedule = null);

public sealed record RuntimeWorldState(
    string? Season,
    int? Day,
    bool? IsRaining,
    int? Time);

public interface IModRegistryStatus
{
    bool IsLoaded(string uniqueId);
}

public static class GameStateCollector
{
    /// <summary>
    /// 发往 Bridge 的 <c>completedEventIds</c> 上限。
    /// </summary>
    /// <remarks>
    /// 事件链门控（Bridge 侧 <c>resolve_relationship_gate</c>）要求「已完成的全部事件」，
    /// 截断会让门控把已完成的事件误判成未完成，从而把已婚等既成关系压回 <c>acquaintance</c>
    /// （2026-09-21：用户存档 391 条被截到 128 条，7 个配了事件门的角色里 6 个被压级）。
    /// 因此这里只做防御性上限、不再承担业务语义；512 覆盖正常存档（含 SVE 等大型扩展）的
    /// 事件总量，Bridge 侧 <c>NpcGameState.completed_event_ids</c> 的上限必须与此保持一致，
    /// 否则超出部分会被 422 拒绝（<c>extra="forbid"</c> + 长度校验）。
    /// </remarks>
    public const int MaxCompletedEventIds = 512;

    /// <summary>
    /// 读玩家已完成的事件 id（`player.eventsSeen`），供跨天差异计算用（2026-09-27）。
    ///
    /// 与 <see cref="Collect"/> 那条读法共用同一套规则（反射 + 规范化 + 同一个上限），
    /// 并且**故意只留这一个入口** —— 两处各自读的话，上限或规范化一旦漂移，
    /// 就会出现「审计认为新、上报认为旧」这种查不出来的静默错位。
    ///
    /// ⚠ 必须在主线程调用：它碰了 `Game1`。`DayStarted` 里要在第一个 `await`
    /// **之前**取好（见 <c>ModEntry.AnnounceMorningMessagesAsync</c>）。
    /// </summary>
    public static IReadOnlyList<string> ReadSeenEventIds()
    {
        return ReadEnumerableStrings(
            ReadMember(Game1.player, "eventsSeen"),
            maxCount: MaxCompletedEventIds);
    }

    private static readonly IModRegistryStatus EmptyModRegistry = new EmptyModRegistryStatus();
    private static IModRegistryStatus modRegistry = EmptyModRegistry;

    private static readonly (string Marker, string[] UniqueIds)[] ModFamilies =
    {
        (
            "SVE",
            new[]
            {
                "FlashShifter.SVECode",
                "FlashShifter.StardewValleyExpandedCP",
                "FlashShifter.SVE-FTM",
            }),
        (
            "female-bachelors",
            new[]
            {
                "Invatorzen.idcsm",
                "female.bachelors.beach",
                "female.bachelors.winter",
            }),
        (
            "Romanceable Rasmodius",
            new[]
            {
                "Nom0ri.RomRas",
                "Parrot.RomRas",
                "Dacar.SeasRomRasmodia",
            }),
    };

    public static void ConfigureModRegistry(IModRegistryStatus registry)
    {
        modRegistry = registry ?? EmptyModRegistry;
    }

    public static NpcGameState Collect(StardewNpc? npc)
    {
        if (npc is null)
        {
            return Empty("NPC unavailable");
        }

        var warnings = new List<string>();
        var npcId = ReadString(npc, "Name", warnings, "npcId");
        var displayName = ReadString(npc, "displayName", warnings, "displayName");
        var gender = ReadString(npc, "Gender", warnings, "gender");
        var locationObject = ReadMember(npc, "currentLocation");
        var location = ReadString(locationObject, "NameOrUniqueName") ??
                       ReadString(locationObject, "Name");
        if (location is null)
        {
            warnings.Add("location unavailable");
        }

        var season = ReadStaticString("currentSeason");
        if (season is null)
        {
            warnings.Add("season unavailable");
        }

        var day = ReadStaticInt("dayOfMonth");
        if (day is null)
        {
            warnings.Add("date unavailable");
        }

        var isRaining = ReadStaticBool("isRaining");
        var weather = isRaining.HasValue ? (isRaining.Value ? "rain" : "clear") : null;
        if (weather is null)
        {
            warnings.Add("weather unavailable");
        }
        var time = ReadStaticInt("timeOfDay");
        if (time is null)
        {
            warnings.Add("time unavailable");
        }

        var (friendship, relationship) = ReadFriendship(npcId);
        if (friendship is null)
        {
            warnings.Add("friendship unavailable");
        }

        var state = Collect(
            new RuntimeNpcState(npcId, displayName, gender, location, friendship, relationship),
            new RuntimeWorldState(season, day, isRaining, time),
            modRegistry,
            ReadRuntimeStoryState(npcId, relationship, npc));

        return new NpcGameState
        {
            NpcId = state.NpcId,
            DisplayName = state.DisplayName,
            Gender = state.Gender,
            // 玩家性别**刻意不走 `RuntimeNpcState`**：那个 record 的每个成员都是
            // 「关于这个 NPC 的」，把玩家字段塞进去会污染它的语义，也会让纯函数重载
            // （`Collect(RuntimeNpcState, ...)` 的测试契约）多出一个不该有的入参。
            // 它只在终点对象上补一次，见 `NpcGameState.PlayerGender` 的 remarks。
            PlayerGender = ReadString(Game1.player, "Gender", warnings, "playerGender"),
            Location = state.Location,
            Season = state.Season,
            Date = state.Date,
            Weather = state.Weather,
            Time = state.Time,
            Friendship = state.Friendship,
            FriendshipHearts = state.FriendshipHearts,
            Relationship = state.Relationship,
            MarriageStatus = state.MarriageStatus,
            ChildrenCount = state.ChildrenCount,
            LivesWithPlayer = state.LivesWithPlayer,
            TodaySchedule = state.TodaySchedule,
            CompletedEventIds = state.CompletedEventIds,
            SourceMods = state.SourceMods,
            Warnings = warnings.Concat(state.Warnings).Distinct().ToArray(),
        };
    }

    public static NpcGameState Collect(
        RuntimeNpcState npc,
        RuntimeWorldState world,
        IModRegistryStatus registry,
        RuntimeStoryState? story = null)
    {
        var warnings = new List<string>();
        var normalizedStory = NormalizeStoryState(story, npc.Relationship);
        AddWarningWhenMissing(npc.NpcId, warnings, "npcId");
        AddWarningWhenMissing(npc.DisplayName, warnings, "displayName");
        AddWarningWhenMissing(npc.Gender, warnings, "gender");
        AddWarningWhenMissing(npc.Location, warnings, "location");
        AddWarningWhenMissing(world.Season, warnings, "season");
        if (!world.Day.HasValue)
        {
            warnings.Add("date unavailable");
        }

        var weather = world.IsRaining.HasValue
            ? world.IsRaining.Value ? "rain" : "clear"
            : null;
        if (weather is null)
        {
            warnings.Add("weather unavailable");
        }

        if (!world.Time.HasValue)
        {
            warnings.Add("time unavailable");
        }

        if (!npc.Friendship.HasValue)
        {
            warnings.Add("friendship unavailable");
        }

        return new NpcGameState
        {
            NpcId = npc.NpcId,
            DisplayName = npc.DisplayName,
            Gender = npc.Gender,
            Location = npc.Location,
            Season = world.Season,
            Date = world.Day?.ToString(CultureInfo.InvariantCulture),
            Weather = weather,
            Time = world.Time,
            Friendship = npc.Friendship,
            FriendshipHearts = ToFriendshipHearts(npc.Friendship),
            Relationship = npc.Relationship,
            MarriageStatus = normalizedStory.MarriageStatus,
            ChildrenCount = normalizedStory.ChildrenCount,
            LivesWithPlayer = normalizedStory.LivesWithPlayer,
            TodaySchedule = normalizedStory.TodaySchedule ?? Array.Empty<TodayScheduleEntry>(),
            CompletedEventIds = normalizedStory.CompletedEventIds ?? Array.Empty<string>(),
            SourceMods = DetectSourceMods(registry, warnings),
            Warnings = warnings,
        };
    }

    private static NpcGameState Empty(string warning)
    {
        return new NpcGameState { Warnings = new[] { warning } };
    }

    private static string? ReadString(object? source, string memberName)
    {
        try
        {
            return ReadMember(source, memberName)?.ToString();
        }
        catch
        {
            return null;
        }
    }

    private static string? ReadString(
        object source,
        string memberName,
        ICollection<string> warnings,
        string label)
    {
        var value = ReadString(source, memberName);
        if (value is null)
        {
            warnings.Add($"{label} unavailable");
        }

        return value;
    }

    private static object? ReadStatic(string memberName)
    {
        try
        {
            var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;
            var property = typeof(Game1).GetProperty(memberName, flags);
            if (property is not null)
            {
                return property.GetValue(null);
            }

            return typeof(Game1).GetField(memberName, flags)?.GetValue(null);
        }
        catch
        {
            return null;
        }
    }

    private static object? ReadMember(object? source, string memberName)
    {
        if (source is null)
        {
            return null;
        }

        try
        {
            var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            var type = source.GetType();
            var property = type.GetProperty(memberName, flags);
            if (property is not null)
            {
                return property.GetValue(source);
            }

            return type.GetField(memberName, flags)?.GetValue(source);
        }
        catch
        {
            return null;
        }
    }

    private static object? ReadMethod(object? source, string methodName)
    {
        if (source is null)
        {
            return null;
        }

        try
        {
            var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            var method = source.GetType().GetMethod(methodName, flags, Type.EmptyTypes);
            return method?.Invoke(source, null);
        }
        catch
        {
            return null;
        }
    }

    private static string? ReadStaticString(string memberName)
    {
        return ReadStatic(memberName)?.ToString();
    }

    private static int? ReadStaticInt(string memberName)
    {
        var value = ReadStatic(memberName);
        try
        {
            return value is null ? null : Convert.ToInt32(value, CultureInfo.InvariantCulture);
        }
        catch
        {
            return null;
        }
    }

    private static bool? ReadStaticBool(string memberName)
    {
        var value = ReadStatic(memberName);
        try
        {
            return value is null ? null : Convert.ToBoolean(value, CultureInfo.InvariantCulture);
        }
        catch
        {
            return null;
        }
    }

    private static (int? Friendship, string? Relationship) ReadFriendship(string? npcId)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(npcId))
            {
                return (null, null);
            }

            var data = ReadMember(Game1.player, "friendshipData");
            if (!FriendshipDataAccessor.TryGetValue(data, npcId, out var friendship))
            {
                return (null, null);
            }

            var points = ReadMember(friendship, "Points");
            var status = ReadString(friendship, "Status");
            return (
                points is null ? null : Convert.ToInt32(points, CultureInfo.InvariantCulture),
                status);
        }
        catch
        {
            return (null, null);
        }
    }

    private static RuntimeStoryState ReadRuntimeStoryState(
        string? npcId,
        string? relationship,
        object? npc = null)
    {
        var marriageStatus = DeriveMarriageStatus(relationship);
        var spouse = ReadString(Game1.player, "spouse");
        // L2a：这个布尔此前被算出来又直接丢掉（只拿它决定要不要数孩子）。
        // 三态语义见 `NpcGameState.LivesWithPlayer`：读不到 spouse 才是 null。
        // **它只代表住处**——配偶 NPC 白天照样按日程外出，不能当行踪用。
        var livesWithPlayer = spouse is null
            ? (bool?)null
            : string.Equals(spouse, npcId, StringComparison.OrdinalIgnoreCase);
        var childrenCount = livesWithPlayer == true
            ? ReadChildrenCount()
            : null;
        var completedEventIds = ReadSeenEventIds();

        return new RuntimeStoryState(
            marriageStatus,
            childrenCount,
            completedEventIds,
            livesWithPlayer,
            // L2b：当日日程快照。取不到时是空列表，Bridge 侧据此不发卡。
            ReadTodaySchedule(npc));
    }

    private static RuntimeStoryState NormalizeStoryState(
        RuntimeStoryState? story,
        string? relationship)
    {
        var marriageStatus = story?.MarriageStatus;
        if (string.IsNullOrWhiteSpace(marriageStatus))
        {
            marriageStatus = DeriveMarriageStatus(relationship);
        }

        var childrenCount = story?.ChildrenCount;
        if (childrenCount is < 0)
        {
            childrenCount = null;
        }

        return new RuntimeStoryState(
            string.IsNullOrWhiteSpace(marriageStatus) ? null : marriageStatus.Trim(),
            childrenCount,
            NormalizeEventIds(story?.CompletedEventIds),
            story?.LivesWithPlayer,
            NormalizeSchedule(story?.TodaySchedule));
    }

    /// <summary>
    /// 日程条目的防御性规范化：调用方可能绕开 <see cref="TodayScheduleRules.Project"/>
    /// 直接塞数据进来（测试、视觉 harness、将来别的采集路径）。
    /// </summary>
    private static IReadOnlyList<TodayScheduleEntry> NormalizeSchedule(
        IReadOnlyList<TodayScheduleEntry>? entries)
    {
        if (entries is null || entries.Count == 0)
        {
            return Array.Empty<TodayScheduleEntry>();
        }

        var result = new List<TodayScheduleEntry>();
        foreach (var entry in entries)
        {
            if (entry is null || !TodayScheduleRules.IsValidTime(entry.Time))
            {
                continue;
            }

            var location = entry.Location?.Trim();
            if (string.IsNullOrEmpty(location))
            {
                continue;
            }

            if (location.Length > TodayScheduleRules.MaxLocationLength)
            {
                location = location[..TodayScheduleRules.MaxLocationLength];
            }

            result.Add(new TodayScheduleEntry(entry.Time, location));
            if (result.Count >= TodayScheduleRules.MaxEntries)
            {
                break;
            }
        }

        return result;
    }

    private static string? DeriveMarriageStatus(string? relationship)
    {
        if (string.IsNullOrWhiteSpace(relationship))
        {
            return null;
        }

        var normalized = relationship.Trim().ToLowerInvariant();
        return normalized switch
        {
            "married" or "roommate" or "dating" or "divorced" => normalized,
            _ => null,
        };
    }

    private static int? ToFriendshipHearts(int? friendship)
    {
        return friendship.HasValue
            ? Math.Clamp(friendship.Value / 250, 0, 14)
            : null;
    }

    private static int? ReadChildrenCount()
    {
        var children = ReadMethod(Game1.player, "getChildren") ??
                       ReadMember(Game1.player, "children");
        if (children is not IEnumerable values)
        {
            return null;
        }

        var count = 0;
        foreach (var _ in values)
        {
            count++;
        }

        return Math.Max(0, count);
    }

    /// <summary>
    /// <c>SchedulePathDescription</c> 里目标地点名的候选成员名。
    /// </summary>
    /// <remarks>
    /// **成员名跨版本不同**：1.6.15 实测是 <c>targetLocationName</c>
    /// （<c>StardewValley.Pathfinding.SchedulePathDescription</c> 的字段），
    /// 而文档与旧版本写作 <c>targetLocation</c>。这里按候选顺序取第一个非空值，
    /// 全都取不到就丢掉这一条日程——宁可少一段安排，也不要发一个空地点。
    /// </remarks>
    private static readonly string[] ScheduleLocationMembers =
    {
        "targetLocationName",
        "targetLocation",
    };

    /// <summary>
    /// 读取 <c>NPC.Schedule</c>（当天已解析好的日程表）并投影成待外发条目。
    /// </summary>
    /// <remarks>
    /// <para>
    /// **为什么读运行时对象、而不是自己解析 <c>Characters/schedules/*</c>**：
    /// 当天用哪一条日程取决于季节、星期、日期、天气、节日、好感与事件
    /// （<c>NOT friendship Sebastian 6</c> 这类条件），还有 <c>GOTO</c> 跳转和
    /// <c>bed</c>（回家）这种需要 NPC 上下文的写法。游戏已经把当天那条解析进
    /// <c>NPC.Schedule</c>，在外面重做一遍只会得到错的答案。
    /// </para>
    /// <para>
    /// **降级**：SVE 等自定义 NPC 可能当天晚些才 <c>TryLoadSchedule</c>，
    /// 此时 <c>Schedule</c> 是 null 或空字典 → 返回空列表 → Bridge 侧不发卡。
    /// 任何异常同样返回空列表：失效方向是「没有日程」，不是「错的日程」。
    /// </para>
    /// </remarks>
    private static IReadOnlyList<TodayScheduleEntry> ReadTodaySchedule(object? npc)
    {
        try
        {
            if (npc is null || ReadMember(npc, "Schedule") is not IEnumerable pairs)
            {
                return Array.Empty<TodayScheduleEntry>();
            }

            var raw = new List<KeyValuePair<int, string?>>();
            foreach (var pair in pairs)
            {
                var key = ReadMember(pair, "Key");
                var value = ReadMember(pair, "Value");
                if (key is null || value is null)
                {
                    continue;
                }

                int time;
                try
                {
                    time = Convert.ToInt32(key, CultureInfo.InvariantCulture);
                }
                catch
                {
                    continue;
                }

                raw.Add(
                    new KeyValuePair<int, string?>(
                        time,
                        ReadScheduleLocationName(value)));
            }

            return TodayScheduleRules.Project(raw, LocalizeLocationName);
        }
        catch
        {
            return Array.Empty<TodayScheduleEntry>();
        }
    }

    private static string? ReadScheduleLocationName(object? description)
    {
        foreach (var memberName in ScheduleLocationMembers)
        {
            // `bed`（回家睡觉）由 `NormalizeLocationName` 换成语义标记 `home`，
            // Bridge 侧渲染成「家」。见 `TodayScheduleRules.HomeLocationMarker`。
            var value = TodayScheduleRules.NormalizeLocationName(
                ReadString(description, memberName));
            if (!string.IsNullOrEmpty(value))
            {
                return value;
            }
        }

        return null;
    }

    /// <summary>
    /// 地点标识符 → 游戏内显示名（<c>Town</c> → 「鹈鹕镇」）。
    /// </summary>
    /// <remarks>
    /// 取不到时返回 null，交给 <see cref="TodayScheduleRules.Project"/> 回退到
    /// 标识符本身。未解析的本地化 token（<c>Strings\Locations:Town</c>）比标识符
    /// 更难读，按「取不到」处理，而不是把 token 当地点名发出去。
    /// </remarks>
    private static string? LocalizeLocationName(string name)
    {
        // 语义标记（`home`）不是地图名：查不到也不该查，直接走回退。
        if (string.Equals(
                name,
                TodayScheduleRules.HomeLocationMarker,
                StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        try
        {
            var location = Game1.getLocationFromName(name);
            var display = ReadString(location, "DisplayName")?.Trim();
            if (string.IsNullOrEmpty(display))
            {
                return null;
            }

            if (display.StartsWith("Strings\\", StringComparison.Ordinal) ||
                display.StartsWith("Strings/", StringComparison.Ordinal))
            {
                return null;
            }

            return display;
        }
        catch
        {
            return null;
        }
    }

    private static IReadOnlyList<string> ReadEnumerableStrings(
        object? source,
        int maxCount)
    {
        if (source is not IEnumerable values)
        {
            return Array.Empty<string>();
        }

        var result = new List<string>();
        foreach (var value in values)
        {
            var text = value?.ToString()?.Trim();
            if (string.IsNullOrWhiteSpace(text) || result.Contains(text, StringComparer.Ordinal))
            {
                continue;
            }

            result.Add(text);
            if (result.Count >= maxCount)
            {
                break;
            }
        }

        return result;
    }

    private static IReadOnlyList<string> NormalizeEventIds(
        IReadOnlyList<string>? eventIds)
    {
        if (eventIds is null || eventIds.Count == 0)
        {
            return Array.Empty<string>();
        }

        return eventIds
            .Where(id => !string.IsNullOrWhiteSpace(id))
            .Select(id => id.Trim())
            .Distinct(StringComparer.Ordinal)
            .Take(MaxCompletedEventIds)
            .ToArray();
    }

    private static IReadOnlyList<string> DetectSourceMods(
        IModRegistryStatus? registry,
        ICollection<string> warnings)
    {
        var sourceMods = new List<string>();
        foreach (var family in ModFamilies)
        {
            var familyLoaded = false;
            foreach (var uniqueId in family.UniqueIds)
            {
                bool loaded;
                try
                {
                    loaded = registry?.IsLoaded(uniqueId) == true;
                }
                catch
                {
                    loaded = false;
                    warnings.Add($"mod registry unavailable: {uniqueId}");
                }

                if (!loaded)
                {
                    continue;
                }

                if (!familyLoaded)
                {
                    sourceMods.Add(family.Marker);
                    familyLoaded = true;
                }

                sourceMods.Add(uniqueId);
            }
        }

        return sourceMods;
    }

    private static void AddWarningWhenMissing(
        string? value,
        ICollection<string> warnings,
        string label)
    {
        if (value is null)
        {
            warnings.Add($"{label} unavailable");
        }
    }

    private sealed class EmptyModRegistryStatus : IModRegistryStatus
    {
        public bool IsLoaded(string uniqueId)
        {
            return false;
        }
    }
}
