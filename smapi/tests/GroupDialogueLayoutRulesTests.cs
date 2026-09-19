using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupDialogueLayoutRulesTests
{
    [Fact]
    public void Layout_rejects_non_positive_viewport()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => GroupDialogueLayoutRules.Calculate(0, 720));
    }
}
