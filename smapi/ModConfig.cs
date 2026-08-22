using StardewModdingAPI;
using StardewModdingAPI.Utilities;

namespace StardewAI.NPC;

public sealed class ModConfig
{
    public const int DefaultBridgeTimeoutSeconds = 15;
    public const int MinBridgeTimeoutSeconds = 1;
    public const int MaxBridgeTimeoutSeconds = 120;

    public KeybindList DialogueKey { get; set; } = new(SButton.F8);

    public bool EnableDialogue { get; set; } = true;

    public string BridgeEndpoint { get; set; } = "http://127.0.0.1:5678";

    public int BridgeTimeoutSeconds { get; set; } = DefaultBridgeTimeoutSeconds;

    public static ModConfig CreateDefault() => new();

    public ModConfig Normalize()
    {
        return new ModConfig
        {
            DialogueKey = DialogueKey?.IsBound == true
                ? DialogueKey
                : new KeybindList(SButton.F8),
            EnableDialogue = EnableDialogue,
            BridgeEndpoint = IsSafeEndpoint(BridgeEndpoint)
                ? new Uri(BridgeEndpoint).ToString().TrimEnd('/')
                : "http://127.0.0.1:5678",
            BridgeTimeoutSeconds = BridgeTimeoutSeconds is >= MinBridgeTimeoutSeconds and <= MaxBridgeTimeoutSeconds
                ? BridgeTimeoutSeconds
                : DefaultBridgeTimeoutSeconds,
        };
    }

    public static T ParseDialogueKey<T>(string? value, T fallback)
        where T : struct, Enum
    {
        return Enum.TryParse(value, ignoreCase: true, out T button) &&
            Enum.IsDefined(typeof(T), button)
            ? button
            : fallback;
    }

    private static bool IsSafeEndpoint(string? value)
    {
        return Uri.TryCreate(value, UriKind.Absolute, out var endpoint) &&
            endpoint.IsLoopback &&
            (endpoint.Scheme == Uri.UriSchemeHttp || endpoint.Scheme == Uri.UriSchemeHttps);
    }
}
