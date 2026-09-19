using StardewModdingAPI;
using StardewModdingAPI.Utilities;

namespace StardewAI.NPC;

public sealed class ModConfig
{
    // Bridge 云端请求最多等待 45 秒；客户端最多等待 60 秒，留出读取余量。
    public const int DefaultBridgeTimeoutSeconds = 60;
    public const int MinBridgeTimeoutSeconds = 1;
    public const int MaxBridgeTimeoutSeconds = 120;

    /// <summary>
    /// 线上群聊默认策略：自然接话流，允许多人依次发言而不是固定一人一句。
    /// </summary>
    public const string MultiTurnGroupStrategy = "multi_turn";

    /// <summary>旧的固定一人一轮策略，保留为可回退选项。</summary>
    public const string TurnBasedGroupStrategy = "turn_based";

    public KeybindList DialogueKey { get; set; } = new(SButton.F8);

    public KeybindList GroupDialogueKey { get; set; } = new(SButton.F9);

    public bool EnableDialogue { get; set; } = true;

    /// <summary>
    /// 是否记录 Rendered 事件的窗口帧率，用于游戏内性能诊断；普通运行默认关闭。
    /// </summary>
    public bool EnablePerformanceDiagnostics { get; set; }

    /// <summary>
    /// 允许单人游戏提前进入已识别的 NPC 住宅；个人测试档默认开启。
    /// </summary>
    public bool EnableHouseAccess { get; set; } = true;

    /// <summary>
    /// 是否连同住宅与商店共用的复合建筑一起放宽；个人测试档默认开启。
    /// </summary>
    public bool AllowMixedBuildingAccess { get; set; } = true;

    public string BridgeEndpoint { get; set; } = "http://127.0.0.1:5678";

    public int BridgeTimeoutSeconds { get; set; } = DefaultBridgeTimeoutSeconds;

    /// <summary>
    /// 线上群聊策略。默认 natural 接话流（multi_turn）：一次请求可以让名单里
    /// 多个人依次发言；turn_based 只让当前发言人回一句，作为回退选项保留。
    /// </summary>
    public string GroupDialogueStrategy { get; set; } = MultiTurnGroupStrategy;

    public static ModConfig CreateDefault() => new();

    public ModConfig Normalize()
    {
        var normalizedDialogueKey = DialogueKey?.IsBound == true
            ? DialogueKey
            : new KeybindList(SButton.F8);
        var normalizedGroupDialogueKey = GroupDialogueKey?.IsBound == true
            ? GroupDialogueKey
            : new KeybindList(SButton.F9);
        if (string.Equals(
                normalizedDialogueKey.ToString(),
                normalizedGroupDialogueKey.ToString(),
                StringComparison.OrdinalIgnoreCase))
        {
            normalizedGroupDialogueKey = new KeybindList(
                normalizedDialogueKey.ToString().Equals(
                    "F9",
                    StringComparison.OrdinalIgnoreCase)
                    ? SButton.F10
                    : SButton.F9);
        }

        return new ModConfig
        {
            DialogueKey = normalizedDialogueKey,
            GroupDialogueKey = normalizedGroupDialogueKey,
            EnableDialogue = EnableDialogue,
            EnablePerformanceDiagnostics = EnablePerformanceDiagnostics,
            EnableHouseAccess = EnableHouseAccess,
            AllowMixedBuildingAccess = AllowMixedBuildingAccess,
            BridgeEndpoint = IsSafeEndpoint(BridgeEndpoint)
                ? new Uri(BridgeEndpoint).ToString().TrimEnd('/')
                : "http://127.0.0.1:5678",
            BridgeTimeoutSeconds = BridgeTimeoutSeconds is >= MinBridgeTimeoutSeconds and <= MaxBridgeTimeoutSeconds
                ? BridgeTimeoutSeconds
                : DefaultBridgeTimeoutSeconds,
            GroupDialogueStrategy = NormalizeGroupStrategy(GroupDialogueStrategy),
        };
    }

    /// <summary>只接受 multi_turn 与 turn_based；其他值（含空）一律回落到默认。</summary>
    public static string NormalizeGroupStrategy(string? value)
    {
        return string.Equals(
            value?.Trim(),
            TurnBasedGroupStrategy,
            StringComparison.OrdinalIgnoreCase)
            ? TurnBasedGroupStrategy
            : MultiTurnGroupStrategy;
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
