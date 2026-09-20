namespace StardewAI.NPC;

public static class KissInteractionRules
{
    public const double MinimumAnimationMilliseconds = 500;
    public const double MaximumAnimationMilliseconds = 2000;

    public static bool CanArmAfterReply(
        bool effectiveReply,
        string? relationshipStage,
        string? customRelationshipType)
    {
        if (!effectiveReply)
        {
            return false;
        }

        // 阶段白名单与关系类型白名单都只有一份定义：
        // 阶段在 RelationshipStageRules（阶段名域的定义处），
        // 关系类型在 RelationshipTypeRules（审计 #39）。
        return RelationshipStageRules.IsEstablishedRomantic(relationshipStage) ||
            RelationshipTypeRules.IsRomantic(customRelationshipType);
    }

    /// <summary>
    /// 亲吻能否触发。
    ///
    /// 2026-09-20（语义层审计 #33/#34）：前七项与续聊共用
    /// <see cref="FaceToFaceGate.AllowsInteraction"/>（此前是两处逐字重复的合取），
    /// 其余四项是本路径特有的「玩家此刻腾得出手」条件。
    ///
    /// 门槛只在这里判一次：<see cref="NpcKissAnimationController.TryStart"/>
    /// 不再重复判一遍（它只保留控制器自身的运行时前置）。
    /// </summary>
    public static bool CanTriggerKiss(
        FaceToFaceGate gate,
        bool playerCanMove,
        bool usingTool,
        bool ridingHorse,
        bool sitting)
    {
        ArgumentNullException.ThrowIfNull(gate);
        return gate.AllowsInteraction &&
            playerCanMove &&
            !usingTool &&
            !ridingHorse &&
            !sitting;
    }

    public static bool ShouldCompleteKiss(
        double elapsedMilliseconds,
        bool playerCanMove)
    {
        if (elapsedMilliseconds < MinimumAnimationMilliseconds)
        {
            return false;
        }

        return playerCanMove || elapsedMilliseconds >= MaximumAnimationMilliseconds;
    }
}
