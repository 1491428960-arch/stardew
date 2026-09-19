namespace StardewAI.NPC;

/// <summary>
/// 判断一轮对话是否真正完成了关系修复；不负责修改故事状态或游戏状态。
/// </summary>
public static class RelationshipRepairRules
{
    private static readonly string[] ConflictMarkers =
    {
        "吃醋",
        "嫉妒",
        "不安",
        "介意",
        "难受",
        "误会",
        "心结",
        "失望",
        "冷落",
        "忽视",
        "失约",
        "承诺",
        "偏心",
    };

    private static readonly string[] AcknowledgementMarkers =
    {
        "我承认",
        "我知道",
        "我明白",
        "是我",
        "我不该",
        "对不起",
        "抱歉",
        "你说得对",
    };

    private static readonly string[] ExplanationMarkers =
    {
        "解释",
        "说清楚",
        "说明白",
        "因为",
        "原因",
        "不是故意",
        "事情是",
        "把话说开",
    };

    private static readonly string[] RepairMarkers =
    {
        "我会改",
        "我会做到",
        "说到做到",
        "守住承诺",
        "兑现承诺",
        "弥补",
        "修补",
        "尊重你的选择",
        "尊重你的感受",
        "不会再让你",
        "不再让你",
    };

    private static readonly string[] SpaceMarkers =
    {
        "给你空间",
        "不逼你",
        "你不用现在回答",
        "慢慢想",
        "等你愿意",
        "尊重你的节奏",
    };

    private static readonly string[] FutureSchedulingMarkers =
    {
        "今晚",
        "明天",
        "后天",
        "晚点",
        "等会儿",
        "下次",
        "以后",
        "每天",
        "每周",
        "轮流",
        "排期",
        "预约",
        "时间表",
        "安排时间",
    };

    public static bool IsValuableRelationshipRepair(
        string? playerMessage,
        string? npcReply,
        RelationshipWorldSnapshot? relationshipWorld)
    {
        if (string.IsNullOrWhiteSpace(playerMessage) ||
            string.IsNullOrWhiteSpace(npcReply))
        {
            return false;
        }

        // 关系回应不能把未来排期或时间分配当成修复动作。
        if (ContainsAny(npcReply, FutureSchedulingMarkers))
        {
            return false;
        }

        var hasActiveIssue = relationshipWorld?.Jealousy?.Active == true ||
            relationshipWorld?.Mediation?.Status is "offered" or "active";
        var hasConflictInThisTurn = ContainsAny(playerMessage, ConflictMarkers);
        if (!hasActiveIssue && !hasConflictInThisTurn)
        {
            return false;
        }

        return HasRepairEvidence(npcReply);
    }

    private static bool HasRepairEvidence(string reply)
    {
        var acknowledgement = ContainsAny(reply, AcknowledgementMarkers);
        var explanation = ContainsAny(reply, ExplanationMarkers);
        var repair = ContainsAny(reply, RepairMarkers);
        var givesSpace = ContainsAny(reply, SpaceMarkers);

        return givesSpace || repair || acknowledgement && explanation;
    }

    private static bool ContainsAny(string value, IReadOnlyList<string> markers)
    {
        return markers.Any(marker =>
            value.Contains(marker, StringComparison.OrdinalIgnoreCase));
    }
}
