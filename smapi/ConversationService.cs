namespace StardewAI.NPC;

public sealed class ConversationService : IDisposable
{
    private const string TopicPrompt = "请主动找一个自然的话题。";
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
        ItemConversationContext? itemContext = null)
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
                    itemContext),
                cancellationToken).ConfigureAwait(false);
            var recorded = !response.Fallback;
            if (recorded)
            {
                storyStateStore.RecordConversation(state, message, response.Reply, usedFallback: false);
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
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(state);
        ThrowIfDisposed();

        EnterSending();
        try
        {
            var response = await transport.SendAsync(
                new ConversationRequest(
                    state.NpcId ?? string.Empty,
                    TopicPrompt,
                    ConversationIntent.Topic,
                    state,
                    storyStateStore.RecentMemoryFacts(state.NpcId ?? string.Empty),
                    null),
                cancellationToken).ConfigureAwait(false);
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
}
