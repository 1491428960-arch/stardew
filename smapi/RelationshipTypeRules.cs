namespace StardewAI.NPC;

/// <summary>
/// 关系类型（<c>relationType</c>）白名单的**唯一**定义。
///
/// 2026-09-20（语义层审计 #39）：此前同一份三项白名单存在三处
/// （<see cref="StoryStateValidation"/>、<see cref="StoryStateStore"/>、
/// <see cref="KissInteractionRules"/>），成员一致但**比较口径不同**——
/// 校验侧用 <see cref="StringComparison.Ordinal"/>，亲吻侧用
/// <see cref="StringComparison.OrdinalIgnoreCase"/>，于是同一个 <c>"Dating"</c>
/// 会被校验拒绝、却被亲吻接受。
///
/// 这里收敛的是**成员表**：现在只有一份数组，两个口径各留一个显式命名的方法。
/// 口径差异本身保持原样——把任一侧改成另一侧都会改变行为（校验变宽或亲吻变严），
/// 那属于需要产品决策的变更，不在本次「等价重构」范围内。
/// </summary>
public static class RelationshipTypeRules
{
    /// <summary>关系类型的唯一成员表。</summary>
    private static readonly string[] Members =
    {
        "dating",
        "engaged",
        "married",
    };

    /// <summary>校验口径：与存档校验/写入原有的区分大小写比较一致。</summary>
    private static readonly HashSet<string> CanonicalMembers =
        new(Members, StringComparer.Ordinal);

    /// <summary>亲吻口径：与原有的忽略大小写比较一致。</summary>
    private static readonly HashSet<string> CaseInsensitiveMembers =
        new(Members, StringComparer.OrdinalIgnoreCase);

    /// <summary>存档校验用的严格判定（区分大小写），口径不变。</summary>
    public static bool IsSupported(string? relationType)
    {
        return relationType is not null && CanonicalMembers.Contains(relationType);
    }

    /// <summary>亲吻门槛用的宽放判定（忽略大小写并 Trim），口径不变。</summary>
    public static bool IsRomantic(string? relationType)
    {
        return relationType is not null &&
            CaseInsensitiveMembers.Contains(relationType.Trim());
    }
}
