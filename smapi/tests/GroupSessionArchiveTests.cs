using System.Diagnostics;
using System.Net;
using System.Text;
using System.Text.Json;
using StardewAI.NPC;
using Xunit;
using Xunit.Abstractions;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 「群聊场次」的存档形态与落盘往返：<see cref="ChatHistoryArchive"/> 的
/// <c>groupSessions</c> 字段、<see cref="BridgeClient"/> 的写入与读回。
///
/// 这里钉的四件事：
/// 1. **一场群聊 = 一条记录 + 完整发言序列**，关掉游戏再进来翻得到；
/// 2. **老档案兼容**：没有这个字段的档案照常读、不刷警告；从没开过群聊的新档案
///    与加这个字段之前**逐字节相同**（体积预算用例的数字也因此不漂）；
/// 3. **降级**：坏 JSON / 不认识的版本 / 别的存档 / 手改坏的单条场次 —— 一律空手开局，不崩；
/// 4. **不重复、不进请求体**：群聊不再往按 NPC 的条目里写摘要，
///    显示专用的序号也绝不出现在发给模型的 history 里。
/// </summary>
public sealed class GroupSessionArchiveTests
{
    private readonly ITestOutputHelper output;

    public GroupSessionArchiveTests(ITestOutputHelper output)
    {
        this.output = output;
    }

    // ── 存档往返 ──────────────────────────────────────────────────────────────

    [Fact]
    public void Round_trip_keeps_the_whole_session_in_order()
    {
        var sessions = new[] { Session("invite-1") };

        var json = ChatHistoryArchive.Serialize(null, sessions, "MyFarm_123456789");
        var loaded = ChatHistoryArchive.Load(json, "MyFarm_123456789");

        Assert.Empty(loaded.Warnings);
        var session = Assert.Single(loaded.Sessions);
        Assert.Equal("invite-1", session.SessionId);
        Assert.Equal("公共话题", session.Title);
        Assert.Equal("最近的公共小事", session.Topic);        Assert.Equal("秋 12", session.DateLabel);
        Assert.Equal(132, session.TotalDays);
        Assert.Equal(new[] { "Abigail", "Emily" }, session.Participants);
        Assert.Equal(new[] { "阿比盖尔", "艾米丽" }, session.ParticipantDisplayNames);
        Assert.Equal(
            new[] { "你们怎么看？", "我也这么想。", "那你呢？" },
            session.Lines.Select(line => line.Content).ToArray());
        Assert.Equal(
            new[] { "player", "npc", "npc" },
            session.Lines.Select(line => line.SpeakerType).ToArray());
        Assert.Equal(3, loaded.SessionLineCount);
    }

    [Fact]
    public void Sessions_and_private_history_travel_in_the_same_payload()
    {
        var history = new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
        {
            ["Abigail"] = new[]
            {
                new BridgeDialogueHistoryItem { Role = "user", Content = "私聊一句", Sequence = 1 },
            },
        };

        var loaded = ChatHistoryArchive.Load(
            ChatHistoryArchive.Serialize(history, new[] { Session("invite-1") }, "MyFarm_1"),
            "MyFarm_1");

        Assert.Equal("私聊一句", Assert.Single(loaded.History["Abigail"]).Content);
        Assert.Single(loaded.Sessions);
    }

    [Fact]
    public void Archive_without_sessions_is_written_exactly_as_before()
    {
        // 从没开过群聊的档案里不该出现 groupSessions 字段：这样它与加这个字段之前逐字节相同
        // （体积预算用例的数字也不会漂），老版 DLL 读它更是毫无差别。
        var json = ChatHistoryArchive.Serialize(
            new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
            {
                ["Abigail"] = new[] { new BridgeDialogueHistoryItem { Role = "user", Content = "在吗" } },
            },
            "MyFarm_1");

        Assert.DoesNotContain("groupSessions", json);
        Assert.DoesNotContain("sequence", json);
    }

    [Fact]
    public void Empty_session_is_not_written_into_the_payload()
    {
        // 「进过 F9 但一句话都没说」不该在存档里占位，也不该在 F8 里留下一行光秃秃的抬头。
        var json = ChatHistoryArchive.Serialize(
            null,
            new[] { Session("invite-1") with { Lines = Array.Empty<GroupDialogueHistoryEntry>() } },
            "MyFarm_1");

        Assert.DoesNotContain("groupSessions", json);
        Assert.Empty(ChatHistoryArchive.Load(json, "MyFarm_1").Sessions);
    }

    [Fact]
    public void Archive_written_before_sessions_existed_still_loads()
    {
        // 「老档案」= 加场次字段之前写下的那份 JSON：只有 schemaVersion / saveId / byNpc。
        const string oldJson = "{\"schemaVersion\":1,\"saveId\":\"1\",\"byNpc\":{\"Abigail\":["
            + "{\"role\":\"user\",\"content\":\"早上好\"}]}}";

        var loaded = ChatHistoryArchive.Load(oldJson, "MyFarm_1");

        Assert.Empty(loaded.Warnings);
        Assert.Equal("早上好", Assert.Single(loaded.History["Abigail"]).Content);
        Assert.Empty(loaded.Sessions);
        Assert.Equal(0, loaded.SessionLineCount);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Missing_payload_starts_empty_and_silent(string? json)
    {
        var loaded = ChatHistoryArchive.Load(json, "MyFarm_1");

        Assert.Empty(loaded.History);
        Assert.Empty(loaded.Sessions);
        Assert.Empty(loaded.Warnings);
    }

    [Theory]
    [InlineData("{ this is not json")]
    [InlineData("[]")]
    [InlineData("42")]
    public void Broken_payload_degrades_to_empty_with_a_warning(string json)
    {
        var loaded = ChatHistoryArchive.Load(json, "MyFarm_1");

        Assert.Empty(loaded.History);
        Assert.Empty(loaded.Sessions);
        Assert.Equal(0, loaded.SessionLineCount);
        Assert.Single(loaded.Warnings);
    }

    [Fact]
    public void Unsupported_schema_version_drops_the_sessions_too()
    {
        var loaded = ChatHistoryArchive.Load(
            "{\"schemaVersion\":99,\"saveId\":\"1\",\"byNpc\":{},"
            + "\"groupSessions\":[{\"sessionId\":\"invite-1\",\"participants\":[\"Abigail\"],"
            + "\"lines\":[{\"speakerType\":\"npc\",\"speakerId\":\"Abigail\",\"content\":\"在。\"}]}]}",
            "MyFarm_1");

        Assert.Empty(loaded.Sessions);
        Assert.Contains(loaded.Warnings, warning => warning.Contains("schema version"));
    }

    [Fact]
    public void Sessions_from_another_save_are_dropped()
    {
        var json = ChatHistoryArchive.Serialize(null, new[] { Session("invite-1") }, "MyFarm_111");

        var loaded = ChatHistoryArchive.Load(json, "OtherFarm_222");

        Assert.Empty(loaded.Sessions);
        Assert.Contains(loaded.Warnings, warning => warning.Contains("another save"));
    }

    [Fact]
    public void Unusable_sessions_are_dropped_with_a_warning_but_the_rest_survives()
    {
        // 存档是可被外部编辑的输入：坏的那几条丢掉，好的照读，谁也不许拦住载入。
        var json = "{\"schemaVersion\":1,\"saveId\":\"1\",\"byNpc\":{},"
            + "\"groupSessions\":["
            + "{\"sessionId\":\"\",\"participants\":[\"Abigail\"],\"lines\":[{\"speakerType\":\"npc\",\"speakerId\":\"Abigail\",\"content\":\"没有身份。\"}]},"
            + "{\"sessionId\":\"invite-2\",\"participants\":[],\"lines\":[{\"speakerType\":\"npc\",\"speakerId\":\"Abigail\",\"content\":\"没有名单。\"}]},"
            + "{\"sessionId\":\"invite-3\",\"participants\":[\"Abigail\"],\"lines\":[]},"
            + "{\"sessionId\":\"invite-4\",\"participants\":[\"Abigail\"],\"lines\":[{\"speakerType\":\"npc\",\"speakerId\":\"Abigail\",\"content\":\"这条是好的。\"}]}"
            + "]}";

        var loaded = ChatHistoryArchive.Load(json, "MyFarm_1");

        Assert.Equal("invite-4", Assert.Single(loaded.Sessions).SessionId);
        Assert.Contains(
            loaded.Warnings,
            warning => warning.Contains("3 unusable group sessions"));
    }

    [Fact]
    public void Chinese_stays_readable_in_session_lines_too()
    {
        var json = ChatHistoryArchive.Serialize(null, new[] { Session("invite-1") }, "MyFarm_1");

        Assert.Contains("你们怎么看？", json);
        Assert.DoesNotContain("\\u", json);
    }

    // ── 落盘往返（BridgeClient 两端）────────────────────────────────────────────

    [Fact]
    public async Task Group_session_survives_a_client_restart()
    {
        var first = CreateClient(out _);
        await SendGroupAsync(first, "invite-1", "你们怎么看？");
        await SendGroupAsync(first, "invite-1", "那你呢？");
        await SendGroupAsync(first, "invite-1", "散了吧。");

        var saved = first.SerializeDisplayHistory("Farm_1");
        Assert.Equal(6, Assert.Single(first.RecentGroupSessions("Abigail")).Lines.Count);
        first.Dispose();

        // 第二天载入同一个存档：整场群聊从存档里回来。
        var second = CreateClient(out _);
        var loaded = second.LoadDisplayHistory(saved, "Farm_1");

        Assert.Empty(loaded.Warnings);
        var session = Assert.Single(second.RecentGroupSessions("Abigail"));
        Assert.Equal(
            new[]
            {
                "你们怎么看？", "回应：你们怎么看？",
                "那你呢？", "回应：那你呢？",
                "散了吧。", "回应：散了吧。",
            },
            session.Lines.Select(line => line.Content).ToArray());
        // 两位在场的 NPC 都能在自己的面板里翻到这一场。
        Assert.Single(second.RecentGroupSessions("Emily"));
        Assert.Empty(second.RecentGroupSessions("Penny"));
    }

    [Fact]
    public async Task Two_invitations_stay_two_sessions()
    {
        var client = CreateClient(out _);
        await SendGroupAsync(client, "invite-1", "第一场的问题");
        await SendGroupAsync(client, "invite-2", "第二场的问题");

        var sessions = client.RecentGroupSessions("Abigail");

        Assert.Equal(2, sessions.Count);
        Assert.Equal(new[] { "invite-1", "invite-2" }, sessions.Select(item => item.SessionId).ToArray());
        Assert.Equal(
            new[] { "第一场的问题", "回应：第一场的问题" },
            sessions[0].Lines.Select(line => line.Content).ToArray());
    }

    [Fact]
    public async Task Fallback_group_turn_leaves_no_session_behind()
    {
        // Bridge 不可用（fallback）时 F9 界面上一个气泡都不出现，所以存档里也不该留下一场。
        var client = CreateClient(out var handler, fallback: true);

        await SendGroupAsync(client, "invite-1", "你们怎么看？");

        Assert.Empty(client.RecentGroupSessions("Abigail"));
        Assert.Empty(client.RecentHistory("Abigail"));
        Assert.DoesNotContain("groupSessions", client.SerializeDisplayHistory("Farm_1"));
        Assert.NotEmpty(handler.RequestBodies);
    }

    [Fact]
    public async Task Loading_an_archive_keeps_new_turns_after_the_restored_session()
    {
        // 序号必须接着读回来的最大值往下发，否则新聊的那句会插到旧场次前面去。
        var first = CreateClient(out _);
        await SendGroupAsync(first, "invite-1", "存档里的问题");
        var saved = first.SerializeDisplayHistory("Farm_1");

        var second = CreateClient(out _);
        second.LoadDisplayHistory(saved, "Farm_1");
        await SendPrivateAsync(second, "Abigail", "载入之后的第一句");

        var timeline = GroupSessionRules.ToTimeline(
            second.RecentHistory("Abigail"),
            second.RecentGroupSessions("Abigail"),
            "Abigail");

        Assert.Equal(
            new[]
            {
                "线上多人对话 · 阿比盖尔、艾米丽 · 秋 12 · 主题：最近的公共小事",
                "存档里的问题",
                "回应：存档里的问题",
                "载入之后的第一句",
                "私聊回复0",
            },
            timeline.Select(message => message.Content).ToArray());
    }

    [Fact]
    public async Task Loading_an_archive_replaces_the_sessions_instead_of_merging()
    {
        var client = CreateClient(out _);
        await SendGroupAsync(client, "invite-9", "别的存档里的问题");

        client.LoadDisplayHistory(
            ChatHistoryArchive.Serialize(null, new[] { Session("invite-1") }, "FarmB_222"),
            "FarmB_222");

        var session = Assert.Single(client.RecentGroupSessions("Abigail"));
        Assert.Equal("invite-1", session.SessionId);
    }

    [Fact]
    public async Task Model_window_never_carries_display_only_fields()
    {
        // ⚠️ Bridge 侧的请求模型是 extra="forbid"：私聊 history 里多一个 sequence 字段
        // 就会 422、整轮对话退化成兜底。回看档案的那一份可以有，发送窗口的那一份不许有。
        var client = CreateClient(out var handler);
        await SendPrivateAsync(client, "Abigail", "第一句");
        await SendGroupAsync(client, "invite-1", "群里的一句");
        await SendPrivateAsync(client, "Abigail", "第二句");

        using var request = JsonDocument.Parse(handler.RequestBodies[^1]);
        var sent = request.RootElement.GetProperty("history").EnumerateArray().ToArray();
        Assert.NotEmpty(sent);
        Assert.All(sent, item => Assert.False(item.TryGetProperty("sequence", out _)));
        // 回看档案那一份则带上序号（F8 靠它插回原位）。
        Assert.All(
            client.RecentHistory("Abigail"),
            item => Assert.NotNull(item.Sequence));
    }

    [Fact]
    public async Task F8_panel_shows_private_chat_only_while_the_session_stays_in_the_archive()
    {
        // 2026-09-21 用户口径：F8 里**不再显示**群聊场次（回到「只显示私聊和私聊相关的记录」），
        // 群聊记录各归各位到 F9 那张邀约卡里。⚠ 存档层的场次一条不少 —— 这条用例两头都钉住：
        // 面板上看不到了，但整场发言序列仍从档案里拿得到（F9 点进去看的就是它）。
        var client = CreateClient(out _);
        await SendPrivateAsync(client, "Abigail", "私聊第一句");
        await SendGroupAsync(client, "invite-1", "群聊第一句");
        await SendPrivateAsync(client, "Abigail", "私聊第二句");

        using var service = new ConversationService(client, new StoryStateStore());
        var messages = service.RecentMessages("Abigail");

        Assert.Equal(
            new[] { "私聊第一句", "私聊回复0", "私聊第二句", "私聊回复1" },
            messages.Select(message => message.Content).ToArray());
        // 分节线那一档在 F8 里彻底不出现（它是群聊场次的抬头）。
        Assert.DoesNotContain(messages, message => message.Role == ChatHistoryRules.SessionRole);
        Assert.DoesNotContain(messages, message => message.Content.Contains("线上多人对话"));

        // 记录本体仍在存档里，一场一条、含完整发言序列（玩家与 NPC 都在）。
        var session = Assert.Single(client.RecentGroupSessions("Abigail"));
        Assert.Same(session, client.GroupSession("invite-1"));
        Assert.Equal(
            new[] { "群聊第一句", "回应：群聊第一句" },
            session.Lines.Select(line => line.Content).ToArray());
    }

    [Fact]
    public void Full_capacity_session_archive_stays_within_the_size_and_time_budget()
    {
        // 场次是**额外**加在私聊档案上的体积，所以上限要有个数：满档 = 40 场 × 120 条 × 240 字。
        // 现实规模（一场十来条、几句闲聊）在这里一并量出来，数字打在测试输出里备查。
        var content = new string('聊', GroupSessionRules.MaxLineLength);
        var sessions = Enumerable.Range(0, GroupSessionRules.MaxSessions)
            .Select(index => new GroupChatSessionRecord
            {
                SessionId = $"invite-{index}",
                Title = "公共话题",
                Topic = "最近的公共小事",
                DateLabel = "秋 12",
                TotalDays = 100 + index,
                Participants = new[] { "Abigail", "Emily" },
                ParticipantDisplayNames = new[] { "阿比盖尔", "艾米丽" },
                Lines = Enumerable.Range(0, GroupSessionRules.MaxLinesPerSession)
                    .Select(line => new GroupDialogueHistoryEntry(
                        line % 2 == 0 ? "player" : "npc",
                        line % 2 == 0 ? "player" : "Abigail",
                        content))
                    .ToArray(),
            })
            .ToArray();

        var warmup = ChatHistoryArchive.Serialize(null, sessions, "MyFarm_123456789");
        _ = ChatHistoryArchive.Load(warmup, "MyFarm_123456789");

        string json = warmup;
        var serializeMs = double.MaxValue;
        var loadMs = double.MaxValue;
        for (var round = 0; round < 3; round++)
        {
            var serializeWatch = Stopwatch.StartNew();
            json = ChatHistoryArchive.Serialize(null, sessions, "MyFarm_123456789");
            serializeWatch.Stop();

            var loadWatch = Stopwatch.StartNew();
            _ = ChatHistoryArchive.Load(json, "MyFarm_123456789");
            loadWatch.Stop();

            serializeMs = Math.Min(serializeMs, serializeWatch.Elapsed.TotalMilliseconds);
            loadMs = Math.Min(loadMs, loadWatch.Elapsed.TotalMilliseconds);
        }

        var loaded = ChatHistoryArchive.Load(json, "MyFarm_123456789");
        var bytes = Encoding.UTF8.GetByteCount(json);
        output.WriteLine(
            $"满档群聊场次：场次={loaded.Sessions.Count}；发言={loaded.SessionLineCount}；"
            + $"UTF8 字节={bytes}（{bytes / 1024.0 / 1024.0:0.00} MB）；"
            + $"序列化={serializeMs:0.0} ms；反序列化={loadMs:0.0} ms（各取三轮最快）");

        Assert.Equal(GroupSessionRules.MaxSessions, loaded.Sessions.Count);
        Assert.Equal(
            GroupSessionRules.MaxSessions * GroupSessionRules.MaxLinesPerSession,
            loaded.SessionLineCount);

        // 3～5 MB 量级：与私聊那份满档 15 MB 合起来仍在「存档能承受」的那一档。
        Assert.InRange(bytes, 2 * 1024 * 1024, 6 * 1024 * 1024);
        Assert.True(serializeMs < 5000);
        Assert.True(loadMs < 5000);
    }

    // ── 夹具 ─────────────────────────────────────────────────────────────────

    private static GroupChatSessionRecord Session(string sessionId)
    {
        return new GroupChatSessionRecord
        {
            SessionId = sessionId,
            Title = "公共话题",
            Topic = "最近的公共小事",
            DateLabel = "秋 12",
            TotalDays = 132,
            Participants = new[] { "Abigail", "Emily" },
            ParticipantDisplayNames = new[] { "阿比盖尔", "艾米丽" },
            Lines = new[]
            {
                new GroupDialogueHistoryEntry("player", "player", "你们怎么看？"),
                new GroupDialogueHistoryEntry("npc", "Abigail", "我也这么想。"),
                new GroupDialogueHistoryEntry("npc", "Emily", "那你呢？"),
            },
        };
    }

    private static BridgeClient CreateClient(out Responder handler, bool fallback = false)
    {
        handler = new Responder(fallback);
        return new BridgeClient(
            new HttpClient(handler),
            new Uri("http://127.0.0.1:5678"),
            groupStrategy: "multi_turn");
    }

    private static Task<BridgeGroupDialogueResponse> SendGroupAsync(
        BridgeClient client,
        string sessionId,
        string playerMessage)
    {
        return client.SendGroupAsync(new GroupDialogueRequest(
            playerMessage,
            new[]
            {
                new GroupDialogueParticipant("Abigail", "阿比盖尔"),
                new GroupDialogueParticipant("Emily", "艾米丽"),
            },
            "最近的公共小事",
            null,
            Array.Empty<GroupDialogueHistoryEntry>(),
            ActiveSpeakerNpcId: "Abigail",
            Session: new GroupSessionContext(sessionId, "公共话题", "最近的公共小事", "秋 12", 132)));
    }

    private static Task<BridgeDialogueResponse> SendPrivateAsync(
        BridgeClient client,
        string npcId,
        string message)
    {
        return client.SendAsync(npcId, message);
    }

    private sealed class Responder : HttpMessageHandler
    {
        private readonly bool fallback;
        private int privateCalls;

        public Responder(bool fallback)
        {
            this.fallback = fallback;
        }

        public List<string> RequestBodies { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            var body = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            RequestBodies.Add(body);
            var isGroup = request.RequestUri!.AbsolutePath.EndsWith("/group", StringComparison.Ordinal);
            var payload = fallback
                ? "{\"strategy\":\"multi_turn\",\"channel\":\"remote\",\"provider\":\"offline\","
                    + "\"fallback\":true,\"turns\":[],\"warnings\":[\"bridge: offline\"]}"
                : isGroup
                    ? GroupPayload(body)
                    : $"{{\"reply\":\"私聊回复{privateCalls++}\",\"provider\":\"fake\",\"fallback\":false}}";
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(payload, Encoding.UTF8, "application/json"),
            };
        }

        /// <summary>群聊回复的内容由请求里的玩家消息推出：断言因此可预期，也不用猜调用顺序。</summary>
        private static string GroupPayload(string requestBody)
        {
            using var document = JsonDocument.Parse(requestBody);
            var message = document.RootElement.GetProperty("message").GetString() ?? string.Empty;
            var reply = JsonSerializer.Serialize($"回应：{message}");
            return "{\"strategy\":\"multi_turn\",\"channel\":\"remote\",\"provider\":\"fake\","
                + "\"fallback\":false,\"turns\":[{\"speakerNpcId\":\"Abigail\","
                + $"\"content\":{reply}}}],"
                + "\"providerCalls\":1,\"providerErrors\":[],\"fallbackCount\":0,\"latencyMs\":5}";
        }
    }
}
