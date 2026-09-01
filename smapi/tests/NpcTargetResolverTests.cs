using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class NpcTargetResolverTests
{
    [Fact]
    public void Resolves_the_internal_wizard_name_when_Rasmodia_display_name_is_not_an_internal_id()
    {
        var resolved = NpcTargetResolver.ResolveTargetName(
            candidate => candidate == "Wizard");

        Assert.Equal("Wizard", resolved);
    }

    [Fact]
    public void Prefers_Rasmodia_if_a_mod_adds_that_as_a_real_internal_name()
    {
        var resolved = NpcTargetResolver.ResolveTargetName(
            candidate => candidate is "Rasmodia" or "Wizard");

        Assert.Equal("Rasmodia", resolved);
    }

    [Fact]
    public void Selects_a_nearby_friendship_npc_when_no_legacy_template_is_present()
    {
        var resolved = NpcTargetResolver.SelectFriendshipTarget(new[]
        {
            new NpcTargetCandidate("Caroline", true, false, 9f, false),
            new NpcTargetCandidate("Marnie", true, true, 25f, false),
        });

        Assert.Equal("Marnie", resolved?.NpcId);
    }

    [Fact]
    public void Interaction_target_beats_a_closer_friendship_npc()
    {
        var resolved = NpcTargetResolver.SelectFriendshipTarget(new[]
        {
            new NpcTargetCandidate("Caroline", true, true, 4f, false),
            new NpcTargetCandidate("Marnie", true, true, 25f, true),
        });

        Assert.Equal("Marnie", resolved?.NpcId);
    }

    [Fact]
    public void Ignores_npcs_without_friendship_records_and_empty_candidates()
    {
        var resolved = NpcTargetResolver.SelectFriendshipTarget(new[]
        {
            new NpcTargetCandidate("", true, true, 1f, true),
            new NpcTargetCandidate("Pierre", false, true, 1f, true),
        });

        Assert.Null(resolved);
    }
}
