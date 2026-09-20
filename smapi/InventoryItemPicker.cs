using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Microsoft.Xna.Framework.Input;
using StardewValley;
using StardewValley.Menus;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

/// <summary>
/// 用原版 InventoryMenu 选择物品；选择阶段只读，不改动背包。
/// </summary>
public sealed class InventoryItemPicker : IClickableMenu
{
    private readonly StardewNpc npc;
    private readonly Action<ItemConversationSelection> onSelected;
    private readonly Action onCanceled;
    private readonly Rectangle panel;
    private readonly Rectangle displayButton;
    private readonly Rectangle shareButton;
    private readonly Rectangle giftButton;
    private readonly Rectangle cancelButton;
    private readonly InventoryMenu inventoryMenu;
    private Item? selectedItem;

    public InventoryItemPicker(
        StardewNpc npc,
        Action<ItemConversationSelection> onSelected,
        Action onCanceled)
        : base(0, 0, 1, 1)
    {
        this.npc = npc ?? throw new ArgumentNullException(nameof(npc));
        this.onSelected = onSelected ?? throw new ArgumentNullException(nameof(onSelected));
        this.onCanceled = onCanceled ?? throw new ArgumentNullException(nameof(onCanceled));

        var viewport = Game1.viewport;
        var panelWidth = Math.Min(1040, Math.Max(760, viewport.Width - 48));
        var panelHeight = Math.Min(620, Math.Max(500, viewport.Height - 48));
        panel = new Rectangle(
            (viewport.Width - panelWidth) / 2,
            (viewport.Height - panelHeight) / 2,
            panelWidth,
            panelHeight);
        xPositionOnScreen = panel.X;
        yPositionOnScreen = panel.Y;
        width = panel.Width;
        height = panel.Height;

        inventoryMenu = new InventoryMenu(
            panel.X + 48,
            panel.Y + 112,
            playerInventory: true,
            actualInventory: Game1.player.Items,
            highlightMethod: HighlightItem,
            capacity: Game1.player.MaxItems,
            rows: 3,
            horizontalGap: 0,
            verticalGap: 0,
            drawSlots: true);

        var buttonY = panel.Bottom - 88;
        const int buttonWidth = 150;
        const int gap = 12;
        var totalWidth = (buttonWidth * 4) + (gap * 3);
        var buttonX = panel.Center.X - (totalWidth / 2);
        displayButton = new Rectangle(buttonX, buttonY, buttonWidth, 64);
        shareButton = new Rectangle(displayButton.Right + gap, buttonY, buttonWidth, 64);
        giftButton = new Rectangle(shareButton.Right + gap, buttonY, buttonWidth, 64);
        cancelButton = new Rectangle(giftButton.Right + gap, buttonY, buttonWidth, 64);
    }

    public Item? SelectedItem => selectedItem;

    public override void receiveLeftClick(int x, int y, bool playSound = true)
    {
        if (cancelButton.Contains(x, y))
        {
            onCanceled();
            return;
        }

        if (selectedItem is not null)
        {
            if (displayButton.Contains(x, y))
            {
                SelectAction(ItemInteractionAction.Display);
                return;
            }

            if (shareButton.Contains(x, y) && CanShare(selectedItem))
            {
                SelectAction(ItemInteractionAction.Share);
                return;
            }

            if (giftButton.Contains(x, y) && CanGift(selectedItem))
            {
                SelectAction(ItemInteractionAction.Gift);
                return;
            }
        }

        var item = inventoryMenu.getItemAt(x, y);
        if (item is not null && item.Stack > 0)
        {
            selectedItem = item;
        }
    }

    public override void receiveKeyPress(Keys key)
    {
        if (key == Keys.Escape)
        {
            onCanceled();
            return;
        }

        base.receiveKeyPress(key);
    }

    public override void draw(SpriteBatch b)
    {
        Game1.drawDialogueBox(
            panel.X,
            panel.Y,
            panel.Width,
            panel.Height,
            speaker: false,
            drawOnlyBox: true,
            ignoreTitleSafe: true);
        b.DrawString(
            Game1.dialogueFont,
            $"选择要和 {npc.displayName} 互动的物品",
            new Vector2(panel.X + 48, panel.Y + 36),
            Color.Black);
        inventoryMenu.draw(b);

        if (selectedItem is not null)
        {
            b.DrawString(
                Game1.smallFont,
                $"已选择：{selectedItem.DisplayName}",
                new Vector2(panel.X + 48, panel.Bottom - 132),
                Color.DarkSlateGray);
        }

        MenuButtonDrawing.DrawButton(b, displayButton, "展示", selectedItem is not null);
        MenuButtonDrawing.DrawButton(b, shareButton, "分享", selectedItem is not null && CanShare(selectedItem));
        MenuButtonDrawing.DrawButton(b, giftButton, "赠送", selectedItem is not null && CanGift(selectedItem));
        MenuButtonDrawing.DrawButton(b, cancelButton, "取消", true);
        drawMouse(b);
    }

    private bool HighlightItem(Item item)
    {
        return item is not null && item.Stack > 0;
    }

    private bool CanGift(Item item)
    {
        return item is StardewValley.Object &&
            item.canBeGivenAsGift() &&
            npc.CanReceiveGifts();
    }

    private static bool CanShare(Item item)
    {
        return ItemInteractionRules.CanShare(ItemInteractionRules.Classify(item));
    }

    private void SelectAction(ItemInteractionAction action)
    {
        if (selectedItem is null)
        {
            return;
        }

        var snapshot = ItemSnapshot.FromItem(selectedItem);
        var specialInteraction = action == ItemInteractionAction.Share
            ? ItemInteractionRules.ResolveSpecialInteraction(
                npc.Name,
                snapshot.Kind,
                Random.Shared.NextDouble())
            : ItemSpecialInteraction.None;
        onSelected(new ItemConversationSelection(
            selectedItem,
            snapshot,
            action,
            ItemInteractionRules.ReadGiftTaste(npc, selectedItem),
            specialInteraction));
    }
}
