using System.Net;
using System.Text;
using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 隐性知识真的到达模型（2026-10-04）。
///
/// 前三层（规则 / 存储 / 写入接线）都全绿**也推不出**这一层成立 —— 项目实测过
/// 一类失效形态：「实现完备、测试全绿、生产零调用点」。
/// 所以这里看的是**真实请求体**：`latentKnowledge` 必须出现在发给 Bridge 的
/// JSON 里，而不只是停在内存集合中。
///
/// 与 <c>MorningMessagePersistenceTests.Morning_message_enters_the_send_window</c>
/// 同一个取向。
///
/// ⚠ 契约风险：Bridge 侧请求模型是 <c>extra="forbid"</c>，多一个字段就 422、
/// 整轮对话退化成兜底。所以「带出去了」和「Bridge 认这个字段」是**两件事**，
/// 后者由 Bridge 侧的 `test_latent_knowledge_card.py` 与本文件共同覆盖：
/// 前者证明 C# 发了，后者证明 Bridge 收得下。
/// </summary>
public sealed class LatentKnowledgeRequestTests
{
    private static BridgeClient CreateClient(out Responder handler)
    {
        handler = new Responder();
        return new BridgeClient(new HttpClient(handler), new Uri("http://127.0.0.1:5678"));
    }

    [Fact]
    public async Task 隐性知识出现在发给_bridge_的请求体里()
    {
        var client = CreateClient(out var handler);

        await client.SendAsync(
            "Sophia",
            "你最近在忙什么？",
            memoryFacts: new[] { "玩家送过我一条项链。" },
            latentKnowledge: new[] { "听说 Abigail 说：我倒是想练练剑。" });

        var body = Assert.Single(handler.RequestBodies);
        using var document = JsonDocument.Parse(body);

        Assert.True(
            document.RootElement.TryGetProperty("latentKnowledge", out var latent),
            "请求体里没有 latentKnowledge —— 隐性知识停在了内存里，模型看不到。");

        var items = latent.EnumerateArray().Select(item => item.GetString()!).ToArray();
        Assert.Contains(items, item => item.Contains("练练剑"));
    }

    [Fact]
    public async Task 没有隐性知识时不发这个字段()
    {
        // 空数组也发出去是浪费：Bridge 侧会走一遍渲染逻辑再得出「没内容」。
        // 更重要的是「不主动提」——没有内容时不该凭空出现一张空卡。
        var client = CreateClient(out var handler);

        await client.SendAsync("Sophia", "你最近在忙什么？");

        var body = Assert.Single(handler.RequestBodies);
        using var document = JsonDocument.Parse(body);

        Assert.False(document.RootElement.TryGetProperty("latentKnowledge", out _));
    }

    [Fact]
    public async Task 隐性知识与普通记忆走两个字段互不污染()
    {
        // 分流在请求层同样要成立：普通记忆走 `recentFacts`（会主动提），
        // 隐性知识走 `latentKnowledge`（不主动提）。若混进 `recentFacts`，
        // 那张「把记忆自然用起来」的卡会让模型主动提起，与需求相反。
        var client = CreateClient(out var handler);

        await client.SendAsync(
            "Sophia",
            "你最近在忙什么？",
            memoryFacts: new[] { "玩家送过我一条项链。" },
            latentKnowledge: new[] { "听说 Abigail 说：我倒是想练练剑。" });

        var body = Assert.Single(handler.RequestBodies);
        using var document = JsonDocument.Parse(body);

        var facts = document.RootElement.GetProperty("recentFacts")
            .EnumerateArray().Select(item => item.GetString()!).ToArray();
        var latent = document.RootElement.GetProperty("latentKnowledge")
            .EnumerateArray().Select(item => item.GetString()!).ToArray();

        Assert.Contains(facts, item => item.Contains("项链"));
        Assert.DoesNotContain(facts, item => item.Contains("练练剑"));
        Assert.Contains(latent, item => item.Contains("练练剑"));
        Assert.DoesNotContain(latent, item => item.Contains("项链"));
    }

    [Fact]
    public async Task 群聊请求不带隐性知识()
    {
        // 隐性知识是**私聊**的召回机制：她在私聊里「想起听谁说过什么」。
        // 群聊当场就听得见，再塞一遍等于让模型以为自己已经知道，
        // 反而会说出「我听 Abigail 说过」这种在当场很怪的话。
        var client = CreateClient(out var handler);

        await client.SendGroupAsync(new GroupDialogueRequest(
            Message: "你们怎么看？",
            Participants: new[]
            {
                new GroupDialogueParticipant("Sophia", "索菲娅"),
                new GroupDialogueParticipant("Abigail", "阿比盖尔"),
            },
            InvitationTopic: "聊聊近况",
            InvitationGuidance: null,
            History: Array.Empty<GroupDialogueHistoryEntry>()));

        var body = Assert.Single(handler.RequestBodies);
        using var document = JsonDocument.Parse(body);

        Assert.False(document.RootElement.TryGetProperty("latentKnowledge", out _));
    }

    internal sealed class Responder : HttpMessageHandler
    {
        public List<string> RequestBodies { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            if (request.Content is not null)
            {
                RequestBodies.Add(
                    await request.Content.ReadAsStringAsync(cancellationToken));
            }

            // 同时满足单聊与群聊两种响应的最低字段要求。
            var payload = """
                {
                  "reply": "嗯，我知道了。",
                  "provider": "fake",
                  "requestCount": 1,
                  "latencyMs": 12,
                  "fallback": false,
                  "warnings": [],
                  "turns": []
                }
                """;
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(payload, Encoding.UTF8, "application/json"),
            };
        }
    }
}