using Microsoft.Xna.Framework;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class TestNpcPlacementRulesTests
{
    [Theory]
    [InlineData(9, 7, true)]
    [InlineData(0, 0, false)]
    [InlineData(-1, 4, false)]
    [InlineData(4, -1, false)]
    public void Bed_spot_must_be_loaded_before_spawning_test_npc(
        int x,
        int y,
        bool expected)
    {
        Assert.Equal(expected, TestNpcPlacementRules.IsUsableBedSpot(new Point(x, y)));
    }

    [Fact]
    public void Test_npc_uses_a_stable_name_and_stays_inside_the_farmhouse()
    {
        var bed = new Point(9, 7);

        var spawn = TestNpcPlacementRules.GetSpawnTile(bed);

        Assert.Equal("StardewAI_NPC_Test", TestNpcPlacementRules.InternalName);
        Assert.Equal(new Point(6, 7), spawn);
    }

    [Fact]
    public void Test_npc_spawn_does_not_use_negative_map_tiles()
    {
        Assert.Equal(new Point(1, 1), TestNpcPlacementRules.GetSpawnTile(new Point(-4, -2)));
    }

    [Fact]
    public void Test_npc_spawn_converts_tile_coordinates_to_world_pixels()
    {
        var pixels = TestNpcPlacementRules.GetSpawnPixelPosition(new Point(7, 7), 64);

        Assert.Equal(new Vector2(448, 448), pixels);
    }

    [Fact]
    public void Test_npc_preserves_known_assets_without_becoming_non_interactive()
    {
        var appearance = TestNpcPlacementRules.GetAppearancePolicy();

        Assert.Equal("Characters\\Wizard", appearance.SpriteAssetName);
        Assert.Equal("Portraits/Wizard", appearance.PortraitAssetName);
        Assert.True(appearance.PreserveInjectedSprite);
        Assert.True(appearance.PreserveInjectedPortrait);
        Assert.False(appearance.UseSimpleNonVillagerNpc);
    }

    [Fact]
    public void Runtime_test_npc_is_replaced_after_load_and_excluded_from_save_data()
    {
        var lifecycle = TestNpcPlacementRules.GetLifecyclePolicy();

        Assert.True(lifecycle.ReplaceExistingNpcOnLoad);
        Assert.True(lifecycle.RemoveBeforeSave);
        Assert.True(lifecycle.RecreateAfterSave);
        Assert.True(lifecycle.ResetRepeatTargetBeforeSave);
    }

    [Theory]
    [InlineData("StardewAI_NPC_Test", true)]
    [InlineData("Rasmodia", false)]
    [InlineData("", false)]
    public void Only_the_runtime_test_npc_can_bypass_a_friendship_record_for_dialogue(
        string npcId,
        bool expected)
    {
        Assert.Equal(
            expected,
            TestNpcPlacementRules.IsDialogueTargetWithoutFriendshipRecord(npcId));
    }
}
