namespace StardewAI.NPC;

/// <summary>
/// 聊天气泡的纯文本布局规则；实际宽度由游戏字体测量函数提供。
/// </summary>
public static class ChatTextLayoutRules
{
    public static IReadOnlyList<string> Wrap(
        string text,
        float maxWidth,
        Func<string, float> measure)
    {
        ArgumentNullException.ThrowIfNull(text);
        if (maxWidth <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxWidth));
        }
        ArgumentNullException.ThrowIfNull(measure);

        var lines = new List<string>();
        foreach (var paragraph in text.Replace("\r\n", "\n").Split('\n'))
        {
            var current = string.Empty;
            foreach (var character in paragraph)
            {
                var candidate = current + character;
                if (current.Length > 0 && measure(candidate) > maxWidth)
                {
                    lines.Add(current);
                    current = character.ToString();
                }
                else
                {
                    current = candidate;
                }
            }

            lines.Add(current);
        }

        return lines;
    }

    public static IReadOnlyList<string> Fit(
        IReadOnlyList<string> lines,
        int maxLines,
        float maxWidth,
        Func<string, float> measure,
        string ellipsis = "…")
    {
        ArgumentNullException.ThrowIfNull(lines);
        if (maxLines <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxLines));
        }
        if (maxWidth <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxWidth));
        }
        ArgumentNullException.ThrowIfNull(measure);
        if (string.IsNullOrEmpty(ellipsis))
        {
            throw new ArgumentException("省略号不能为空。", nameof(ellipsis));
        }

        if (lines.Count <= maxLines)
        {
            return lines;
        }

        var result = lines.Take(maxLines).ToArray();
        result[^1] = TruncateWithEllipsis(result[^1], maxWidth, measure, ellipsis);
        return result;
    }

    public static IReadOnlyList<T> SelectLatestThatFit<T>(
        IReadOnlyList<T> items,
        int maxItems,
        int availableHeight,
        int gap,
        Func<T, int> measureHeight)
    {
        ArgumentNullException.ThrowIfNull(items);
        if (maxItems <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxItems));
        }
        if (availableHeight <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(availableHeight));
        }
        if (gap < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(gap));
        }
        ArgumentNullException.ThrowIfNull(measureHeight);

        var selected = new List<T>();
        var remainingHeight = availableHeight;
        for (var index = items.Count - 1;
             index >= 0 && selected.Count < maxItems;
             index--)
        {
            var height = measureHeight(items[index]);
            if (height <= 0)
            {
                throw new ArgumentException("消息高度必须大于 0。", nameof(measureHeight));
            }

            var cost = selected.Count == 0 ? height : checked(height + gap);
            // 即使最新消息本身需要截断，也必须保留它；调用方会再用 Fit
            // 将它压缩到可用高度内。
            if (selected.Count > 0 && cost > remainingHeight)
            {
                break;
            }

            selected.Add(items[index]);
            remainingHeight -= cost;
        }

        selected.Reverse();
        return selected;
    }

    private static string TruncateWithEllipsis(
        string line,
        float maxWidth,
        Func<string, float> measure,
        string ellipsis)
    {
        if (measure(ellipsis) > maxWidth)
        {
            return string.Empty;
        }

        var prefix = line;
        while (prefix.Length > 0 && measure(prefix + ellipsis) > maxWidth)
        {
            prefix = prefix[..^1];
        }

        return prefix + ellipsis;
    }
}
