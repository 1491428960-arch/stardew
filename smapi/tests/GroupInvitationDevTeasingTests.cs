using System.Linq;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 开发用的「直接造一张打趣卡」入口（2026-10-09；Ctrl+Shift+F9 / 控制台 <c>ainpc_invite</c>）。
///
/// 它存在的唯一理由是把「验措辞」和「等生成」解耦：真机上要看到一张**新**打趣卡，
/// 得同时等过 7 天主题冷却、2 天生成节奏、以及那一轮恰好挑中 ≥2 位已接受者 ——
/// 三道闸门叠加，改一次措辞要等一周才能验一次，根本改不动。
///
/// 下面这些测试守的是两件相反的事，缺一不可：
/// ① 它**确实绕过了**那三道闸门（否则这功能没用）；
/// ② 它**没有把卡片本身做坏** —— 绕闸门是目的，做出与自然生成不一致的卡就是 bug。
/// 第 ② 条尤其重要：这个项目反复出现的失败形态是「能力做好了但没人调用」
/// （<c>DiscloseRelationship</c> 至今零生产调用点就是同一个形状），
/// 所以必须证明协调器真的把卡塞进了队列，而不只是生成器能造出来。
/// </summary>
public sealed class GroupInvitationDevTeasingTests
{
    private static readonly (string Id, string Name)[] Pair =
    {
        ("Abigail", "阿比盖尔"), ("Emily", "艾米丽"),
    };

    private static GroupParticipantCandidate[] Group() =>
        Pair.Select(item => new GroupParticipantCandidate(item.Id, item.Name, HasFriendshipRecord: true))
            .ToArray();

    [Fact]
    public void Forced_teasing_works_even_when_the_theme_is_on_cooldown()
    {
        var generator = new GroupInvitationGenerator(GroupInvitationTemplates.All);
        // 今天刚生成过一张打趣卡 —— 自然路径此时因冷却与去重，不可能再产出打趣卡。
        var existing = GroupInvitationTeasingTests.Generate(
            new[] { "Abigail", "Emily" }, 20, null, Pair);
        Assert.True(GroupInvitationTeasingTests.IsTeasing(existing));

        var natural = generator.Generate(GroupInvitationTeasingTests.Context(
            new[] { "Abigail", "Emily" }, new[] { existing }, 20, Pair));
        // 自然路径不会**什么都没产出**（还有 animals 等普通主题），
        // 但一定不会再给一张打趣卡 —— 这才是要断言的那件事。
        Assert.All(
            natural,
            invitation => Assert.False(GroupInvitationTeasingTests.IsTeasing(invitation)));

        var forced = Assert.Single(generator.GenerateForcedTeasing(20, "Spring 20", Group()));
        Assert.True(GroupInvitationTeasingTests.IsTeasing(forced));
    }

    [Fact]
    public void Forced_teasing_card_carries_the_same_fields_as_a_natural_one()
    {
        var forced = Assert.Single(new GroupInvitationGenerator(GroupInvitationTemplates.All)
            .GenerateForcedTeasing(20, "Spring 20", Group()));

        // 与 GroupInvitationTeasingTests 里自然生成的卡逐项对齐。
        Assert.Equal("几个人和玩家之间的来往", forced.Topic);
        Assert.Equal("镇上那点风声", forced.Title);
        Assert.Contains("打趣", forced.Guidance);
        // ⚠ Guidance 里点名用的是 **npcId**（`CreateTeasing` 走 `InOnIt`），
        // 不是本地化名 —— 这是给模型看的文本，不是给玩家看的，属既有设计。
        Assert.Contains("Abigail", forced.Guidance);
        Assert.Contains("Emily", forced.Guidance);

        Assert.Equal(new[] { "Abigail", "Emily" }, forced.Participants);
        // 而卡片列表给玩家看的是本地化名 —— 两条路径不能混。
        Assert.Equal(new[] { "阿比盖尔", "艾米丽" }, forced.ParticipantDisplayNames);

        Assert.Equal(GroupInvitationStatus.Unread, forced.Status);
        Assert.Equal(20, forced.CreatedTotalDays);
        Assert.Equal(20 + GroupInvitationRules.ExpirationDays, forced.ExpiresTotalDays);
        // 2026-09-20 真机事故：模板 ID 不在白名单里会**在 DayStarted 里抛异常，
        // 之后再也不生成任何邀约**。dev 造的卡走同一条校验，必须过。
        Assert.True(GroupInvitationRules.IsKnownTemplateId(forced.TemplateId));
    }

    [Fact]
    public void Coordinator_injects_the_card_into_the_queue()
    {
        var store = new StoryStateStore();
        Assert.Equal(2, store.EnsureSpouseAcceptance(new[] { "Abigail", "Emily" }));
        var coordinator = new GroupDialogueCoordinator(
            store,
            new GroupInvitationGenerator(GroupInvitationTemplates.All),
            () => Group(),
            () => 20,
            () => "Spring 20");

        var summary = coordinator.TryInjectTeasingInvitation(Group());

        var injected = Assert.Single(store.State.GroupDialogueInvitations);
        Assert.True(GroupInvitationTeasingTests.IsTeasing(injected));
        Assert.Contains(injected.InvitationId, summary);
    }

    [Fact]
    public void Coordinator_refuses_a_group_that_is_too_small()
    {
        var store = new StoryStateStore();
        var coordinator = new GroupDialogueCoordinator(
            store,
            new GroupInvitationGenerator(GroupInvitationTemplates.All),
            () => Group(),
            () => 20,
            () => "Spring 20");

        var summary = coordinator.TryInjectTeasingInvitation(
            new[] { new GroupParticipantCandidate("Abigail", "阿比盖尔", HasFriendshipRecord: true) });

        // 拒绝时既要说清原因，也不能留下半张卡。
        Assert.Contains("至少要", summary);
        Assert.Empty(store.State.GroupDialogueInvitations);
    }
}
