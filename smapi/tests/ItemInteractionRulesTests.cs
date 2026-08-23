using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ItemInteractionRulesTests
{
    [Fact]
    public void PreviewAndShareNeverConsumeItem()
    {
        var action = ItemInteractionRules.CreatePreview(
            new ItemSnapshot("74", "黄金南瓜", "礼物", 0),
            ItemInteractionAction.Share);

        Assert.Equal(ItemInteractionAction.Share, action.Action);
        Assert.False(action.ConsumesItem);
    }

    [Fact]
    public void GiftRequiresExplicitConfirmation()
    {
        var pending = ItemInteractionRules.CreatePreview(
            new ItemSnapshot("74", "黄金南瓜", "礼物", 0),
            ItemInteractionAction.Gift);

        Assert.False(pending.ConsumesItem);
        Assert.False(ItemInteractionRules.ShouldInvokeVanillaGift(pending, confirmed: false));
        Assert.True(ItemInteractionRules.ShouldInvokeVanillaGift(pending, confirmed: true));
    }
}
