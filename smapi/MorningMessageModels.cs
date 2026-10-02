using System.Text.Json.Serialization;

namespace StardewAI.NPC;

/// <summary>
/// 游戏端问 Bridge「今天早上有没有人要主动开口」的请求体。
///
/// ⚠ **字段必须与 Bridge 侧的 <c>MorningPlanRequest</c> 逐一对应**：
/// 那边是 <c>extra="forbid"</c>，多送一个字段就是 422，而 422 在这条路径上的
/// 表现是「今天没人发消息」——不报错、不 crash，只是功能静默消失。
/// 所以**不要**顺手往这里加 gameState／好感度／关系阶段。
/// </summary>
public sealed class MorningPlanRequest
{
    /// <summary>绝对天数（<c>Game1.Date.TotalDays</c>）。预设按天索引。</summary>
    [JsonPropertyName("dayIndex")]
    public int DayIndex { get; init; }

    /// <summary>
    /// 玩家已经认识的人（与 F8 名册同源）。当前只用于将来的轮转候选池；
    /// 节点预设不看它——节点是写死的调度，玩家没见过也该照发。
    /// </summary>
    [JsonPropertyName("knownNpcIds")]
    public IReadOnlyList<string> KnownNpcIds { get; init; } = Array.Empty<string>();

    /// <summary>
    /// **昨天**刚完成的剧情事件 id（2026-09-27），用于「事件后」预设。
    ///
    /// ⚠ **只送昨天那一批。** Bridge 那边无从判断新旧：`completedEventIds` 是
    /// 累积全集、不含完成时间，所以「是不是昨天」这个判断只能在游戏端做
    /// （<see cref="RecentEventTracker"/> + `DayStarted`）。送多了的后果是
    /// 一件三个月前的事被 NPC 当成刚发生的事来提。
    ///
    /// ⚠ 事件 ID **大小写敏感**，与 NPC ID 忽略大小写的规则相反。
    ///
    /// 这个字段与本类上面那条「不要顺手加 gameState／好感度」的警告不冲突：
    /// 那些是**上下文**，而这个和 <see cref="KnownNpcIds"/> 一样，是
    /// 「今天该由谁开口」这个决策**本身的输入**。
    /// </summary>
    [JsonPropertyName("recentEventIds")]
    public IReadOnlyList<string> RecentEventIds { get; init; } = Array.Empty<string>();
}

/// <summary>一条「今天该由谁开口、说什么」。</summary>
public sealed class MorningMessagePlan
{
    [JsonPropertyName("npcId")]
    public string NpcId { get; init; } = string.Empty;

    [JsonPropertyName("displayName")]
    public string DisplayName { get; init; } = string.Empty;

    /// <summary>预设的标识（如 <c>day2-lewis</c>）；写日志用，不参与判定。</summary>
    [JsonPropertyName("scenarioId")]
    public string ScenarioId { get; init; } = string.Empty;

    /// <summary>
    /// **已经写好的一句话**，游戏端拿到直接写进聊天记录，不经过模型。
    ///
    /// ⚠ 它必须与 Bridge 侧数据文件里的 <c>opening</c> **逐字一致**：
    /// Bridge 是靠「历史首条 == 某条 opening」认出「这是晨间对话的后续」并注入
    /// 方向约束的。两端一旦漂移，方向约束会**静默失效**——对话照常进行，
    /// 只是少了引导。所以这里**不做任何清洗、截断或改写**。
    /// </summary>
    [JsonPropertyName("opening")]
    public string Opening { get; init; } = string.Empty;
}

/// <summary>Bridge 的回答。没人发消息时 <see cref="Messages"/> 是空数组。</summary>
public sealed class MorningPlanResponse
{
    [JsonPropertyName("messages")]
    public IReadOnlyList<MorningMessagePlan> Messages { get; init; } =
        Array.Empty<MorningMessagePlan>();
}
