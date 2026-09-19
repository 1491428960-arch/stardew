using System.Text.Json;

namespace StardewAI.NPC;

public sealed record VisualTestManifest(
    int SchemaVersion,
    string ScenarioId,
    string GameVersion,
    string SmapiVersion,
    string ModDllSha256,
    string Locale,
    int BackBufferWidth,
    int BackBufferHeight,
    int UiViewportWidth,
    int UiViewportHeight,
    float UiScale,
    float Zoom,
    string ScreenshotFile,
    string CaptureSource = "backbuffer",
    int? GroupResponseTurns = null,
    int? GroupMemoryCount = null,
    int? GroupMemoryNpcCount = null,
    string? GroupInvitationStatus = null,
    int? GroupRequestStateCount = null,
    int? GroupMemoryLayerCount = null,
    int? GroupMemoryLayerGainCount = null)
{
    public string ToJson()
    {
        ValidateFileName(ScenarioId);
        ValidateFileName(ScreenshotFile);
        var payload = new
        {
            schemaVersion = SchemaVersion,
            scenarioId = ScenarioId,
            gameVersion = GameVersion,
            smapiVersion = SmapiVersion,
            modDllSha256 = ModDllSha256,
            locale = Locale,
            backBufferWidth = BackBufferWidth,
            backBufferHeight = BackBufferHeight,
            uiViewportWidth = UiViewportWidth,
            uiViewportHeight = UiViewportHeight,
            uiScale = UiScale,
            zoom = Zoom,
            screenshotFile = ScreenshotFile,
            captureSource = CaptureSource,
            groupResponseTurns = GroupResponseTurns,
            groupMemoryCount = GroupMemoryCount,
            groupMemoryNpcCount = GroupMemoryNpcCount,
            groupInvitationStatus = GroupInvitationStatus,
            groupRequestStateCount = GroupRequestStateCount,
            groupMemoryLayerCount = GroupMemoryLayerCount,
            groupMemoryLayerGainCount = GroupMemoryLayerGainCount,
        };

        return JsonSerializer.Serialize(payload);
    }

    public static void ValidateFileName(string value)
    {
        if (string.IsNullOrWhiteSpace(value) ||
            value is "." or ".." ||
            Path.GetFileName(value) != value ||
            value.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
        {
            throw new ArgumentException("只允许使用单层文件名。", nameof(value));
        }
    }
}
