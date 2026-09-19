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
    public async Task Chat_sends_group_highlights_as_recent_facts_for_that_npc_only()
    {
        var transport = new FakeTransport();
        var store = new StoryStateStore();
        // 群聊里玩家当着 Rasmodia 说的约定会写进她的长期记忆。
        store.RecordMemoryHighlight("Rasmodia", "玩家下周要交一份报告。", "Spring 14");
        // 别人在群里听到的事不该出现在她的请求里。
        store.RecordMemoryHighlight("Abigail", "不该出现在 Rasmodia 的请求里", "Spring 14");
        var service = new ConversationService(transport, store);

        await service.SendAsync(
            TestNpcState(),
            "你还记得我说过什么吗？",
            CancellationToken.None);

        var facts = transport.LastRequest!.RecentFacts ?? Array.Empty<string>();
        Assert.Contains(facts, fact => fact.Contains("报告"));
        Assert.DoesNotContain(facts, fact => fact.Contains("不该出现"));
    }

    [Fact]
    public async Task SuccessfulChat_sends_the_current_npcs_relationship_snapshot_only()
    {
        var transport = new FakeTransport();
        var store = new StoryStateStore();
        store.Replace(StoryStateEnvelope.Empty with
        {
            Relationships = new[]
            {
                new RelationshipEdgeRecord
                {
                    FromNpcId = "player",
                    ToNpcId = "Sophia",
                    RelationType = "dating",
                },
                new RelationshipEdgeRecord
                {
                    FromNpcId = "player",
                    ToNpcId = "Alex",
                    RelationType = "married",
                    PublicEventId = "wedding:alex",
                },
            },
            RelationshipViews = new[]
            {
                new RelationshipViewRecord
                {
                    OwnerNpcId = "Sophia",
                    SubjectNpcId = "Alex",
                    RelationType = "married",
                    Visibility = "known",
                    Source = "wedding",
                },
                new RelationshipViewRecord
                {
                    OwnerNpcId = "Alex",
                    SubjectNpcId = "Sophia",
                    RelationType = "dating",
                    Visibility = "known",
                    Source = "player_statement",
                },
            },
        });
        var service = new ConversationService(transport, store);
        var sophiaState = new NpcGameState
        {
            NpcId = "Sophia",
            DisplayName = "Sophia",
            Date = "Spring 1",
            Location = "Vineyard",
            Friendship = 750,
            FriendshipHearts = 3,
        };

        await service.SendAsync(sophiaState, "你好", CancellationToken.None);

        var snapshot = transport.LastRequest!.RelationshipWorld!;
        Assert.All(snapshot.Views, view => Assert.Equal("Sophia", view.OwnerNpcId));
        Assert.DoesNotContain(snapshot.ObjectiveRelationships, relation => relation.ToNpcId == "Alex");
    }

    [Fact]
    public async Task Successful_chat_sends_channel_and_applies_open_loop_signal()
    {
        var transport = new FakeTransport
        {
            Response = new BridgeDialogueResponse
            {
                Reply = "那我们下次当面继续。",
                Provider = "fake",
                OpenLoop = new OpenLoopSignal
                {
                    Action = "open",
                    LoopId = "rasmodia:rune:Spring-1",
                    Topic = "rune_review",
                    ShortSummary = "线上留下了核对符文数据的话题",
                },
            },
        };
        var store = new StoryStateStore();
        var service = new ConversationService(transport, store);

        await service.SendAsync(
            TestNpcState(),
            "这件事我们下次继续。",
            CancellationToken.None,
            channel: ConversationChannel.Remote);

        Assert.Equal(ConversationChannel.Remote, transport.LastRequest!.Channel);
        Assert.Equal("open", Assert.Single(store.State.OpenLoops).Status);
    }

    [Fact]
    public async Task Face_to_face_resolution_is_applied_but_fallback_signal_is_ignored()
    {
        var store = new StoryStateStore();
        var npcState = TestNpcState();
        store.ApplyOpenLoopSignal(npcState, ConversationChannel.Remote, new OpenLoopSignal
        {
            Action = "open",
            LoopId = "rasmodia:rune:Spring-1",
            Topic = "rune_review",
            ShortSummary = "线上留下了核对符文数据的话题",
        });
        var transport = new FakeTransport
        {
            Response = new BridgeDialogueResponse
            {
                Reply = "我们说开了。",
                Provider = "fake",
                OpenLoop = new OpenLoopSignal
                {
                    Action = "resolve",
                    LoopId = "rasmodia:rune:Spring-1",
                },
            },
        };
        var service = new ConversationService(transport, store);

        await service.SendAsync(
            npcState,
            "现在当面聊聊吧。",
            CancellationToken.None,
            channel: ConversationChannel.FaceToFace);
        Assert.Equal("resolved", Assert.Single(store.State.OpenLoops).Status);

        transport.Response = new BridgeDialogueResponse
        {
            Reply = "失败回复不应改变状态。",
            Provider = "offline",
            Fallback = true,
            OpenLoop = new OpenLoopSignal
            {
                Action = "open",
                LoopId = "rasmodia:new",
                Topic = "new",
                ShortSummary = "不应写入",
            },
        };
        await service.SendAsync(
            npcState,
            "失败回复不应改变状态。",
            CancellationToken.None,
            channel: ConversationChannel.FaceToFace);
        Assert.Equal("resolved", Assert.Single(store.State.OpenLoops).Status);
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
