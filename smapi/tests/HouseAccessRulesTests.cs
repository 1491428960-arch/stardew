using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class HouseAccessRulesTests
{
    [Fact]
    public void Known_residential_door_can_open_when_feature_is_enabled()
    {
        var decision = HouseAccessRules.Evaluate(
            DoorAccessContext.Residential(
                "SophiaHouse",
                "Sophia"),
            HouseAccessOptions.EnabledForSinglePlayer());

        Assert.True(decision.AllowPhysicalEntry);
        Assert.True(decision.AllowNpcChat);
        Assert.False(decision.PreserveVanillaDoor);
    }

    [Fact]
    public void Mixed_residential_service_door_can_open_when_explicitly_allowed()
    {
        var decision = HouseAccessRules.Evaluate(
            DoorAccessContext.MixedResidentialService(
                "ScienceHouse",
                "Robin",
                "Carpenter"),
            HouseAccessOptions.EnabledForSinglePlayer(allowMixedBuildings: true));

        Assert.True(decision.AllowPhysicalEntry);
        Assert.True(decision.AllowNpcChat);
        Assert.Equal(HouseAccessReason.MixedBuildingAllowed, decision.Reason);
    }

    [Fact]
    public void Unknown_custom_service_action_stays_vanilla_when_mixed_is_disabled()
    {
        var decision = HouseAccessRules.Evaluate(
            new DoorAccessContext
            {
                TargetLocationName = "CustomHome",
                ResidentNpcIds = new[] { "Aurora" },
                IsKnownResidence = true,
                HasUnknownServiceInteraction = true,
            },
            HouseAccessOptions.EnabledForSinglePlayer(allowMixedBuildings: false));

        Assert.False(decision.AllowPhysicalEntry);
        Assert.True(decision.PreserveVanillaDoor);
        Assert.Equal(HouseAccessReason.UnknownServiceProtection, decision.Reason);
    }

    [Fact]
    public void Known_residence_with_unknown_service_action_can_open_when_mixed_is_enabled()
    {
        var decision = HouseAccessRules.Evaluate(
            new DoorAccessContext
            {
                TargetLocationName = "CustomClinic",
                ResidentNpcIds = new[] { "Harvey" },
                IsKnownResidence = true,
                HasUnknownServiceInteraction = true,
            },
            HouseAccessOptions.EnabledForSinglePlayer(allowMixedBuildings: true));

        Assert.True(decision.AllowPhysicalEntry);
        Assert.True(decision.AllowNpcChat);
        Assert.Equal(HouseAccessReason.MixedBuildingAllowed, decision.Reason);
    }

    [Fact]
    public void Unknown_location_preserves_vanilla_door_and_still_exposes_no_access()
    {
        var decision = HouseAccessRules.Evaluate(
            DoorAccessContext.Unknown("CustomRoom"),
            HouseAccessOptions.EnabledForSinglePlayer());

        Assert.False(decision.AllowPhysicalEntry);
        Assert.False(decision.AllowNpcChat);
        Assert.True(decision.PreserveVanillaDoor);
        Assert.Equal(HouseAccessReason.UnknownResidence, decision.Reason);
    }

    [Fact]
    public void Festival_door_preserves_vanilla_by_default()
    {
        var decision = HouseAccessRules.Evaluate(
            DoorAccessContext.Residential("HaleyHouse", "Haley") with { IsFestival = true },
            HouseAccessOptions.EnabledForSinglePlayer());

        Assert.False(decision.AllowPhysicalEntry);
        Assert.True(decision.PreserveVanillaDoor);
        Assert.Equal(HouseAccessReason.FestivalProtection, decision.Reason);
    }

    [Fact]
    public void Active_event_does_not_get_interrupted_by_house_access()
    {
        var decision = HouseAccessRules.Evaluate(
            DoorAccessContext.Residential("SamHouse", "Sam") with { IsEventActive = true },
            HouseAccessOptions.EnabledForSinglePlayer());

        Assert.False(decision.AllowPhysicalEntry);
        Assert.True(decision.PreserveVanillaDoor);
        Assert.Equal(HouseAccessReason.EventProtection, decision.Reason);
    }
}
