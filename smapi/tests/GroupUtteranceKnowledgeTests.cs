using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 群聊里**别的 NPC** 说的话 → 隐性知识（2026-10-04）。
///
/// 用户口径两句话定死了这个功能的形状：
///
/// ① 「群聊记忆中别的 npc 说了什么能不能作为一个隐性的知识库这样的形式，
///    我不主动提到就不唤醒」
/// ② 「标记吧」（她自己在群里说的话要带来源标记 —— 那条已由
///    <c>BridgeClient.RememberGroupTurn</c> 实现，**本次不动**）
///
/// 现状缺口：<see cref="GroupMemoryRules.Plan"/> 只按「参与者 × 玩家高亮」做笛卡尔积，
/// 于是**同一句玩家的话被复制 N 份**（每人一条），而**任何 NPC 说过什么，一条都不记**
/// （见该类注释「闲聊不会出现在高亮里」）。群聊攒了很久，NPC 之间仍然互相失忆。
///
/// 与「玩家说的」那条路的区别，正是本测试要钉住的东西：
/// - 玩家说的 → 每人各记一条**同一句话**（既有行为，不改）
/// - NPC 说的 → 每位在场者记**别人**说的话，且**不记自己说的**
///   （自己说的走 <c>RememberGroupTurn</c> 的发送窗口，第一人称）
/// </summary>
public sealed class GroupUtteranceKnowledgeTests
{
    [Fact]
    public void 在场者记住别人说的话()
    {
        var writes = GroupUtteranceRules.Plan(
            new[] { "Sophia", "Abigail", "Emily" },
            new[]
            {
                new GroupUtterance("Sophia", "我最近在酒窖里研究新的酿法。"),
                new GroupUtterance("Abigail", "我倒是想练练剑。"),
            });

        // Sophia 该记住 Abigail 说的那句。
        Assert.Contains(
            writes,
            w => w.OwnerNpcId == "Sophia" && w.Content.Contains("练练剑"));

        // Abigail 该记住 Sophia 说的那句。
        Assert.Contains(
            writes,
            w => w.OwnerNpcId == "Abigail" && w.Content.Contains("酿法"));

        // Emily 全程没说话，但她在场，两句都该记住。
        Assert.Contains(
            writes,
            w => w.OwnerNpcId == "Emily" && w.Content.Contains("酿法"));
        Assert.Contains(
            writes,
            w => w.OwnerNpcId == "Emily" && w.Content.Contains("练练剑"));
    }

    [Fact]
    public void 不把某人自己说的话记成隐性知识()
    {
        // 她自己说的已经由 `RememberGroupTurn` 写进发送窗口（第一人称）。
        // 若这里再记一份，私聊里会出现「听说 Sophia 说过……」这种荒唐转述。
        var writes = GroupUtteranceRules.Plan(
            new[] { "Sophia", "Abigail" },
            new[] { new GroupUtterance("Sophia", "我最近在酒窖里研究新的酿法。") });

        Assert.DoesNotContain(
            writes,
            w => w.OwnerNpcId == "Sophia" && w.Content.Contains("酿法"));
    }

    [Fact]
    public void 转述里带上是谁说的()
    {
        // 隐性知识的语义是「我知道**某人**说过这事」，不是「我知道这事」。
        // 丢掉说话人，NPC 会在私聊里把别人的话当成无主的事实断言出来。
        var writes = GroupUtteranceRules.Plan(
            new[] { "Sophia", "Abigail" },
            new[] { new GroupUtterance("Abigail", "我倒是想练练剑。") });

        var write = Assert.Single(writes, w => w.OwnerNpcId == "Sophia");
        Assert.Contains("Abigail", write.Content);
    }

    [Fact]
    public void 说话人不在参与者名单里就整条丢弃()
    {
        // 伪造/串味的发言（比如模型报了个不在场的人）不能进记忆——
        // 否则会产生「她记得一个当时不在场的人说过的话」这种不可能的知识。
        var writes = GroupUtteranceRules.Plan(
            new[] { "Sophia", "Abigail" },
            new[] { new GroupUtterance("Lewis", "我最近在忙镇上的事。") });

        Assert.Empty(writes);
    }

    [Fact]
    public void 空白与空发言被忽略()
    {
        var writes = GroupUtteranceRules.Plan(
            new[] { "Sophia", "Abigail" },
            new[]
            {
                new GroupUtterance("Abigail", "   "),
                new GroupUtterance("Abigail", ""),
                new GroupUtterance("", "我倒是想练练剑。"),
            });

        Assert.Empty(writes);
    }

    [Fact]
    public void 同一句重复出现只记一次()
    {
        // 一人多轮发言时同一个说话人可能反复开口，重复条目会白占 prompt 额度。
        var writes = GroupUtteranceRules.Plan(
            new[] { "Sophia", "Abigail" },
            new[]
            {
                new GroupUtterance("Abigail", "我倒是想练练剑。"),
                new GroupUtterance("Abigail", "我倒是想练练剑。"),
            });

        Assert.Single(writes, w => w.OwnerNpcId == "Sophia");
    }

    [Fact]
    public void 参与者不足两人时不产生隐性知识()
    {
        // 单人群聊不存在；没有「别的 NPC」也就没有隐性知识可言。
        Assert.Empty(GroupUtteranceRules.Plan(
            new[] { "Sophia" },
            new[] { new GroupUtterance("Abigail", "我倒是想练练剑。") }));
        Assert.Empty(GroupUtteranceRules.Plan(
            Array.Empty<string>(),
            new[] { new GroupUtterance("Abigail", "我倒是想练练剑。") }));
    }

    [Fact]
    public void 条数有上限避免长期记忆被群聊刷爆()
    {
        // 群聊攒久了，隐性知识会线性增长并挤占 prompt。
        // 每次场次写入的条数要有确定上限。
        var utterances = Enumerable
            .Range(0, 40)
            .Select(index => new GroupUtterance("Abigail", $"第 {index} 句话"))
            .ToArray();

        var writes = GroupUtteranceRules.Plan(new[] { "Sophia", "Abigail" }, utterances);

        var sophia = writes.Count(w => w.OwnerNpcId == "Sophia");
        Assert.True(sophia <= GroupUtteranceRules.MaxPerNpc, $"每人不该超过 {GroupUtteranceRules.MaxPerNpc} 条，实得 {sophia}");
    }

    [Fact]
    public void 记忆来源标为_NPC_之间而不是玩家发言()
    {
        // `Source` 决定这条记忆怎么被理解与统计。标成 PlayerChat 会让
        // 「她记得别人的话」与「她记得玩家的话」混成同一类。
        var writes = GroupUtteranceRules.Plan(
            new[] { "Sophia", "Abigail" },
            new[] { new GroupUtterance("Abigail", "我倒是想练练剑。") });

        var write = Assert.Single(writes, w => w.OwnerNpcId == "Sophia");
        Assert.Equal(MemorySource.NpcNpcEvent, write.Source);
    }

    [Fact]
    public void 知识范围标为参与者可见而不是公开()
    {
        // 群聊里说的话只在**在场的人**之间成立。标成 Public 会让 NPC
        // 在别处默认全镇都知道，标成 Private 又会让 prompt 层整条丢掉
        // （`_MEMORY_FACT_PRIVATE_SCOPES` 是直接 return ""）。
        var writes = GroupUtteranceRules.Plan(
            new[] { "Sophia", "Abigail" },
            new[] { new GroupUtterance("Abigail", "我倒是想练练剑。") });

        var write = Assert.Single(writes, w => w.OwnerNpcId == "Sophia");
        Assert.Equal(MemoryKnowledgeScope.Participants, write.KnowledgeScope);
        // KnownBy 必须含**在场所有人**（她与说话人），这正是「Participants」的含义。
        Assert.Contains("Sophia", write.KnownBy);
        Assert.Contains("Abigail", write.KnownBy);
    }
}