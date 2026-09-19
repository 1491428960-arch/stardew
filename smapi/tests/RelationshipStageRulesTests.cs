using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class RelationshipStageRulesTests
{
    [Theory]
    // 婚配状态优先：有孩子时进“育儿”，否则“婚后”
    [InlineData("married", 2, null, 0, "育儿", "parent")]
    [InlineData("roommate", 1, null, 0, "育儿", "parent")]
    [InlineData("married", 0, null, 8, "婚后", "married")]
    // 恋爱可由 marriageStatus 或 relationship 任一表达
    [InlineData("dating", 0, null, 8, "恋爱", "dating")]
    [InlineData(null, 0, "Dating", 8, "恋爱", "dating")]
    // 都没有时按好感心数分档
    [InlineData(null, 0, null, 10, "亲近", "close")]
    [InlineData(null, 0, null, 8, "亲近", "close")]
    [InlineData(null, 0, null, 7, "朋友", "friend")]
    [InlineData(null, 0, null, 6, "朋友", "friend")]
    [InlineData(null, 0, null, 5, "熟悉", "acquaintance")]
    [InlineData(null, 0, null, 3, "熟悉", "acquaintance")]
    [InlineData(null, 0, null, 2, "初识", "stranger")]
    [InlineData(null, 0, null, 0, "初识", "stranger")]
    public void Resolve_and_ResolveKey_map_state_to_stage(
        string? marriageStatus,
        int childrenCount,
        string? relationship,
        int friendshipHearts,
        string expectedStage,
        string expectedKey)
    {
        var state = new NpcGameState
        {
            NpcId = "Shane",
            MarriageStatus = marriageStatus,
            ChildrenCount = childrenCount == 0 ? null : childrenCount,
            Relationship = relationship,
            FriendshipHearts = friendshipHearts,
        };

        Assert.Equal(expectedStage, RelationshipStageRules.Resolve(state));
        Assert.Equal(expectedKey, RelationshipStageRules.ResolveKey(state));
    }

    [Fact]
    public void Children_without_marriage_do_not_reach_the_parent_stage()
    {
        // “育儿”要求有孩子**且**处于婚配状态；只是有孩子仍按心数分档。
        var state = new NpcGameState
        {
            NpcId = "Shane",
            ChildrenCount = 2,
            FriendshipHearts = 8,
        };

        Assert.Equal("亲近", RelationshipStageRules.Resolve(state));
        Assert.Equal("close", RelationshipStageRules.ResolveKey(state));
    }

    [Fact]
    public void Marriage_status_is_trimmed_and_case_insensitive()
    {
        var state = new NpcGameState
        {
            NpcId = "Shane",
            MarriageStatus = "  MARRIED  ",
        };

        Assert.Equal("婚后", RelationshipStageRules.Resolve(state));
    }

    [Fact]
    public void Null_state_is_rejected()
    {
        Assert.Throws<ArgumentNullException>(() => RelationshipStageRules.Resolve(null!));
    }
}
