using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ShareFriendshipLedgerTests
{
    [Fact]
    public void Awards_at_most_once_per_npc_per_game_day()
    {
        var ledger = new ShareFriendshipLedger();

        Assert.True(ledger.TryClaim("Abigail", gameDay: 42));
        Assert.False(ledger.TryClaim("abigail", gameDay: 42));
        Assert.True(ledger.TryClaim("Abigail", gameDay: 43));
        Assert.True(ledger.TryClaim("Dwarf", gameDay: 42));
    }

    [Fact]
    public void Rejects_empty_npc_ids_without_poisoning_the_day()
    {
        var ledger = new ShareFriendshipLedger();

        Assert.False(ledger.TryClaim("", gameDay: 42));
        Assert.True(ledger.TryClaim("Leah", gameDay: 42));
    }

    [Fact]
    public void Can_be_reset_when_the_loaded_save_changes()
    {
        var ledger = new ShareFriendshipLedger();
        Assert.True(ledger.TryClaim("Leah", gameDay: 42));

        ledger.Reset();

        Assert.True(ledger.TryClaim("Leah", gameDay: 42));
    }
}
