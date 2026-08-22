using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewModdingAPI.Utilities;
using StardewValley;

namespace StardewAI.NPC;

public sealed class ModEntry : Mod
{
    private ModConfig config = ModConfig.CreateDefault();
    private BridgeClient? bridgeClient;
    private KeybindList dialogueKey = new(SButton.F8);

    public override void Entry(IModHelper helper)
    {
        config = helper.ReadConfig<ModConfig>().Normalize();
        ApplyConfig();
        GameStateCollector.ConfigureModRegistry(new SmapiModRegistryStatus(helper.ModRegistry));
        helper.Events.Input.ButtonPressed += OnButtonPressed;
        helper.Events.GameLoop.GameLaunched += OnGameLaunched;
        Monitor.Log($"AI NPC 原型已加载。按 {dialogueKey} 与 Rasmodia 对话。", LogLevel.Info);
    }

    private void OnGameLaunched(object? sender, GameLaunchedEventArgs e)
    {
        var api = Helper.ModRegistry.GetApi<IGenericModConfigMenuApi>("spacechase0.GenericModConfigMenu");
        if (api is null)
        {
            return;
        }

        api.Register(ModManifest, ResetConfig, SaveConfig);
        api.AddKeybindList(
            ModManifest,
            () => config.DialogueKey,
            value => config.DialogueKey = value.IsBound ? value : new KeybindList(SButton.F8),
            () => "Dialogue key",
            () => "启动与 Rasmodia 对话的快捷键。",
            "DialogueKey");
        api.AddBoolOption(
            ModManifest,
            () => config.EnableDialogue,
            value => config.EnableDialogue = value,
            () => "Enable dialogue",
            () => "是否启用 AI NPC 对话。",
            "EnableDialogue");
        api.AddTextOption(
            ModManifest,
            () => config.BridgeEndpoint,
            value => config.BridgeEndpoint = value,
            () => "Bridge endpoint",
            () => "仅允许本机回环 HTTP(S) 地址。",
            fieldId: "BridgeEndpoint");
        api.AddNumberOption(
            ModManifest,
            () => config.BridgeTimeoutSeconds,
            value => config.BridgeTimeoutSeconds = value,
            () => "Bridge timeout (seconds)",
            () => "请求超时秒数，范围为 1 到 120。",
            ModConfig.MinBridgeTimeoutSeconds,
            ModConfig.MaxBridgeTimeoutSeconds,
            1,
            fieldId: "BridgeTimeoutSeconds");
    }

    private void ResetConfig()
    {
        config = ModConfig.CreateDefault();
        ApplyConfig();
    }

    private void SaveConfig()
    {
        config = config.Normalize();
        Helper.WriteConfig(config);
        ApplyConfig();
    }

    private void ApplyConfig()
    {
        config = config.Normalize();
        dialogueKey = config.DialogueKey;
        bridgeClient?.Dispose();
        bridgeClient = config.EnableDialogue
            ? new BridgeClient(
                endpoint: new Uri(config.BridgeEndpoint),
                timeout: TimeSpan.FromSeconds(config.BridgeTimeoutSeconds))
            : null;
    }

    private void OnButtonPressed(object? sender, ButtonPressedEventArgs e)
    {
        if (!config.EnableDialogue || !dialogueKey.JustPressed() || !Context.IsWorldReady || Game1.activeClickableMenu is not null ||
            bridgeClient is null)
        {
            return;
        }

        var rasmodia = Game1.getCharacterFromName("Rasmodia");
        if (rasmodia is null)
        {
            Monitor.Log("未找到 Rasmodia；请确认对应 NPC 内容包已启用。", LogLevel.Warn);
            return;
        }

        Game1.activeClickableMenu = new DialogueMenu(rasmodia, bridgeClient);
    }

    private sealed class SmapiModRegistryStatus : IModRegistryStatus
    {
        private readonly IModRegistry registry;

        public SmapiModRegistryStatus(IModRegistry registry)
        {
            this.registry = registry;
        }

        public bool IsLoaded(string uniqueId)
        {
            try
            {
                return registry.IsLoaded(uniqueId);
            }
            catch
            {
                return false;
            }
        }
    }
}
