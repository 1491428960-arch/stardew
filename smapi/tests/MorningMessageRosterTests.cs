using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 「早上有人主动发来消息」在 F8 名单上的两个表现：**置顶**与**标记**。
///
/// 置顶是「只看名字」那条排序规则唯一的例外，所以这里既要守住新行为，
/// 也要守住**没有未读消息时行为一点没变**——否则等于把 2026-09-21 定稿的
/// 排序口径悄悄改掉了。
/// </summary>
public sealed class MorningMessageRosterTests
{
    private static PrivateChatRosterSource Source(
        string npcId,
        bool hasUnreadMorning = false,
        bool isPresent = false,
        float distanceInTiles = float.MaxValue)
    {
        return new PrivateChatRosterSource(
            npcId,
            npcId,
            isPresent,
            distanceInTiles,
            IsInteractionTarget: false,
            HasUnreadMorning: hasUnreadMorning);
    }

    [Fact]
    public void Senders_are_pinned_above_everyone_else()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Abigail"),
            Source("Emily"),
            Source("Sophia", hasUnreadMorning: true),
        });

        Assert.Equal(
            new[] { "Sophia", "Abigail", "Emily" },
            roster.Select(entry => entry.NpcId));
    }

    /// <summary>一天可能有一两个人发；他们之间仍然按名字排，不引入第二种次序。</summary>
    [Fact]
    public void Multiple_senders_are_ordered_by_name_among_themselves()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Sophia", hasUnreadMorning: true),
            Source("Abigail", hasUnreadMorning: true),
            Source("Emily"),
            Source("Zoe"),
        });

        Assert.Equal(
            new[] { "Abigail", "Sophia", "Emily", "Zoe" },
            roster.Select(entry => entry.NpcId));
    }

    /// <summary>回归：没人发消息时，顺序必须与加这个功能之前**逐字一致**。</summary>
    [Fact]
    public void Without_any_sender_the_order_is_unchanged()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Pierre"),
            Source("Emily", isPresent: true, distanceInTiles: 8f),
            Source("Abigail", isPresent: true, distanceInTiles: 1f),
            Source("Sebastian"),
        });

        Assert.Equal(
            new[] { "Abigail", "Emily", "Pierre", "Sebastian" },
            roster.Select(entry => entry.NpcId));
    }

    /// <summary>
    /// 置顶**只挪位置，不改状态字**：位置原本会随玩家走动变，而这里置顶的是
    /// 「有人给你留了话」这件稳定的事——每行右侧该说什么还是说什么。
    /// </summary>
    [Fact]
    public void Pinning_does_not_disturb_status_labels()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Abigail", hasUnreadMorning: true, isPresent: true, distanceInTiles: 1f),
            Source("Emily", isPresent: true, distanceInTiles: 9f),
            Source("Pierre"),
        });

        Assert.Equal(
            new[] { "身边", "同处一地", "线上" },
            roster.Select(entry => entry.StatusLabel));
    }

    [Fact]
    public void Unread_label_is_set_only_for_senders()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Sophia", hasUnreadMorning: true),
            Source("Abigail"),
        });

        Assert.Equal("新消息", roster.Single(e => e.NpcId == "Sophia").UnreadLabel);
        // 空串而不是 null：名单里绝大多数行都是空的，画之前先判空就够了。
        Assert.Equal(string.Empty, roster.Single(e => e.NpcId == "Abigail").UnreadLabel);
    }

    /// <summary>同一个人被传两次时仍然只出现一行，且仍然置顶。</summary>
    [Fact]
    public void A_sender_appearing_twice_still_yields_one_pinned_row()
    {
        var roster = PrivateChatRosterRules.Build(new[]
        {
            Source("Sophia", hasUnreadMorning: true),
            Source("Sophia"),
            Source("Abigail"),
        });

        Assert.Equal(new[] { "Sophia", "Abigail" }, roster.Select(entry => entry.NpcId));
    }

    /// <summary>
    /// 空名单与 null 不因为多了这一维就抛异常——名单本身来自存档，
    /// 新档里一个人都没有是正常状态。
    /// </summary>
    [Fact]
    public void Empty_input_still_returns_empty()
    {
        Assert.Empty(PrivateChatRosterRules.Build(Array.Empty<PrivateChatRosterSource>()));
        Assert.Empty(PrivateChatRosterRules.Build(null));
    }
}
