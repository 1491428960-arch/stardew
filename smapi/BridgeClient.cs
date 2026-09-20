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
    private const int MaxHistoryItems = 6;
    private const int MaxHistoryContentLength = 240;
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
    private readonly Action<string>? diagnosticLogger;
    // 线上群聊策略由配置决定：默认自然接话流（multi_turn），turn_based 为回退选项。
    private readonly string groupStrategy = ModConfig.MultiTurnGroupStrategy;
    private readonly object memoryLock = new();
    private readonly Dictionary<string, List<BridgeDialogueHistoryItem>> historyByNpc = new();
    private readonly Dictionary<string, NpcGameState> previousStateByNpc = new();

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

        var boundedHistory = (request.History ?? Array.Empty<GroupDialogueHistoryEntry>())
            .Take(MaxHistoryItems)
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
            RememberGroupTurn(participants, request.Message, result);
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
    /// 群聊结束后，把每个参与者自己说过的内容**合并成一条**写进它自己的记忆。
    /// 只记本人发言：别人的话不进这一份记忆；一次群聊最多占一条，
    /// 免得随口聊的把私聊记忆挤出 6 条窗口。
    /// </summary>
    private void RememberGroupTurn(
        IReadOnlyList<GroupDialogueParticipant> participants,
        string playerMessage,
        BridgeGroupDialogueResponse result)
    {
        if (result.Fallback || result.Turns.Count == 0)
        {
            return;
        }

        lock (memoryLock)
        {
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

                if (!historyByNpc.TryGetValue(npcId, out var history))
                {
                    history = new List<BridgeDialogueHistoryItem>();
                    historyByNpc[npcId] = history;
                }

                var stage = participant.GameState is null
                    ? null
                    : RelationshipStageRules.ResolveKey(participant.GameState);
                var joined = string.Join(" ", spoken);
                var summary = string.IsNullOrWhiteSpace(playerMessage)
                    ? $"群里我说：“{joined}”"
                    : $"群里玩家说：“{playerMessage.Trim()}”；我回应：“{joined}”";
                history.Add(new BridgeDialogueHistoryItem
                {
                    Role = "assistant",
                    Content = Truncate(summary, MaxHistoryContentLength),
                    RelationshipStage = stage,
                });

                if (history.Count > MaxHistoryItems)
                {
                    history.RemoveRange(0, history.Count - MaxHistoryItems);
                }
            }
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
            if (!historyByNpc.TryGetValue(npcId, out var history))
            {
                history = new List<BridgeDialogueHistoryItem>();
                historyByNpc[npcId] = history;
            }

            if (intent != ConversationIntent.Topic)
            {
                history.Add(new BridgeDialogueHistoryItem
                {
                    Role = "user",
                    Content = Truncate(message, MaxHistoryContentLength),
                    Intent = intent,
                    RelationshipStage = relationshipStage,
                });
            }
            history.Add(new BridgeDialogueHistoryItem
            {
                Role = "assistant",
                Content = Truncate(result.Reply, MaxHistoryContentLength),
                Intent = intent,
                RelationshipStage = relationshipStage,
            });
            if (history.Count > MaxHistoryItems)
            {
                history.RemoveRange(0, history.Count - MaxHistoryItems);
            }

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
