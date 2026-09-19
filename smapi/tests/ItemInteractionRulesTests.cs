using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ItemInteractionRulesTests
{
    [Fact]
    public void ShareConsumes_food_mineral_and_artifact_items()
    {
        var food = ItemInteractionRules.CreatePreview(
            new ItemSnapshot("194", "炒青豆", "食物", 0, ItemInteractionKind.Food),
            ItemInteractionAction.Share);
        var mineral = ItemInteractionRules.CreatePreview(
            new ItemSnapshot("80", "石英", "矿石", 0, ItemInteractionKind.Mineral),
            ItemInteractionAction.Share);
        var artifact = ItemInteractionRules.CreatePreview(
            new ItemSnapshot("96", "矮人头盔", "文物", 0, ItemInteractionKind.Artifact),
            ItemInteractionAction.Share);

        Assert.True(food.ConsumesItem);
        Assert.True(mineral.ConsumesItem);
        Assert.True(artifact.ConsumesItem);
    }

    [Fact]
    public void Display_never_consumes_and_unknown_items_cannot_be_shared()
    {
        var display = ItemInteractionRules.CreatePreview(
            new ItemSnapshot("(BC)Bench", "长椅", "家具", 0, ItemInteractionKind.Other),
            ItemInteractionAction.Display);
        var unknownShare = ItemInteractionRules.CreatePreview(
            new ItemSnapshot("(O)246", "南瓜种子", "种子", 0, ItemInteractionKind.Other),
            ItemInteractionAction.Share);

        Assert.False(display.ConsumesItem);
        Assert.False(unknownShare.ConsumesItem);
        Assert.False(ItemInteractionRules.CanShare(ItemInteractionKind.Other));
    }

    [Theory]
    [InlineData("-7", ItemInteractionKind.Food)]
    [InlineData("-12", ItemInteractionKind.Mineral)]
    [InlineData("artifact", ItemInteractionKind.Artifact)]
    public void Classifies_shareable_item_categories(string category, ItemInteractionKind expected)
    {
        Assert.Equal(expected, ItemInteractionRules.Classify(category));
        Assert.True(ItemInteractionRules.CanShare(expected));
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

    [Fact]
    public void Mineral_tasting_easter_egg_is_game_side_and_not_model_decided()
    {
        Assert.Equal(
            ItemSpecialInteraction.MineralTasting,
            ItemInteractionRules.ResolveSpecialInteraction(
                "Dwarf",
                ItemInteractionKind.Mineral,
                roll: 0.99));
        Assert.Equal(
            ItemSpecialInteraction.MineralTasting,
            ItemInteractionRules.ResolveSpecialInteraction(
                "Abigail",
                ItemInteractionKind.Mineral,
                roll: 0.19));
        Assert.Equal(
            ItemSpecialInteraction.None,
            ItemInteractionRules.ResolveSpecialInteraction(
                "Abigail",
                ItemInteractionKind.Mineral,
                roll: 0.20));
        Assert.Equal(
            ItemSpecialInteraction.None,
            ItemInteractionRules.ResolveSpecialInteraction(
                "Dwarf",
                ItemInteractionKind.Artifact,
                roll: 0));
    }
}
