using StardewValley;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

/// <summary>
/// 只调用原版 NPC 收礼入口，不在 Mod 中直接修改背包堆叠数量。
/// </summary>
public static class VanillaGiftHandler
{
    public static bool TryConsumeOne(Item item, Farmer farmer)
    {
        ArgumentNullException.ThrowIfNull(item);
        ArgumentNullException.ThrowIfNull(farmer);

        if (item.Stack <= 0 || !farmer.Items.Contains(item))
        {
            return false;
        }

        item.Stack -= 1;
        if (item.Stack <= 0)
        {
            farmer.Items.Remove(item);
        }

        return true;
    }

    public static int TryAwardShareFriendship(
        StardewNpc npc,
        Farmer farmer,
        ShareFriendshipLedger ledger,
        int gameDay)
    {
        ArgumentNullException.ThrowIfNull(npc);
        ArgumentNullException.ThrowIfNull(farmer);
        ArgumentNullException.ThrowIfNull(ledger);

        if (!HasFriendshipRecord(farmer, npc.Name) ||
            !ledger.TryClaim(npc.Name, gameDay))
        {
            return 0;
        }

        farmer.changeFriendship(ItemInteractionRules.ShareFriendshipPoints, npc);
        return ItemInteractionRules.ShareFriendshipPoints;
    }

    public static bool TryGive(StardewNpc npc, Item item, Farmer farmer)
    {
        ArgumentNullException.ThrowIfNull(npc);
        ArgumentNullException.ThrowIfNull(item);
        ArgumentNullException.ThrowIfNull(farmer);

        if (item is not StardewValley.Object gift || !npc.CanReceiveGifts())
        {
            return false;
        }

        var previousActiveObject = farmer.ActiveObject;
        farmer.ActiveObject = gift;
        try
        {
            return npc.tryToReceiveActiveObject(farmer, probe: false);
        }
        finally
        {
            farmer.ActiveObject = previousActiveObject;
        }
    }

    private static bool HasFriendshipRecord(Farmer farmer, string npcId)
    {
        var flags = System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.Instance;
        var property = farmer.GetType().GetProperty("friendshipData", flags);
        var data = property?.GetValue(farmer);
        if (data is null)
        {
            data = farmer.GetType().GetField("friendshipData", flags)?.GetValue(farmer);
        }

        return FriendshipDataAccessor.ContainsKey(data, npcId);
    }
}
