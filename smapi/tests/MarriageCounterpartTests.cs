using System.Linq;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 婚姻事实必须带上「另一端是谁」。
/// </summary>
/// <remarks>
/// 2026-10-04 实机事故（用户原话：「维克托不知道他妈嫁给我了，这不对吧」）。
///
/// 根因不是数据缺失，也不是"NPC 互相不认识"：`townRelations` 里
/// `Victor：Olivia妈妈` 一直都在，Bridge 实测也确认投给了 Victor。缺口在婚姻
/// view 的**语义**上——它只写 SubjectNpcId（配偶自己），没写另一端，于是
/// Victor 读到「Olivia 已婚」+「Olivia 是我妈妈」，能推出的上限是
/// 「我妈妈结婚了」，推不出新郎就是玩家。
///
/// 这几条测试守的就是那个被丢掉的一半。
/// </remarks>
public class MarriageCounterpartTests
{
    [Fact]
    public void Wedding_view_names_both_ends_of_the_marriage()
    {
        var store = new StoryStateStore();

        store.SyncMarriages(new[] { "Olivia" }, "spring 12");

        var view = store
            .RelationshipSnapshotFor("Olivia")
            .Views.Single(v => v.RelationType == "married");

        Assert.Equal("Olivia", view.SubjectNpcId);
        Assert.Equal("player", view.CounterpartNpcId);
    }

    [Fact]
    public void Counterpart_is_the_player_for_every_spouse_not_the_viewer()
    {
        // 这是修复的核心：另一端是玩家，不是"读这条 view 的人"。
        // 原实现干脆没有这个字段，所以 Victor 拿到的信息和 Sophia 一样贫瘠。
        var store = new StoryStateStore();

        store.SyncMarriages(new[] { "Olivia", "Abigail", "Sophia" }, "spring 12");

        foreach (var viewer in new[] { "Olivia", "Abigail", "Sophia", "Victor" })
        {
            var views = store
                .RelationshipSnapshotFor(viewer)
                .Views.Where(v => v.RelationType == "married")
                .ToArray();

            Assert.All(views, view => Assert.Equal("player", view.CounterpartNpcId));
        }
    }

    [Fact]
    public void Family_member_of_a_spouse_can_learn_who_the_spouse_married()
    {
        // 用户的原始场景：Victor 是 Olivia 的儿子，他应该能看到
        // 「Olivia 和玩家结了婚」这条完整事实，而不是只知道"我妈已婚"。
        var store = new StoryStateStore();

        store.SyncMarriages(new[] { "Olivia" }, "spring 12");

        var victorViews = store
            .RelationshipSnapshotFor("Victor")
            .Views.Where(view => view.RelationType == "married")
            .ToArray();

        var oliviaView = Assert.Single(victorViews);
        Assert.Equal("Olivia", oliviaView.SubjectNpcId);
        Assert.Equal("player", oliviaView.CounterpartNpcId);
        Assert.Equal("known", oliviaView.Visibility);
    }

    [Fact]
    public void Counterpart_stays_null_on_non_marriage_views()
    {
        // 只有婚姻事实才需要宾语。恋人 / 暧昧阶段不进公开知识，
        // 不该因为这次改动被顺手补上 counterpart。
        var store = new StoryStateStore();

        store.SyncMarriages(new[] { "Olivia" }, "spring 12");

        var snapshot = store.RelationshipSnapshotFor("Olivia");
        Assert.All(
            snapshot.Views.Where(view => view.RelationType != "married"),
            view => Assert.Null(view.CounterpartNpcId));
    }
}