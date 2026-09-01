namespace StardewAI.NPC;

public static class ChatScrollRules
{
    public static int ClampStartIndex(int startIndex, int maxStartIndex)
    {
        if (maxStartIndex < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxStartIndex));
        }

        return Math.Clamp(startIndex, 0, maxStartIndex);
    }

    public static int MoveStartIndex(int startIndex, int delta, int maxStartIndex)
    {
        if (maxStartIndex < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxStartIndex));
        }

        var target = (long)startIndex + delta;
        return ClampStartIndex(
            target < int.MinValue
                ? int.MinValue
                : target > int.MaxValue
                    ? int.MaxValue
                    : (int)target,
            maxStartIndex);
    }
}
