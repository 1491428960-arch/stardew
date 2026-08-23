using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ConversationStateRulesTests
{
    [Fact]
    public void Successful_conversation_persists_scoped_memory_and_progress()
    {
        var state = ConversationStateRules.RecordConversation(
            StoryStateEnvelope.Empty,
            GameState(friendshipHearts: 6, relationship: "friend"),
            "葡萄园最近怎么样？",
            "最近的葡萄长得不错。\n谢谢你的关心。",
            usedFallback: false);

        var memory = Assert.Single(state.Memories);
        Assert.Equal("Sophia", memory.OwnerNpcId);
        Assert.Equal(MemorySource.PlayerChat, memory.Source);
        Assert.Equal(MemoryKnowledgeScope.Participants, memory.KnowledgeScope);
        Assert.Equal(new[] { "Sophia", "player" }, memory.Participants);
        Assert.False(memory.Canonical);
        Assert.Contains("葡萄园最近怎么样？", memory.Content);

        var progress = Assert.Single(state.InteractionProgresses);
        Assert.Equal("朋友", progress.Stage);
        Assert.Equal(1, progress.EffectiveSessions);
        Assert.Equal(4, progress.RequiredSessions);
    }

    [Fact]
    public void Fallback_or_missing_date_does_not_persist_memory_or_progress()
    {
        var initial = new StoryStateEnvelope
        {
            InteractionProgresses = new[] { InteractionProgress.Create("Sophia", "朋友") },
        };

        var fallback = ConversationStateRules.RecordConversation(
            initial,
            GameState(),
            "你好",
            "备用回复",
            usedFallback: true);
        var missingDate = ConversationStateRules.RecordConversation(
            initial,
            GameState(date: null),
            "你好",
            "正式回复",
            usedFallback: false);

        Assert.Empty(fallback.Memories);
        Assert.Equal(0, fallback.InteractionProgresses[0].EffectiveSessions);
        Assert.Empty(missingDate.Memories);
        Assert.Equal(0, missingDate.InteractionProgresses[0].EffectiveSessions);
    }

    [Fact]
    public void Repeating_the_same_successful_conversation_does_not_duplicate_memory()
    {
        var first = ConversationStateRules.RecordConversation(
            StoryStateEnvelope.Empty,
            GameState(),
            "你好",
            "你好，今天也很平静。",
            usedFallback: false);
        var second = ConversationStateRules.RecordConversation(
            first,
            GameState(),
            "你好",
            "你好，今天也很平静。",
            usedFallback: false);

        Assert.Single(second.Memories);
        Assert.Equal(1, second.InteractionProgresses[0].EffectiveSessions);
    }

    [Theory]
    [InlineData("dating", 0, 8, "恋爱")]
    [InlineData("married", 0, 8, "婚后")]
    [InlineData("married", 1, 8, "育儿")]
    [InlineData("friend", 8, 8, "亲近")]
    [InlineData("friend", 0, 3, "熟悉")]
    public void Relationship_stage_follows_vanilla_state(
        string relationship,
        int childrenCount,
        int friendshipHearts,
        string expectedStage)
    {
        var state = ConversationStateRules.RecordConversation(
            StoryStateEnvelope.Empty,
            GameState(
                friendshipHearts: friendshipHearts,
                relationship: relationship,
                marriageStatus: relationship,
                childrenCount: childrenCount),
            "你好",
            "你好。",
            usedFallback: false);

        Assert.Equal(expectedStage, Assert.Single(state.InteractionProgresses).Stage);
    }

    private static NpcGameState GameState(
        int friendshipHearts = 2,
        string relationship = "friend",
        string? marriageStatus = null,
        int childrenCount = 0,
        string? date = "Spring 14") =>
        new()
        {
            NpcId = "Sophia",
            DisplayName = "Sophia",
            Friendship = friendshipHearts * 250,
            FriendshipHearts = friendshipHearts,
            Relationship = relationship,
            MarriageStatus = marriageStatus,
            ChildrenCount = childrenCount,
            Date = date,
        };
}
