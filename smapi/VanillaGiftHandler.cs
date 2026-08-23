using StardewValley;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

/// <summary>
/// 只调用原版 NPC 收礼入口，不在 Mod 中直接修改背包堆叠数量。
/// </summary>
public static class VanillaGiftHandler
{
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
}
