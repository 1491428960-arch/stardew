using Microsoft.Xna.Framework;
using StardewValley;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

/// <summary>
/// 播放一次原版玩家亲吻，并在可用时临时显示 NPC 的 kiss frame。
/// 该控制器只维护本次交互的内存状态，不写入存档或原版关系字段。
/// </summary>
public sealed class NpcKissAnimationController
{
    private ActiveKiss? activeKiss;

    public bool IsActive => activeKiss is not null;

    public bool TryStart(
        StardewNpc npc,
        Action<StardewNpc> onCompleted)
    {
        ArgumentNullException.ThrowIfNull(npc);
        ArgumentNullException.ThrowIfNull(onCompleted);

        var player = Game1.player;
        if (activeKiss is not null ||
            player is null ||
            Game1.currentLocation is null ||
            npc.currentLocation is null ||
            !ReferenceEquals(player.currentLocation, npc.currentLocation) ||
            Game1.activeClickableMenu is not null ||
            Game1.eventUp ||
            Game1.isFestival() ||
            !player.CanMove ||
            player.UsingTool ||
            player.isRidingHorse() ||
            player.IsSitting())
        {
            return false;
        }

        var originalNpcFacingDirection = npc.FacingDirection;
        var npcAnimationApplied = TryApplyNpcKissFrame(
            npc,
            out originalNpcFacingDirection);

        try
        {
            player.faceDirection(
                Utility.getDirectionFromChange(player.Position, npc.Position));
            player.PerformKiss(player.FacingDirection);
        }
        catch
        {
            RestoreNpc(npc, originalNpcFacingDirection, npcAnimationApplied);
            return false;
        }

        activeKiss = new ActiveKiss(
            npc,
            originalNpcFacingDirection,
            npcAnimationApplied,
            ElapsedMilliseconds: 0,
            onCompleted);
        return true;
    }

    public void Update(GameTime gameTime)
    {
        ArgumentNullException.ThrowIfNull(gameTime);
        var current = activeKiss;
        if (current is null)
        {
            return;
        }

        var elapsedMilliseconds = current.ElapsedMilliseconds +
            Math.Max(0, gameTime.ElapsedGameTime.TotalMilliseconds);
        current = current with { ElapsedMilliseconds = elapsedMilliseconds };
        activeKiss = current;

        if (!KissInteractionRules.ShouldCompleteKiss(
                elapsedMilliseconds,
                Game1.player?.CanMove == true))
        {
            return;
        }

        activeKiss = null;
        RestoreNpc(
            current.Npc,
            current.OriginalNpcFacingDirection,
            current.NpcAnimationApplied);
        current.OnCompleted(current.Npc);
    }

    public void Reset()
    {
        var current = activeKiss;
        activeKiss = null;
        if (current is not null)
        {
            RestoreNpc(
                current.Npc,
                current.OriginalNpcFacingDirection,
                current.NpcAnimationApplied);
        }
    }

    private static bool TryApplyNpcKissFrame(
        StardewNpc npc,
        out int originalNpcFacingDirection)
    {
        originalNpcFacingDirection = npc.FacingDirection;
        try
        {
            var data = npc.GetData();
            if (data.KissSpriteIndex < 0)
            {
                return false;
            }

            npc.faceDirection(data.KissSpriteFacingRight ? 1 : 3);
            npc.Sprite.setCurrentAnimation(
                new List<FarmerSprite.AnimationFrame>
                {
                    new(data.KissSpriteIndex, 1000),
                });
            return true;
        }
        catch
        {
            npc.faceDirection(originalNpcFacingDirection);
            return false;
        }
    }

    private static void RestoreNpc(
        StardewNpc npc,
        int originalFacingDirection,
        bool animationApplied)
    {
        if (!animationApplied)
        {
            return;
        }

        try
        {
            npc.Sprite.StopAnimation();
            npc.faceDirection(originalFacingDirection);
        }
        catch
        {
            // A removed NPC can invalidate its sprite between ticks; the
            // player animation and coordinator state still need to finish.
        }
    }

    private sealed record ActiveKiss(
        StardewNpc Npc,
        int OriginalNpcFacingDirection,
        bool NpcAnimationApplied,
        double ElapsedMilliseconds,
        Action<StardewNpc> OnCompleted);
}
