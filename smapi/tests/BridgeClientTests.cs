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
    public async Task SendAsync_preserves_a_custom_bridge_base_path()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"收到\",\"provider\":\"fake\",\"fallback\":false}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:6000/base"));

        await client.SendAsync("Rasmodia", "你好");

        Assert.Equal(
            "http://127.0.0.1:6000/base/api/dialogue/test",
            handler.Request!.RequestUri!.ToString());
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
            FriendshipHearts = 5,
            Relationship = "friend",
            MarriageStatus = "dating",
            ChildrenCount = 0,
            CompletedEventIds = new[] { "evt-1" },
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
        Assert.Equal(5, root.GetProperty("gameState").GetProperty("friendshipHearts").GetInt32());
        Assert.Equal("friend", root.GetProperty("gameState").GetProperty("relationship").GetString());
        Assert.Equal("dating", root.GetProperty("gameState").GetProperty("marriageStatus").GetString());
        Assert.Equal(0, root.GetProperty("gameState").GetProperty("childrenCount").GetInt32());
        Assert.Equal("evt-1", root.GetProperty("gameState").GetProperty("completedEventIds")[0].GetString());
        Assert.Equal(
            new[] { "SVE", "FlashShifter.SVECode" },
            root.GetProperty("gameState").GetProperty("sourceMods").EnumerateArray()
                .Select(item => item.GetString())
            .ToArray());
    }

    [Fact]
    public async Task SendAsync_adds_persistent_memory_facts_to_recent_facts()
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

        await client.SendAsync(
            "Sophia",
            "你好",
            cancellationToken: default,
            memoryFacts: new[] { "记忆（Spring 14）：玩家关心了葡萄园。" });

        using var request = JsonDocument.Parse(await handler.Request!.Content!.ReadAsStringAsync());
        var facts = request.RootElement.GetProperty("recentFacts").EnumerateArray()
            .Select(item => item.GetString())
            .ToArray();
        Assert.Contains(facts, fact => fact == "记忆（Spring 14）：玩家关心了葡萄园。");
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
            FriendshipHearts = 5,
            Relationship = "friend",
            MarriageStatus = "dating",
            ChildrenCount = 0,
            CompletedEventIds = new[] { "evt-1" },
        };
        var secondState = new NpcGameState
        {
            NpcId = "Wizard",
            DisplayName = "Rasmodia",
            Date = "15",
            Weather = "rain",
            Location = "Town",
            Friendship = 140,
            FriendshipHearts = 6,
            Relationship = "dating",
            MarriageStatus = "married",
            ChildrenCount = 1,
            CompletedEventIds = new[] { "evt-1", "evt-2" },
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
        Assert.Contains(recentFacts, fact => fact!.Contains("心级"));
        Assert.Contains(recentFacts, fact => fact!.Contains("婚姻状态"));
        Assert.Contains(recentFacts, fact => fact!.Contains("孩子数量"));
        Assert.Contains(recentFacts, fact => fact!.Contains("剧情事件"));
    }

    [Fact]
    public async Task SendAsync_does_not_remember_failed_fallback_before_next_success()
    {
        var handler = new RecordingHandler(requestIndex => requestIndex == 0
            ? new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
            : new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    "{\"reply\":\"成功回复\",\"provider\":\"fake\",\"fallback\":false,\"warnings\":[]}",
                    Encoding.UTF8,
                    "application/json"),
            });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));
        var state = new NpcGameState
        {
            NpcId = "Wizard",
            DisplayName = "Rasmodia",
            Location = "WizardTower",
            Friendship = 128,
        };

        var failed = await client.SendAsync("Wizard", "失败的问题", state);
        var succeeded = await client.SendAsync("Wizard", "成功的问题", state);

        Assert.True(failed.Fallback);
        Assert.False(succeeded.Fallback);
        using var secondRequest = JsonDocument.Parse(handler.RequestBodies[1]);
        Assert.Empty(secondRequest.RootElement.GetProperty("history").EnumerateArray());
    }

    [Fact]
    public async Task SendAsync_does_not_remember_failed_state_before_next_success()
    {
        var handler = new RecordingHandler(requestIndex => requestIndex == 0
            ? new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
            : new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    "{\"reply\":\"成功回复\",\"provider\":\"fake\",\"fallback\":false,\"warnings\":[]}",
                    Encoding.UTF8,
                    "application/json"),
            });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));
        var failedState = new NpcGameState
        {
            NpcId = "Wizard",
            Location = "WizardTower",
            Friendship = 128,
        };
        var succeededState = new NpcGameState
        {
            NpcId = "Wizard",
            Location = "Town",
            Friendship = 140,
        };

        await client.SendAsync("Wizard", "失败的问题", failedState);
        await client.SendAsync("Wizard", "成功的问题", succeededState);

        using var secondRequest = JsonDocument.Parse(handler.RequestBodies[1]);
        Assert.Empty(secondRequest.RootElement.GetProperty("recentFacts").EnumerateArray());
    }

    [Fact]
    public async Task SendAsync_limits_message_history_and_recent_fact_lengths()
    {
        var handler = new RecordingHandler(requestIndex => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                JsonSerializer.Serialize(new BridgeDialogueResponse
                {
                    Reply = requestIndex == 0 ? new string('回', 300) : "成功回复",
                    Provider = "fake",
                    Fallback = false,
                }),
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));
        var firstState = new NpcGameState { NpcId = "Wizard", Location = new string('A', 300) };
        var secondState = new NpcGameState { NpcId = "Wizard", Location = new string('B', 300) };
        var longMessage = new string('问', 2500);

        await client.SendAsync("Wizard", longMessage, firstState);
        await client.SendAsync("Wizard", "第二次问题", secondState);

        using var firstRequest = JsonDocument.Parse(handler.RequestBodies[0]);
        Assert.Equal(2000, firstRequest.RootElement.GetProperty("message").GetString()!.Length);
        using var secondRequest = JsonDocument.Parse(handler.RequestBodies[1]);
        var history = secondRequest.RootElement.GetProperty("history").EnumerateArray().ToArray();
        Assert.All(history, item => Assert.InRange(item.GetProperty("content").GetString()!.Length, 0, 240));
        Assert.All(
            secondRequest.RootElement.GetProperty("recentFacts").EnumerateArray(),
            item => Assert.InRange(item.GetString()!.Length, 0, 240));
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
