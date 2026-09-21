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

public enum ItemInteractionKind
{
    Other,
    Food,
    Mineral,
    Artifact,
}

public enum ItemSpecialInteraction
{
    None,
    MineralTasting,
}

public sealed record ItemSnapshot(
    string ItemId,
    string DisplayName,
    string Category,
    int Quality,
    ItemInteractionKind Kind = ItemInteractionKind.Other)
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
            item.Quality,
            ItemInteractionRules.Classify(item));
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
    int GiftTaste,
    ItemSpecialInteraction SpecialInteraction = ItemSpecialInteraction.None)
{
    public ItemConversationContext ToConversationContext(int? friendshipAwarded = null)
    {
        var preview = ItemInteractionRules.CreatePreview(Snapshot, Action);
        return new ItemConversationContext(
            Snapshot.ItemId,
            Snapshot.DisplayName,
            Snapshot.Category,
            Snapshot.Quality,
            Action.ToString().ToLowerInvariant(),
            GiftTaste,
            Snapshot.Kind,
            preview.ConsumesItem,
            friendshipAwarded ?? (preview.Action == ItemInteractionAction.Share
                ? ItemInteractionRules.ShareFriendshipPoints
                : 0),
            SpecialInteraction);
    }
}

public static class ItemInteractionRules
{
    public const int ShareFriendshipPoints = 5;
    private const double AbigailMineralTastingChance = 0.20;

    public static ItemInteractionPreview CreatePreview(
        ItemSnapshot item,
        ItemInteractionAction action)
    {
        ArgumentNullException.ThrowIfNull(item);
        return new ItemInteractionPreview(
            item,
            action,
            ConsumesItem: action == ItemInteractionAction.Share && CanShare(item.Kind));
    }

    public static ItemInteractionKind Classify(string? category)
    {
        var normalized = category?.Trim() ?? string.Empty;
        if (normalized is "-7" or "food" or "cooking" or "食物" or "饮料" or "烹饪")
        {
            return ItemInteractionKind.Food;
        }

        if (normalized is "-2" or "-12" or "mineral" or "minerals" or "ore" or
            "gem" or "geode" or "矿石" or "宝石" or "晶球")
        {
            return ItemInteractionKind.Mineral;
        }

        if (normalized is "artifact" or "museum" or "collectible" or "文物" or "收藏品")
        {
            return ItemInteractionKind.Artifact;
        }

        return ItemInteractionKind.Other;
    }

    public static ItemInteractionKind Classify(Item item)
    {
        ArgumentNullException.ThrowIfNull(item);

        if (ReadIntProperty(item, "Edibility") >= 0)
        {
            return ItemInteractionKind.Food;
        }

        if (HasContextTag(item, "mineral") ||
            HasContextTag(item, "ore") ||
            HasContextTag(item, "gem") ||
            HasContextTag(item, "geode"))
        {
            return ItemInteractionKind.Mineral;
        }

        if (HasContextTag(item, "artifact") || HasContextTag(item, "museum"))
        {
            return ItemInteractionKind.Artifact;
        }

        return Classify(item.Category.ToString(CultureInfo.InvariantCulture));
    }

    public static bool CanShare(ItemInteractionKind kind)
    {
        return kind is ItemInteractionKind.Food or
            ItemInteractionKind.Mineral or
            ItemInteractionKind.Artifact;
    }

    public static ItemSpecialInteraction ResolveSpecialInteraction(
        string? npcId,
        ItemInteractionKind kind,
        double roll)
    {
        if (roll < 0 || roll > 1)
        {
            throw new ArgumentOutOfRangeException(nameof(roll));
        }

        if (kind != ItemInteractionKind.Mineral || string.IsNullOrWhiteSpace(npcId))
        {
            return ItemSpecialInteraction.None;
        }

        if (string.Equals(npcId.Trim(), "Dwarf", StringComparison.OrdinalIgnoreCase))
        {
            return ItemSpecialInteraction.MineralTasting;
        }

        if (string.Equals(npcId.Trim(), "Abigail", StringComparison.OrdinalIgnoreCase) &&
            roll < AbigailMineralTastingChance)
        {
            return ItemSpecialInteraction.MineralTasting;
        }

        return ItemSpecialInteraction.None;
    }

    public static bool ShouldInvokeVanillaGift(
        ItemInteractionPreview preview,
        bool confirmed)
    {
        ArgumentNullException.ThrowIfNull(preview);
        return preview.Action == ItemInteractionAction.Gift && confirmed;
    }

    /// <summary>
    /// 赠送只在**当面**成立。
    ///
    /// 原版收礼是「当场把东西递到对方手里」的动作（随即触发 NPC 的反应），
    /// 而线上频道 <see cref="ConversationChannel.Remote"/> 的语义正是
    /// 「只表达当前想法或提出待确认的安排，**不写成已经见面**」——
    /// 隔着地图把礼物塞过去比那还过分，所以线上私聊（B26）里不接赠送。
    ///
    /// 分享与展示不受影响：那两样本来就是「给你看看／分你一点」的线上说法。
    /// </summary>
    public static bool CanGift(string? channel)
    {
        // 大小写不敏感：生产路径上的 channel 已经归一化过，这里是防御性判定，
        // 宁可把 "REMOTE" 也拦住，也不要因为大小写差异放过一次隔空送礼。
        return !string.Equals(channel, ConversationChannel.Remote, StringComparison.OrdinalIgnoreCase);
    }

    public static int ReadGiftTaste(StardewNpc npc, Item item)
    {
        ArgumentNullException.ThrowIfNull(npc);
        ArgumentNullException.ThrowIfNull(item);
        return npc.getGiftTasteForThisItem(item);
    }

    private static int ReadIntProperty(Item item, string name)
    {
        try
        {
            var property = item.GetType().GetProperty(name);
            return property?.GetValue(item) is int value ? value : int.MinValue;
        }
        catch
        {
            return int.MinValue;
        }
    }

    private static bool HasContextTag(Item item, string tag)
    {
        try
        {
            var method = item.GetType().GetMethod("HasContextTag", new[] { typeof(string) });
            return method?.Invoke(item, new object?[] { tag }) is true;
        }
        catch
        {
            return false;
        }
    }
}
