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
                    NormalizeChannel(channel)),
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
                    NormalizeChannel(channel)),
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
    /// 只读回看：该 NPC 最近的历史对话，映射成面板消息（角色与条数规则见
    /// <see cref="ChatHistoryRules"/>）。F8 面板打开时铺进消息区，之后新消息继续追加；
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
