using System.Net;
using System.Text;
using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 回看档案随存档持久化的两端（BridgeClient 上的
/// <see cref="BridgeClient.SerializeDisplayHistory"/> 与
/// <see cref="BridgeClient.LoadDisplayHistory"/>）。
///
/// 与之配套的规则测试在 <see cref="ChatHistoryArchiveTests"/>；这里管的是
/// 「关掉游戏再进来记录还在」「换存档不串」「载入历史不改变发给模型的窗口」。
/// </summary>
public sealed class ChatHistoryPersistenceTests
{
    [Fact]
    public async Task Display_history_survives_a_client_restart()
    {
        // 关掉游戏：客户端连同内存一起没了，只有存档里那份 JSON 留下来。
        var first = CreateClient(out var handler);
        for (var index = 0; index < 8; index++)
        {
            await first.SendAsync("Abigail", $"问题{index}");
        }

        var saved = first.SerializeDisplayHistory("Farm_1");
        Assert.Equal(16, first.RecentHistory("Abigail").Count);
        first.Dispose();

        // 第二天载入同一个存档：新的客户端从存档里把回看档案读回来。
        var second = CreateClient(out var freshHandler);
        var loaded = second.LoadDisplayHistory(saved, "Farm_1");

        Assert.Empty(loaded.Warnings);
        Assert.Equal(16, loaded.MessageCount);
        var recalled = second.RecentHistory("Abigail");
        Assert.Equal("问题0", recalled[0].Content);
        Assert.Equal("回复7", recalled[^1].Content);
        Assert.Empty(freshHandler.RequestBodies);
    }

    [Fact]
    public async Task Loading_an_archive_leaves_the_model_window_untouched()
    {
        // 硬边界：存档恢复的是「给玩家翻的档案」，不是「发给模型的窗口」。
        // 载入 60 条之后，下一次请求里的 history 仍只装这一轮刚发生的对话。
        var client = CreateClient(out var handler);
        var archive = ChatHistoryArchive.Serialize(
            new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
            {
                ["Abigail"] = Enumerable.Range(0, ChatHistoryRules.MaxDisplayMessages)
                    .Select(index => new BridgeDialogueHistoryItem
                    {
                        Role = index % 2 == 0 ? "user" : "assistant",
                        Content = $"存档里的第{index}句",
                    })
                    .ToArray(),
            },
            "Farm_1");

        client.LoadDisplayHistory(archive, "Farm_1");
        Assert.Equal(ChatHistoryRules.MaxDisplayMessages, client.RecentHistory("Abigail").Count);

        await client.SendAsync("Abigail", "新的一句");

        using var request = JsonDocument.Parse(handler.RequestBodies[0]);
        var sent = request.RootElement.GetProperty("history").EnumerateArray().ToArray();
        Assert.Empty(sent);
    }

    [Fact]
    public void Loading_another_save_replaces_the_archive_instead_of_merging()
    {
        var client = CreateClient(out _);
        client.LoadDisplayHistory(ChatHistoryArchive.Serialize(SampleHistory(), "FarmA_111"), "FarmA_111");
        Assert.NotEmpty(client.RecentHistory("Abigail"));

        // 换到另一个存档，那边没有这份数据（老存档）：档案必须清空，
        // 而不是把上一个存档里的话留着。
        var loaded = client.LoadDisplayHistory(null, "FarmB_222");

        Assert.Empty(loaded.History);
        Assert.Empty(client.RecentHistory("Abigail"));
    }

    [Fact]
    public void Archive_written_by_another_save_is_rejected()
    {
        var client = CreateClient(out _);
        var foreign = ChatHistoryArchive.Serialize(SampleHistory(), "FarmA_111");

        var loaded = client.LoadDisplayHistory(foreign, "FarmB_222");

        Assert.Empty(loaded.History);
        Assert.Empty(client.RecentHistory("Abigail"));
        Assert.Single(loaded.Warnings);
    }

    [Fact]
    public void Exporting_a_client_that_never_talked_is_safe()
    {
        // 新档、或者一整天没聊过：导出的是一份空档案，仍能被读回。
        var client = CreateClient(out _);

        var json = client.SerializeDisplayHistory("Farm_1");
        var loaded = ChatHistoryArchive.Load(json, "Farm_1");

        Assert.False(string.IsNullOrWhiteSpace(json));
        Assert.Empty(loaded.History);
        Assert.Empty(loaded.Warnings);
    }

    [Fact]
    public void Loaded_archive_carries_group_summaries_too()
    {
        // 群聊摘要同样在回看档案里，存档往返之后 F8 面板也该翻得到。
        var client = CreateClient(out _);
        var archive = ChatHistoryArchive.Serialize(
            new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
            {
                ["Abigail"] = new[]
                {
                    new BridgeDialogueHistoryItem
                    {
                        Role = "assistant",
                        Content = "群里玩家说：“你们怎么看？”；我回应：“我觉得挺好。”",
                    },
                },
            },
            "Farm_1");

        client.LoadDisplayHistory(archive, "Farm_1");

        var recalled = Assert.Single(client.RecentHistory("Abigail"));
        Assert.Contains("群里玩家说", recalled.Content);
    }

    private static Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>> SampleHistory()
    {
        return new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
        {
            ["Abigail"] = new[]
            {
                new BridgeDialogueHistoryItem { Role = "user", Content = "在忙什么？" },
                new BridgeDialogueHistoryItem { Role = "assistant", Content = "刚给花浇完水。" },
            },
        };
    }

    private static BridgeClient CreateClient(out Responder handler)
    {
        handler = new Responder();
        return new BridgeClient(new HttpClient(handler), new Uri("http://127.0.0.1:5678"));
    }

    private sealed class Responder : HttpMessageHandler
    {
        private int calls;

        public List<string> RequestBodies { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            RequestBodies.Add(request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken));
            var index = calls++;
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    $"{{\"reply\":\"回复{index}\",\"provider\":\"fake\",\"fallback\":false}}",
                    Encoding.UTF8,
                    "application/json"),
            };
        }
    }
}
