using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class StoryStateStoreTests
{
    [Fact]
    public void Load_applies_valid_state_and_serialize_round_trips_it()
    {
        var store = new StoryStateStore();
        var expected = new StoryStateEnvelope
        {
            StoryEvents = new[]
            {
                new StoryEventRecord
                {
                    EventId = "vanilla:event-1",
                    SourceMod = "vanilla",
                    SourceKey = "event-1",
                    Participants = new[] { "Wizard", "player" },
                    Status = "completed",
                    GameDate = "Spring 14",
                    Canonical = true,
                    Summary = "玩家完成了法师塔事件",
                },
            },
        };

        store.Load(StoryStateSerializer.Serialize(expected));

        Assert.Single(store.State.StoryEvents);
        Assert.Equal("vanilla:event-1", store.State.StoryEvents[0].EventId);
        using var document = JsonDocument.Parse(store.Serialize());
        Assert.Equal(1, document.RootElement.GetProperty("schemaVersion").GetInt32());
        Assert.Equal(
            "completed",
            document.RootElement.GetProperty("storyEvents")[0].GetProperty("status").GetString());
        Assert.Empty(store.LastWarnings);
    }

    [Fact]
    public void RecordMemoryHighlight_writes_one_group_memory_for_its_owner()
    {
        var store = new StoryStateStore();

        store.RecordMemoryHighlight("Abigail", "玩家说下周要交一份报告", "Spring 14");

        var memory = Assert.Single(store.State.Memories);
        Assert.Equal("Abigail", memory.OwnerNpcId);
        Assert.Equal("fact", memory.Kind);
        Assert.Equal("Spring 14", memory.GameDate);
        Assert.StartsWith("group:abigail:", memory.MemoryId);
        Assert.Contains("报告", memory.Content);
        Assert.Contains("player", memory.Participants);
    }

    [Fact]
    public void RecordMemoryHighlight_does_not_duplicate_the_same_text()
    {
        var store = new StoryStateStore();

        store.RecordMemoryHighlight("Abigail", "玩家说下周要交一份报告", "Spring 14");
        store.RecordMemoryHighlight("Abigail", "玩家说下周要交一份报告", "Spring 14");

        Assert.Single(store.State.Memories);
    }

    [Fact]
    public void RecordMemoryHighlight_skips_invalid_input_and_truncates_long_text()
    {
        var store = new StoryStateStore();

        store.RecordMemoryHighlight("Abigail", "   ", "Spring 14");
        store.RecordMemoryHighlight("", "玩家说下周要交一份报告", "Spring 14");
        // 缺游戏日期时不写：记录本身会因为 gameDate 为空而不合法
        store.RecordMemoryHighlight("Abigail", "玩家说下周要交一份报告", "  ");
        Assert.Empty(store.State.Memories);

        store.RecordMemoryHighlight("Abigail", new string('长', 300), "Spring 14");

        Assert.Equal(240, Assert.Single(store.State.Memories).Content.Length);
    }

    [Fact]
    public void Load_invalid_json_resets_state_and_keeps_warnings()
    {
        var store = new StoryStateStore();
        store.Load("{not-json");

        Assert.Empty(store.State.StoryEvents);
        Assert.Empty(store.State.Memories);
        Assert.Contains("invalid", store.LastWarnings[0]);
    }

    [Fact]
    public void Reset_clears_loaded_state_and_warnings()
    {
        var store = new StoryStateStore();
        store.Load(StoryStateSerializer.Serialize(new StoryStateEnvelope
        {
            Relationships = new[]
            {
                new RelationshipEdgeRecord
                {
                    FromNpcId = "player",
                    ToNpcId = "Wizard",
                    RelationType = "friend",
                },
            },
        }));

        store.Reset();

        Assert.Empty(store.State.Relationships);
        Assert.Empty(store.LastWarnings);
    }

    [Fact]
    public void Group_invitation_status_can_be_updated_without_touching_other_story_state()
    {
        var invitation = new GroupDialogueInvitationRecord
        {
            InvitationId = "invite-1",
            TemplateId = "neutral-public-topic",
            Participants = new[] { "Abigail", "Emily" },
            ParticipantDisplayNames = new[] { "Abigail", "Emily" },
            Title = "公共话题",
            Topic = "最近的公共小事",
            Guidance = "只作为讨论方向。",
            CreatedOn = "Spring 20",
            ExpiresOn = "Spring 27",
            CreatedTotalDays = 20,
            ExpiresTotalDays = 27,
            Source = "periodic",
            Status = GroupInvitationStatus.Unread,
        };
        var store = new StoryStateStore();
        store.Replace(StoryStateEnvelope.Empty with
        {
            GroupDialogueInvitations = new[] { invitation },
        });

        Assert.True(store.TrySetGroupInvitationStatus(
            "invite-1",
            GroupInvitationStatus.Deferred));

        Assert.Equal(
            GroupInvitationStatus.Deferred,
            Assert.Single(store.State.GroupDialogueInvitations).Status);
    }

    [Fact]
    public void RecordConversation_updates_the_loaded_state_for_the_next_save()
    {
        var store = new StoryStateStore();
        store.RecordConversation(
            new NpcGameState
            {
                NpcId = "Sophia",
                Date = "Spring 14",
                FriendshipHearts = 6,
                Relationship = "friend",
            },
            "葡萄园最近怎么样？",
            "最近还不错。",
            usedFallback: false);

        Assert.Single(store.State.Memories);
        Assert.Single(store.State.InteractionProgresses);
        Assert.Equal("Spring 14", store.State.Memories[0].GameDate);
    }

    [Fact]
    public void RecentMemoryFacts_returns_only_the_current_npc_and_caps_results()
    {
        var store = new StoryStateStore();
        var state = StoryStateEnvelope.Empty with
        {
            Memories = Enumerable.Range(1, 8)
                .Select(index => new MemoryRecord
                {
                    MemoryId = $"sophia-{index}",
                    OwnerNpcId = "Sophia",
                    Content = $"Sophia 记忆 {index}",
                    Source = MemorySource.PlayerChat,
                    Confidence = 0.8,
                    GameDate = $"Spring {index}",
                    Participants = new[] { "Sophia", "player" },
                    KnowledgeScope = MemoryKnowledgeScope.Participants,
                    KnownBy = new[] { "Sophia", "player" },
                })
                .Append(new MemoryRecord
                {
                    MemoryId = "wizard-1",
                    OwnerNpcId = "Wizard",
                    Content = "不应泄露给 Sophia",
                    Source = MemorySource.PlayerChat,
                    Confidence = 0.8,
                    GameDate = "Spring 9",
                    Participants = new[] { "Wizard", "player" },
                    KnowledgeScope = MemoryKnowledgeScope.Participants,
                    KnownBy = new[] { "Wizard", "player" },
                })
                .ToArray(),
        };
        store.Replace(state);

        var facts = store.RecentMemoryFacts("Sophia", limit: 6);

        Assert.Equal(6, facts.Count);
        Assert.All(facts, fact => Assert.Contains("Sophia", fact));
        Assert.DoesNotContain(facts, fact => fact.Contains("Wizard"));
    }

    [Fact]
    public void Group_highlights_reach_the_npcs_own_recent_facts()
    {
        var store = new StoryStateStore();

        // 群聊里玩家当着 Abigail 与 Emily 说的约定：在场两人各记一条。
        store.RecordMemoryHighlight("Abigail", "玩家下周要交一份报告。", "Spring 14");
        store.RecordMemoryHighlight("Emily", "玩家下周要交一份报告。", "Spring 14");
        store.RecordMemoryHighlight("Abigail", "玩家答应周末去葡萄园。", "Spring 14");

        var abigail = store.RecentMemoryFacts("Abigail");
        var emily = store.RecentMemoryFacts("Emily");
        var sebastian = store.RecentMemoryFacts("Sebastian");

        // 群里说过的话要能在私聊里被想起来，最近写入的排在最前。
        Assert.Equal(2, abigail.Count);
        Assert.Contains("葡萄园", abigail[0]);
        Assert.Contains("记忆（Spring 14）", abigail[0]);
        Assert.Single(emily);
        Assert.Contains("报告", emily[0]);
        // 不在场的人不该知道群里说过什么。
        Assert.Empty(sebastian);
    }

    [Fact]
    public void RelationshipSnapshotFor_returns_only_the_current_npcs_view()
    {
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
                    OwnerNpcId = "Sebastian",
                    SubjectNpcId = "Alex",
                    RelationType = "married",
                    Visibility = "unknown",
                    Source = "none",
                },
            },
        });

        var snapshot = store.RelationshipSnapshotFor("Sophia");

        Assert.Contains(snapshot.Views, view => view.OwnerNpcId == "Sophia");
        Assert.DoesNotContain(snapshot.Views, view => view.OwnerNpcId == "Sebastian");
        Assert.DoesNotContain(
            snapshot.ObjectiveRelationships,
            relation => relation.ToNpcId == "Alex" && relation.RelationType == "married");
    }

    [Fact]
    public void RelationshipSnapshotFor_returns_only_active_open_loops_for_that_npc()
    {
        var store = new StoryStateStore();
        store.Replace(StoryStateEnvelope.Empty with
        {
            OpenLoops = new[]
            {
                ValidOpenLoop("Wizard", "wizard:one", "open"),
                ValidOpenLoop("Sophia", "sophia:one", "open"),
                ValidOpenLoop("Wizard", "wizard:progress", "in_progress"),
                ValidOpenLoop("Wizard", "wizard:done", "resolved"),
            },
        });

        var snapshot = store.RelationshipSnapshotFor("Wizard");

        Assert.Equal(
            new[] { "wizard:one", "wizard:progress" },
            snapshot.OpenLoops.Select(loop => loop.LoopId));
    }

    [Fact]
    public void ApplyOpenLoopSignal_requires_remote_open_and_face_to_face_resolution()
    {
        var store = new StoryStateStore();
        var state = new NpcGameState { NpcId = "Wizard", Date = "Spring 14" };

        store.ApplyOpenLoopSignal(state, ConversationChannel.Remote, new OpenLoopSignal
        {
            Action = "open",
            LoopId = "wizard:rune:Spring-14",
            Topic = "rune_review",
            ShortSummary = "线上留下了核对符文数据的话题",
        });
        Assert.Equal("open", Assert.Single(store.State.OpenLoops).Status);

        store.ApplyOpenLoopSignal(state, ConversationChannel.FaceToFace, new OpenLoopSignal
        {
            Action = "continue",
            LoopId = "wizard:rune:Spring-14",
        });
        Assert.Equal("in_progress", Assert.Single(store.State.OpenLoops).Status);

        store.ApplyOpenLoopSignal(state, ConversationChannel.FaceToFace, new OpenLoopSignal
        {
            Action = "resolve",
            LoopId = "wizard:rune:Spring-14",
        });

        Assert.Equal("resolved", Assert.Single(store.State.OpenLoops).Status);
    }

    [Fact]
    public void ApplyOpenLoopSignal_does_not_cross_npc_or_reopen_resolved_loop()
    {
        var store = new StoryStateStore();
        var wizard = new NpcGameState { NpcId = "Wizard", Date = "Spring 14" };
        store.ApplyOpenLoopSignal(wizard, ConversationChannel.Remote, new OpenLoopSignal
        {
            Action = "open", LoopId = "wizard:rune", Topic = "rune_review", ShortSummary = "核对符文",
        });

        store.ApplyOpenLoopSignal(
            new NpcGameState { NpcId = "Sophia", Date = "Spring 14" },
            ConversationChannel.FaceToFace,
            new OpenLoopSignal { Action = "resolve", LoopId = "wizard:rune" });
        Assert.Equal("open", Assert.Single(store.State.OpenLoops).Status);

        store.ApplyOpenLoopSignal(wizard, ConversationChannel.FaceToFace,
            new OpenLoopSignal { Action = "resolve", LoopId = "wizard:rune" });
        store.ApplyOpenLoopSignal(wizard, ConversationChannel.Remote,
            new OpenLoopSignal { Action = "open", LoopId = "wizard:rune", Topic = "new", ShortSummary = "不应重开" });

        Assert.Equal("resolved", Assert.Single(store.State.OpenLoops).Status);
    }

    [Fact]
    public void ApplyOpenLoopSignal_does_not_duplicate_a_loop_id_for_another_npc()
    {
        var store = new StoryStateStore();
        store.ApplyOpenLoopSignal(
            new NpcGameState { NpcId = "Wizard", Date = "Spring 14" },
            ConversationChannel.Remote,
            new OpenLoopSignal
            {
                Action = "open",
                LoopId = "shared-loop-id",
                Topic = "rune_review",
                ShortSummary = "核对符文",
            });

        store.ApplyOpenLoopSignal(
            new NpcGameState { NpcId = "Sophia", Date = "Spring 14" },
            ConversationChannel.Remote,
            new OpenLoopSignal
            {
                Action = "open",
                LoopId = "shared-loop-id",
                Topic = "private_topic",
                ShortSummary = "不应复制",
            });

        var loop = Assert.Single(store.State.OpenLoops);
        Assert.Equal("Wizard", loop.NpcId);
        Assert.Equal("rune_review", loop.Topic);
    }

    private static OpenLoopRecord ValidOpenLoop(string npcId, string loopId, string status) => new()
    {
        LoopId = loopId,
        NpcId = npcId,
        Topic = "rune_review",
        OriginChannel = "remote",
        NextChannel = "face_to_face",
        Status = status,
        ShortSummary = "核对符文",
        CreatedOn = "Spring 14",
    };

    [Fact]
    public void ResolveMediation_and_jealousy_updates_are_scoped_to_one_npc()
    {
        var store = new StoryStateStore();
        store.Replace(StoryStateEnvelope.Empty with
        {
            Mediations = new[]
            {
                new RelationshipMediationRecord { NpcId = "Alex", Status = "active" },
            },
            Jealousies = new[]
            {
                new RelationshipJealousyRecord
                {
                    NpcId = "Sophia",
                    Active = true,
                    Trigger = "time",
                    Intensity = "light",
                    Need = "固定的相处时间",
                },
            },
        });

        store.ResolveMediation("Alex", "accepted");
        store.RecordJealousy("Sophia", "companionship", "moderate", "安排陪伴");

        Assert.Equal("accepted", Assert.Single(store.State.Mediations).Outcome);
        Assert.Equal("companionship", Assert.Single(store.State.Jealousies).Trigger);
        Assert.Equal("resolved", Assert.Single(store.State.Mediations).Status);
    }
}
