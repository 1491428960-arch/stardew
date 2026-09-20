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
    /// 单次回看最多铺多少条历史。2026-09-21 由 60 提到 1000：60 条只够回看十来屏，
    /// 玩家想翻「上周那次」根本翻不到，而回看档案本来就是给玩家翻的（发给模型的窗口
    /// 仍是 <c>BridgeClient.MaxHistoryItems</c> 条，一字不动）。
    ///
    /// 这个常量同时是**存档体积的上限**（这一份随存档保存，见 <see cref="ChatHistoryArchive"/>）。
    /// 2026-09-21 实测（数字打在 <c>ChatHistoryArchiveTests</c> 的两条预算用例里备查）：
    /// 满档 = 每位 NPC 都聊满 1000 条 240 字 → 20 位 / 2 万条 = **15.23 MB**，
    /// 序列化 28 ms、反序列化 40 ms、常驻内存 10.7 MB；
    /// 现实规模 = 只跟 5 位深聊（玩家 12 字 / NPC 60 字）→ **0.89 MB**、
    /// 序列化 1.7 ms、反序列化 2.4 ms。存档里一个中文字 3 字节且不做转义，
    /// 所以「档案多大，存档就长大多少」——再往上加之前先看那两条用例的数字。
    /// </summary>
    public const int MaxDisplayMessages = 1000;

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
