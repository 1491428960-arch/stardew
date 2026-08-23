using System.Globalization;
using StardewValley;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

public enum ItemInteractionAction
{
    Display,
    Share,
    Gift,
}

public sealed record ItemSnapshot(
    string ItemId,
    string DisplayName,
    string Category,
    int Quality)
{
    public static ItemSnapshot FromItem(Item item)
    {
        ArgumentNullException.ThrowIfNull(item);
        return new ItemSnapshot(
            string.IsNullOrWhiteSpace(item.QualifiedItemId)
                ? item.ItemId
                : item.QualifiedItemId,
            item.DisplayName,
            item.Category.ToString(CultureInfo.InvariantCulture),
            item.Quality);
    }
}

public sealed record ItemInteractionPreview(
    ItemSnapshot Item,
    ItemInteractionAction Action,
    bool ConsumesItem);

public sealed record ItemConversationSelection(
    Item Item,
    ItemSnapshot Snapshot,
    ItemInteractionAction Action,
    int GiftTaste)
{
    public ItemConversationContext ToConversationContext()
    {
        return new ItemConversationContext(
            Snapshot.ItemId,
            Snapshot.DisplayName,
            Snapshot.Category,
            Snapshot.Quality,
            Action.ToString().ToLowerInvariant(),
            GiftTaste);
    }
}

public static class ItemInteractionRules
{
    public static ItemInteractionPreview CreatePreview(
        ItemSnapshot item,
        ItemInteractionAction action)
    {
        ArgumentNullException.ThrowIfNull(item);
        return new ItemInteractionPreview(item, action, ConsumesItem: false);
    }

    public static bool ShouldInvokeVanillaGift(
        ItemInteractionPreview preview,
        bool confirmed)
    {
        ArgumentNullException.ThrowIfNull(preview);
        return preview.Action == ItemInteractionAction.Gift && confirmed;
    }

    public static int ReadGiftTaste(StardewNpc npc, Item item)
    {
        ArgumentNullException.ThrowIfNull(npc);
        ArgumentNullException.ThrowIfNull(item);
        return npc.getGiftTasteForThisItem(item);
    }
}
