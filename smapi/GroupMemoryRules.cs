namespace StardewAI.NPC;

/// <summary>一条待写入的群聊长期记忆：某位在场 NPC 记住的一句事实或约定。</summary>
public sealed record GroupMemoryWrite(string NpcId, string Content);

/// <summary>
/// 群聊长期记忆的写入计划。Bridge 只挑出值得长期记住的少量高亮，
/// 而这些高亮是玩家当着所有参与者说的，因此在场的每个人各记一条；
/// 闲聊不会出现在高亮里，所以这里不做额外的“重要性”判断。
/// 计划本身是纯函数，便于离线验证，也避免生产路径与测试路径各写一份。
/// </summary>
public static class GroupMemoryRules
{
    public static IReadOnlyList<GroupMemoryWrite> Plan(
        IEnumerable<string>? participantNpcIds,
        IEnumerable<string>? highlights)
    {
        if (participantNpcIds is null || highlights is null)
        {
            return Array.Empty<GroupMemoryWrite>();
        }

        var participants = Normalize(participantNpcIds);
        if (participants.Length == 0)
        {
            return Array.Empty<GroupMemoryWrite>();
        }

        var contents = Normalize(highlights);
        if (contents.Length == 0)
        {
            return Array.Empty<GroupMemoryWrite>();
        }

        return participants
            .SelectMany(npcId => contents.Select(content => new GroupMemoryWrite(npcId, content)))
            .ToArray();
    }

    private static string[] Normalize(IEnumerable<string> values)
    {
        return values
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }
}
