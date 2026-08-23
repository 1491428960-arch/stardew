using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class DialogueEntryRulesTests
{
    [Theory]
    [InlineData(false, false, false, false)]
    [InlineData(true, false, false, false)]
    [InlineData(true, true, true, false)]
    [InlineData(true, true, false, false)]
    public void HotkeyGuardRejectsUnsafeEntry(
        bool enabled,
        bool worldReady,
        bool hasMenu,
        bool hasConversationService)
    {
        Assert.False(DialogueEntryRules.CanOpen(
            enabled,
            worldReady,
            hasMenu,
            hasConversationService));
    }

    [Fact]
    public void HotkeyGuardAllowsOnlyReadyWorldWithoutExistingMenu()
    {
        Assert.True(DialogueEntryRules.CanOpen(
            enabled: true,
            worldReady: true,
            hasMenu: false,
            hasConversationService: true));
    }
}
