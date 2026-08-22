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

    [JsonPropertyName("displayName")]
    public string? DisplayName { get; init; }

    [JsonPropertyName("sourceMods")]
    public IReadOnlyList<string> SourceMods { get; init; } = Array.Empty<string>();

    [JsonPropertyName("gameState")]
    public object? GameState { get; init; }
}

public sealed class BridgeDialogueResponse
{
    [JsonPropertyName("reply")]
    public string Reply { get; init; } = string.Empty;

    [JsonPropertyName("provider")]
    public string Provider { get; init; } = string.Empty;

    [JsonPropertyName("fallback")]
    public bool Fallback { get; init; }

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

public sealed class BridgeClient : IDisposable
{
    public static readonly Uri DefaultEndpoint = new("http://127.0.0.1:5678");
    public static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(15);

    private readonly HttpClient httpClient;
    private readonly bool ownsHttpClient;
    private readonly Uri dialogueEndpoint;

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
        dialogueEndpoint = new Uri(baseEndpoint, "/api/dialogue/test");
    }

    public async Task<BridgeDialogueResponse> SendAsync(
        string npcId,
        string message,
        object? gameState = null,
        CancellationToken cancellationToken = default)
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
            using var response = await httpClient.PostAsJsonAsync(
                dialogueEndpoint,
                new BridgeDialogueRequest
                {
                    NpcId = npcId,
                    Message = message,
                    DisplayName = npcGameState?.DisplayName,
                    SourceMods = npcGameState?.SourceMods ?? Array.Empty<string>(),
                    GameState = gameState,
                },
                cancellationToken);

            if (!response.IsSuccessStatusCode)
            {
                return BridgeDialogueResponse.Offline(
                    $"bridge: HTTP {(int)response.StatusCode} {response.ReasonPhrase}".Trim());
            }

            var result = await response.Content.ReadFromJsonAsync<BridgeDialogueResponse>(
                cancellationToken: cancellationToken);
            if (result is null || string.IsNullOrWhiteSpace(result.Reply))
            {
                return BridgeDialogueResponse.Offline("bridge: 响应缺少 reply。");
            }

            return result;
        }
        catch (TaskCanceledException)
        {
            return BridgeDialogueResponse.Offline("bridge: timeout");
        }
        catch (HttpRequestException exception)
        {
            return BridgeDialogueResponse.Offline($"bridge: offline ({exception.Message})");
        }
        catch (JsonException exception)
        {
            return BridgeDialogueResponse.Offline($"bridge: invalid JSON ({exception.Message})");
        }
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
}
