using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewValley;
using StardewValley.Menus;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

public enum DialogueStatus
{
    Idle,
    Sending,
    Success,
    Failed,
}

public sealed class DialogueMenu : IClickableMenu
{
    private readonly BridgeClient bridgeClient;
    private readonly StardewNpc npc;
    private string reply = "点击菜单发送“你好”。";

    public DialogueMenu(StardewNpc npc, BridgeClient bridgeClient)
        : base(Game1.viewport.Width / 2 - 300, Game1.viewport.Height / 2 - 180, 600, 360)
    {
        this.npc = npc;
        this.bridgeClient = bridgeClient;
    }

    public DialogueStatus Status { get; private set; } = DialogueStatus.Idle;

    public async Task SendAsync(string message, CancellationToken cancellationToken = default)
    {
        Status = DialogueStatus.Sending;
        reply = "正在联系本地 Bridge…";

        try
        {
            var state = GameStateCollector.Collect(npc);
            var response = await bridgeClient.SendAsync(
                npc.Name,
                message,
                state,
                cancellationToken);
            reply = response.Reply;
            Status = response.Fallback ? DialogueStatus.Failed : DialogueStatus.Success;
        }
        catch (Exception exception)
        {
            reply = $"离线：{exception.Message}";
            Status = DialogueStatus.Failed;
        }
    }

    public override void receiveLeftClick(int x, int y, bool playSound = true)
    {
        if (x > xPositionOnScreen + width - 64 && y < yPositionOnScreen + 64)
        {
            exitThisMenu();
            return;
        }

        if (Status != DialogueStatus.Sending)
        {
            _ = SendAsync("你好");
        }
    }

    public override void draw(SpriteBatch b)
    {
        Game1.drawDialogueBox(xPositionOnScreen, yPositionOnScreen, width, height, false, true);
        var status = Status switch
        {
            DialogueStatus.Sending => "状态：发送中",
            DialogueStatus.Success => "状态：成功",
            DialogueStatus.Failed => "状态：失败/离线",
            _ => "状态：待发送",
        };
        b.DrawString(Game1.dialogueFont, $"{npc.displayName} · {status}",
            new Vector2(xPositionOnScreen + 48, yPositionOnScreen + 48), Color.Black);
        b.DrawString(Game1.dialogueFont, reply,
            new Vector2(xPositionOnScreen + 48, yPositionOnScreen + 120), Color.Black);
        drawMouse(b);
    }
}
