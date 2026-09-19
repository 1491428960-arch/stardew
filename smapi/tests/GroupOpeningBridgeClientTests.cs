using System.Net;
using System.Text;
using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 群聊「开场」在 <see cref="BridgeClient"/> 这一层的合法性。
///
/// 2026-09-20 真机排查：接受邀约后 NPC 不开口，界面显示
/// `无可用回复(fb=True n=0 ...)`。根因是 `SendGroupAsync` 里还有一道守卫
///
///     if (string.IsNullOrWhiteSpace(request.Message))
///         return BridgeGroupDialogueResponse.Offline("bridge: message empty");
///
/// ——它**在发 HTTP 之前**就返回了离线响应（`Fallback=true`、turns 为空），
/// 所以 Bridge 侧根本没收到那次开场请求。而「重试」走的是非空占位文案，
/// 因此能通过。**`GroupDialogueMenu` 侧的改动看不到这一层。**
/// </summary>
public sealed class GroupOpeningBridgeClientTests
{
    private const string SuccessBody =
        "{\"strategy\":\"multi_turn\",\"channel\":\"remote\",\"provider\":\"fake\"," +
        "\"fallback\":false,\"turns\":[{\"speakerNpcId\":\"Abigail\",\"content\":\"先说件小事。\"}]," +
        "\"providerCalls\":1,\"providerErrors\":[],\"fallbackCount\":0,\"latencyMs\":9}";

    private sealed class StubHandler : HttpMessageHandler
    {
        public HttpRequestMessage? Request { get; private set; }
        public string? Body { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Request = request;
            Body = request.Content is null
                ? null
                : await request.Content.ReadAsStringAsync(cancellationToken);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(SuccessBody, Encoding.UTF8, "application/json"),
            };
        }
    }

    private static GroupDialogueRequest Request(string message) => new(
        message,
        new[]
        {
            new GroupDialogueParticipant("Abigail", "Abigail"),
            new GroupDialogueParticipant("Sebastian", "Sebastian"),
        },
        "矿洞传闻",
        "围绕最近发现的矿石聊聊",
        Array.Empty<GroupDialogueHistoryEntry>());

    private static GroupDialogueRequest RequestWithHistory(string message) => new(
        message,
        new[]
        {
            new GroupDialogueParticipant("Abigail", "Abigail"),
            new GroupDialogueParticipant("Sebastian", "Sebastian"),
        },
        "矿洞传闻",
        "围绕最近发现的矿石聊聊",
        new[]
        {
            new GroupDialogueHistoryEntry("player", "player", "你们好啊"),
        });

    private static (BridgeClient Client, StubHandler Handler) Build()
    {
        var handler = new StubHandler();
        var client = new BridgeClient(
            new HttpClient(handler),
            new Uri("http://127.0.0.1:5678"),
            groupStrategy: "multi_turn");
        return (client, handler);
    }

    [Fact]
    public async Task An_empty_message_is_still_rejected_by_default()
    {
        // 回归保护：不显式放行时，空消息仍走离线兜底。
        var (client, handler) = Build();

        var response = await client.SendGroupAsync(Request(string.Empty));

        Assert.True(response.Fallback);
        Assert.Empty(response.Turns);
        Assert.Contains("message empty", string.Join("|", response.Warnings));
        Assert.Null(handler.Request);
    }

    [Fact]
    public async Task An_empty_message_is_sent_when_it_is_an_opening()
    {
        // 开场：空消息必须真的发出去，而不是在本地兜底。
        var (client, handler) = Build();

        var response = await client.SendGroupAsync(Request(string.Empty), allowEmptyMessage: true);

        Assert.NotNull(handler.Request);
        Assert.Equal("http://127.0.0.1:5678/api/dialogue/group", handler.Request!.RequestUri!.ToString());
        Assert.False(response.Fallback);
        Assert.Single(response.Turns);
    }

    [Fact]
    public async Task The_opening_request_carries_an_empty_message_field()
    {
        var (client, handler) = Build();

        await client.SendGroupAsync(Request(string.Empty), allowEmptyMessage: true);

        Assert.NotNull(handler.Body);
        using var json = JsonDocument.Parse(handler.Body!);
        Assert.Equal(string.Empty, json.RootElement.GetProperty("message").GetString());
        // 参与者与邀约上下文照常带上。
        Assert.Equal(2, json.RootElement.GetProperty("participants").GetArrayLength());
        Assert.Equal("矿洞传闻", json.RootElement.GetProperty("invitationTopic").GetString());
    }

    [Fact]
    public async Task A_real_message_still_works_with_the_flag_off()
    {
        var (client, handler) = Build();

        var response = await client.SendGroupAsync(Request("你们周末干嘛？"));

        Assert.NotNull(handler.Request);
        Assert.False(response.Fallback);
    }

    [Fact]
    public async Task An_opening_flag_with_history_is_still_rejected()
    {
        // 与 Bridge 侧保持**同一条规则**：空消息只有在历史也为空时才是开场。
        // 两处规则不同的话，就会出现「SMAPI 放行、Bridge 422」这种静默不一致
        // —— 2026-09-20 的开场问题正是这类不一致造成的，所以这里提前钉住。
        var (client, handler) = Build();

        var response = await client.SendGroupAsync(
            RequestWithHistory(string.Empty), allowEmptyMessage: true);

        Assert.True(response.Fallback);
        Assert.Empty(response.Turns);
        Assert.Null(handler.Request);
    }

    [Fact]
    public async Task A_real_message_with_history_is_still_sent()
    {
        var (client, handler) = Build();

        var response = await client.SendGroupAsync(RequestWithHistory("那你们呢？"));

        Assert.NotNull(handler.Request);
        Assert.False(response.Fallback);
    }
}
