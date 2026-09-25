using System.Net;
using System.Text;
using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 「早上发来、还没看」这个状态的两端：内存里的行为，以及它跟着聊天档案
/// 跨存档会话的存取。
///
/// 它和回看档案共用一份存档载荷（<c>ChatHistoryArchiveEnvelope.UnreadMorning</c>），
/// 所以要守的不只是「存得下、读得回」，还有**换存档时必须一起清掉**——
/// 否则新档里会凭空出现「有人在早上给你留了话」。
/// </summary>
public sealed class MorningMessagePersistenceTests
{
    private const string Opening = "你在那个破屋里过的第一晚怎么样？";

    private static BridgeClient CreateClient()
    {
        return new BridgeClient();
    }

    private static BridgeClient CreateClient(out Responder handler)
    {
        handler = new Responder();
        return new BridgeClient(new HttpClient(handler), new Uri("http://127.0.0.1:5678"));
    }

    [Fact]
    public void Unread_state_survives_a_client_restart()
    {
        // 关掉游戏：客户端连同内存一起没了，只有存档里那份 JSON 留下来。
        var first = CreateClient();
        Assert.True(first.RememberMorningMessage("Lewis", Opening));
        Assert.True(first.HasUnreadMorning("Lewis"));
        var saved = first.SerializeDisplayHistory("Farm_1");
        first.Dispose();

        var second = CreateClient();
        var loaded = second.LoadDisplayHistory(saved, "Farm_1");

        Assert.Empty(loaded.Warnings);
        Assert.True(second.HasUnreadMorning("Lewis"));
    }

    [Fact]
    public void Reading_the_message_clears_the_unread_flag()
    {
        var client = CreateClient();
        client.RememberMorningMessage("Lewis", Opening);

        // 第一次清掉返回 true（调用方据此决定要不要存档），第二次就没什么可清的了。
        Assert.True(client.MarkMorningRead("Lewis"));
        Assert.False(client.HasUnreadMorning("Lewis"));
        Assert.False(client.MarkMorningRead("Lewis"));
    }

    /// <summary>
    /// 晨间消息**必须也进发送窗口**：它是这段对话的开头，玩家接着回话时
    /// 模型得看得到「自己先说过什么」，否则会答非所问。
    /// 这里直接看真实请求体，而不是看内存里的某个集合——只写回看档案的话，
    /// 玩家看到的是一个人的话，模型看到的是另一个人凭空开口。
    /// </summary>
    [Fact]
    public async Task Morning_message_enters_the_send_window()
    {
        var client = CreateClient(out var handler);
        client.RememberMorningMessage("Lewis", Opening);

        await client.SendAsync("Lewis", "还行，就是床有点响。");

        var body = Assert.Single(handler.RequestBodies);
        using var document = JsonDocument.Parse(body);
        var history = document.RootElement.GetProperty("history");
        // 只有那条晨间消息：`SendAsync` 是**先取历史、再发请求、最后才记本轮**，
        // 而本轮玩家输入本来就由 `message` 字段单独传，不重复出现在 history 里。
        var only = Assert.Single(history.EnumerateArray().ToArray());
        Assert.Equal("assistant", only.GetProperty("role").GetString());
        Assert.Equal(Opening, only.GetProperty("content").GetString());
        // intent 必须是 chat：Bridge 侧是 Literal["chat","topic","item"] + extra="forbid"，
        // 自造一个 "morning" 会直接 422。
        Assert.Equal("chat", only.GetProperty("intent").GetString());
    }

    /// <summary>
    /// 没有未读时那个字段**整个不写**：这样「没人在早上发过消息」的档案与加这个
    /// 功能之前逐字节相同，体积预算用例的数字也不会漂。
    /// </summary>
    [Fact]
    public void Without_any_unread_the_field_is_absent()
    {
        var client = CreateClient();
        client.RememberMorningMessage("Lewis", Opening);
        client.MarkMorningRead("Lewis");

        var json = client.SerializeDisplayHistory("Farm_1");

        Assert.DoesNotContain("unreadMorning", json, StringComparison.Ordinal);
    }

    /// <summary>存了未读时字段**要出现**——上面那条只证明了「会消失」。</summary>
    [Fact]
    public void With_unread_the_field_is_written()
    {
        var client = CreateClient();
        client.RememberMorningMessage("Lewis", Opening);

        var json = client.SerializeDisplayHistory("Farm_1");

        Assert.Contains("unreadMorning", json, StringComparison.Ordinal);
    }

    /// <summary>
    /// 换存档：上一个存档的未读必须清掉。合并而不是替换的话，
    /// 新档里会凭空冒出「有人在早上给你留了话」。
    /// </summary>
    [Fact]
    public void Loading_another_save_drops_the_previous_unread()
    {
        var client = CreateClient();
        client.RememberMorningMessage("Lewis", Opening);

        // 另一个存档的档案：里面没有未读名单。
        var otherSave = ChatHistoryArchive.Serialize(
            new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal),
            "Farm_2");
        var loaded = client.LoadDisplayHistory(otherSave, "Farm_2");

        Assert.Empty(loaded.Warnings);
        Assert.False(client.HasUnreadMorning("Lewis"));
    }

    /// <summary>老档案没有这个字段：读成空列表，**不刷警告**（那时还没有这个功能）。</summary>
    [Fact]
    public void Legacy_archive_without_the_field_reads_as_empty()
    {
        var legacy = "{\"schemaVersion\":1,\"saveId\":\"1\",\"byNpc\":{}}";

        var loaded = ChatHistoryArchive.Load(legacy, "Farm_1");

        Assert.Empty(loaded.Warnings);
        Assert.Empty(loaded.UnreadMorning);
    }

    /// <summary>
    /// 乱写的未读名单（手改存档、名字带空格、重复项）不能让存档读不进来，
    /// 也不该留下重复行。
    /// </summary>
    [Fact]
    public void Malformed_unread_entries_are_dropped_not_fatal()
    {
        var messy = "{\"schemaVersion\":1,\"saveId\":\"1\",\"byNpc\":{},"
            + "\"unreadMorning\":[\"Lewis\",\"  \",\"lewis\",\"  Abigail  \"]}";

        var loaded = ChatHistoryArchive.Load(messy, "Farm_1");

        Assert.Empty(loaded.Warnings);
        Assert.Equal(new[] { "Lewis", "Abigail" }, loaded.UnreadMorning);
    }

    private sealed class Responder : HttpMessageHandler
    {
        public List<string> RequestBodies { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            RequestBodies.Add(request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken));
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(
                    "{\"reply\":\"回复\",\"provider\":\"fake\",\"fallback\":false}",
                    Encoding.UTF8,
                    "application/json"),
            };
        }
    }
}
