using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 隐性知识的**生产接线**（2026-10-04）。
///
/// 前两个文件已经证明规则层（<see cref="GroupUtteranceRules"/>）与存储层
/// （<c>StoryStateStore.LatentKnowledge</c>）各自成立。本文件钉的是**接线**：
/// 群聊结束 → 写进长期记忆 → 下次请求真的带出去。
///
/// 项目教训（STATE.md §三/§四 反复出现的一类）：一个功能「实现完备、测试全绿、
/// 生产零调用点」是真实发生过的失效形态。规则层与存储层全绿**不能**推出
/// 「游戏里真的生效」——所以这里必须测真实调用链，而不是再测一遍纯函数。
/// </summary>
public sealed class LatentKnowledgeWiringTests
{
    private static StoryStateStore CreateStore()
    {
        return new StoryStateStore();
    }

    [Fact]
    public void 群聊发言会写进长期记忆()
    {
        var store = CreateStore();

        var written = LatentKnowledgeWriter.Record(
            store,
            new[] { "Sophia", "Abigail" },
            new[]
            {
                new GroupUtterance("Abigail", "我倒是想练练剑。"),
            },
            "春 28");

        Assert.Equal(1, written);
        Assert.Contains(
            store.LatentKnowledge("Sophia"),
            item => item.Contains("练练剑"));
        // Abigail 是说话人，**不该**把这句话记成「听说的」——她自己的发言
        // 走发送窗口（第一人称），在这里再记一份会变成「听说我自己说过」。
        Assert.DoesNotContain(
            store.LatentKnowledge("Abigail"),
            item => item.Contains("练练剑"));
    }

    [Fact]
    public void 沉默的在场者也记住()
    {
        // Emily 一句没说，但她在场听见了。这正是「隐性知识」与
        // 「发言窗口」的分界：她不能在私聊里说「我说过」，但可以知道。
        var store = CreateStore();

        LatentKnowledgeWriter.Record(
            store,
            new[] { "Sophia", "Abigail", "Emily" },
            new[] { new GroupUtterance("Abigail", "我倒是想练练剑。") },
            "春 28");

        Assert.Contains(
            store.LatentKnowledge("Emily"),
            item => item.Contains("练练剑"));
    }

    [Fact]
    public void 拿不到日期时不写入()
    {
        // `MemoryRecord.GameDate` 要求非空，写入空日期会让 Serialize 抛异常。
        // 既有 `RecordMemoryHighlight` 用同样的守则。
        var store = CreateStore();

        var written = LatentKnowledgeWriter.Record(
            store,
            new[] { "Sophia", "Abigail" },
            new[] { new GroupUtterance("Abigail", "我倒是想练练剑。") },
            "");

        Assert.Equal(0, written);
        Assert.Empty(store.LatentKnowledge("Sophia"));
    }

    [Fact]
    public void 同一场次重复调用不产生重复条目()
    {
        // 群聊菜单可能在重试/回顾时再次走到写入口，幂等性是必须的。
        var store = CreateStore();
        var utterances = new[] { new GroupUtterance("Abigail", "我倒是想练练剑。") };
        var participants = new[] { "Sophia", "Abigail" };

        LatentKnowledgeWriter.Record(store, participants, utterances, "春 28");
        LatentKnowledgeWriter.Record(store, participants, utterances, "春 28");

        Assert.Single(store.LatentKnowledge("Sophia"));
    }

    [Fact]
    public void 单人群聊不产生隐性知识()
    {
        var store = CreateStore();

        var written = LatentKnowledgeWriter.Record(
            store,
            new[] { "Sophia" },
            new[] { new GroupUtterance("Sophia", "我倒是想练练剑。") },
            "春 28");

        Assert.Equal(0, written);
    }

    [Fact]
    public void 写入的来源与范围与需求一致()
    {
        var store = CreateStore();

        LatentKnowledgeWriter.Record(
            store,
            new[] { "Sophia", "Abigail" },
            new[] { new GroupUtterance("Abigail", "我倒是想练练剑。") },
            "春 28");

        var memory = Assert.Single(store.State.Memories);
        Assert.Equal(MemorySource.NpcNpcEvent, memory.Source);
        Assert.Equal(MemoryKnowledgeScope.Participants, memory.KnowledgeScope);
        Assert.Equal(MemoryStatus.Active, memory.Status);
        Assert.Equal("Sophia", memory.OwnerNpcId);
        Assert.Equal("春 28", memory.GameDate);
    }

    [Fact]
    public void 写入后不进_recent_memory()
    {
        // 分流是需求「不主动提」的机制保证，接线之后同样要成立。
        var store = CreateStore();

        LatentKnowledgeWriter.Record(
            store,
            new[] { "Sophia", "Abigail" },
            new[] { new GroupUtterance("Abigail", "我倒是想练练剑。") },
            "春 28");

        Assert.DoesNotContain(
            store.RecentMemoryFacts("Sophia"),
            fact => fact.Contains("练练剑"));
    }
}