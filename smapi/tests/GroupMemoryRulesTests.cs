using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupMemoryRulesTests
{
    [Fact]
    public void PlanWritesEveryHighlightForEveryPresentParticipant()
    {
        var writes = GroupMemoryRules.Plan(
            new[] { "Abigail", "Emily" },
            new[] { "玩家下周要交一份报告。" });

        Assert.Equal(2, writes.Count);
        Assert.Equal(
            new[] { "Abigail", "Emily" },
            writes.Select(write => write.NpcId).ToArray());
        Assert.All(
            writes,
            write => Assert.Equal("玩家下周要交一份报告。", write.Content));
    }

    [Fact]
    public void PlanDropsBlankAndRepeatedInputs()
    {
        var writes = GroupMemoryRules.Plan(
            new[] { "Abigail", " abigail ", "  ", "Emily", null! },
            new[] { " 玩家下周要交一份报告。 ", "玩家下周要交一份报告。", "   ", null! });

        Assert.Equal(2, writes.Count);
        Assert.Equal(
            new[] { "Abigail", "Emily" },
            writes.Select(write => write.NpcId).ToArray());
        Assert.All(
            writes,
            write => Assert.Equal("玩家下周要交一份报告。", write.Content));
    }

    [Fact]
    public void PlanWithoutBothSidesWritesNothing()
    {
        Assert.Empty(GroupMemoryRules.Plan(null, new[] { "玩家下周要交一份报告。" }));
        Assert.Empty(GroupMemoryRules.Plan(new[] { "Abigail" }, null));
        Assert.Empty(GroupMemoryRules.Plan(Array.Empty<string>(), new[] { "玩家下周要交一份报告。" }));
        Assert.Empty(GroupMemoryRules.Plan(new[] { "Abigail" }, Array.Empty<string>()));
    }

    [Fact]
    public void PlanKeepsMultipleHighlightsInOrder()
    {
        var writes = GroupMemoryRules.Plan(
            new[] { "Abigail" },
            new[] { "玩家下周要交一份报告。", "玩家答应周末去葡萄园。" });

        Assert.Equal(2, writes.Count);
        Assert.Equal("玩家下周要交一份报告。", writes[0].Content);
        Assert.Equal("玩家答应周末去葡萄园。", writes[1].Content);
    }
}
