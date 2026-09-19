using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class VisualTestManifestTests
{
    [Fact]
    public void SerializeUsesStableFieldOrderAndIncludesRuntimeIdentity()
    {
        var manifest = new VisualTestManifest(
            SchemaVersion: 1,
            ScenarioId: "chat-empty",
            GameVersion: "1.6.15.24356",
            SmapiVersion: "4.5.2",
            ModDllSha256: "ABC",
            Locale: "zh-CN",
            BackBufferWidth: 1920,
            BackBufferHeight: 1080,
            UiViewportWidth: 1920,
            UiViewportHeight: 1080,
            UiScale: 1f,
            Zoom: 1f,
            ScreenshotFile: "chat-empty.png");

        var json = manifest.ToJson();

        Assert.StartsWith(
            "{\"schemaVersion\":1,\"scenarioId\":\"chat-empty\"",
            json);
        Assert.Contains("\"modDllSha256\":\"ABC\"", json);
        Assert.Contains("\"screenshotFile\":\"chat-empty.png\"", json);
        Assert.Contains("\"captureSource\":\"backbuffer\"", json);
    }

    [Fact]
    public void SerializeKeepsGroupEvidenceFieldsConsumedByVisualTests()
    {
        var manifest = new VisualTestManifest(
            SchemaVersion: 1,
            ScenarioId: "group-send",
            GameVersion: "1.6.15",
            SmapiVersion: "4.5.2",
            ModDllSha256: "ABC",
            Locale: "zh",
            BackBufferWidth: 1280,
            BackBufferHeight: 720,
            UiViewportWidth: 1280,
            UiViewportHeight: 720,
            UiScale: 1f,
            Zoom: 1f,
            ScreenshotFile: "group-send.png",
            CaptureSource: "isolated-game-spritebatch-render-target",
            GroupResponseTurns: 3,
            GroupMemoryCount: 2,
            GroupMemoryNpcCount: 2,
            GroupInvitationStatus: "Completed",
            GroupRequestStateCount: 2,
            GroupMemoryLayerCount: 3,
            GroupMemoryLayerGainCount: 3);

        var json = manifest.ToJson();

        // 视觉测试的机读断言直接读这些字段（见各场景的 manifest）；字段名或
        // 序列化被改动时会静默变成 null，让断言失去意义，因此逐项钉住。
        Assert.Contains("\"groupResponseTurns\":3", json);
        Assert.Contains("\"groupMemoryCount\":2", json);
        Assert.Contains("\"groupMemoryNpcCount\":2", json);
        Assert.Contains("\"groupInvitationStatus\":\"Completed\"", json);
        Assert.Contains("\"groupRequestStateCount\":2", json);
        Assert.Contains("\"groupMemoryLayerCount\":3", json);
        Assert.Contains("\"groupMemoryLayerGainCount\":3", json);
    }

    [Fact]
    public void RejectsUnsafeScenarioAndScreenshotNames()
    {
        Assert.Throws<ArgumentException>(
            () => VisualTestManifest.ValidateFileName("..\\old.png"));
        Assert.Throws<ArgumentException>(
            () => VisualTestManifest.ValidateFileName("nested/old.png"));
        Assert.Throws<ArgumentException>(
            () => VisualTestManifest.ValidateFileName(string.Empty));
    }
}
