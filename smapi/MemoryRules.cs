using System.Security.Cryptography;
using System.Text;

namespace StardewAI.NPC;

/// <summary>
/// 长期记忆写入的**统一规则**：条目上限、单条长度上限、稳定 ID、截断。
///
/// 2026-09-20（语义层审计 #44）：单聊（<see cref="ConversationStateRules"/>）与群聊
/// （<see cref="StoryStateStore.RecordMemoryHighlight"/>）各写一份字段模板 + 去重 +
/// 上限 + 截断；上限常量靠注释「与某某保持一致」人工同步，截断规则也已经漂移
/// （只有单聊那份带代理对保护）。这里把**常量与算法**收敛到一处，
/// 两份模板各自保留（它们承载的字段语义不同）。
/// </summary>
public static class MemoryRules
{
    /// <summary>长期记忆总量上限：超出后保留最新的若干条。</summary>
    public const int MaxCount = 200;

    /// <summary>长期记忆单条文本长度上限（UTF-16 单元数）。</summary>
    public const int MaxTextLength = 240;

    /// <summary>稳定记忆 ID 里哈希部分的十六进制位数。</summary>
    private const int IdHashLength = 24;

    /// <summary>
    /// 记忆 ID：<c>{kind}:{owner}:{SHA256(payload) 前 24 个十六进制位}</c>。
    ///
    /// 用 SHA256 而不是 <c>string.GetHashCode()</c>：后者跨进程随机化，
    /// 重启后同一条记忆的 ID 会变，去重失效（2026-09-20 已修过一次）。
    /// 单聊与群聊此前各调一次同样的算法、只差前缀，现在共用这一个入口。
    /// </summary>
    public static string BuildId(string kind, string owner, string payload)
    {
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(payload));
        return $"{kind}:{owner}:{Convert.ToHexString(hash)[..IdHashLength]}";
    }

    /// <summary>
    /// 截断到 <paramref name="maxLength"/>。
    ///
    /// 不要把 UTF-16 代理对切成两半：孤立的代理项会被序列化成替换字符，
    /// 让写进存档的记忆文本出现乱码。群聊侧原先没有这层保护，统一后与单聊同规
    /// （审计 #44 里唯一一处**边界行为修正**：仅当截断点恰好落在代理对之间时不同）。
    /// </summary>
    public static string Truncate(string value, int maxLength)
    {
        ArgumentNullException.ThrowIfNull(value);
        if (value.Length <= maxLength)
        {
            return value;
        }

        var length = maxLength;
        if (char.IsHighSurrogate(value[length - 1]))
        {
            length -= 1;
        }

        return value[..length];
    }
}
