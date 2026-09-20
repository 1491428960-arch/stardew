namespace StardewAI.NPC;

public interface IConversationTransport
{
    Task<BridgeDialogueResponse> SendAsync(
        ConversationRequest request,
        CancellationToken cancellationToken);

    /// <summary>
    /// 只读回看入口：某位 NPC 最近真实发生过的对话（玩家与 NPC 都在），
    /// 供 F8 面板打开时铺历史。它**不参与发送**，也不改变请求里那份
    /// 6 条窗口——只把已经发生的事情多留一会儿给玩家翻。
    ///
    /// 默认返回空：显示历史是可选的，轻量 transport（测试替身、只转发不记忆的实现）
    /// 不必为了满足接口而写一个空方法。
    /// </summary>
    IReadOnlyList<BridgeDialogueHistoryItem> RecentHistory(string npcId) =>
        Array.Empty<BridgeDialogueHistoryItem>();
}
