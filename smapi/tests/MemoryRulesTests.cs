using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 审计 #44：单聊与群聊的记忆写入规则（上限、截断、稳定 ID）收敛到
/// <see cref="MemoryRules"/>。这里钉住常量值、截断语义与 ID 形状。
/// </summary>
public sealed class MemoryRulesTests
{
    [Fact]
    public void Limits_match_the_values_both_writers_used_before()
    {
        Assert.Equal(200, MemoryRules.MaxCount);
        Assert.Equal(240, MemoryRules.MaxTextLength);
    }

    [Fact]
    public void Truncate_keeps_short_text_unchanged()
    {
        Assert.Equal("玩家下周要交报告。", MemoryRules.Truncate("玩家下周要交报告。", 240));
        Assert.Equal("abc", MemoryRules.Truncate("abc", 3));
    }

    [Fact]
    public void Truncate_cuts_to_the_limit()
    {
        var text = new string('长', 300);

        var truncated = MemoryRules.Truncate(text, 240);

        Assert.Equal(240, truncated.Length);
        Assert.Equal(text[..240], truncated);
    }

    [Fact]
    public void Truncate_never_splits_a_surrogate_pair()
    {
        // 让第 240 个 UTF-16 单元正好是某个 emoji 的高位代理。
        var text = new string('长', 239) + "😀" + new string('长', 10);

        var truncated = MemoryRules.Truncate(text, 240);

        Assert.Equal(239, truncated.Length);
        Assert.DoesNotContain(truncated, char.IsHighSurrogate);
        Assert.DoesNotContain(truncated, char.IsLowSurrogate);
    }

    [Fact]
    public void Build_id_shape_and_stability()
    {
        var first = MemoryRules.BuildId("chat", "Abigail", "payload");
        var second = MemoryRules.BuildId("chat", "Abigail", "payload");

        Assert.Equal(first, second);
        Assert.StartsWith("chat:Abigail:", first);
        Assert.Equal("chat:Abigail:".Length + 24, first.Length);
    }

    [Fact]
    public void Build_id_is_process_stable_and_payload_sensitive()
    {
        // 用 SHA256 而不是 string.GetHashCode()：同输入必得同 ID（跨进程也一样），
        // 不同输入必得不同 ID。这里钉住已知向量（SHA256("") 的前 24 个十六进制位），
        // 防止有人换回随机化哈希。
        Assert.Equal(
            "chat:Abigail:E3B0C44298FC1C149AFBF4C8",
            MemoryRules.BuildId("chat", "Abigail", string.Empty));

        Assert.NotEqual(
            MemoryRules.BuildId("chat", "Abigail", "a"),
            MemoryRules.BuildId("chat", "Abigail", "b"));
        Assert.NotEqual(
            MemoryRules.BuildId("chat", "Abigail", "a"),
            MemoryRules.BuildId("group", "Abigail", "a"));
    }

    [Fact]
    public void Group_and_chat_ids_keep_their_distinct_prefixes()
    {
        var store = new StoryStateStore();
        store.RecordMemoryHighlight("Abigail", "玩家答应周末去葡萄园。", "Spring 14");
        store.RecordConversation(
            new NpcGameState
            {
                NpcId = "Abigail",
                Date = "Spring 14",
                FriendshipHearts = 8,
            },
            "葡萄园最近怎么样？",
            "最近的葡萄长得不错。",
            usedFallback: false);

        var ids = store.State.Memories.Select(memory => memory.MemoryId).ToArray();

        Assert.Contains(ids, id => id.StartsWith("group:abigail:", StringComparison.Ordinal));
        Assert.Contains(ids, id => id.StartsWith("chat:Abigail:", StringComparison.Ordinal));
    }

    [Fact]
    public void Group_memory_content_is_truncated_by_the_shared_rule()
    {
        var store = new StoryStateStore();
        var text = new string('长', 239) + "😀" + new string('长', 10);

        store.RecordMemoryHighlight("Abigail", text, "Spring 14");

        var content = Assert.Single(store.State.Memories).Content;
        Assert.Equal(239, content.Length);
        Assert.DoesNotContain(content, char.IsHighSurrogate);
    }
}
