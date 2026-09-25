using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace StardewAI.NPC;

public sealed class BridgeDialogueRequest
{
    [JsonPropertyName("npcId")]
    public string NpcId { get; init; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;

    [JsonPropertyName("intent")]
    public string Intent { get; init; } = ConversationIntent.Chat;

    // 2026-09-20（语义层审计 #46）：这里默认 true，而 Bridge 侧
    // DialogueTestRequest.compactPrompt 默认 false——**两处不同是刻意的**：
    // 游戏端默认紧凑（线上省 token），Bridge 的默认值服务评测与脚本（评质量需要
    // 完整 gameState）。两个默认值从不同时生效，因为本字段总是显式发送。
    // 不要为了「看起来一致」改这里；护栏用例见
    // bridge/tests/test_cross_language_constants.py。
    [JsonPropertyName("compactPrompt")]
    public bool CompactPrompt { get; init; } = true;

    [JsonPropertyName("itemContext")]
    public ItemConversationContext? ItemContext { get; init; }

    [JsonPropertyName("displayName")]
    public string? DisplayName { get; init; }

    [JsonPropertyName("sourceMods")]
    public IReadOnlyList<string> SourceMods { get; init; } = Array.Empty<string>();

    [JsonPropertyName("gameState")]
    public object? GameState { get; init; }

    [JsonPropertyName("recentFacts")]
    public IReadOnlyList<string> RecentFacts { get; init; } = Array.Empty<string>();

    [JsonPropertyName("history")]
    public IReadOnlyList<BridgeDialogueHistoryItem> History { get; init; } =
        Array.Empty<BridgeDialogueHistoryItem>();

    /// <summary>
    /// **跨窗口**的"她最近说过什么"（2026-09-23）：只装 NPC 本人的回复原文、时间正序，
    /// 比 <see cref="History"/> 长得多，取自**回看档案**（<c>displayHistoryByNpc</c>）。
    ///
    /// 为什么需要：<see cref="History"/> 被 <see cref="BridgeClient.MaxHistoryItems"/> 封顶在
    /// 6 条（约 3 轮），更早谈过的话题被挤出去之后，Bridge 侧的生活面槽位就以为"这条素材
    /// 还没谈过"——于是池子前几条被反复建议，玩家听到的是"又来了"。
    ///
    /// ⚠️ 它**只**参与判定（槽位排除"整场谈过的素材"、素材卡轮转去重）。Bridge 侧不会把
    /// 它放进模型看得到的 history —— 那条路径仍只由 <see cref="History"/> 决定，
    /// 所以这一份不撑大 prompt、也不改对话上下文。
    /// ⚠️ 发布顺序：Bridge 侧 <c>ApiModel</c> 是 <c>extra="forbid"</c> ⇒ 新 DLL + 旧 Bridge
    /// 会 422 并退化成兜底回复。**先发 Bridge、再发 DLL**；反方向安全（旧 DLL 不发这个键）。
    /// </summary>
    [JsonPropertyName("recentReplies")]
    public IReadOnlyList<string> RecentReplies { get; init; } = Array.Empty<string>();

    [JsonPropertyName("relationshipWorld")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RelationshipWorldSnapshot? RelationshipWorld { get; init; }

    [JsonPropertyName("channel")]
    public string Channel { get; init; } = ConversationChannel.Remote;
}

public sealed class BridgeDialogueHistoryItem
{
    [JsonPropertyName("role")]
    public string Role { get; init; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; init; } = string.Empty;

    [JsonPropertyName("intent")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Intent { get; init; }

    [JsonPropertyName("relationshipStage")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? RelationshipStage { get; init; }

    /// <summary>
    /// 回看档案里的发生序号（与 <see cref="GroupChatSessionRecord.Sequence"/> 共用一个序号空间，
    /// 由 <see cref="BridgeClient"/> 的单调计数器发放），F8 靠它把私聊记录与群聊场次并成一条时间线。
    ///
    /// ⚠️ **它只服务显示，永远不进请求体**：发送窗口（<c>historyByNpc</c>）里的每条都保持
    /// <c>null</c>（<see cref="JsonIgnoreCondition.WhenWritingNull"/> 会让它整个不出现在 JSON 里），
    /// 因为 Bridge 侧的请求模型是 <c>extra="forbid"</c> —— 多一个字段就 422、整轮对话退化成兜底。
    /// 写入路径见 <c>AppendHistory</c>，护栏用例见
    /// <c>GroupSessionArchiveTests.Model_window_never_carries_display_only_fields</c>。
    /// </summary>
    [JsonPropertyName("sequence")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? Sequence { get; init; }
}

/// <summary>
/// 示例记录（<see cref="SampleChatHistory"/>）注入或清理的结果：涉及几位 NPC、多少条消息。
/// 与"回看档案总共多少条"不是一回事 —— 这里只数带标记的那些。
/// </summary>
public readonly record struct SampleHistoryChange(int NpcCount, int MessageCount)
{
    public static SampleHistoryChange None => default;

    public bool IsEmpty => NpcCount == 0 || MessageCount == 0;

    public override string ToString() => $"NPC={NpcCount} 条={MessageCount}";
}

public sealed class BridgeDialogueResponse
{
    [JsonPropertyName("reply")]
    public string Reply { get; init; } = string.Empty;

    [JsonPropertyName("provider")]
    public string Provider { get; init; } = string.Empty;

    [JsonPropertyName("fallback")]
    public bool Fallback { get; init; }

    [JsonPropertyName("latencyMs")]
    public int LatencyMs { get; init; }

    [JsonPropertyName("warnings")]
    public IReadOnlyList<string> Warnings { get; init; } = Array.Empty<string>();

    [JsonPropertyName("openLoop")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public OpenLoopSignal? OpenLoop { get; init; }

    public static BridgeDialogueResponse Offline(string warning)
    {
        return new BridgeDialogueResponse
        {
            Reply = "Rasmodia：暂时没有合适的回复，请稍后再试。",
            Provider = "offline",
            Fallback = true,
            Warnings = new[] { warning },
        };
    }
}

public sealed class BridgeGroupTurn
{
    [JsonPropertyName("speakerNpcId")]
    public string SpeakerNpcId { get; init; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; init; } = string.Empty;

    [JsonPropertyName("addressedTo")]
    public IReadOnlyList<string> AddressedTo { get; init; } = Array.Empty<string>();
}

public sealed class BridgeGroupDialogueResponse
{
    [JsonPropertyName("strategy")]
    public string Strategy { get; init; } = "turn_based";

    [JsonPropertyName("channel")]
    public string Channel { get; init; } = ConversationChannel.Remote;

    [JsonPropertyName("provider")]
    public string Provider { get; init; } = string.Empty;

    [JsonPropertyName("fallback")]
    public bool Fallback { get; init; }

    [JsonPropertyName("turns")]
    public IReadOnlyList<BridgeGroupTurn> Turns { get; init; } = Array.Empty<BridgeGroupTurn>();

    [JsonPropertyName("providerCalls")]
    public int ProviderCalls { get; init; }

    [JsonPropertyName("providerErrors")]
    public IReadOnlyList<string> ProviderErrors { get; init; } = Array.Empty<string>();

    [JsonPropertyName("fallbackCount")]
    public int FallbackCount { get; init; }

    [JsonPropertyName("latencyMs")]
    public int LatencyMs { get; init; }

    [JsonPropertyName("warnings")]
    public IReadOnlyList<string> Warnings { get; init; } = Array.Empty<string>();

    [JsonPropertyName("usage")]
    public BridgeProviderUsage? Usage { get; init; }

    /// <summary>Bridge 从群聊里挑出的、值得长期记住的事实或约定（闲聊不会出现在这里）。</summary>
    [JsonPropertyName("memoryHighlights")]
    public IReadOnlyList<string> MemoryHighlights { get; init; } = Array.Empty<string>();

    public static BridgeGroupDialogueResponse Offline(string warning)
    {
        return new BridgeGroupDialogueResponse
        {
            Provider = "offline",
            Fallback = true,
            Turns = Array.Empty<BridgeGroupTurn>(),
            Warnings = new[] { warning },
        };
    }
}

public sealed class BridgeProviderUsage
{
    [JsonPropertyName("inputTokens")]
    public int? InputTokens { get; init; }

    [JsonPropertyName("outputTokens")]
    public int? OutputTokens { get; init; }

    [JsonPropertyName("totalTokens")]
    public int? TotalTokens { get; init; }
}

internal sealed class BridgeGroupDialogueHttpRequest
{
    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;

    [JsonPropertyName("provider")]
    public string Provider { get; init; } = "auto";

    [JsonPropertyName("strategy")]
    public string Strategy { get; init; } = "turn_based";

    [JsonPropertyName("channel")]
    public string Channel { get; init; } = ConversationChannel.Remote;

    [JsonPropertyName("participants")]
    public IReadOnlyList<GroupDialogueParticipant> Participants { get; init; } =
        Array.Empty<GroupDialogueParticipant>();

    [JsonPropertyName("activeSpeakerNpcId")]
    public string ActiveSpeakerNpcId { get; init; } = string.Empty;

    [JsonPropertyName("history")]
    public IReadOnlyList<GroupDialogueHistoryEntry> History { get; init; } =
        Array.Empty<GroupDialogueHistoryEntry>();

    [JsonPropertyName("invitationTopic")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? InvitationTopic { get; init; }

    [JsonPropertyName("invitationGuidance")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? InvitationGuidance { get; init; }

    [JsonPropertyName("gameState")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public NpcGameState? GameState { get; init; }

    [JsonPropertyName("recentFacts")]
    public IReadOnlyList<string> RecentFacts { get; init; } = Array.Empty<string>();

    [JsonPropertyName("relationshipWorld")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RelationshipWorldSnapshot? RelationshipWorld { get; init; }
}

public sealed class BridgeClient : IDisposable, IConversationTransport
{
    public static readonly Uri DefaultEndpoint = new("http://127.0.0.1:5678");
    public static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(60);
    /// <summary>私聊历史窗口的条数（`SendAsync` 的 history 与
    /// <see cref="AppendSendWindowHistory"/> 的发送窗口都用它）。</summary>
    private const int MaxHistoryItems = 6;

    /// <summary>
    /// **群聊**历史窗口的条数（<see cref="SendGroupAsync"/> 的 history）。
    ///
    /// 为什么要和私聊那份分开（2026-09-22）：私聊一条历史 = 一个完整回合，
    /// 群聊一条 = 一个人的一次发言 —— 一轮（玩家 1 条 + NPC 2～3 条）要占 3～4 条，
    /// 6 条只够 1.5～2 轮。玩家发言进历史后这个额度还会被玩家行占去一部分
    /// （见 <see cref="GroupSessionRules.ToRequestHistory"/>），覆盖轮数会进一步减半。
    /// 10 条在 3 人场里约 2.5～3 轮，与改前「纯 NPC 6 条」的覆盖相当。
    ///
    /// 有界：单条 ≤ <see cref="MaxHistoryContentLength"/>（240 字），10 条 ≤ 2400 字；
    /// Bridge 侧 `history` 的 `max_length=40`，远在上限以内。
    /// **不要**直接放大 <see cref="MaxHistoryItems"/> 来达到同样效果——那是私聊那份额度。
    /// </summary>
    private const int MaxGroupHistoryItems = 10;

    /// <summary>
    /// 跨窗口那一份"她最近说过什么"的条数上限
    /// （<see cref="BridgeDialogueRequest.RecentReplies"/>，取自回看档案）。
    ///
    /// 为什么是 24：私聊一轮通常只有 1 条 NPC 回复（`topic` 路径）或 2 条（`chat` 路径），
    /// 24 条 ≈ 12～24 轮，与索菲亚的素材池同量级（12 条）—— 判定要的正是"整场覆盖"。
    /// 再长收益递减：判据是 2-gram 回声，离线实测在 24 轮窗口上假阳只有 0~1 条、
    /// 漏报明显（偏保守），把窗口再拉长也不会更准。
    ///
    /// 有界：单条 ≤ <see cref="MaxHistoryContentLength"/>（240 字），24 条 ≤ 5760 字；
    /// Bridge 侧 `recentReplies` 的 `max_length=40`，在上限以内。
    /// **不要**直接放大 <see cref="MaxHistoryItems"/> 来达到同样效果 —— 那是
    /// "发给模型的对话上下文"那份额度，放大它同时改变 prompt 长度与模型看到的历史。
    /// </summary>
    private const int MaxRecentReplyItems = 24;

    private const int MaxHistoryContentLength = ChatHistoryRules.MaxContentLength;
    private const int MaxMessageLength = 2000;
    private const int MaxRecentFactLength = 240;
    private const int MaxRecentFactItems = 20;
    private static readonly Regex TopicPromptEcho = new(
        @"(?:请\s*主动\s*找|主动\s*找|请\s*找)"
            + @"(?:一个|个)?(?:自然(?:、符合当前情境)?的?)?话题",
        RegexOptions.Compiled);

    private readonly HttpClient httpClient;
    private readonly bool ownsHttpClient;
    private readonly Uri dialogueEndpoint;
    private readonly Uri groupDialogueEndpoint;
    private readonly Uri morningPlanEndpoint;
    private readonly Action<string>? diagnosticLogger;
    // 线上群聊策略由配置决定：默认自然接话流（multi_turn），turn_based 为回退选项。
    private readonly string groupStrategy = ModConfig.MultiTurnGroupStrategy;
    private readonly object memoryLock = new();
    private readonly Dictionary<string, List<BridgeDialogueHistoryItem>> historyByNpc = new();
    // 回看档案：F8 面板「往上翻」看的那一份，比发送窗口长（ChatHistoryRules.MaxDisplayMessages）。
    // 与 historyByNpc 并存、各裁各的。**它不进模型看得到的 history**（那份仍只由 historyByNpc
    // 决定），但**是**跨窗口判定那一份的取数来源（见 RecentRepliesFor / MaxRecentReplyItems）：
    // 2026-09-23 起它多了一个读取端，不再只是"给玩家翻的"。
    private readonly Dictionary<string, List<BridgeDialogueHistoryItem>> displayHistoryByNpc = new();
    // 群聊场次：一场群聊一条（见 GroupChatSessionRecord），最早的在前。
    // 与 displayHistoryByNpc 同属「给玩家翻的档案」，同样不参与任何请求。
    private readonly List<GroupChatSessionRecord> groupSessions = new();
    // 回看档案的单调序号：私聊条目与群聊场次共用一个号池，F8 据此把两者并成一条时间线。
    // 它是显示层的东西，**不进请求体**（见 BridgeDialogueHistoryItem.Sequence）。
    private int displaySequence;
    private readonly Dictionary<string, NpcGameState> previousStateByNpc = new();
    // 早上主动发来、玩家还没点开看的人（2026-09-26）。F8 名册据此**置顶并标记**。
    //
    // 存「未读」而不是「今天谁发过」：发过但已经看过的人不该继续置顶——
    // 置顶的价值在于「有件事等你」，看过之后它就没了。
    // 随聊天档案一起存取（见 ChatHistoryArchiveEnvelope.UnreadMorning），
    // 于是换存档时它跟着一起丢弃，不会跨存档残留。
    private readonly HashSet<string> unreadMorningByNpc = new(StringComparer.OrdinalIgnoreCase);

    public BridgeClient(
        HttpClient? httpClient = null,
        Uri? endpoint = null,
        TimeSpan? timeout = null,
        Action<string>? diagnosticLogger = null,
        string? groupStrategy = null)
    {
        var baseEndpoint = endpoint ?? DefaultEndpoint;
        ValidateEndpoint(baseEndpoint);

        this.httpClient = httpClient ?? new HttpClient();
        ownsHttpClient = httpClient is null;
        this.diagnosticLogger = diagnosticLogger;
        this.groupStrategy = ModConfig.NormalizeGroupStrategy(groupStrategy);
        this.httpClient.Timeout = timeout ?? DefaultTimeout;
        var normalizedBaseEndpoint = new Uri(
            baseEndpoint.AbsoluteUri.TrimEnd('/') + "/",
            UriKind.Absolute);
        dialogueEndpoint = new Uri(normalizedBaseEndpoint, "api/dialogue/test");
        groupDialogueEndpoint = new Uri(normalizedBaseEndpoint, "api/dialogue/group");
        morningPlanEndpoint = new Uri(normalizedBaseEndpoint, "api/morning/plan");
    }

    public async Task<BridgeDialogueResponse> SendAsync(
        string npcId,
        string message,
        object? gameState = null,
        CancellationToken cancellationToken = default,
        IReadOnlyList<string>? memoryFacts = null,
        string intent = ConversationIntent.Chat,
        ItemConversationContext? itemContext = null,
        RelationshipWorldSnapshot? relationshipWorld = null,
        string channel = ConversationChannel.Remote)
    {
        if (string.IsNullOrWhiteSpace(npcId))
        {
            throw new ArgumentException("NPC ID 不能为空。", nameof(npcId));
        }

        var normalizedIntent = string.IsNullOrWhiteSpace(intent)
            ? ConversationIntent.Chat
            : intent;
        var normalizedChannel = string.Equals(channel, ConversationChannel.FaceToFace, StringComparison.Ordinal)
            ? ConversationChannel.FaceToFace
            : ConversationChannel.Remote;
        if (string.IsNullOrWhiteSpace(message) && normalizedIntent != ConversationIntent.Topic)
        {
            throw new ArgumentException("消息不能为空。", nameof(message));
        }

        var boundedMessage = normalizedIntent == ConversationIntent.Topic
            ? string.Empty
            : Truncate(message, MaxMessageLength);
        try
        {
            var npcGameState = gameState as NpcGameState;
            BridgeDialogueRequest request;
            lock (memoryLock)
            {
                request = new BridgeDialogueRequest
                {
                    NpcId = npcId,
                    Message = boundedMessage,
                    Intent = normalizedIntent,
                    Channel = normalizedChannel,
                    ItemContext = itemContext,
                    DisplayName = npcGameState?.DisplayName,
                    SourceMods = npcGameState?.SourceMods ?? Array.Empty<string>(),
                    GameState = gameState,
                    RelationshipWorld = relationshipWorld is null
                        ? null
                        : FilterRelationshipWorld(npcId, relationshipWorld),
                    RecentFacts = MergeRecentFacts(
                        BuildRecentFacts(
                            previousStateByNpc.GetValueOrDefault(npcId),
                            npcGameState),
                        memoryFacts),
                    History = historyByNpc.TryGetValue(npcId, out var history)
                        ? history.ToArray()
                        : Array.Empty<BridgeDialogueHistoryItem>(),
                    // 跨窗口那一份（2026-09-23）：比上面的发送窗口长，取自回看档案。
                    RecentReplies = RecentRepliesFor(npcId),
                };
            }

            using var response = await httpClient.PostAsJsonAsync(
                dialogueEndpoint,
                request,
                cancellationToken).ConfigureAwait(false);

            BridgeDialogueResponse result;
            if (!response.IsSuccessStatusCode)
            {
                result = BridgeDialogueResponse.Offline(
                    $"bridge: HTTP {(int)response.StatusCode} {response.ReasonPhrase}".Trim());
            }
            else
            {
                var parsed = await response.Content.ReadFromJsonAsync<BridgeDialogueResponse>(
                    cancellationToken: cancellationToken).ConfigureAwait(false);
                result = parsed is null || string.IsNullOrWhiteSpace(parsed.Reply)
                    ? BridgeDialogueResponse.Offline("bridge: 响应缺少 reply。")
                    : parsed;
            }

            if (normalizedIntent == ConversationIntent.Topic && TopicPromptEcho.IsMatch(result.Reply))
            {
                // Bridge 已经有同样的保护；这里再拦一层，避免旧 Bridge 或错误路由把内部任务说明画进游戏。
                result = BridgeDialogueResponse.Offline("bridge: topic prompt echo");
            }

            LogSafeResponseMetadata(result);
            RememberResult(npcId, boundedMessage, normalizedIntent, result, npcGameState);
            return result;
        }
        catch (TaskCanceledException)
        {
            var result = BridgeDialogueResponse.Offline("bridge: timeout");
            LogSafeResponseMetadata(result);
            RememberResult(npcId, boundedMessage, normalizedIntent, result, gameState as NpcGameState);
            return result;
        }
        catch (HttpRequestException exception)
        {
            var result = BridgeDialogueResponse.Offline($"bridge: offline ({exception.Message})");
            LogSafeResponseMetadata(result);
            RememberResult(npcId, boundedMessage, normalizedIntent, result, gameState as NpcGameState);
            return result;
        }
        catch (JsonException exception)
        {
            var result = BridgeDialogueResponse.Offline($"bridge: invalid JSON ({exception.Message})");
            LogSafeResponseMetadata(result);
            RememberResult(npcId, boundedMessage, normalizedIntent, result, gameState as NpcGameState);
            return result;
        }
    }

    public async Task<BridgeGroupDialogueResponse> SendGroupAsync(
        GroupDialogueRequest request,
        CancellationToken cancellationToken = default,
        bool allowEmptyMessage = false)
    {
        ArgumentNullException.ThrowIfNull(request);

        var participants = request.Participants ?? Array.Empty<GroupDialogueParticipant>();
        if (participants.Count is < 2 or > 3)
        {
            return BridgeGroupDialogueResponse.Offline("bridge: participant count invalid");
        }

        var participantIds = participants
            .Select(item => item.NpcId?.Trim() ?? string.Empty)
            .ToArray();
        if (participantIds.Any(string.IsNullOrWhiteSpace) ||
            participantIds.Distinct(StringComparer.OrdinalIgnoreCase).Count() != participantIds.Length)
        {
            return BridgeGroupDialogueResponse.Offline("bridge: participant list invalid");
        }

        var activeSpeakerNpcId = string.IsNullOrWhiteSpace(request.ActiveSpeakerNpcId)
            ? participantIds[0]
            : request.ActiveSpeakerNpcId.Trim();
        if (!participantIds.Contains(activeSpeakerNpcId, StringComparer.OrdinalIgnoreCase))
        {
            return BridgeGroupDialogueResponse.Offline("bridge: active speaker invalid");
        }

        // 空消息只在「开场」语义下合法：玩家接受邀约后一句话都没说，由 NPC 起头
        // （2026-09-20 用户反馈）。此前这里**无条件**拒绝，于是 GroupDialogueMenu
        // 侧发起的开场请求在这一层被兜底掉——而且它发生在发 HTTP 之前，
        // 所以 Bridge 侧完全看不到那次请求，排查时极具误导性。
        //
        // ⚠️ 这里必须与 Bridge 侧 `GroupDialogueRequest._validate_group_shape` 保持
        // **同一条规则**：空消息只在**历史也为空**时才是开场。两处规则不同就会产生
        // “SMAPI 放行、Bridge 422” 这种静默不一致——本次的开场问题正是这类不一致
        // 的表现，所以两边一起改，并由 GroupOpeningBridgeClientTests 钉住。
        if (string.IsNullOrWhiteSpace(request.Message) &&
            (!allowEmptyMessage || (request.History?.Count ?? 0) > 0))
        {
            return BridgeGroupDialogueResponse.Offline("bridge: message empty");
        }

        // **取最近**的若干条（2026-09-22 修）：改前这里是 `.Take(MaxHistoryItems)` —— 取的是
        // **最旧**的 6 条，与私聊 `TrimHistory`（保留末尾）方向相反。玩家发言进历史后这个
        // 方向性错误会被放大：越聊，模型看到的越是这场对话的开头，而刚发生的事被挡在外面。
        // 与私聊对齐用 TakeLast，别改回 Take。
        var boundedHistory = (request.History ?? Array.Empty<GroupDialogueHistoryEntry>())
            .TakeLast(MaxGroupHistoryItems)
            .Select(item => new GroupDialogueHistoryEntry(
                item.SpeakerType,
                item.SpeakerId,
                Truncate(item.Content ?? string.Empty, MaxHistoryContentLength),
                (item.AddressedTo ?? Array.Empty<string>())
                    .Where(value => !string.IsNullOrWhiteSpace(value))
                    .Take(participants.Count)
                    .Select(value => Truncate(value.Trim(), 100))
                    .ToArray()))
            .ToArray();
        var bridgeRequest = new BridgeGroupDialogueHttpRequest
        {
            Message = Truncate(request.Message.Trim(), MaxMessageLength),
            Provider = string.IsNullOrWhiteSpace(request.Provider) ? "auto" : request.Provider.Trim(),
            Strategy = groupStrategy,
            Channel = ConversationChannel.Remote,
            Participants = participants
                .Select(item => new GroupDialogueParticipant(
                    item.NpcId.Trim(),
                    Truncate(item.DisplayName?.Trim() ?? item.NpcId.Trim(), 100),
                    item.GameState))
                .ToArray(),
            ActiveSpeakerNpcId = activeSpeakerNpcId,
            History = boundedHistory,
            InvitationTopic = TruncateNullable(request.InvitationTopic, 240),
            InvitationGuidance = TruncateNullable(request.InvitationGuidance, 500),
            GameState = request.GameState,
            RecentFacts = (request.RecentFacts ?? Array.Empty<string>())
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Take(MaxRecentFactItems)
                .Select(value => Truncate(value.Trim(), MaxRecentFactLength))
                .ToArray(),
            RelationshipWorld = request.RelationshipWorld,
        };

        try
        {
            using var response = await httpClient.PostAsJsonAsync(
                groupDialogueEndpoint,
                bridgeRequest,
                cancellationToken).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                var failed = BridgeGroupDialogueResponse.Offline(
                    $"bridge: HTTP {(int)response.StatusCode} {response.ReasonPhrase}".Trim());
                LogSafeGroupResponseMetadata(failed);
                return failed;
            }

            var parsed = await response.Content.ReadFromJsonAsync<BridgeGroupDialogueResponse>(
                cancellationToken: cancellationToken).ConfigureAwait(false);
            var result = ValidateGroupResponse(parsed, participantIds, groupStrategy);
            LogSafeGroupResponseMetadata(result);
            RememberGroupTurn(participants, request.Message, result, request.Session);
            return result;
        }
        catch (TaskCanceledException)
        {
            var result = BridgeGroupDialogueResponse.Offline("bridge: timeout");
            LogSafeGroupResponseMetadata(result);
            return result;
        }
        catch (HttpRequestException)
        {
            var result = BridgeGroupDialogueResponse.Offline("bridge: offline");
            LogSafeGroupResponseMetadata(result);
            return result;
        }
        catch (JsonException)
        {
            var result = BridgeGroupDialogueResponse.Offline("bridge: invalid JSON");
            LogSafeGroupResponseMetadata(result);
            return result;
        }
    }

    private void LogSafeGroupResponseMetadata(BridgeGroupDialogueResponse result)
    {
        diagnosticLogger?.Invoke(
            $"[StardewAI.Bridge] group response provider={result.Provider}; " +
            $"fallback={result.Fallback.ToString().ToLowerInvariant()}; " +
            $"latencyMs={result.LatencyMs}; turnCount={result.Turns.Count}; " +
            $"warningCount={result.Warnings.Count}");
    }

    /// <summary>
    /// 只读诊断入口：某位 NPC 内存层对话历史的条数（不含进存档的长期记忆）。
    /// 供视觉测试核对“一次群聊只占一条”的合并写法。
    /// </summary>
    internal int VisualTestHistoryCount(string npcId)
    {
        var normalized = npcId?.Trim();
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return 0;
        }

        lock (memoryLock)
        {
            return historyByNpc
                .Where(pair => string.Equals(pair.Key, normalized, StringComparison.OrdinalIgnoreCase))
                .Select(pair => pair.Value.Count)
                .FirstOrDefault();
        }
    }

    /// <summary>
    /// 只读回看入口：某位 NPC 最近真实发生过的对话（玩家与 NPC 都在，群聊摘要也在），
    /// 供 F8 面板打开时铺进消息区。读的是**回看档案**，与发给模型的 6 条窗口无关：
    /// 那份窗口一字不动，这里只是把它保留得更久一点给玩家翻。
    /// </summary>
    public IReadOnlyList<BridgeDialogueHistoryItem> RecentHistory(string npcId)
    {
        var normalized = npcId?.Trim();
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return Array.Empty<BridgeDialogueHistoryItem>();
        }

        lock (memoryLock)
        {
            return displayHistoryByNpc
                .Where(pair => string.Equals(pair.Key, normalized, StringComparison.OrdinalIgnoreCase))
                .Select(pair => pair.Value.ToArray())
                .FirstOrDefault() ?? Array.Empty<BridgeDialogueHistoryItem>();
        }
    }

    /// <summary>
    /// 跨窗口那一份"她最近说过什么"（<see cref="BridgeDialogueRequest.RecentReplies"/> 的来源）：
    /// 从**回看档案**取 NPC 本人的回复原文，时间正序，最多 <see cref="MaxRecentReplyItems"/> 条。
    ///
    /// 三条口径：
    /// 1. **只取 assistant**：Bridge 侧判的是"这句话是不是她说过的"，玩家的话对它没有用，
    ///    带过去只会占额度；
    /// 2. **跳过示例记录**（<see cref="SampleChatHistory.IsSample"/>）：那是注入给玩家翻的
    ///    演示数据，不是她真说过的话 —— 让它参与判定会凭空把一批素材标成"谈过了"；
    /// 3. **取最近的 N 条**：从尾部往前收，收满再反转回时间正序。发送窗口在 2026-09-22
    ///    修过一次方向（此前取到的是**最旧**的几条），这里一开始就写对。
    ///
    /// 必须在 <c>memoryLock</c> 里调用。
    /// </summary>
    private IReadOnlyList<string> RecentRepliesFor(string npcId)
    {
        if (string.IsNullOrWhiteSpace(npcId)
            || !displayHistoryByNpc.TryGetValue(npcId, out var log)
            || log.Count == 0)
        {
            return Array.Empty<string>();
        }

        var replies = new List<string>();
        for (var index = log.Count - 1;
             index >= 0 && replies.Count < MaxRecentReplyItems;
             index--)
        {
            var item = log[index];
            if (!string.Equals(item.Role, "assistant", StringComparison.OrdinalIgnoreCase)
                || SampleChatHistory.IsSample(item)
                || string.IsNullOrWhiteSpace(item.Content))
            {
                continue;
            }

            replies.Add(item.Content);
        }

        replies.Reverse();
        return replies;
    }

    /// <summary>
    /// 只读回看入口：这位 NPC **在场**的每一场群聊（一场一条，含完整发言序列）。
    ///
    /// ⚠ 2026-09-21 用户口径：这一份**不再并进 F8**（F8 只显示私聊）。群聊记录的出口是
    /// F9 那张邀约卡 —— <see cref="GroupSession"/> 按邀约 id 取回同一场，点开就是整场
    /// 发言序列（只读）。按 NPC 查询这一头保留给诊断与将来的「他参与过哪几场」。
    /// </summary>
    public IReadOnlyList<GroupChatSessionRecord> RecentGroupSessions(string? npcId)
    {
        if (string.IsNullOrWhiteSpace(npcId))
        {
            return Array.Empty<GroupChatSessionRecord>();
        }

        lock (memoryLock)
        {
            return groupSessions
                .Where(session => GroupSessionRules.InvolvesNpc(session, npcId))
                .ToArray();
        }
    }

    /// <summary>
    /// 一场群聊的存档记录（按邀约卡 id 找）。F9 菜单重开时用它把整场历史接回来 ——
    /// 这是「session.PublicHistory 随存档走」的读取端。
    /// </summary>
    public GroupChatSessionRecord? GroupSession(string? sessionId)
    {
        lock (memoryLock)
        {
            return FindGroupSession(sessionId);
        }
    }

    /// <summary>
    /// 把**回看档案**编成存档载荷（见 <see cref="ChatHistoryArchive"/>）。
    /// 只导出 F8 面板那一份：发给模型的 6 条窗口本就是它的尾部子集，重复存没有意义，
    /// 也免得将来有人误以为窗口能靠存档恢复。
    ///
    /// 群聊场次与私聊档案同属这一份，一起写进同一段 JSON（同一个存档键、同一次 Saving）——
    /// 它们是同一批「发生过的事」的两种形态，只是**看的入口不同**：私聊回 F8 面板，
    /// 群聊回 F9 那张邀约卡（2026-09-21 用户口径，见 <see cref="GroupDialogueHubMenu"/>）。
    /// 入口换了，存档格式与键都没动 —— 老档案照旧读得进，场次一条不丢。
    /// </summary>
    /// <param name="saveFolder">当前存档的文件夹名；写入时会被归一化成存档 ID 存下来。</param>
    public string SerializeDisplayHistory(string? saveFolder)
    {
        lock (memoryLock)
        {
            var snapshot = displayHistoryByNpc.ToDictionary(
                pair => pair.Key,
                pair => (IReadOnlyList<BridgeDialogueHistoryItem>)pair.Value.ToArray(),
                StringComparer.Ordinal);
            return ChatHistoryArchive.Serialize(
                snapshot,
                groupSessions.ToArray(),
                saveFolder,
                unreadMorningByNpc.ToArray());
        }
    }

    /// <summary>
    /// 用存档里的回看档案**替换**内存里的那一份（读不到就是清空，不是合并——
    /// 载入另一个存档时必须把上一个存档的记录清干净）。
    ///
    /// 只动回看档案：发给模型的 <c>historyByNpc</c> 一字不动，
    /// <c>previousStateByNpc</c> 这类运行时推导状态也不受影响。
    ///
    /// 显示序号会**接着读回来的最大值往下发**：否则新写的条目拿到 1、2、3，
    /// 会插到存档里那批旧条目的前面（序号小的排前面）。
    /// </summary>
    public ChatHistoryArchiveLoadResult LoadDisplayHistory(string? json, string? saveFolder)
    {
        var loaded = ChatHistoryArchive.Load(json, saveFolder);
        lock (memoryLock)
        {
            displayHistoryByNpc.Clear();
            foreach (var pair in loaded.History)
            {
                displayHistoryByNpc[pair.Key] = pair.Value.ToList();
            }

            groupSessions.Clear();
            groupSessions.AddRange(loaded.Sessions);
            // 未读名单跟着档案一起替换（不是合并）：换存档时上一个存档的未读必须清掉，
            // 否则新档里会凭空出现「有人在早上给你留了话」。
            unreadMorningByNpc.Clear();
            foreach (var npcId in loaded.UnreadMorning)
            {
                unreadMorningByNpc.Add(npcId);
            }

            displaySequence = HighestSequence(loaded) ?? 0;
        }

        return loaded;
    }

    /// <summary>
    /// 问 Bridge「今天早上有没有人要主动开口」。
    ///
    /// **失败一律返回空列表，绝不抛异常**：这是个锦上添花的功能，
    /// Bridge 没启动、超时、返回坏 JSON，都不该让 <c>DayStarted</c> 抛出去——
    /// 那会打断玩家一天的开始。失败的表现就是「今天没人发消息」，与没有预设时一致。
    /// </summary>
    public async Task<IReadOnlyList<MorningMessagePlan>> RequestMorningPlanAsync(
        int dayIndex,
        IReadOnlyList<string>? knownNpcIds = null,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var request = new MorningPlanRequest
            {
                DayIndex = dayIndex,
                KnownNpcIds = knownNpcIds ?? Array.Empty<string>(),
            };
            using var response = await httpClient
                .PostAsJsonAsync(morningPlanEndpoint, request, cancellationToken)
                .ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                diagnosticLogger?.Invoke(
                    $"[StardewAI.Morning] plan request failed: {(int)response.StatusCode}");
                return Array.Empty<MorningMessagePlan>();
            }

            // ⚠ 必须是命名参数：`ReadFromJsonAsync<T>` 的第二个位置参数是
            // `JsonSerializerOptions?`，直接传 token 会编译失败（CS1503）。
            var plan = await response.Content
                .ReadFromJsonAsync<MorningPlanResponse>(cancellationToken: cancellationToken)
                .ConfigureAwait(false);
            return plan?.Messages ?? Array.Empty<MorningMessagePlan>();
        }
        catch (Exception ex) when (
            ex is HttpRequestException
                or TaskCanceledException
                or JsonException
                or NotSupportedException)
        {
            diagnosticLogger?.Invoke(
                $"[StardewAI.Morning] plan request threw: {ex.GetType().Name}");
            return Array.Empty<MorningMessagePlan>();
        }
    }

    /// <summary>
    /// 记一条「早上主动发来」的消息：写进回看档案与发送窗口，并标为未读。
    ///
    /// **为什么也要写发送窗口**：这条消息的作用不只是给玩家看——它是这段对话的**开头**。
    /// 玩家接着回话时，模型必须看得到「自己先说过什么」，否则会答非所问。
    /// 这正是「用预设对话引导自由聊天」能成立的前提；只写回看档案的话，
    /// 玩家看到的是一个人的话，而模型看到的是另一个人凭空开口。
    ///
    /// `intent` 固定用 <see cref="ConversationIntent.Chat"/>：这个字段**会进请求体**，
    /// 而 Bridge 侧是 `Literal["chat","topic","item"]` + `extra="forbid"`，
    /// 自造一个 `"morning"` 会直接 422。
    /// </summary>
    public bool RememberMorningMessage(string npcId, string text)
    {
        var id = npcId?.Trim();
        var content = Truncate(text?.Trim() ?? string.Empty, MaxHistoryContentLength);
        if (string.IsNullOrWhiteSpace(id) || string.IsNullOrWhiteSpace(content))
        {
            return false;
        }

        lock (memoryLock)
        {
            AppendHistory(id, new BridgeDialogueHistoryItem
            {
                Role = "assistant",
                Content = content,
                Intent = ConversationIntent.Chat,
            });
            unreadMorningByNpc.Add(id);
        }

        return true;
    }

    /// <summary>
    /// 玩家看过了（打开了这个人的聊天窗）。返回是否**确实清掉了一条**——
    /// 调用方据此决定要不要立刻存档，没清掉就不必写盘。
    /// </summary>
    public bool MarkMorningRead(string npcId)
    {
        var id = npcId?.Trim();
        if (string.IsNullOrWhiteSpace(id))
        {
            return false;
        }

        lock (memoryLock)
        {
            return unreadMorningByNpc.Remove(id);
        }
    }

    /// <summary>F8 名册用：这个人有未读的晨间消息吗。</summary>
    public bool HasUnreadMorning(string npcId)
    {
        var id = npcId?.Trim();
        if (string.IsNullOrWhiteSpace(id))
        {
            return false;
        }

        lock (memoryLock)
        {
            return unreadMorningByNpc.Contains(id);
        }
    }

    /// <summary>档案里出现过的最大显示序号；一条都没有时返回 null（新档从 0 起）。</summary>
    private static int? HighestSequence(ChatHistoryArchiveLoadResult loaded)
    {
        var sequences = loaded.History
            .SelectMany(pair => pair.Value)
            .Select(item => item.Sequence)
            .Concat(loaded.Sessions.Select(session => session.Sequence))
            .Where(sequence => sequence.HasValue)
            .Select(sequence => sequence!.Value);
        return sequences.Any() ? sequences.Max() : null;
    }

    /// <summary>
    /// 把一批**示例记录**（<see cref="SampleChatHistory"/>）灌进回看档案，供玩家验收
    /// 「F8 往上翻历史」与「记录随存档持久化」——他自己还没聊过几句，没有历史可翻。
    ///
    /// 三条边界：
    /// 1. **只动回看档案**：发给模型的 <c>historyByNpc</c> 一字不改。示例是给玩家翻的，
    ///    不是 NPC 真实经历过的事，所以 NPC 不会"记得"玩家没说过的话；
    /// 2. **重复注入不翻倍**：同一位 NPC 上先按标记（见 <see cref="SampleChatHistory.IsSample"/>）
    ///    清掉上一批，再追加这一批；玩家真实聊过的记录一条不动；
    /// 3. **规格与真实记录一致**：与 <see cref="AppendHistory"/> 一样裁到
    ///    <see cref="ChatHistoryRules.MaxDisplayMessages"/> 条，所以超量注入（压力用例）
    ///    同样会丢掉最旧的那一截。
    ///
    /// 落盘不由这里负责：示例进了内存档案之后，玩家正常保存（SMAPI 的 Saving）时会与
    /// 真实记录一起被 <see cref="SerializeDisplayHistory"/> 写进当前存档。
    /// </summary>
    public SampleHistoryChange InjectSampleHistory(
        IReadOnlyDictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>? samples)
    {
        if (samples is null || samples.Count == 0)
        {
            return SampleHistoryChange.None;
        }

        lock (memoryLock)
        {
            var npcCount = 0;
            var messageCount = 0;
            foreach (var pair in samples)
            {
                var npcId = pair.Key?.Trim();
                if (string.IsNullOrWhiteSpace(npcId))
                {
                    continue;
                }

                var log = EnsureHistory(displayHistoryByNpc, npcId);
                log.RemoveAll(SampleChatHistory.IsSample);

                var added = (pair.Value ?? Array.Empty<BridgeDialogueHistoryItem>())
                    .Where(item => item is not null && !string.IsNullOrWhiteSpace(item.Content))
                    .ToList();
                if (added.Count == 0)
                {
                    if (log.Count == 0)
                    {
                        displayHistoryByNpc.Remove(npcId);
                    }

                    continue;
                }

                log.AddRange(added);
                TrimHistory(log, ChatHistoryRules.MaxDisplayMessages);
                npcCount++;
                messageCount += added.Count;
            }

            return new SampleHistoryChange(npcCount, messageCount);
        }
    }

    /// <summary>
    /// 清掉内存档案里的示例记录（只按标记删，玩家真实聊过的记录一条不动），
    /// 返回移除的条数。
    ///
    /// 清完要**再保存一次**（睡觉过夜、退出到标题或手动保存都行）：存档里那份是上一次
    /// 保存时写下的，只有等下一次保存把它覆盖掉才算真正清干净。
    /// </summary>
    public int ClearSampleHistory()
    {
        lock (memoryLock)
        {
            var removed = 0;
            foreach (var npcId in displayHistoryByNpc.Keys.ToArray())
            {
                var log = displayHistoryByNpc[npcId];
                removed += log.RemoveAll(SampleChatHistory.IsSample);
                if (log.Count == 0)
                {
                    displayHistoryByNpc.Remove(npcId);
                }
            }

            return removed;
        }
    }

    /// <summary>只读：内存档案里还剩多少示例记录，用来在日志里说清"现在是什么状态"。</summary>
    public SampleHistoryChange CountSampleHistory()
    {
        lock (memoryLock)
        {
            var npcCount = 0;
            var messageCount = 0;
            foreach (var log in displayHistoryByNpc.Values)
            {
                var count = log.Count(SampleChatHistory.IsSample);
                if (count == 0)
                {
                    continue;
                }

                npcCount++;
                messageCount += count;
            }

            return new SampleHistoryChange(npcCount, messageCount);
        }
    }

    /// <summary>
    /// 记一条**私聊**历史：**发送窗口**（发给模型，<see cref="MaxHistoryItems"/> 条）与
    /// **回看档案**（F8 面板，<see cref="ChatHistoryRules.MaxDisplayMessages"/> 条）各存一份、各自裁剪。
    /// 两份的文本是同一个不可变字符串，不重复占内存（回看那一份多带一个显示序号，见下）。
    ///
    /// ⚠️ 群聊**不走这里**：群聊的发送窗口一份（每位发言者本人发言合并成一条）与回看档案一份
    /// （整场一条场次记录）内容不同，分别写在 <see cref="RememberGroupTurn"/>，
    /// 免得「一条摘要」既当模型记忆又当回看记录（那正是玩家翻不到对话流的原因）。
    /// </summary>
    private void AppendHistory(string npcId, BridgeDialogueHistoryItem item)
    {
        AppendSendWindowHistory(npcId, item);

        var displayLog = EnsureHistory(displayHistoryByNpc, npcId);
        // 回看那一份盖上显示序号：下一个号只发给回看档案，发送窗口里的那条保持 null。
        displayLog.Add(item.Sequence.HasValue ? item : WithSequence(item, NextDisplaySequence()));
        TrimHistory(displayLog, ChatHistoryRules.MaxDisplayMessages);
    }

    /// <summary>回看档案专用的一份副本（只多一个显示序号；其余字段照抄）。</summary>
    private static BridgeDialogueHistoryItem WithSequence(BridgeDialogueHistoryItem item, int sequence)
    {
        return new BridgeDialogueHistoryItem
        {
            Role = item.Role,
            Content = item.Content,
            Intent = item.Intent,
            RelationshipStage = item.RelationshipStage,
            Sequence = sequence,
        };
    }

    /// <summary>只写**私聊**那个发送窗口（发给模型的 <see cref="MaxHistoryItems"/> 条）。
    /// 这里的记录必须与 Bridge 的请求模型逐字段对齐，
    /// 因此显示专用的字段（<see cref="BridgeDialogueHistoryItem.Sequence"/>）一律不填。
    /// 群聊的发送窗口也走这里（同样用私聊那份额度），它另有一份与请求无关的用途，
    /// 见 <see cref="RememberGroupTurn"/>。</summary>
    private void AppendSendWindowHistory(string npcId, BridgeDialogueHistoryItem item)
    {
        var sendWindow = EnsureHistory(historyByNpc, npcId);
        sendWindow.Add(item);
        TrimHistory(sendWindow, MaxHistoryItems);
    }

    /// <summary>发一个显示序号（只在 <c>memoryLock</c> 里调用）。</summary>
    private int NextDisplaySequence()
    {
        displaySequence = displaySequence == int.MaxValue ? int.MaxValue : displaySequence + 1;
        return displaySequence;
    }

    private static List<BridgeDialogueHistoryItem> EnsureHistory(
        Dictionary<string, List<BridgeDialogueHistoryItem>> store,
        string npcId)
    {
        if (!store.TryGetValue(npcId, out var history))
        {
            history = new List<BridgeDialogueHistoryItem>();
            store[npcId] = history;
        }

        return history;
    }

    private static void TrimHistory(List<BridgeDialogueHistoryItem> history, int maxItems)
    {
        if (history.Count > maxItems)
        {
            history.RemoveRange(0, history.Count - maxItems);
        }
    }

    /// <summary>
    /// 群聊结果落进两份**用途不同**的记忆：
    ///
    /// 1. **发送窗口**（每位参与者本人发言合并成一条，与改前一致）：NPC 私下再聊时得记得
    ///    群里说过什么，所以这一份必须留；它只在内存里，从不进回看档案；
    /// 2. **回看档案 → 群聊场次**（<see cref="GroupChatSessionRecord"/>）：整场一条记录、
    ///    含完整发言序列（玩家的话也在里面），F8 因此能按顺序翻完整场。
    ///
    /// 改前第 2 份写的是「本人发言合并成一条」的转述（<c>Role=assistant</c>）——那既不是对话流、
    /// 又让同一句群聊发言在存档里出现好几遍（每人一份转述）。现在一场群聊在存档里**只此一份**，
    /// 按 NPC 的条目里不再有群聊内容，两者不可能重复。
    ///
    /// 判据与 F9 界面同源：fallback／没有可用回合时，菜单既不画气泡也不记档
    /// （玩家那句留在输入框状态里可以重试），所以这里同样一条都不写。
    /// </summary>
    private void RememberGroupTurn(
        IReadOnlyList<GroupDialogueParticipant> participants,
        string playerMessage,
        BridgeGroupDialogueResponse result,
        GroupSessionContext? sessionContext)
    {
        if (result.Fallback || result.Turns.Count == 0)
        {
            return;
        }

        lock (memoryLock)
        {
            // 1) 发送窗口：每位发言者一条合并摘要（不进回看档案）。
            foreach (var participant in participants)
            {
                var npcId = participant.NpcId?.Trim();
                if (string.IsNullOrWhiteSpace(npcId))
                {
                    continue;
                }

                var spoken = result.Turns
                    .Where(turn => string.Equals(
                        turn.SpeakerNpcId?.Trim(),
                        npcId,
                        StringComparison.OrdinalIgnoreCase))
                    .Select(turn => (turn.Content ?? string.Empty).Trim())
                    .Where(text => text.Length > 0)
                    .ToArray();
                if (spoken.Length == 0)
                {
                    continue;
                }

                var stage = participant.GameState is null
                    ? null
                    : RelationshipStageRules.ResolveKey(participant.GameState);
                var joined = string.Join(" ", spoken);
                var summary = string.IsNullOrWhiteSpace(playerMessage)
                    ? $"群里我说：“{joined}”"
                    : $"群里玩家说：“{playerMessage.Trim()}”；我回应：“{joined}”";
                AppendSendWindowHistory(npcId, new BridgeDialogueHistoryItem
                {
                    Role = "assistant",
                    Content = Truncate(summary, MaxHistoryContentLength),
                    RelationshipStage = stage,
                });
            }

            // 2) 回看档案：整场群聊一条记录。没有场次身份（老调用点／测试替身没带上下文）时
            //    退回按参与者姓名拼的身份，仍然只写一条，而不是每人一条。
            var context = sessionContext ?? FallbackSessionContext(participants);
            var existing = FindGroupSession(context.SessionId);
            var next = GroupSessionRules.Append(
                existing,
                context,
                participants,
                playerMessage,
                result.Turns,
                fallback: false,
                sequence: NextDisplaySequence());
            if (next is null)
            {
                return;
            }

            if (existing is null)
            {
                groupSessions.Add(next);
                TrimGroupSessions();
                return;
            }

            var index = groupSessions.IndexOf(existing);
            groupSessions[index] = next;
        }
    }

    /// <summary>
    /// 调用点没带场次身份时的兜底：用参与者名单拼一个稳定 id。
    /// 正常路径（F9 菜单）总会带上邀约卡 id；这里只服务测试替身与旧调用点，
    /// 让它们仍然得到「一场一条」而不是「每人一条」。
    /// </summary>
    private static GroupSessionContext FallbackSessionContext(
        IReadOnlyList<GroupDialogueParticipant> participants)
    {
        var ids = participants
            .Select(item => item.NpcId?.Trim() ?? string.Empty)
            .Where(id => id.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(id => id, StringComparer.OrdinalIgnoreCase);
        return new GroupSessionContext($"group:{string.Join("+", ids)}");
    }

    private GroupChatSessionRecord? FindGroupSession(string? sessionId)
    {
        var normalized = sessionId?.Trim();
        if (string.IsNullOrEmpty(normalized))
        {
            return null;
        }

        return groupSessions.FirstOrDefault(session =>
            string.Equals(session.SessionId, normalized, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>场次数上限（丢最旧的）。</summary>
    private void TrimGroupSessions()
    {
        if (groupSessions.Count > GroupSessionRules.MaxSessions)
        {
            groupSessions.RemoveRange(0, groupSessions.Count - GroupSessionRules.MaxSessions);
        }
    }

    private static BridgeGroupDialogueResponse ValidateGroupResponse(
        BridgeGroupDialogueResponse? response,
        IReadOnlyList<string> participantIds,
        string expectedStrategy)
    {
        if (response is null)
        {
            return BridgeGroupDialogueResponse.Offline("bridge: response missing");
        }

        if (response.Fallback)
        {
            return SafeGroupFailure(response, "bridge: provider fallback");
        }

        if (!string.Equals(response.Channel, ConversationChannel.Remote, StringComparison.Ordinal) ||
            !string.Equals(response.Strategy, expectedStrategy, StringComparison.Ordinal))
        {
            return SafeGroupFailure(response, "bridge: response mode invalid");
        }

        var turns = response.Turns ?? Array.Empty<BridgeGroupTurn>();
        if (turns.Count == 0 || turns.Any(turn =>
                string.IsNullOrWhiteSpace(turn.SpeakerNpcId) ||
                !participantIds.Contains(turn.SpeakerNpcId, StringComparer.OrdinalIgnoreCase) ||
                string.IsNullOrWhiteSpace(turn.Content)))
        {
            return SafeGroupFailure(response, "bridge: response speaker invalid");
        }

        return new BridgeGroupDialogueResponse
        {
            Strategy = expectedStrategy,
            Channel = ConversationChannel.Remote,
            Provider = response.Provider,
            Fallback = false,
            Turns = turns
                .Select(turn => new BridgeGroupTurn
                {
                    SpeakerNpcId = turn.SpeakerNpcId.Trim(),
                    Content = turn.Content.Trim(),
                    AddressedTo = (turn.AddressedTo ?? Array.Empty<string>())
                        .Where(value => participantIds.Contains(value, StringComparer.OrdinalIgnoreCase))
                        .Take(3)
                        .ToArray(),
                })
                .ToArray(),
            ProviderCalls = response.ProviderCalls,
            ProviderErrors = Array.Empty<string>(),
            // 2026-09-20 修（契约审计）：这里重建响应时**漏复制了 MemoryHighlights**，
            // 于是「Bridge 挑出值得长期记住的事实」这条链从未生效——群聊长期记忆永远不写。
            // 之前的视觉验证用 QueueResponseForVisualTest 直接塞响应、绕过了本方法，
            // 所以一直没暴露。
            MemoryHighlights = response.MemoryHighlights ?? Array.Empty<string>(),
            FallbackCount = response.FallbackCount,
            LatencyMs = response.LatencyMs,
            Warnings = response.Warnings ?? Array.Empty<string>(),
            Usage = response.Usage,
        };
    }

    private static BridgeGroupDialogueResponse SafeGroupFailure(
        BridgeGroupDialogueResponse response,
        string warning)
    {
        return new BridgeGroupDialogueResponse
        {
            Strategy = "turn_based",
            Channel = ConversationChannel.Remote,
            Provider = string.IsNullOrWhiteSpace(response.Provider) ? "unknown" : response.Provider,
            Fallback = true,
            ProviderCalls = response.ProviderCalls,
            FallbackCount = Math.Max(1, response.FallbackCount),
            LatencyMs = response.LatencyMs,
            Warnings = new[] { warning },
            Usage = response.Usage,
        };
    }

    private static string? TruncateNullable(string? value, int maxLength)
    {
        return string.IsNullOrWhiteSpace(value) ? null : Truncate(value.Trim(), maxLength);
    }

    private void LogSafeResponseMetadata(BridgeDialogueResponse result)
    {
        diagnosticLogger?.Invoke(
            $"[StardewAI.Bridge] response provider={result.Provider}; " +
            $"fallback={result.Fallback.ToString().ToLowerInvariant()}; " +
            $"latencyMs={result.LatencyMs}; warningCount={result.Warnings.Count}");
    }

    async Task<BridgeDialogueResponse> IConversationTransport.SendAsync(
        ConversationRequest request,
        CancellationToken cancellationToken)
    {
        return await SendAsync(
            request.NpcId,
            request.Message,
            request.GameState,
            cancellationToken,
            request.RecentFacts,
            request.Intent,
            request.ItemContext,
            request.RelationshipWorld,
            request.Channel).ConfigureAwait(false);
    }

    public void Dispose()
    {
        if (ownsHttpClient)
        {
            httpClient.Dispose();
        }
    }

    private static void ValidateEndpoint(Uri endpoint)
    {
        if (!endpoint.IsAbsoluteUri || !endpoint.IsLoopback ||
            (endpoint.Scheme != Uri.UriSchemeHttp && endpoint.Scheme != Uri.UriSchemeHttps))
        {
            throw new ArgumentException("Bridge 地址必须是 HTTP(S) 回环地址。", nameof(endpoint));
        }
    }

    private void RememberResult(
        string npcId,
        string message,
        string intent,
        BridgeDialogueResponse result,
        NpcGameState? currentState)
    {
        if (result.Fallback)
        {
            return;
        }

        var relationshipStage = currentState is null
            ? null
            : RelationshipStageRules.ResolveKey(currentState);

        lock (memoryLock)
        {
            if (intent != ConversationIntent.Topic)
            {
                AppendHistory(npcId, new BridgeDialogueHistoryItem
                {
                    Role = "user",
                    Content = Truncate(message, MaxHistoryContentLength),
                    Intent = intent,
                    RelationshipStage = relationshipStage,
                });
            }

            AppendHistory(npcId, new BridgeDialogueHistoryItem
            {
                Role = "assistant",
                Content = Truncate(result.Reply, MaxHistoryContentLength),
                Intent = intent,
                RelationshipStage = relationshipStage,
            });

            if (currentState is not null)
            {
                previousStateByNpc[npcId] = currentState;
            }
        }
    }

    private static IReadOnlyList<string> BuildRecentFacts(
        NpcGameState? previous,
        NpcGameState? current)
    {
        if (previous is null || current is null)
        {
            return Array.Empty<string>();
        }

        var facts = new List<string>();
        AddStringChange(facts, "季节", previous.Season, current.Season);
        AddStringChange(facts, "日期", previous.Date, current.Date);
        AddStringChange(facts, "天气", previous.Weather, current.Weather);
        AddStringChange(facts, "地点", previous.Location, current.Location);
        AddIntChange(facts, "时间", previous.Time, current.Time);
        AddIntChange(facts, "好感", previous.Friendship, current.Friendship);
        AddIntChange(facts, "心级", previous.FriendshipHearts, current.FriendshipHearts);
        AddStringChange(facts, "关系", previous.Relationship, current.Relationship);
        AddStringChange(facts, "婚姻状态", previous.MarriageStatus, current.MarriageStatus);
        AddIntChange(facts, "孩子数量", previous.ChildrenCount, current.ChildrenCount);
        AddEventChanges(facts, previous.CompletedEventIds, current.CompletedEventIds);
        return facts;
    }

    private static IReadOnlyList<string> MergeRecentFacts(
        IReadOnlyList<string> stateFacts,
        IReadOnlyList<string>? memoryFacts)
    {
        var facts = stateFacts.ToList();
        foreach (var memoryFact in memoryFacts ?? Array.Empty<string>())
        {
            if (string.IsNullOrWhiteSpace(memoryFact))
            {
                continue;
            }

            facts.Add(Truncate(memoryFact.Trim(), MaxRecentFactLength));
        }

        return facts.Take(MaxRecentFactItems).ToArray();
    }

    private static void AddEventChanges(
        ICollection<string> facts,
        IReadOnlyList<string> previous,
        IReadOnlyList<string> current)
    {
        var previousSet = previous.ToHashSet(StringComparer.Ordinal);
        var currentSet = current.ToHashSet(StringComparer.Ordinal);
        if (previousSet.SetEquals(currentSet))
        {
            return;
        }

        var previousText = previousSet.Count == 0
            ? "无"
            : string.Join(", ", previousSet.OrderBy(value => value, StringComparer.Ordinal));
        var currentText = currentSet.Count == 0
            ? "无"
            : string.Join(", ", currentSet.OrderBy(value => value, StringComparer.Ordinal));
        facts.Add(Truncate(
            $"剧情事件从“{previousText}”变为“{currentText}”",
            MaxRecentFactLength));
    }

    private static RelationshipWorldSnapshot FilterRelationshipWorld(
        string npcId,
        RelationshipWorldSnapshot relationshipWorld)
    {
        var currentNpcViews = relationshipWorld.Views
            .Where(view => string.Equals(view.OwnerNpcId, npcId, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        var currentNpcRelationships = relationshipWorld.ObjectiveRelationships
            .Where(relationship =>
                string.Equals(relationship.FromNpcId, "player", StringComparison.OrdinalIgnoreCase) &&
                string.Equals(relationship.ToNpcId, npcId, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        return relationshipWorld with
        {
            ObjectiveRelationships = currentNpcRelationships,
            Views = currentNpcViews,
            Mediation = relationshipWorld.Mediation is not null &&
                string.Equals(relationshipWorld.Mediation.NpcId, npcId, StringComparison.OrdinalIgnoreCase)
                ? relationshipWorld.Mediation
                : null,
            Jealousy = relationshipWorld.Jealousy is not null &&
                string.Equals(relationshipWorld.Jealousy.NpcId, npcId, StringComparison.OrdinalIgnoreCase)
                ? relationshipWorld.Jealousy
                : null,
            OpenLoops = relationshipWorld.OpenLoops
                .Where(openLoop =>
                    string.Equals(openLoop.NpcId, npcId, StringComparison.OrdinalIgnoreCase) &&
                    (openLoop.Status == "open" || openLoop.Status == "in_progress"))
                .ToArray(),
        };
    }

    private static void AddStringChange(
        ICollection<string> facts,
        string label,
        string? previous,
        string? current)
    {
        if (!string.Equals(previous, current, StringComparison.Ordinal))
        {
            facts.Add(Truncate(
                $"{label}从“{previous ?? "未知"}”变为“{current ?? "未知"}”",
                MaxRecentFactLength));
        }
    }

    private static void AddIntChange(
        ICollection<string> facts,
        string label,
        int? previous,
        int? current)
    {
        if (previous != current)
        {
            facts.Add(Truncate(
                $"{label}从“{previous?.ToString() ?? "未知"}”变为“{current?.ToString() ?? "未知"}”",
                MaxRecentFactLength));
        }
    }

    private static string Truncate(string value, int maxLength)
    {
        return value.Length <= maxLength ? value : value[..maxLength];
    }
}
