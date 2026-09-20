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

    /// <summary>
    /// 是否应该注入床边测试 NPC。
    ///
    /// 默认关闭：那个克隆体不在角色表里，没有专属配色、没有气泡装饰，
    /// 留在农舍里会干扰「装饰修好没有」的判断；婚后角色本来就都在屋里，
    /// 直接跟真角色测试即可。
    ///
    /// 两种场合才打开：玩家把 <see cref="ModConfig.InjectTestNpc"/> 显式设为 true，
    /// 或视觉 harness 正在运行——harness 用它本来就有的
    /// <see cref="VisualTestHarnessRules.EnabledVariable"/> 环境变量把自己标出来，
    /// 因此 <c>scripts/start_visual_test.ps1</c> 不需要额外写配置。
    ///
    /// 这里是纯函数，好让「开关真的生效」可以脱离游戏被测试。
    /// </summary>
    public static bool ShouldInject(
        bool injectTestNpcConfigured,
        bool visualTestHarnessRunning)
    {
        return injectTestNpcConfigured || visualTestHarnessRunning;
    }

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
