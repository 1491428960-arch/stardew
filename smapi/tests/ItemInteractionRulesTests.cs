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

    /// <summary>
    /// B26 的线上私聊不能让礼物隔空送达：原版收礼是当场递过去，
    /// 而 remote 频道的语义是「不写成已经见面」。分享／展示不受这条限制。
    /// </summary>
    [Theory]
    [InlineData(ConversationChannel.FaceToFace, true)]
    [InlineData(ConversationChannel.Remote, false)]
    [InlineData(null, true)]
    [InlineData("", true)]
    [InlineData("REMOTE", false)]
    public void Gifting_requires_being_face_to_face(string? channel, bool expected)
    {
        Assert.Equal(expected, ItemInteractionRules.CanGift(channel));
    }

    /// <summary>
    /// 玩家那一句话是游戏端**唯一**能让 NPC 分辨展示／分享／赠送的信号：
    /// 线上（compact）路径不下发 itemContext 指令卡（`prompts.py` 的
    /// `not runtime_compact` 分支），三种动作的语义差别只能靠这句话承载。
    ///
    /// 2026-09-23 实机：原措辞「我们一起分享这个：绿宝石。」语义歧义，
    /// 索菲亚直接反问「绿宝石……我们？」—— 歧义变成了跑偏的回复。
    /// 分享的语义是「分你一点」（见 <see cref="CanGift"/> 的摘要），不是「一起分享」。
    /// </summary>
    [Fact]
    public void Share_message_says_the_item_is_split_with_her()
    {
        var share = ItemInteractionRules.DescribeItemAction(
            ItemInteractionAction.Share,
            "绿宝石");

        Assert.Contains("绿宝石", share);
        Assert.Contains("分", share);
        Assert.DoesNotContain("我们一起", share);
    }

    /// <summary>
    /// 三种动作必须说得出区别 —— 否则 NPC 只能靠猜，展示与分享就会长成同一句话。
    /// </summary>
    [Fact]
    public void Each_item_action_gets_a_distinct_message()
    {
        var display = ItemInteractionRules.DescribeItemAction(
            ItemInteractionAction.Display,
            "五彩碎片");
        var share = ItemInteractionRules.DescribeItemAction(
            ItemInteractionAction.Share,
            "五彩碎片");
        var gift = ItemInteractionRules.DescribeItemAction(
            ItemInteractionAction.Gift,
            "五彩碎片");

        Assert.NotEqual(display, share);
        Assert.NotEqual(share, gift);
        Assert.NotEqual(display, gift);
        Assert.Contains("看看", display);
        Assert.Contains("送给你", gift);
    }

    /// <summary>
    /// 分享按钮变灰时点它**毫无反应**（<c>InventoryItemPicker.receiveLeftClick</c>
    /// 里那个分支直接落掉），玩家只能猜自己哪里做错了。
    /// 2026-09-23 实机反馈正是「这个东西是灰的点了没反应」——
    /// 灰按钮至少要说出理由。
    /// </summary>
    [Fact]
    public void Unavailable_share_explains_itself_instead_of_staying_silent()
    {
        Assert.Null(ItemInteractionRules.ShareUnavailableReason(
            ItemInteractionKind.Mineral,
            "绿宝石"));

        var reason = ItemInteractionRules.ShareUnavailableReason(
            ItemInteractionKind.Other,
            "南瓜种子");

        Assert.NotNull(reason);
        Assert.Contains("南瓜种子", reason);
    }
}
