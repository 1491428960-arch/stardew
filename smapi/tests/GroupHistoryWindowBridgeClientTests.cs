using System.Net;
using System.Text;
using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 群聊请求体里历史窗口的**方向与额度**（2026-09-22 修）。
///
/// 改前 <see cref="BridgeClient.SendGroupAsync"/> 用的是 `.Take(MaxHistoryItems)`：
/// 取**最旧**的 6 条，而私聊走 <c>TrimHistory</c>（保留末尾）—— 方向反了。
/// 玩家发言进历史后这个错误会被放大（一轮占 3～4 条），所以这里把两件事一起钉住：
///
/// 1. 窗口取的是**最近**的若干条，不是最早的若干条；
/// 2. 额度是群聊专用的 10 条（私聊那份额度仍是 6，见
///    <c>BridgeClient.MaxHistoryItems</c> 的注释：两个常量分开就是为了不动私聊）。
/// </summary>
public sealed class GroupHistoryWindowBridgeClientTests
{
    /// <summary>群聊历史窗口的条数，与 `BridgeClient.MaxGroupHistoryItems` 对齐（private const，只能写死）。</summary>
    private const int GroupHistoryWindow = 10;

    private const string SuccessBody =
        "{\"strategy\":\"multi_turn\",\"channel\":\"remote\",\"provider\":\"fake\"," +
        "\"fallback\":false,\"turns\":[{\"speakerNpcId\":\"Abigail\",\"content\":\"先说件小事。\"}]," +
        "\"providerCalls\":1,\"providerErrors\":[],\"fallbackCount\":0,\"latencyMs\":9}";

    private sealed class StubHandler : HttpMessageHandler
    {
        public string? Body { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Body = request.Content is null
                ? null
                : await request.Content.ReadAsStringAsync(cancellationToken);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(SuccessBody, Encoding.UTF8, "application/json"),
            };
        }
    }

    private static (BridgeClient Client, StubHandler Handler) Build()
    {
        var handler = new StubHandler();
        var client = new BridgeClient(
            new HttpClient(handler),
            new Uri("http://127.0.0.1:5678"),
            groupStrategy: "multi_turn");
        return (client, handler);
    }

    private static GroupDialogueHistoryEntry Line(int index)
    {
        // 偶数号是玩家、奇数号是 Abigail：一轮的真实形态就是「玩家 1 条 + NPC 若干条」。
        var isPlayer = index % 2 == 0;
        return new GroupDialogueHistoryEntry(
            isPlayer ? "player" : "npc",
            isPlayer ? "player" : "Abigail",
            $"第 {index} 条");
    }

    private static GroupDialogueRequest RequestWithHistory(int count) => new(
        "那你们呢？",
        new[]
        {
            new GroupDialogueParticipant("Abigail", "Abigail"),
            new GroupDialogueParticipant("Sebastian", "Sebastian"),
        },
        null,
        null,
        Enumerable.Range(0, count).Select(Line).ToArray());

    private static string[] SentHistoryContents(StubHandler handler)
    {
        Assert.NotNull(handler.Body);
        using var json = JsonDocument.Parse(handler.Body!);
        return json.RootElement.GetProperty("history")
            .EnumerateArray()
            .Select(item => item.GetProperty("content").GetString() ?? string.Empty)
            .ToArray();
    }

    [Fact]
    public async Task The_group_history_window_keeps_the_most_recent_lines_not_the_oldest()
    {
        // 12 条 > 额度 10：模型必须拿到**最后** 10 条（第 2…11 条），而不是最旧的 10 条。
        // 取最旧的会让玩家越聊越看不到刚发生的事 —— 这正是改前的行为。
        var (client, handler) = Build();

        await client.SendGroupAsync(RequestWithHistory(12));

        var sent = SentHistoryContents(handler);
        Assert.Equal(GroupHistoryWindow, sent.Length);
        Assert.Equal("第 2 条", sent[0]);
        Assert.Equal("第 11 条", sent[^1]);
    }

    [Fact]
    public async Task The_group_history_window_keeps_the_order_of_the_lines()
    {
        // 窗口只裁两端，不重排：历史仍是「旧 → 新」，与公开历史的语义一致
        // （模型靠顺序判断谁先说的）。
        var (client, handler) = Build();

        await client.SendGroupAsync(RequestWithHistory(4));

        var sent = SentHistoryContents(handler);
        Assert.Equal(new[] { "第 0 条", "第 1 条", "第 2 条", "第 3 条" }, sent);
    }

    [Fact]
    public async Task A_short_group_history_is_sent_whole()
    {
        // 不够一个窗口时一条都不能丢（TakeLast 在条数不足时原样返回）。
        var (client, handler) = Build();

        await client.SendGroupAsync(RequestWithHistory(3));

        var sent = SentHistoryContents(handler);
        Assert.Equal(new[] { "第 0 条", "第 1 条", "第 2 条" }, sent);
    }

    [Fact]
    public async Task The_group_window_carries_the_player_lines()
    {
        // 玩家行**必须在请求体里**（本次修复的核心）：改前 SMAPI 侧根本不会送出这种条目。
        // Bridge 侧 `GroupHistoryItem.speaker_type` 本来就接受 "player"，
        // 名单归属只对 npc 行校验，所以这里只需确认它们真的被发出去、而且没被窗口裁掉。
        var (client, handler) = Build();

        await client.SendGroupAsync(RequestWithHistory(12));

        Assert.NotNull(handler.Body);
        using var json = JsonDocument.Parse(handler.Body!);
        var speakerTypes = json.RootElement.GetProperty("history")
            .EnumerateArray()
            .Select(item => item.GetProperty("speakerType").GetString())
            .ToArray();
        // 第 2…11 条里偶数号是玩家（生成规则见 Line），奇数号是 NPC，顺序交替。
        Assert.Equal(
            new[]
            {
                "player", "npc", "player", "npc", "player",
                "npc", "player", "npc", "player", "npc",
            },
            speakerTypes);
    }
}
