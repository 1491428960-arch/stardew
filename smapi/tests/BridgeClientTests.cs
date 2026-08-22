using System.Net;
using System.Text;
using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class BridgeClientTests
{
    [Fact]
    public async Task SendAsync_posts_required_json_and_parses_success_response()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"Rasmodia：你好\",\"provider\":\"fake\",\"fallback\":false,\"latencyMs\":37,\"warnings\":[]}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));

        var result = await client.SendAsync("Rasmodia", "你好");

        Assert.Equal("Rasmodia：你好", result.Reply);
        Assert.Equal("fake", result.Provider);
        Assert.False(result.Fallback);
        Assert.Equal(37, result.LatencyMs);
        Assert.NotNull(handler.Request);
        Assert.Equal(HttpMethod.Post, handler.Request!.Method);
        Assert.Equal("http://127.0.0.1:5678/api/dialogue/test", handler.Request.RequestUri!.ToString());
        using var requestJson = JsonDocument.Parse(await handler.Request.Content!.ReadAsStringAsync());
        Assert.Equal("Rasmodia", requestJson.RootElement.GetProperty("npcId").GetString());
        Assert.Equal("你好", requestJson.RootElement.GetProperty("message").GetString());
    }

    [Fact]
    public async Task SendAsync_preserves_npc_game_state_and_legacy_identity_fields()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"收到\",\"provider\":\"fake\",\"fallback\":false,\"warnings\":[]}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));
        var gameState = new NpcGameState
        {
            NpcId = "Wizard",
            DisplayName = "Rasmodia",
            Season = "Summer",
            Date = "14",
            Weather = "rain",
            Time = 1830,
            Location = "WizardTower",
            Friendship = 128,
            Relationship = "friend",
            SourceMods = new[] { "SVE", "FlashShifter.SVECode" },
        };

        await client.SendAsync("Wizard", "你好", gameState);

        using var requestJson = JsonDocument.Parse(await handler.Request!.Content!.ReadAsStringAsync());
        var root = requestJson.RootElement;
        Assert.Equal("Rasmodia", root.GetProperty("displayName").GetString());
        Assert.Equal(
            new[] { "SVE", "FlashShifter.SVECode" },
            root.GetProperty("sourceMods").EnumerateArray()
                .Select(item => item.GetString())
                .ToArray());
        Assert.Equal("Rasmodia", root.GetProperty("gameState").GetProperty("displayName").GetString());
        Assert.Equal("Summer", root.GetProperty("gameState").GetProperty("season").GetString());
        Assert.Equal("14", root.GetProperty("gameState").GetProperty("date").GetString());
        Assert.Equal("rain", root.GetProperty("gameState").GetProperty("weather").GetString());
        Assert.Equal(1830, root.GetProperty("gameState").GetProperty("time").GetInt32());
        Assert.Equal("WizardTower", root.GetProperty("gameState").GetProperty("location").GetString());
        Assert.Equal(128, root.GetProperty("gameState").GetProperty("friendship").GetInt32());
        Assert.Equal("friend", root.GetProperty("gameState").GetProperty("relationship").GetString());
        Assert.Equal(
            new[] { "SVE", "FlashShifter.SVECode" },
            root.GetProperty("gameState").GetProperty("sourceMods").EnumerateArray()
                .Select(item => item.GetString())
            .ToArray());
    }

    [Fact]
    public async Task SendAsync_sends_previous_history_and_state_change_facts_on_second_call()
    {
        var handler = new RecordingHandler(requestIndex => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                requestIndex == 0
                    ? "{\"reply\":\"第一次回复\",\"provider\":\"fake\",\"fallback\":false,\"warnings\":[]}"
                    : "{\"reply\":\"第二次回复\",\"provider\":\"fake\",\"fallback\":false,\"warnings\":[]}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));
        var firstState = new NpcGameState
        {
            NpcId = "Wizard",
            DisplayName = "Rasmodia",
            Date = "14",
            Weather = "clear",
            Location = "WizardTower",
            Friendship = 128,
            Relationship = "friend",
        };
        var secondState = new NpcGameState
        {
            NpcId = "Wizard",
            DisplayName = "Rasmodia",
            Date = "15",
            Weather = "rain",
            Location = "Town",
            Friendship = 140,
            Relationship = "dating",
        };

        await client.SendAsync("Wizard", "第一次问题", firstState);
        await client.SendAsync("Wizard", "第二次问题", secondState);

        Assert.Equal(2, handler.RequestBodies.Count);
        using var firstRequest = JsonDocument.Parse(handler.RequestBodies[0]);
        Assert.Empty(firstRequest.RootElement.GetProperty("recentFacts").EnumerateArray());
        using var secondRequest = JsonDocument.Parse(handler.RequestBodies[1]);
        var root = secondRequest.RootElement;
        var history = root.GetProperty("history").EnumerateArray().ToArray();
        Assert.Equal(2, history.Length);
        Assert.Equal("user", history[0].GetProperty("role").GetString());
        Assert.Equal("第一次问题", history[0].GetProperty("content").GetString());
        Assert.Equal("assistant", history[1].GetProperty("role").GetString());
        Assert.Equal("第一次回复", history[1].GetProperty("content").GetString());
        var recentFacts = root.GetProperty("recentFacts").EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => item is not null)
            .ToArray();
        Assert.NotEmpty(recentFacts);
        Assert.Contains(recentFacts, fact => fact!.Contains("地点"));
        Assert.Contains(recentFacts, fact => fact!.Contains("WizardTower"));
        Assert.Contains(recentFacts, fact => fact!.Contains("Town"));
    }

    [Fact]
    public async Task SendAsync_returns_offline_fallback_for_service_unavailable()
    {
        using var httpClient = new HttpClient(
            new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)));
        var client = new BridgeClient(httpClient);

        var result = await client.SendAsync("Rasmodia", "你好");

        Assert.True(result.Fallback);
        Assert.Equal("offline", result.Provider);
        Assert.Contains("503", result.Warnings.Single());
        Assert.NotEmpty(result.Reply);
    }

    [Fact]
    public async Task SendAsync_returns_offline_fallback_for_timeout()
    {
        using var httpClient = new HttpClient(
            new ThrowingHandler(new TaskCanceledException("simulated timeout")));
        var client = new BridgeClient(httpClient);

        var result = await client.SendAsync("Rasmodia", "你好");

        Assert.True(result.Fallback);
        Assert.Equal("offline", result.Provider);
        Assert.Contains("timeout", result.Warnings.Single(), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Constructor_rejects_non_loopback_endpoint()
    {
        using var httpClient = new HttpClient(new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)));

        Assert.Throws<ArgumentException>(() => new BridgeClient(httpClient, new Uri("http://example.com")));
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        public RecordingHandler(Func<int, HttpResponseMessage> responder)
        {
            this.responder = responder;
        }

        public HttpRequestMessage? Request { get; private set; }

        public List<string> RequestBodies { get; } = new();

        private readonly Func<int, HttpResponseMessage> responder;

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Request = request;
            RequestBodies.Add(request.Content?.ReadAsStringAsync(cancellationToken).GetAwaiter().GetResult() ?? "");
            return Task.FromResult(responder(RequestBodies.Count - 1));
        }
    }

    private sealed class ThrowingHandler : HttpMessageHandler
    {
        private readonly Exception exception;

        public ThrowingHandler(Exception exception)
        {
            this.exception = exception;
        }

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            return Task.FromException<HttpResponseMessage>(exception);
        }
    }
}
