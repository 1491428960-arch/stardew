using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class HouseDoorTargetRulesTests
{
    [Fact]
    public void Known_service_building_without_npc_gate_is_a_known_test_target()
    {
        var context = HouseDoorTargetRules.CreateContext(
            targetLocationName: "Hospital",
            requiredNpcId: null,
            npcHomeMatchesTarget: false,
            targetIsShopLocation: true);

        Assert.True(context.IsKnownResidence);
        Assert.Contains("Hospital", context.ResidentNpcIds);
        Assert.True(context.HasServiceInteraction);
    }

    [Fact]
    public void Matches_npc_home_as_known_pure_residence()
    {
        var context = HouseDoorTargetRules.CreateContext(
            targetLocationName: "HaleyHouse",
            requiredNpcId: "Haley",
            npcHomeMatchesTarget: true,
            targetIsShopLocation: false);

        Assert.True(context.IsKnownResidence);
        Assert.False(context.HasServiceInteraction);
        Assert.Equal("Haley", Assert.Single(context.ResidentNpcIds));
    }

    [Fact]
    public void Treats_known_shop_location_as_mixed_building()
    {
        var context = HouseDoorTargetRules.CreateContext(
            targetLocationName: "SeedShop",
            requiredNpcId: "Pierre",
            npcHomeMatchesTarget: true,
            targetIsShopLocation: true);

        Assert.True(context.IsKnownResidence);
        Assert.True(context.HasServiceInteraction);
    }

    [Fact]
    public void Treats_unmatched_npc_home_as_unknown_residence()
    {
        var context = HouseDoorTargetRules.CreateContext(
            targetLocationName: "CustomRoom",
            requiredNpcId: "UnknownNpc",
            npcHomeMatchesTarget: false,
            targetIsShopLocation: false);

        Assert.False(context.IsKnownResidence);
        Assert.Empty(context.ResidentNpcIds);
    }

    [Theory]
    [InlineData("Shop shop")]
    [InlineData("OpenShopMenu")]
    [InlineData("CustomShop AuroraLedger")]
    [InlineData("MermaidStore")]
    [InlineData("IceCreamStand")]
    [InlineData("Theater_BoxOffice")]
    [InlineData("Bookseller")]
    [InlineData("Boat")]
    [InlineData("Trade AuroraLedger")]
    public void Detects_custom_service_actions_in_map_tiles(string action)
    {
        Assert.True(HouseDoorTargetRules.HasServiceAction(new[] { action }));
        Assert.Equal(
            ServiceActionClassification.KnownService,
            HouseDoorTargetRules.ClassifyServiceActions(new[] { action }));
    }

    [Theory]
    [InlineData("LockedDoorWarp 5 9 CustomRoom 600 2600")]
    [InlineData("Warp 5 9 Town")]
    [InlineData("Message hello")]
    public void Ignores_non_service_map_actions(string action)
    {
        Assert.False(HouseDoorTargetRules.HasServiceAction(new[] { action }));
        Assert.NotEqual(
            ServiceActionClassification.KnownService,
            HouseDoorTargetRules.ClassifyServiceActions(new[] { action }));
    }

    [Fact]
    public void Marks_unknown_custom_action_as_conservative_unknown()
    {
        Assert.Equal(
            ServiceActionClassification.Unknown,
            HouseDoorTargetRules.ClassifyServiceActions(new[] { "MysteryAction Foo" }));
    }

    [Fact]
    public void Unknown_service_action_is_carried_into_access_context()
    {
        var context = HouseDoorTargetRules.CreateContext(
            targetLocationName: "CustomHome",
            requiredNpcId: "Aurora",
            npcHomeMatchesTarget: true,
            targetIsShopLocation: false,
            unknownServiceAction: true);

        Assert.True(context.HasUnknownServiceInteraction);
    }
}
