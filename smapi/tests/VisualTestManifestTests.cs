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
