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

    /// <summary>
    /// 只读回看入口之二：这位 NPC **在场**的群聊场次（一场一条，含完整发言序列）。
    ///
    /// ⚠ 2026-09-21 用户口径：它**不再并进 F8**（F8 只显示私聊，见
    /// <c>ConversationService.RecentMessages</c>）。群聊记录的出口是 F9 那张邀约卡：
    /// <c>GroupDialogueHubMenu</c> 用 <c>BridgeClient.GroupSession(邀约id)</c> 取这一场，
    /// 点开就是整场发言序列。按 NPC 查询这一头因此暂时只服务诊断（视觉测试会把
    /// 每位参与者在场的场次数打进日志）；留着是因为「这位 NPC 参与过哪几场」
    /// 本身仍是个合理的只读问法。
    ///
    /// 同样默认返回空：轻量 transport 不必为了满足接口而写一个空方法。
    /// </summary>
    IReadOnlyList<GroupChatSessionRecord> RecentGroupSessions(string npcId) =>
        Array.Empty<GroupChatSessionRecord>();
}
