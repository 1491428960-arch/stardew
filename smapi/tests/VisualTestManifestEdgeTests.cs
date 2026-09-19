using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// <c>VisualTestManifest</c> 是视觉测试的机读凭据，有两条不能松的契约：
/// 写盘前挡住路径逃逸（保存名与截图名都必须是单层文件名），
/// 以及未被使用的场景字段在 JSON 里保持**显式 null**——
/// 下游脚本按字段名取值，“字段缺省”与“字段为 null”并不等价。
/// 已有 <c>VisualTestManifestTests</c> 覆盖了字段顺序、非空字段与三种非法名，
/// 这里补合法名、<c>"."</c>/<c>".."</c> 专门分支、<c>ToJson</c> 自身的守门与空字段形状。
/// </summary>
public sealed class VisualTestManifestEdgeTests
{
    [Fact]
    public void ValidateFileName_accepts_a_single_segment_name()
    {
        Assert.Null(Record.Exception(
            () => VisualTestManifest.ValidateFileName("chat-empty.png")));
        Assert.Null(Record.Exception(
            () => VisualTestManifest.ValidateFileName("群聊 01.png")));
    }

    [Fact]
    public void ValidateFileName_rejects_dot_and_dotdot()
    {
        // "." / ".." 能通过“非空 + 单层文件名 + 无非法字符”这套检查，
        // 必须由专门的分支拦下，否则场景名会指向目录本身。
        Assert.Throws<ArgumentException>(
            () => VisualTestManifest.ValidateFileName("."));
        Assert.Throws<ArgumentException>(
            () => VisualTestManifest.ValidateFileName(".."));
    }

    [Theory]
    [InlineData("..\\escape")]
    [InlineData("nested/shot")]
    public void ToJson_validates_the_scenario_id_before_serialising(string scenarioId)
    {
        var manifest = Manifest() with { ScenarioId = scenarioId };

        Assert.Throws<ArgumentException>(() => manifest.ToJson());
    }

    [Fact]
    public void ToJson_validates_the_screenshot_file_before_serialising()
    {
        var manifest = Manifest() with { ScreenshotFile = "..\\old.png" };

        Assert.Throws<ArgumentException>(() => manifest.ToJson());
    }

    [Fact]
    public void Unused_group_fields_stay_visible_as_explicit_nulls()
    {
        var json = Manifest().ToJson();

        using var document = JsonDocument.Parse(json);
        foreach (var name in new[]
        {
            "groupResponseTurns",
            "groupMemoryCount",
            "groupMemoryNpcCount",
            "groupInvitationStatus",
            "groupRequestStateCount",
            "groupMemoryLayerCount",
            "groupMemoryLayerGainCount",
        })
        {
            Assert.True(
                document.RootElement.TryGetProperty(name, out var value),
                $"manifest 缺少字段 {name}");
            Assert.Equal(JsonValueKind.Null, value.ValueKind);
        }
    }

    private static VisualTestManifest Manifest() =>
        new(
            SchemaVersion: 1,
            ScenarioId: "chat-empty",
            GameVersion: "1.6.15.24356",
            SmapiVersion: "4.5.2",
            ModDllSha256: "ABC",
            Locale: "zh-CN",
            BackBufferWidth: 1280,
            BackBufferHeight: 720,
            UiViewportWidth: 1280,
            UiViewportHeight: 720,
            UiScale: 1f,
            Zoom: 1f,
            ScreenshotFile: "chat-empty.png");
}
