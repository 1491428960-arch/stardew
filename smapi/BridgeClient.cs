using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace StardewAI.NPC;

public sealed class BridgeDialogueRequest
{
    [JsonPropertyName("npcId")]
    public string NpcId { get; init; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;

    [JsonPropertyName("intent")]
    public string Intent { get; init; } = ConversationIntent.Chat;

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
}

public sealed class BridgeDialogueHistoryItem
{
    [JsonPropertyName("role")]
    public string Role { get; init; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; init; } = string.Empty;
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

public sealed class BridgeClient : IDisposable, IConversationTransport
{
    public static readonly Uri DefaultEndpoint = new("http://127.0.0.1:5678");
    public static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(15);
    private const int MaxHistoryItems = 6;
    private const int MaxHistoryContentLength = 240;
    private const int MaxMessageLength = 2000;
    private const int MaxRecentFactLength = 240;
    private const int MaxRecentFactItems = 20;

    private readonly HttpClient httpClient;
    private readonly bool ownsHttpClient;
    private readonly Uri dialogueEndpoint;
    private readonly object memoryLock = new();
    private readonly Dictionary<string, List<BridgeDialogueHistoryItem>> historyByNpc = new();
    private readonly Dictionary<string, NpcGameState> previousStateByNpc = new();

    public BridgeClient(
        HttpClient? httpClient = null,
        Uri? endpoint = null,
        TimeSpan? timeout = null)
    {
        var baseEndpoint = endpoint ?? DefaultEndpoint;
        ValidateEndpoint(baseEndpoint);

        this.httpClient = httpClient ?? new HttpClient();
        ownsHttpClient = httpClient is null;
        this.httpClient.Timeout = timeout ?? DefaultTimeout;
        var normalizedBaseEndpoint = new Uri(
            baseEndpoint.AbsoluteUri.TrimEnd('/') + "/",
            UriKind.Absolute);
        dialogueEndpoint = new Uri(normalizedBaseEndpoint, "api/dialogue/test");
    }

    public async Task<BridgeDialogueResponse> SendAsync(
        string npcId,
        string message,
        object? gameState = null,
        CancellationToken cancellationToken = default,
        IReadOnlyList<string>? memoryFacts = null,
        string intent = ConversationIntent.Chat,
        ItemConversationContext? itemContext = null)
    {
        if (string.IsNullOrWhiteSpace(npcId))
        {
            throw new ArgumentException("NPC ID 不能为空。", nameof(npcId));
        }

        if (string.IsNullOrWhiteSpace(message))
        {
            throw new ArgumentException("消息不能为空。", nameof(message));
        }

        try
        {
            var npcGameState = gameState as NpcGameState;
            var boundedMessage = Truncate(message, MaxMessageLength);
            BridgeDialogueRequest request;
            lock (memoryLock)
            {
                request = new BridgeDialogueRequest
                {
                    NpcId = npcId,
                    Message = boundedMessage,
                    Intent = string.IsNullOrWhiteSpace(intent) ? ConversationIntent.Chat : intent,
                    ItemContext = itemContext,
                    DisplayName = npcGameState?.DisplayName,
                    SourceMods = npcGameState?.SourceMods ?? Array.Empty<string>(),
                    GameState = gameState,
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

            RememberResult(npcId, boundedMessage, result, npcGameState);
            return result;
        }
        catch (TaskCanceledException)
        {
            var result = BridgeDialogueResponse.Offline("bridge: timeout");
            RememberResult(npcId, Truncate(message, MaxMessageLength), result, gameState as NpcGameState);
            return result;
        }
        catch (HttpRequestException exception)
        {
            var result = BridgeDialogueResponse.Offline($"bridge: offline ({exception.Message})");
            RememberResult(npcId, Truncate(message, MaxMessageLength), result, gameState as NpcGameState);
            return result;
        }
        catch (JsonException exception)
        {
            var result = BridgeDialogueResponse.Offline($"bridge: invalid JSON ({exception.Message})");
            RememberResult(npcId, Truncate(message, MaxMessageLength), result, gameState as NpcGameState);
            return result;
        }
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
            request.ItemContext).ConfigureAwait(false);
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
        BridgeDialogueResponse result,
        NpcGameState? currentState)
    {
        if (result.Fallback)
        {
            return;
        }

        lock (memoryLock)
        {
            if (!historyByNpc.TryGetValue(npcId, out var history))
            {
                history = new List<BridgeDialogueHistoryItem>();
                historyByNpc[npcId] = history;
            }

            history.Add(new BridgeDialogueHistoryItem
            {
                Role = "user",
                Content = Truncate(message, MaxHistoryContentLength),
            });
            history.Add(new BridgeDialogueHistoryItem
            {
                Role = "assistant",
                Content = Truncate(result.Reply, MaxHistoryContentLength),
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
