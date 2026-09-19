using System.Net;
using System.Text;
using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class BridgeClientTests
{
    [Fact]
    public void Default_timeout_leaves_room_for_bridge_cloud_deadline()
    {
        Assert.Equal(TimeSpan.FromSeconds(60), BridgeClient.DefaultTimeout);
    }

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
        Assert.Equal("chat", requestJson.RootElement.GetProperty("intent").GetString());
    }

    [Fact]
    public async Task SendGroupAsync_posts_remote_turn_based_request_and_parses_turns()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"strategy\":\"turn_based\",\"channel\":\"remote\",\"provider\":\"fake\",\"fallback\":false,\"turns\":[{\"speakerNpcId\":\"Abigail\",\"content\":\"我有点想知道。\"}],\"providerCalls\":1,\"providerErrors\":[],\"fallbackCount\":0,\"latencyMs\":12}",
                Encoding.UTF8,
                "application/json"),
        });
        using var client = new BridgeClient(
            new HttpClient(handler),
            new Uri("http://127.0.0.1:5678"),
            groupStrategy: "turn_based");

        var response = await client.SendGroupAsync(
            new GroupDialogueRequest(
                "你们怎么看？",
                new[]
                {
                    new GroupDialogueParticipant("Abigail", "Abigail"),
                    new GroupDialogueParticipant("Emily", "Emily"),
                 },
                 "奇怪的矿石",
                 "只作为讨论方向。",
                 Array.Empty<GroupDialogueHistoryEntry>(),
                 GameState: new NpcGameState
                 {
                     NpcId = "Abigail",
                     CompletedEventIds = new[] { "384882" },
                 }));

        Assert.Equal("/api/dialogue/group", handler.Request!.RequestUri!.AbsolutePath);
        Assert.Equal("Abigail", Assert.Single(response.Turns).SpeakerNpcId);
        using var request = JsonDocument.Parse(handler.RequestBodies.Single());
        Assert.Equal("remote", request.RootElement.GetProperty("channel").GetString());
        Assert.Equal("turn_based", request.RootElement.GetProperty("strategy").GetString());
        Assert.Equal(
            "384882",
            request.RootElement.GetProperty("gameState")
                .GetProperty("completedEventIds")[0]
                .GetString());
        Assert.Equal("invitationTopic", request.RootElement.EnumerateObject()
            .Single(property => property.Name == "invitationTopic").Name);
    }

    [Fact]
    public async Task SendGroupAsync_rejects_unknown_speaker_without_exposing_content()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"strategy\":\"turn_based\",\"channel\":\"remote\",\"provider\":\"cloud\",\"fallback\":false,\"turns\":[{\"speakerNpcId\":\"Lewis\",\"content\":\"越界文本\"}],\"providerCalls\":1,\"providerErrors\":[],\"fallbackCount\":0,\"latencyMs\":1}",
                Encoding.UTF8,
                "application/json"),
        });
        using var client = new BridgeClient(new HttpClient(handler));

        var response = await client.SendGroupAsync(
            new GroupDialogueRequest(
                "你们怎么看？",
                new[]
                {
                    new GroupDialogueParticipant("Abigail", "Abigail"),
                    new GroupDialogueParticipant("Emily", "Emily"),
                },
                null,
                null,
                Array.Empty<GroupDialogueHistoryEntry>()));

        Assert.True(response.Fallback);
        Assert.Empty(response.Turns);
        Assert.DoesNotContain("越界文本", response.Warnings);
    }

    [Fact]
    public async Task SendGroupAsync_defaults_to_multi_turn_and_parses_every_turn()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"strategy\":\"multi_turn\",\"channel\":\"remote\",\"provider\":\"cloud\",\"fallback\":false,\"turns\":[{\"speakerNpcId\":\"Abigail\",\"content\":\"我最近在翻旧书。\",\"addressedTo\":[\"Emily\"]},{\"speakerNpcId\":\"Emily\",\"content\":\"那我可以帮你做书套。\"}],\"providerCalls\":1,\"providerErrors\":[],\"fallbackCount\":0,\"latencyMs\":21}",
                Encoding.UTF8,
                "application/json"),
        });
        using var client = new BridgeClient(
            new HttpClient(handler), new Uri("http://127.0.0.1:5678"));

        var response = await client.SendGroupAsync(
            new GroupDialogueRequest(
                "你们最近都在忙什么？",
                new[]
                {
                    new GroupDialogueParticipant("Abigail", "Abigail"),
                    new GroupDialogueParticipant("Emily", "Emily"),
                },
                null,
                null,
                Array.Empty<GroupDialogueHistoryEntry>()));

        using var request = JsonDocument.Parse(handler.RequestBodies.Single());
        Assert.Equal("multi_turn", request.RootElement.GetProperty("strategy").GetString());
        Assert.False(response.Fallback);
        Assert.Equal(
            new[] { "Abigail", "Emily" },
            response.Turns.Select(turn => turn.SpeakerNpcId).ToArray());
    }

    [Fact]
    public async Task SendGroupAsync_rejects_response_strategy_that_differs_from_request()
    {
        // 请求 multi_turn 却收到 turn_based：不能当成功处理，否则游戏会以为
        // 自己拿到的是自然接话流。
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"strategy\":\"turn_based\",\"channel\":\"remote\",\"provider\":\"cloud\",\"fallback\":false,\"turns\":[{\"speakerNpcId\":\"Abigail\",\"content\":\"只有一句。\"}],\"providerCalls\":1,\"providerErrors\":[],\"fallbackCount\":0,\"latencyMs\":21}",
                Encoding.UTF8,
                "application/json"),
        });
        using var client = new BridgeClient(
            new HttpClient(handler), new Uri("http://127.0.0.1:5678"));

        var response = await client.SendGroupAsync(
            new GroupDialogueRequest(
                "你们最近都在忙什么？",
                new[]
                {
                    new GroupDialogueParticipant("Abigail", "Abigail"),
                    new GroupDialogueParticipant("Emily", "Emily"),
                },
                null,
                null,
                Array.Empty<GroupDialogueHistoryEntry>()));

        Assert.True(response.Fallback);
        Assert.Empty(response.Turns);
        Assert.Contains("bridge: response mode invalid", response.Warnings);
    }

    [Fact]
    public async Task SendAsync_marks_game_requests_for_compact_prompt()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"收到\",\"provider\":\"cloud\",\"fallback\":false}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));

        await client.SendAsync(
            "Wizard",
            "你好",
            new NpcGameState { NpcId = "Wizard", DisplayName = "Rasmodia" });

        using var requestJson = JsonDocument.Parse(handler.RequestBodies.Single());
        Assert.True(requestJson.RootElement.GetProperty("compactPrompt").GetBoolean());
    }

    [Fact]
    public async Task SendAsync_logs_safe_response_metadata_without_reply_content()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"不要写入日志的回复\",\"provider\":\"cloud\",\"fallback\":false,\"latencyMs\":37,\"warnings\":[]}",
                Encoding.UTF8,
                "application/json"),
        });
        var logs = new List<string>();
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(
            httpClient,
            new Uri("http://127.0.0.1:5678"),
            diagnosticLogger: logs.Add);

        await client.SendAsync("Rasmodia", "你好");

        var log = Assert.Single(logs);
        Assert.Contains("provider=cloud", log);
        Assert.Contains("fallback=false", log);
        Assert.Contains("latencyMs=37", log);
        Assert.Contains("warningCount=0", log);
        Assert.DoesNotContain("不要写入日志的回复", log);
    }

    [Fact]
    public async Task SendAsync_posts_channel_and_parses_open_loop_signal()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"下次当面继续。\",\"provider\":\"fake\",\"fallback\":false,\"openLoop\":{\"action\":\"open\",\"loopId\":\"wizard:rune:Spring-14\",\"topic\":\"rune_review\",\"shortSummary\":\"线上留下了核对符文数据的话题\"}}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));

        var result = await client.SendAsync(
            "Wizard",
            "这件事下次继续。",
            channel: ConversationChannel.Remote);

        Assert.Equal("open", result.OpenLoop!.Action);
        using var requestJson = JsonDocument.Parse(handler.RequestBodies.Single());
        Assert.Equal("remote", requestJson.RootElement.GetProperty("channel").GetString());
    }

    [Fact]
    public async Task SendAsync_sends_only_the_current_npcs_relationship_snapshot()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"收到\",\"provider\":\"fake\",\"fallback\":false}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));
        var snapshot = new RelationshipWorldSnapshot(
            "Sophia",
            new[]
            {
                new RelationshipEdgeRecord
                {
                    FromNpcId = "player",
                    ToNpcId = "Sophia",
                    RelationType = "dating",
                },
                new RelationshipEdgeRecord
                {
                    FromNpcId = "player",
                    ToNpcId = "Alex",
                    RelationType = "married",
                    PublicEventId = "wedding:alex",
                },
            },
            new[]
            {
                new RelationshipViewRecord
                {
                    OwnerNpcId = "Sophia",
                    SubjectNpcId = "Alex",
                    RelationType = "married",
                    Visibility = "known",
                    Source = "wedding",
                },
                new RelationshipViewRecord
                {
                    OwnerNpcId = "Alex",
                    SubjectNpcId = "Sophia",
                    RelationType = "dating",
                    Visibility = "known",
                    Source = "player_statement",
                },
            },
            new RelationshipMediationRecord { NpcId = "Sophia", Status = "active" },
            new RelationshipJealousyRecord { NpcId = "Sophia", Active = true, Trigger = "time", Intensity = "light" });

        await client.SendAsync("Sophia", "我们聊聊吧。", relationshipWorld: snapshot);

        using var request = JsonDocument.Parse(handler.RequestBodies.Single());
        var world = request.RootElement.GetProperty("relationshipWorld");
        Assert.DoesNotContain(
            world.GetProperty("objectiveRelationships").EnumerateArray(),
            item => item.GetProperty("toNpcId").GetString() == "Alex");
        Assert.All(
            world.GetProperty("views").EnumerateArray(),
            item => Assert.Equal("Sophia", item.GetProperty("ownerNpcId").GetString()));
        Assert.Equal("Sophia", world.GetProperty("mediation").GetProperty("npcId").GetString());
        Assert.True(world.GetProperty("jealousy").GetProperty("active").GetBoolean());
    }

    [Fact]
    public async Task SendAsync_filters_open_loops_to_current_npc_and_active_status()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"收到\",\"provider\":\"fake\",\"fallback\":false}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));
        var snapshot = new RelationshipWorldSnapshot(
            "Sophia",
            Array.Empty<RelationshipEdgeRecord>(),
            Array.Empty<RelationshipViewRecord>(),
            null,
            null)
        {
            OpenLoops = new[]
            {
                new OpenLoopRecord
                {
                    LoopId = "sophia:one", NpcId = "Sophia", Topic = "topic",
                    OriginChannel = "remote", NextChannel = "face_to_face", Status = "open",
                    ShortSummary = "继续聊", CreatedOn = "Spring 1",
                },
                new OpenLoopRecord
                {
                    LoopId = "alex:one", NpcId = "Alex", Topic = "topic",
                    OriginChannel = "remote", NextChannel = "face_to_face", Status = "open",
                    ShortSummary = "不应泄露", CreatedOn = "Spring 1",
                },
                new OpenLoopRecord
                {
                    LoopId = "sophia:done", NpcId = "Sophia", Topic = "topic",
                    OriginChannel = "remote", NextChannel = "face_to_face", Status = "resolved",
                    ShortSummary = "已完成", CreatedOn = "Spring 1",
                },
            },
        };

        await client.SendAsync("Sophia", "继续吧。", relationshipWorld: snapshot);

        using var request = JsonDocument.Parse(handler.RequestBodies.Single());
        var loops = request.RootElement.GetProperty("relationshipWorld")
            .GetProperty("openLoops").EnumerateArray().ToArray();
        Assert.Equal("sophia:one", Assert.Single(loops).GetProperty("loopId").GetString());
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
    public async Task SendAsync_sends_item_intent_and_safe_item_context()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"看起来不错。\",\"provider\":\"fake\",\"fallback\":false,\"warnings\":[]}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));
        var item = new ItemConversationContext(
            "74",
            "黄金南瓜",
            "礼物",
            0,
            "share",
            4);

        await client.SendAsync(
            "Rasmodia",
            "我想给你看看这个。",
            new NpcGameState { NpcId = "Rasmodia", Date = "Spring 1" },
            intent: ConversationIntent.Item,
            itemContext: item);

        using var request = JsonDocument.Parse(await handler.Request!.Content!.ReadAsStringAsync());
        var root = request.RootElement;
        Assert.Equal("item", root.GetProperty("intent").GetString());
        Assert.Equal("74", root.GetProperty("itemContext").GetProperty("itemId").GetString());
        Assert.Equal("黄金南瓜", root.GetProperty("itemContext").GetProperty("displayName").GetString());
        Assert.Equal("share", root.GetProperty("itemContext").GetProperty("action").GetString());
        Assert.False(root.GetProperty("itemContext").TryGetProperty("sourcePath", out _));
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
    public async Task SendAsync_topic_request_does_not_store_internal_user_prompt_in_history()
    {
        var handler = new RecordingHandler(requestIndex => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                requestIndex == 0
                    ? "{\"reply\":\"来聊聊今天的天气吧。\",\"provider\":\"fake\",\"fallback\":false}"
                    : "{\"reply\":\"镇上的风有点大。\",\"provider\":\"fake\",\"fallback\":false}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));

        await client.SendAsync(
            "Wizard",
            string.Empty,
            intent: ConversationIntent.Topic);
        await client.SendAsync(
            "Wizard",
            string.Empty,
            intent: ConversationIntent.Topic);

        using var secondRequest = JsonDocument.Parse(handler.RequestBodies[1]);
        var history = secondRequest.RootElement.GetProperty("history").EnumerateArray().ToArray();
        Assert.Single(history);
        Assert.Equal("assistant", history[0].GetProperty("role").GetString());
        Assert.Equal("来聊聊今天的天气吧。", history[0].GetProperty("content").GetString());
        Assert.DoesNotContain(
            history,
            item => item.GetProperty("content").GetString()!.Contains("请主动"));
        Assert.Empty(secondRequest.RootElement.GetProperty("message").GetString() ?? string.Empty);
        Assert.Equal("topic", secondRequest.RootElement.GetProperty("intent").GetString());
    }

    [Fact]
    public async Task SendAsync_history_keeps_intent_and_relationship_stage_provenance()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"收到\",\"provider\":\"fake\",\"fallback\":false}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));
        var highState = new NpcGameState { NpcId = "Sophia", FriendshipHearts = 8 };
        var lowState = new NpcGameState { NpcId = "Sophia", FriendshipHearts = 3 };

        await client.SendAsync("Sophia", string.Empty, highState, intent: ConversationIntent.Topic);
        await client.SendAsync("Sophia", "我带了葡萄酒。", highState, intent: ConversationIntent.Item);
        await client.SendAsync("Sophia", "今天忙吗？", lowState);
        await client.SendAsync("Sophia", "现在聊聊吧。", highState);

        using var request = JsonDocument.Parse(handler.RequestBodies[3]);
        var history = request.RootElement.GetProperty("history").EnumerateArray().ToArray();

        Assert.Equal("topic", history[0].GetProperty("intent").GetString());
        Assert.Equal("close", history[0].GetProperty("relationshipStage").GetString());
        Assert.Equal("item", history[1].GetProperty("intent").GetString());
        Assert.Equal("item", history[2].GetProperty("intent").GetString());
        Assert.Equal("chat", history[3].GetProperty("intent").GetString());
        Assert.Equal("acquaintance", history[3].GetProperty("relationshipStage").GetString());
        Assert.Equal("chat", history[4].GetProperty("intent").GetString());
        Assert.Equal("acquaintance", history[4].GetProperty("relationshipStage").GetString());
    }

    [Fact]
    public async Task SendAsync_topic_request_rejects_internal_prompt_echo_from_bridge()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"请主动找一个自然的话题啊，这附近的花草长得还不错。\",\"provider\":\"cloud\",\"fallback\":false}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));

        var result = await client.SendAsync(
            "Wizard",
            string.Empty,
            intent: ConversationIntent.Topic);

        Assert.True(result.Fallback);
        Assert.Equal("offline", result.Provider);
        Assert.DoesNotContain("主动找一个自然的话题", result.Reply);
        Assert.Contains("topic prompt echo", result.Warnings.Single());
    }

    [Fact]
    public async Task SendAsync_topic_request_rejects_alternate_internal_prompt_echo_from_bridge()
    {
        var handler = new RecordingHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"reply\":\"请找一个自然的话题啊，今天的天气不错。\",\"provider\":\"cloud\",\"fallback\":false}",
                Encoding.UTF8,
                "application/json"),
        });
        using var httpClient = new HttpClient(handler);
        using var client = new BridgeClient(httpClient, new Uri("http://127.0.0.1:5678"));

        var result = await client.SendAsync(
            "Wizard",
            string.Empty,
            intent: ConversationIntent.Topic);

        Assert.True(result.Fallback);
        Assert.Equal("offline", result.Provider);
        Assert.DoesNotContain("请找一个自然的话题", result.Reply);
        Assert.Contains("topic prompt echo", result.Warnings.Single());
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
