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
}
