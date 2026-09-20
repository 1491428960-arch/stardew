namespace StardewAI.NPC;

public static class RelationshipStageRules
{
    /// <summary>
    /// 「重大阶段」——推进所需有效会话数更多（5 次而不是 4 次）的那几个。
    ///
    /// 2026-09-20（语义层审计 #43）：此前这张表在
    /// <see cref="InteractionProgress"/> 里，与阶段名域（本类的 <see cref="Resolve"/>）
    /// 分离，因此没人发现它含一个**死条目**「订婚/结婚」——阶段名域里从来没有这个名字。
    /// 现在它跟着阶段名域走，只保留域内确实会产出的三个名字。
    /// </summary>
    private static readonly HashSet<string> MajorStages = new(StringComparer.Ordinal)
    {
        "恋爱",
        "婚后",
        "育儿",
    };

    /// <summary>
    /// 「既成亲密关系」的四个阶段键：亲吻/亲密引导的门槛。
    /// 与 <see cref="ResolveKey"/> 产出的键同一域名，此前内联在
    /// <see cref="KissInteractionRules.CanArmAfterReply"/> 里（审计 #39 的“等白名单”）。
    /// </summary>
    private static readonly HashSet<string> EstablishedRomanticStageKeys =
        new(StringComparer.OrdinalIgnoreCase)
        {
            "dating",
            "married",
            "parent",
        };

    /// <summary>该阶段名是否属于「重大阶段」。</summary>
    public static bool IsMajorStage(string? stage)
    {
        return !string.IsNullOrWhiteSpace(stage) && MajorStages.Contains(stage.Trim());
    }

    /// <summary>该阶段键（<see cref="ResolveKey"/> 的输出）是否代表既成亲密关系。</summary>
    public static bool IsEstablishedRomantic(string? stageKey)
    {
        return stageKey is not null &&
            EstablishedRomanticStageKeys.Contains(stageKey.Trim());
    }

    public static string Resolve(NpcGameState state)
    {
        ArgumentNullException.ThrowIfNull(state);

        var marriageStatus = state.MarriageStatus?.Trim().ToLowerInvariant();
        if (state.ChildrenCount is > 0 && marriageStatus is "married" or "roommate")
        {
            return "育儿";
        }

        if (marriageStatus is "married" or "roommate")
        {
            return "婚后";
        }

        if (marriageStatus == "dating" ||
            string.Equals(state.Relationship?.Trim(), "dating", StringComparison.OrdinalIgnoreCase))
        {
            return "恋爱";
        }

        return state.FriendshipHearts switch
        {
            >= 8 => "亲近",
            >= 6 => "朋友",
            >= 3 => "熟悉",
            _ => "初识",
        };
    }

    public static string ResolveKey(NpcGameState state)
    {
        return Resolve(state) switch
        {
            "育儿" => "parent",
            "婚后" => "married",
            "恋爱" => "dating",
            "亲近" => "close",
            "朋友" => "friend",
            "熟悉" => "acquaintance",
            _ => "stranger",
        };
    }
}
