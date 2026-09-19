using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 对话状态的两处边界：
/// 一是记忆文本截断**不能切断 UTF-16 代理对**，否则存档里会出现无效字符；
/// 二是关系阶段变化时互动进度会**新建**（计数归零）——目前 <c>EffectiveSessions</c> 只有自增、
/// JSON 属性与测试断言，没有任何生产代码读取它，所以这是语义固化：将来若拿它当解锁条件，
/// 这条测试会立刻暴露“阶段升级即清零”的行为。
/// </summary>
public sealed class ConversationStateEdgeTests
{
    [Fact]
    public void Memory_text_truncation_does_not_split_a_surrogate_pair()
    {
        // 让内容第 240 个 UTF-16 单元正好落在 emoji 的高位上：
        // 内容 = "玩家说：“"(5) + message + "”；NPC回应：“"(9) + reply + "”(1)
        // message = 'a'×234 + emoji，于是 emoji 位于整体索引 239–240，截断到 240 会切在中间。
        var message = new string('a', 234) + "\U0001F600";

        var state = ConversationStateRules.RecordConversation(
            new StoryStateEnvelope(),
            new NpcGameState { NpcId = "Sophia", Date = "春 8 日" },
            message,
            "嗯。",
            usedFallback: false);

        var content = Assert.Single(state.Memories!).Content;

        // 上限是 240，但为了不切断代理对，这里会连整个 emoji 一起丢掉、停在 239。
        Assert.Equal(239, content.Length);
        Assert.False(char.IsHighSurrogate(content[^1]), "截断不应留下孤立的高位代理");
    }

    [Fact]
    public void Memory_text_shorter_than_the_limit_is_kept_verbatim()
    {
        var state = ConversationStateRules.RecordConversation(
            new StoryStateEnvelope(),
            new NpcGameState { NpcId = "Sophia", Date = "春 8 日" },
            "在忙什么？",
            "没什么。",
            usedFallback: false);

        var content = Assert.Single(state.Memories!).Content;

        Assert.Equal("玩家说：“在忙什么？”；NPC回应：“没什么。”", content);
    }

    [Fact]
    public void Progress_is_recreated_when_the_relationship_stage_changes()
    {
        var state = new StoryStateEnvelope
        {
            InteractionProgresses = new[]
            {
                InteractionProgress.Create("Sophia", "朋友") with { EffectiveSessions = 5 },
            },
        };

        var updated = ConversationStateRules.RecordConversation(
            state,
            // 10 颗心 → 阶段变为“亲近”
            new NpcGameState { NpcId = "Sophia", Date = "春 9 日", FriendshipHearts = 10 },
            "今天还好吗？",
            "还行。",
            usedFallback: false);

        var progress = Assert.Single(updated.InteractionProgresses!);

        Assert.Equal("亲近", progress.Stage);
        // 阶段变化会新建一条：计数从 0 重新开始，这次记录后为 1（原 5 次不计入新阶段）。
        Assert.Equal(1, progress.EffectiveSessions);
    }

    [Fact]
    public void Progress_keeps_counting_when_the_stage_is_unchanged()
    {
        var state = new StoryStateEnvelope
        {
            InteractionProgresses = new[]
            {
                InteractionProgress.Create("Sophia", "朋友") with { EffectiveSessions = 5 },
            },
        };

        var updated = ConversationStateRules.RecordConversation(
            state,
            // 6 颗心 → 仍是“朋友”
            new NpcGameState { NpcId = "Sophia", Date = "春 9 日", FriendshipHearts = 6 },
            "今天还好吗？",
            "还行。",
            usedFallback: false);

        var progress = Assert.Single(updated.InteractionProgresses!);

        Assert.Equal("朋友", progress.Stage);
        Assert.Equal(6, progress.EffectiveSessions);
    }
}
