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

    [Fact]
    public void Group_entry_is_blocked_when_any_menu_is_open()
    {
        Assert.False(DialogueEntryRules.CanOpenGroup(
            enabled: true,
            worldReady: true,
            hasMenu: true,
            hasBridgeClient: true));
    }

    [Fact]
    public void Group_entry_does_not_require_npc_in_current_location()
    {
        Assert.True(DialogueEntryRules.CanOpenGroup(
            enabled: true,
            worldReady: true,
            hasMenu: false,
            hasBridgeClient: true));
    }
}
