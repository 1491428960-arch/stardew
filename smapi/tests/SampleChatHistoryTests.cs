using System.Net;
using System.Text;
using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 开发用示例记录的规格与行为（内容见 <see cref="SampleChatHistory"/>，
/// 内存侧实现在 <see cref="BridgeClient.InjectSampleHistory"/>）。
///
/// 这些用例守的是四件容易在改动中悄悄坏掉的事：
/// 1. 记录的量与「像真对话」的质地（够翻、不是"测试1、测试2"）；
/// 2. 示例**只**进回看档案，绝不进发给模型的窗口；
/// 3. 清理只删示例，玩家真实聊过的一句不动；
/// 4. 超量注入会裁掉最旧的（顺带验收 F8 的 1000 条上限）。
/// </summary>
public sealed class SampleChatHistoryTests
{
    [Fact]
    public void Every_sample_npc_gets_enough_history_to_scroll_through()
    {
        var samples = SampleChatHistory.Build();

        Assert.Equal(
            SampleChatHistory.NpcIds.OrderBy(id => id, StringComparer.Ordinal),
            samples.Keys.OrderBy(id => id, StringComparer.Ordinal));

        foreach (var pair in samples)
        {
            // 每个人至少 20 条（当前是 15 轮 / 30 条）：太少就"翻不动"，
            // 而这一批存在的理由正是让玩家有东西可翻。
            Assert.True(
                pair.Value.Count >= 20,
                $"{pair.Key} 只有 {pair.Value.Count} 条，翻起来太空。");
            Assert.True(pair.Value.Count <= ChatHistoryRules.MaxDisplayMessages);

            for (var index = 0; index < pair.Value.Count; index++)
            {
                // 一轮两条、玩家在前：面板才能画成一问一答的气泡。
                Assert.Equal(index % 2 == 0 ? "user" : "assistant", pair.Value[index].Role);
            }
        }
    }

    [Fact]
    public void Sample_lines_read_like_real_conversations_and_fit_the_spec()
    {
        foreach (var pair in SampleChatHistory.Build())
        {
            var contents = pair.Value.Select(item => item.Content).ToArray();
            Assert.Equal(contents.Length, contents.Distinct(StringComparer.Ordinal).Count());

            Assert.All(pair.Value, item =>
            {
                Assert.False(string.IsNullOrWhiteSpace(item.Content));
                Assert.True(
                    item.Content.Length <= ChatHistoryRules.MaxContentLength,
                    $"{pair.Key} 有一条 {item.Content.Length} 字，超出单条上限。");
                // 标记写在 Intent 上：清理与统计都靠它认人。
                Assert.Equal(SampleChatHistory.MarkerIntent, item.Intent);
                Assert.True(SampleChatHistory.IsSample(item));
            });

            // 反面清单：玩家明确要求"像正常对话"，不是占位符测试数据。
            Assert.DoesNotContain(
                pair.Value,
                item => item.Content.Contains("测试", StringComparison.Ordinal) ||
                    item.Content.Contains("test", StringComparison.OrdinalIgnoreCase) ||
                    item.Content.Contains("lorem", StringComparison.OrdinalIgnoreCase));
        }
    }

    [Fact]
    public async Task Injecting_samples_never_reaches_the_model_window()
    {
        // 硬边界：示例是给玩家翻的，不是 NPC 真实经历过的事。
        // 注入 120 条之后，下一次请求里的 history 仍是空的（本轮之前没聊过）。
        var client = CreateClient(out var handler);
        var change = client.InjectSampleHistory(SampleChatHistory.Build());

        Assert.Equal(SampleChatHistory.NpcIds.Count, change.NpcCount);
        Assert.Equal(4 * 30, change.MessageCount);
        Assert.Equal(30, client.RecentHistory("Abigail").Count);

        await client.SendAsync("Abigail", "今天过得怎么样？");

        using var request = JsonDocument.Parse(handler.RequestBodies[0]);
        Assert.Empty(request.RootElement.GetProperty("history").EnumerateArray());
    }

    [Fact]
    public void Injecting_twice_does_not_double_the_archive()
    {
        // 玩家连按两次键是很正常的事，条数不该翻倍。
        var client = CreateClient(out _);

        client.InjectSampleHistory(SampleChatHistory.Build());
        client.InjectSampleHistory(SampleChatHistory.Build());

        Assert.Equal(30, client.RecentHistory("Abigail").Count);
        Assert.Equal(4 * 30, client.CountSampleHistory().MessageCount);
    }

    [Fact]
    public async Task Clearing_removes_only_the_samples()
    {
        var client = CreateClient(out _);
        await client.SendAsync("Abigail", "我先聊一句");

        client.InjectSampleHistory(SampleChatHistory.Build());
        Assert.Equal(32, client.RecentHistory("Abigail").Count);

        var removed = client.ClearSampleHistory();

        // 清的是**全部**角色的示例（4 × 30），而玩家那句真实记录要留到最后。
        Assert.Equal(4 * 30, removed);
        Assert.Equal(0, client.CountSampleHistory().MessageCount);
        var left = client.RecentHistory("Abigail");
        Assert.Equal(2, left.Count);
        Assert.Equal("我先聊一句", left[0].Content);
        Assert.Equal("回复0", left[1].Content);
        Assert.All(left, item => Assert.False(SampleChatHistory.IsSample(item)));
    }

    [Fact]
    public void Clearing_a_client_without_samples_is_a_no_op()
    {
        var client = CreateClient(out _);

        Assert.Equal(0, client.ClearSampleHistory());
        Assert.True(client.CountSampleHistory().IsEmpty);
    }

    [Fact]
    public void Stress_injection_is_trimmed_to_the_display_limit_and_drops_the_oldest()
    {
        var client = CreateClient(out _);
        var stress = SampleChatHistory.BuildStress("Abigail");
        var injected = stress["Abigail"];

        // 故意超限：这正是"裁掉最旧的"的可验证构造。
        Assert.Equal(ChatHistoryRules.MaxDisplayMessages + 42, injected.Count);
        Assert.Equal(SampleChatHistory.StressMessageCount, injected.Count);

        var change = client.InjectSampleHistory(stress);
        var archive = client.RecentHistory("Abigail");

        Assert.Equal(injected.Count, change.MessageCount);
        Assert.Equal(ChatHistoryRules.MaxDisplayMessages, archive.Count);

        // 留下的是**尾部**：最旧的 42 条整段消失，最上面那条正好是第 43 条。
        Assert.Equal(injected[SampleChatHistory.StressDroppedMessages].Content, archive[0].Content);
        Assert.Equal(injected[^1].Content, archive[^1].Content);
        Assert.StartsWith(
            SampleChatHistory.StressFirstKeptStamp,
            archive[0].Content,
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            archive,
            item => item.Content == injected[SampleChatHistory.StressDroppedMessages - 1].Content);
    }

    [Fact]
    public void Stress_stamps_read_like_a_long_running_diary()
    {
        // 合成流水也要求"读得下去"：每条都带游戏历法的日期戳，四季与年份会往前走。
        var injected = SampleChatHistory.BuildStress("Abigail")["Abigail"];

        Assert.StartsWith("第1年 春1日 ", injected[0].Content, StringComparison.Ordinal);
        Assert.Contains("第1年 夏", injected[56].Content, StringComparison.Ordinal);
        Assert.Contains("第2年 春", injected[224].Content, StringComparison.Ordinal);
        Assert.All(injected, item => Assert.Equal(SampleChatHistory.MarkerIntent, item.Intent));
    }

    [Fact]
    public void Samples_survive_the_save_round_trip_and_stay_clearable()
    {
        // 关掉游戏：客户端连同内存一起没了，只有存档里那份 JSON 留下来。
        var first = CreateClient(out _);
        first.InjectSampleHistory(SampleChatHistory.Build());
        var saved = first.SerializeDisplayHistory("Farm_1");

        // 第二天载入同一个存档。
        var second = CreateClient(out _);
        var loaded = second.LoadDisplayHistory(saved, "Farm_1");

        Assert.Empty(loaded.Warnings);
        Assert.Equal(4 * 30, loaded.MessageCount);
        Assert.Equal(30, second.RecentHistory("Abigail").Count);

        // 标记随存档一起回来：重进游戏之后照样认得出来、照样清得掉。
        Assert.Equal(4 * 30, second.CountSampleHistory().MessageCount);
        Assert.Equal(4 * 30, second.ClearSampleHistory());
        Assert.Empty(second.RecentHistory("Abigail"));
    }

    [Fact]
    public void Samples_map_to_panel_messages_with_alternating_speakers()
    {
        // 玩家真正看到的那一层：F8 打开时铺进消息区的那串气泡。
        // 注入的 role 是 user/assistant，面板只认 player/npc（映射见 ChatHistoryRules）。
        var client = CreateClient(out _);
        client.InjectSampleHistory(SampleChatHistory.Build());

        var messages = ChatHistoryRules.ToDisplayMessages(client.RecentHistory("Abigail"));

        Assert.Equal(30, messages.Count);
        Assert.Equal("今天有空吗？", messages[0].Content);
        Assert.Equal("player", messages[0].Role);
        Assert.Equal("npc", messages[1].Role);
        Assert.Equal("npc", messages[^1].Role);
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
