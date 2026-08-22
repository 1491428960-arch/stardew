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
}
