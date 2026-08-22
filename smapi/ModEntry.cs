using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;

namespace StardewAI.NPC;

public sealed class ModEntry : Mod
{
    private BridgeClient? bridgeClient;

    public override void Entry(IModHelper helper)
    {
        bridgeClient = new BridgeClient();
        helper.Events.Input.ButtonPressed += OnButtonPressed;
        Monitor.Log("AI NPC 原型已加载。按 N 与 Rasmodia 对话。", LogLevel.Info);
    }

    private void OnButtonPressed(object? sender, ButtonPressedEventArgs e)
    {
        if (e.Button != SButton.N || !Context.IsWorldReady || Game1.activeClickableMenu is not null ||
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
}
