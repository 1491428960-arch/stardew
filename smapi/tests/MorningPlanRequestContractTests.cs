using System.Net;
using System.Text;
using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 钉住**真正发给 Bridge 的那个 JSON**（2026-09-27）。
///
/// Bridge 侧 `MorningPlanRequest` 是 `extra="forbid"`：字段名对不上、或者多送一个字段，
/// 就是 422；而 422 在这条路径上的表现是「今天早上没人发消息」——不报错、不 crash，
/// 玩家也不会察觉少了什么。**Bridge 侧自己的测试看不到这里**：它只知道
/// 「请求里有个字段叫 recentEventIds」，没法验证 C# 真发的是这个名字。
///
/// 这与本项目踩过的另一个同形坑一致（`GroupDialogueMenu` 固定发 `gameState=null`，
/// 群聊事件锁因此静默失效）：**接线漏了不会有任何症状。**
/// </summary>
public sealed class MorningPlanRequestContractTests
{
    private sealed class CapturingHandler : HttpMessageHandler
    {
        public string? Body { get; private set; }

        public Uri? RequestUri { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            RequestUri = request.RequestUri;
            Body = request.Content is null
                ? null
                : await request.Content.ReadAsStringAsync(cancellationToken);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    "{\"messages\":[]}",
                    Encoding.UTF8,
                    "application/json"),
            };
        }
    }

    private static async Task<JsonElement> CaptureAsync(
        int dayIndex,
        IReadOnlyList<string>? recentEventIds)
    {
        var handler = new CapturingHandler();
        var client = new BridgeClient(new HttpClient(handler));

        await client.RequestMorningPlanAsync(dayIndex, recentEventIds: recentEventIds);

        Assert.Equal(new Uri("http://127.0.0.1:5678/api/morning/plan"), handler.RequestUri);
        Assert.NotNull(handler.Body);
        return JsonDocument.Parse(handler.Body!).RootElement.Clone();
    }

    [Fact]
    public async Task Plan_request_carries_recent_event_ids()
    {
        var root = await CaptureAsync(84, new[] { "13", "20" });

        Assert.Equal(84, root.GetProperty("dayIndex").GetInt32());
        Assert.Equal(
            new[] { "13", "20" },
            root.GetProperty("recentEventIds")
                .EnumerateArray()
                .Select(item => item.GetString())
                .ToArray());
    }

    [Fact]
    public async Task Plan_request_sends_exactly_the_three_agreed_fields()
    {
        var root = await CaptureAsync(84, new[] { "13" });

        // `extra="forbid"` 是这道契约的护栏。这条钉住**字段集合本身**：
        // 以后谁往 `MorningPlanRequest` 上加东西又忘了同步 Bridge，会在这里断掉，
        // 而不是等到游戏里「今天没人发消息」才发现。
        Assert.Equal(
            new[] { "dayIndex", "knownNpcIds", "recentEventIds" },
            root.EnumerateObject()
                .Select(property => property.Name)
                .OrderBy(name => name, StringComparer.Ordinal)
                .ToArray());
    }

    [Fact]
    public async Task Plan_request_sends_empty_arrays_rather_than_null()
    {
        var root = await CaptureAsync(84, null);

        // 送 `[]` 而不是 `null`：让「明确知道昨天没有新事件」与「忘了送」在日志里可区分。
        // 两者在 Bridge 侧都被默认值接住，所以这是可观测性要求，不是功能要求。
        Assert.Equal(JsonValueKind.Array, root.GetProperty("recentEventIds").ValueKind);
        Assert.Equal(0, root.GetProperty("recentEventIds").GetArrayLength());
        Assert.Equal(JsonValueKind.Array, root.GetProperty("knownNpcIds").ValueKind);
    }

    [Fact]
    public async Task Plan_request_keeps_event_ids_byte_identical()
    {
        var root = await CaptureAsync(84, new[] { "ABC", "abc" });

        // ⚠ 大小写敏感：这两个是**不同**的事件（`EventAuditRules` 的契约，
        // 与 NPC ID 忽略大小写的规则相反）。序列化层不许做任何归一化。
        Assert.Equal(
            new[] { "ABC", "abc" },
            root.GetProperty("recentEventIds")
                .EnumerateArray()
                .Select(item => item.GetString())
                .ToArray());
    }
}
