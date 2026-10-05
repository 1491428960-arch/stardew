using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 隐性知识在**存储与分流**层的两条路（2026-10-04）。
///
/// 需求原话：「群聊记忆中别的 npc 说了什么能不能作为一个隐性的知识库这样的形式，
/// **我不主动提到就不唤醒**」。
///
/// 「不主动提」要成立，光有一张卡片是不够的 —— 隐性知识**不能同时出现在
/// `recent_memory` 那张泛记忆卡里**。后者带的是「把记忆自然用起来」的指令，
/// 两个通道都送，模型看到的就是互相打架的两套约束，而项目实测过
/// **「取最宽」**：同类约束有多个实例时跟最松的那个。
///
/// 所以本文件钉住的是**分流**：同一条记忆，要么走 `recent_memory`（会主动提），
/// 要么走隐性知识（不主动提），不能两边都送。
/// </summary>
public sealed class LatentKnowledgeStoreTests
{
    private static StoryStateStore CreateStore()
    {
        return new StoryStateStore();
    }

    private static void Seed(
        StoryStateStore store,
        string owner,
        string content,
        string date = "春 28",
        MemorySource source = MemorySource.PlayerChat,
        MemoryKnowledgeScope scope = MemoryKnowledgeScope.Participants,
        IReadOnlyList<string>? knownBy = null)
    {
        var memories = store.State.Memories.ToList();
        memories.Add(new MemoryRecord
        {
            MemoryId = $"test-{owner}-{content.GetHashCode()}",
            OwnerNpcId = owner,
            Kind = "fact",
            Content = content,
            Source = source,
            Confidence = 0.75,
            GameDate = date,
            Participants = knownBy ?? new[] { owner, "player" },
            KnowledgeScope = scope,
            KnownBy = knownBy ?? new[] { owner, "player" },
            Importance = 1,
            Canonical = false,
            Status = MemoryStatus.Active,
            Evidence = "test",
        });
        store.Replace(store.State with { Memories = memories });
    }

    [Fact]
    public void 隐性知识不进_recent_memory()
    {
        var store = CreateStore();
        Seed(store, "Sophia", "玩家送过我一条项链。");
        Seed(
            store,
            "Sophia",
            "听说 Abigail 说：我倒是想练练剑。",
            source: MemorySource.NpcNpcEvent);

        var facts = store.RecentMemoryFacts("Sophia");

        Assert.Contains(facts, fact => fact.Contains("项链"));
        // 隐性知识若同时进这里，就等于「会主动提」，与需求相反。
        Assert.DoesNotContain(facts, fact => fact.Contains("练练剑"));
    }

    [Fact]
    public void 隐性知识单独取得()
    {
        var store = CreateStore();
        Seed(store, "Sophia", "玩家送过我一条项链。");
        Seed(
            store,
            "Sophia",
            "听说 Abigail 说：我倒是想练练剑。",
            source: MemorySource.NpcNpcEvent);

        var latent = store.LatentKnowledge("Sophia");

        Assert.Contains(latent, item => item.Contains("练练剑"));
        // 普通记忆不该走隐性知识这条路——否则它会绕过「不主动提」，
        // 而且隐性知识卡的指令（转述/第三人称）套在玩家说的话上是错的。
        Assert.DoesNotContain(latent, item => item.Contains("项链"));
    }

    [Fact]
    public void 隐性知识不带记忆前缀因为那是普通记忆的口径()
    {
        // `recent_memory` 用「记忆（春 28）：…」的抬头。隐性知识卡有自己的
        // 结构与指令，再套一层「记忆」抬头会让模型把两者当成同一类东西。
        var store = CreateStore();
        Seed(
            store,
            "Sophia",
            "听说 Abigail 说：我倒是想练练剑。",
            source: MemorySource.NpcNpcEvent);

        var latent = Assert.Single(store.LatentKnowledge("Sophia"));

        Assert.DoesNotContain("记忆（", latent);
    }

    [Fact]
    public void 只取属于该_npc_的隐性知识()
    {
        var store = CreateStore();
        Seed(
            store,
            "Sophia",
            "听说 Abigail 说：我倒是想练练剑。",
            source: MemorySource.NpcNpcEvent);
        Seed(
            store,
            "Emily",
            "听说 Abigail 说：我倒是想练练剑。",
            source: MemorySource.NpcNpcEvent);

        var latent = store.LatentKnowledge("Sophia");

        Assert.Single(latent);
    }

    [Fact]
    public void 遗忘与更正的隐性知识不再出现()
    {
        // 记忆有生命周期。已 Forget / Superseded 的条目不该继续作为「她知道的事」。
        var store = CreateStore();
        Seed(
            store,
            "Sophia",
            "听说 Abigail 说：我倒是想练练剑。",
            source: MemorySource.NpcNpcEvent);
        store.Replace(store.State with
        {
            Memories = store.State.Memories
                .Select(memory => memory with { Status = MemoryStatus.Forgotten })
                .ToArray(),
        });

        Assert.Empty(store.LatentKnowledge("Sophia"));
    }

    [Fact]
    public void 隐性知识条数封顶()
    {
        var store = CreateStore();
        for (var index = 0; index < 40; index++)
        {
            Seed(
                store,
                "Sophia",
                $"听说 Abigail 说：第 {index} 句话。",
                source: MemorySource.NpcNpcEvent);
        }

        Assert.True(store.LatentKnowledge("Sophia").Count <= 12);
    }

    [Fact]
    public void 空_npcId_返回空而不是抛异常()
    {
        var store = CreateStore();

        Assert.Empty(store.LatentKnowledge(""));
        Assert.Empty(store.LatentKnowledge("   "));
    }
}