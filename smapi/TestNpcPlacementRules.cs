using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

public sealed record TestNpcAppearancePolicy(
    string SpriteAssetName,
    string PortraitAssetName,
    bool PreserveInjectedSprite,
    bool PreserveInjectedPortrait,
    bool UseSimpleNonVillagerNpc);

public sealed record TestNpcLifecyclePolicy(
    bool ReplaceExistingNpcOnLoad,
    bool RemoveBeforeSave,
    bool RecreateAfterSave,
    bool ResetRepeatTargetBeforeSave);

/// <summary>
/// Keeps the temporary test NPC placement deterministic and close to the
/// player's bed without changing the farmhouse map.
/// </summary>
public static class TestNpcPlacementRules
{
    public const string InternalName = "StardewAI_NPC_Test";

    public static bool IsDialogueTargetWithoutFriendshipRecord(string? npcId)
    {
        return string.Equals(npcId, InternalName, StringComparison.Ordinal);
    }

    public static bool IsUsableBedSpot(Point playerBedSpot)
    {
        // FarmHouse.GetPlayerBedSpot returns (0, 0) while some custom maps
        // are still being populated during SaveLoaded. Do not spawn there;
        // wait for the subsequent FarmHouse warp instead.
        return playerBedSpot.X > 0 && playerBedSpot.Y > 0;
    }

    public static Point GetSpawnTile(Point playerBedSpot)
    {
        return new(
            Math.Max(1, playerBedSpot.X - 3),
            Math.Max(1, playerBedSpot.Y));
    }

    public static Vector2 GetSpawnPixelPosition(Point spawnTile, int tileSize)
    {
        if (tileSize <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(tileSize));
        }

        return new Vector2(
            spawnTile.X * tileSize,
            spawnTile.Y * tileSize);
    }

    public static TestNpcAppearancePolicy GetAppearancePolicy()
    {
        return new TestNpcAppearancePolicy(
            SpriteAssetName: "Characters\\Wizard",
            PortraitAssetName: "Portraits/Wizard",
            PreserveInjectedSprite: true,
            PreserveInjectedPortrait: true,
            UseSimpleNonVillagerNpc: false);
    }

    public static TestNpcLifecyclePolicy GetLifecyclePolicy()
    {
        return new TestNpcLifecyclePolicy(
            ReplaceExistingNpcOnLoad: true,
            RemoveBeforeSave: true,
            RecreateAfterSave: true,
            ResetRepeatTargetBeforeSave: true);
    }
}
