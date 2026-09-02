using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ConversationServiceTests
{
    [Fact]
    public async Task TopicRequestDoesNotWriteMemoryUntilPlayerReplies()
    {
        var transport = new FakeTransport();
        var store = new StoryStateStore();
        var service = new ConversationService(transport, store);

        var topic = await service.RequestTopicAsync(TestNpcState(), CancellationToken.None);

        Assert.Equal(ConversationIntent.Topic, transport.LastRequest!.Intent);
        Assert.Empty(transport.LastRequest.Message);
        Assert.Empty(store.State.Memories);
        Assert.Equal("收到。", topic.Reply);
    }

    [Fact]
    public async Task SuccessfulChatRecordsMemoryThroughStoryStateStore()
    {
        var transport = new FakeTransport();
        var store = new StoryStateStore();
        var service = new ConversationService(transport, store);

        var result = await service.SendAsync(
            TestNpcState(),
            "你好",
            CancellationToken.None);

        Assert.False(result.Response.Fallback);
        Assert.Single(store.State.Memories);
        Assert.Equal(ConversationIntent.Chat, transport.LastRequest!.Intent);
    }

    [Fact]
    public async Task SendingSecondMessageWhileFirstIsPendingIsRejected()
    {
        var transport = new BlockingTransport();
        var service = new ConversationService(transport, new StoryStateStore());

        var first = service.SendAsync(TestNpcState(), "第一句", CancellationToken.None);
        await transport.Started.Task;

        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            service.SendAsync(TestNpcState(), "第二句", CancellationToken.None));

        transport.Release();
        await first;
    }

    [Fact]
    public async Task TopicRequest_completes_without_a_game_synchronization_context_pump()
    {
        var transport = new AwaitableTransport();
        var service = new ConversationService(transport, new StoryStateStore());
        var previousContext = SynchronizationContext.Current;

        try
        {
            // MonoGame/SMAPI may install a context which isn't pumped while a
            // menu is waiting on an async request. The service must not capture
            // that context for its completion continuation.
            SynchronizationContext.SetSynchronizationContext(
                new NonPumpingSynchronizationContext());
            var pending = service.RequestTopicAsync(TestNpcState(), CancellationToken.None);
            transport.Release();
            // Restore the test runner context before awaiting so the assertion
            // itself can resume; the request continuation still targets the
            // deliberately non-pumping context captured above.
            SynchronizationContext.SetSynchronizationContext(previousContext);

            var result = await pending.WaitAsync(TimeSpan.FromSeconds(1));

            Assert.Equal("完成。", result.Reply);
        }
        finally
        {
            SynchronizationContext.SetSynchronizationContext(previousContext);
        }
    }

    private static NpcGameState TestNpcState()
    {
        return new NpcGameState
        {
            NpcId = "Rasmodia",
            DisplayName = "Rasmodia",
            Date = "Spring 1",
            Location = "WizardTower",
            Friendship = 750,
            FriendshipHearts = 3,
        };
    }

    private sealed class FakeTransport : IConversationTransport
    {
        public ConversationRequest? LastRequest { get; private set; }

        public BridgeDialogueResponse Response { get; set; } = new()
        {
            Reply = "收到。",
            Provider = "fake",
        };

        public Task<BridgeDialogueResponse> SendAsync(
            ConversationRequest request,
            CancellationToken cancellationToken)
        {
            LastRequest = request;
            return Task.FromResult(Response);
        }
    }

    private sealed class BlockingTransport : IConversationTransport
    {
        public TaskCompletionSource<object?> Started { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        private readonly TaskCompletionSource<object?> release =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task<BridgeDialogueResponse> SendAsync(
            ConversationRequest request,
            CancellationToken cancellationToken)
        {
            Started.TrySetResult(null);
            return WaitAsync();

            async Task<BridgeDialogueResponse> WaitAsync()
            {
                await release.Task.WaitAsync(cancellationToken);
                return new BridgeDialogueResponse
                {
                    Reply = "完成。",
                    Provider = "fake",
                };
            }
        }

        public void Release()
        {
            release.TrySetResult(null);
        }
    }

    private sealed class AwaitableTransport : IConversationTransport
    {
        private readonly TaskCompletionSource<BridgeDialogueResponse> response =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task<BridgeDialogueResponse> SendAsync(
            ConversationRequest request,
            CancellationToken cancellationToken)
        {
            _ = request;
            return response.Task.WaitAsync(cancellationToken);
        }

        public void Release()
        {
            response.TrySetResult(new BridgeDialogueResponse
            {
                Reply = "完成。",
                Provider = "fake",
            });
        }
    }

    private sealed class NonPumpingSynchronizationContext : SynchronizationContext
    {
        public override void Post(SendOrPostCallback d, object? state)
        {
            _ = d;
            _ = state;
            // Deliberately drop callbacks to model a context which is not
            // pumped by the game while an async menu request is in flight.
        }
    }
}
