namespace StardewAI.NPC;

/// <summary>
/// F8 面板「往上翻看历史」的**显示规则**。
///
/// 2026-09-20：Bridge 侧一直按 NPC 累积真实对话（BridgeClient 的 historyByNpc），
/// 但打开面板时那一份从来没有铺进消息区 —— 于是模型看得见、玩家看不见，
/// NPC 会引用玩家没见过的内容，读起来「没头没尾」。这里只补**显示**这一层。
///
/// 两条边界：
/// 1. 发给模型的窗口一字不动（仍是 BridgeClient 的 6 条）；回看档案单独保留更多，
///    只给玩家看；
/// 2. 只做角色映射与条数裁剪，不改文本 —— 面板显示的应当就是模型当时看到的那句话。
/// </summary>
public static class ChatHistoryRules
{
    /// <summary>
    /// 单次回看最多铺多少条历史。取值只看「翻得动」与「占地小」两件事：
    /// 一屏约 6～10 条气泡，60 条约十屏；按单条 <see cref="MaxContentLength"/> 字的上限算，
    /// 一位 NPC 最坏情况约 29 KB，二十位不到 1 MB。这一份会随存档保存
    /// （见 <see cref="ChatHistoryArchive"/>），取值同时是存档体积的上限。
    /// </summary>
    public const int MaxDisplayMessages = 60;

    /// <summary>
    /// 单条记录的文本上限。写入端（<see cref="BridgeClient"/>）与存档读回时共用这一份，
    /// 免得两边各写一个 240 而慢慢走散。
    /// </summary>
    public const int MaxContentLength = 240;

    /// <summary>
    /// 把 Bridge 累积的历史映射成面板消息：<c>user</c> → <c>player</c>，
    /// 其余（<c>assistant</c>，含群聊摘要）→ <c>npc</c>。
    /// 空白内容与超出上限的部分直接丢掉（保留最新的那批）。
    /// </summary>
    public static IReadOnlyList<ChatDisplayMessage> ToDisplayMessages(
        IEnumerable<BridgeDialogueHistoryItem>? history,
        int maximumCount = MaxDisplayMessages)
    {
        if (history is null || maximumCount <= 0)
        {
            return Array.Empty<ChatDisplayMessage>();
        }

        return history
            .Where(item => item is not null && !string.IsNullOrWhiteSpace(item.Content))
            .TakeLast(maximumCount)
            .Select(item => new ChatDisplayMessage(DisplayRole(item.Role), item.Content))
            .ToArray();
    }

    /// <summary>
    /// Bridge 的 role → 面板的 role。面板只认 <c>player</c> 与 <c>npc</c>
    /// （见 <see cref="ChatInputMenu"/> 的气泡绘制），认不出的一律当 NPC 说。
    /// </summary>
    private static string DisplayRole(string? role)
    {
        return role?.Trim().ToLowerInvariant() switch
        {
            "user" or "player" => "player",
            _ => "npc",
        };
    }
}
