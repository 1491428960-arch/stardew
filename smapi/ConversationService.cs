namespace StardewAI.NPC;

public sealed class ConversationService : IDisposable
{
    private readonly IConversationTransport transport;
    private readonly StoryStateStore storyStateStore;
    private int sending;
    private bool disposed;

    public ConversationService(
        IConversationTransport transport,
        StoryStateStore storyStateStore)
    {
        this.transport = transport ?? throw new ArgumentNullException(nameof(transport));
        this.storyStateStore = storyStateStore ?? throw new ArgumentNullException(nameof(storyStateStore));
    }

    public async Task<ConversationTurnResult> SendAsync(
        NpcGameState state,
        string message,
        CancellationToken cancellationToken,
        ItemConversationContext? itemContext = null,
        string channel = ConversationChannel.Remote)
    {
        ArgumentNullException.ThrowIfNull(state);
        ThrowIfDisposed();
        if (string.IsNullOrWhiteSpace(message))
        {
            throw new ArgumentException("消息不能为空。", nameof(message));
        }

        EnterSending();
        try
        {
            var response = await transport.SendAsync(
                new ConversationRequest(
                    state.NpcId ?? string.Empty,
                    message,
                    itemContext is null ? ConversationIntent.Chat : ConversationIntent.Item,
                    state,
                    storyStateStore.RecentMemoryFacts(state.NpcId ?? string.Empty),
                    itemContext,
                    storyStateStore.RelationshipSnapshotFor(state.NpcId ?? string.Empty),
                    NormalizeChannel(channel),
                    // 隐性知识（2026-10-04）：她在群聊里听别人说过的话。
                    // 走独立参数而不是并进上面的 RecentFacts —— 后者那张卡的指令
                    // 是「把记忆自然用起来」（会主动提），而需求是「不主动提就不唤醒」。
                    storyStateStore.LatentKnowledge(state.NpcId ?? string.Empty)),
                cancellationToken).ConfigureAwait(false);
            var recorded = !response.Fallback;
            if (recorded)
            {
                storyStateStore.RecordConversation(state, message, response.Reply, usedFallback: false);
                if (response.OpenLoop is not null)
                {
                    storyStateStore.ApplyOpenLoopSignal(state, NormalizeChannel(channel), response.OpenLoop);
                }
            }

            return new ConversationTurnResult(response, recorded);
        }
        finally
        {
            ExitSending();
        }
    }

    public async Task<ConversationTurnResult> RequestTopicAsync(
        NpcGameState state,
        CancellationToken cancellationToken,
        string channel = ConversationChannel.Remote)
    {
        ArgumentNullException.ThrowIfNull(state);
        ThrowIfDisposed();

        EnterSending();
        try
        {
            var response = await transport.SendAsync(
                new ConversationRequest(
                    state.NpcId ?? string.Empty,
                    string.Empty,
                    ConversationIntent.Topic,
                    state,
                    storyStateStore.RecentMemoryFacts(state.NpcId ?? string.Empty),
                    null,
                    storyStateStore.RelationshipSnapshotFor(state.NpcId ?? string.Empty),
                    NormalizeChannel(channel),
                    storyStateStore.LatentKnowledge(state.NpcId ?? string.Empty)),
                cancellationToken).ConfigureAwait(false);
            if (!response.Fallback && response.OpenLoop is not null)
            {
                storyStateStore.ApplyOpenLoopSignal(state, NormalizeChannel(channel), response.OpenLoop);
            }

            return new ConversationTurnResult(response, Recorded: false);
        }
        finally
        {
            ExitSending();
        }
    }

    public void Cancel()
    {
        // 当前请求的取消由菜单持有的 CancellationTokenSource 负责；此方法用于统一生命周期调用点。
    }

    /// <summary>
    /// 只读回看：该 NPC 的**私聊**历史。
    ///
    /// 2026-09-21 用户口径调整：群聊场次**不再并进 F8**（此前这里会把
    /// <see cref="IConversationTransport.RecentGroupSessions"/> 也铺进来，面板上于是出现
    /// 分节线与整场群聊气泡）。群聊记录各归各位 —— 它在 F9 那张邀约卡里，点开就是整场
    /// 发言序列（见 <c>GroupDialogueHubMenu</c> 与 <c>GroupDialogueMenu</c> 的只读模式）。
    /// **存档里的场次一条没少**：<see cref="ChatHistoryArchive"/> 照旧读写，只是换了地方看。
    ///
    /// 这条路径不发送任何请求，也不会改变发给模型的那份窗口。
    /// </summary>
    public IReadOnlyList<ChatDisplayMessage> RecentMessages(string npcId)
    {
        return ChatHistoryRules.ToDisplayMessages(transport.RecentHistory(npcId));
    }

    public void Dispose()
    {
        disposed = true;
    }

    private void EnterSending()
    {
        if (Interlocked.Exchange(ref sending, 1) == 1)
        {
            throw new InvalidOperationException("当前已有一条对话请求正在处理。");
        }
    }

    private void ExitSending()
    {
        Volatile.Write(ref sending, 0);
    }

    private void ThrowIfDisposed()
    {
        if (disposed)
        {
            throw new ObjectDisposedException(nameof(ConversationService));
        }
    }

    private static string NormalizeChannel(string? channel)
    {
        return string.Equals(channel, ConversationChannel.FaceToFace, StringComparison.Ordinal)
            ? ConversationChannel.FaceToFace
            : ConversationChannel.Remote;
    }
}
