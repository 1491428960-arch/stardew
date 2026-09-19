namespace StardewAI.NPC;

public static class RelationshipStageRules
{
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
