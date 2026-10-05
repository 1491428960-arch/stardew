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

    /// <summary>
    /// 回归（2026-10-04）：<c>State.Relationships</c> 此前在生产代码里没有任何写入点，
    /// 于是 <c>PublicEventId</c> 恒为 null，广播循环永不执行。
    /// 玩家在游戏里真实表现就是「两个都跟他结了婚的人，互相不知道对方存在」。
    /// </summary>
    [Fact]
    public void SyncMarriages_broadcasts_each_wedding_to_every_spouse()
    {
        var store = new StoryStateStore();

        var changed = store.SyncMarriages(new[] { "Sophia", "Abigail" }, "fall 12");

        Assert.Equal(2, changed);

        var sophia = store.RelationshipSnapshotFor("Sophia");
        var knownSubjects = sophia.Views
            .Where(view => view.Visibility == "known")
            .Select(view => view.SubjectNpcId)
            .ToArray();
        Assert.Contains("Sophia", knownSubjects);
        Assert.Contains("Abigail", knownSubjects);

        // 对称：阿比盖尔也要看得到索菲亚，否则只是一半的修复。
        Assert.Contains(
            store.RelationshipSnapshotFor("Abigail").Views,
            view => view.SubjectNpcId == "Sophia");

        // 视角仍然只带自己那条客观关系，不泄底表。
        Assert.All(sophia.ObjectiveRelationships, edge => Assert.Equal("Sophia", edge.ToNpcId));
        Assert.All(
            sophia.Views.Where(view => view.RelationType == "married"),
            view => Assert.Equal("wedding", view.Source));
    }

    [Fact]
    public void SyncMarriages_is_idempotent_and_dedups_case_insensitively()
    {
        var store = new StoryStateStore();

        Assert.Equal(2, store.SyncMarriages(new[] { "Sophia", "abigail", "Sophia" }, "fall 12"));
        Assert.Equal(0, store.SyncMarriages(new[] { "SOPHIA", "Abigail" }, "winter 3"));
        Assert.Equal(2, store.State.Relationships.Count);
    }

    [Fact]
    public void SyncMarriages_backfills_public_event_on_an_existing_edge()
    {
        var store = new StoryStateStore();
        store.Replace(new StoryStateEnvelope
        {
            Relationships = new[]
            {
                new RelationshipEdgeRecord
                {
                    FromNpcId = "player",
                    ToNpcId = "Sophia",
                    RelationType = "married",
                },
            },
        });

        Assert.Equal(1, store.SyncMarriages(new[] { "Sophia" }, "fall 12"));

        var edge = Assert.Single(store.State.Relationships);
        Assert.Equal("wedding:Sophia", edge.PublicEventId);
        Assert.Equal("fall 12", edge.PublicOn);
    }

    [Fact]
    public void SyncMarriages_ignores_blank_input_and_keeps_the_first_wedding_date()
    {
        var store = new StoryStateStore();

        Assert.Equal(0, store.SyncMarriages(null, "fall 12"));
        Assert.Equal(0, store.SyncMarriages(new[] { "  " }, "fall 12"));
        Assert.Equal(0, store.SyncMarriages(Array.Empty<string>(), "fall 12"));
        Assert.Empty(store.State.Relationships);

        Assert.Equal(1, store.SyncMarriages(new[] { "Sophia" }, "spring 2"));
        // 已有的婚礼日期是【原件】，后续同步不得覆盖它。
        Assert.Equal(0, store.SyncMarriages(new[] { "Sophia" }, "summer 9"));
        Assert.Equal("spring 2", Assert.Single(store.State.Relationships).PublicOn);
    }

    /// <summary>
    /// 回归（2026-10-04）：<c>not_ready</c> 曾经被一律写成 <c>resolved</c>，
    /// 于是「这轮没谈成」在存档里变成永久结论——NPC 再也没有第二次机会，
    /// 而设计文档要求情绪靠后续相处与履约恢复，不是一次性判定。
    /// 现在它必须停在 <c>active</c>，等下一轮继续谈。
    /// </summary>
    [Fact]
    public void ResolveMediation_keeps_not_ready_as_an_open_round()
    {
        var store = new StoryStateStore();

        store.ResolveMediation("Sophia", "not_ready", "想先一个人待几天");
        var pending = Assert.Single(store.State.Mediations);
        Assert.Equal("active", pending.Status);
        Assert.Equal("not_ready", pending.Outcome);
        Assert.Equal("想先一个人待几天", pending.NextStep);

        // 下一轮谈成了就落终态，而不是并存两条记录。
        store.ResolveMediation("Sophia", "accepted");
        var settled = Assert.Single(store.State.Mediations);
        Assert.Equal("resolved", settled.Status);
        Assert.Equal("accepted", settled.Outcome);
        Assert.Null(settled.NextStep);
    }

    /// <summary>
    /// 产品规则（2026-10-04）：调解只对机制上线时已存在的那批角色成立，
    /// 之后新发生的关系默认已知晓并接受——每个新伴侣都来一遍协商会困扰玩家。
    /// 所以这里直接落终态，并且【只落一次】。
    /// </summary>
    [Fact]
    public void EnsureSpouseAcceptance_writes_once_per_npc_and_never_overwrites()
    {
        var store = new StoryStateStore();

        Assert.Equal(0, store.EnsureSpouseAcceptance(null));
        Assert.Equal(0, store.EnsureSpouseAcceptance(new[] { "  " }));
        Assert.Empty(store.State.Mediations);

        Assert.Equal(2, store.EnsureSpouseAcceptance(new[] { "Sophia", "Abigail" }));
        Assert.All(store.State.Mediations, item =>
        {
            Assert.Equal("resolved", item.Status);
            Assert.Equal("accepted", item.Outcome);
        });

        // 反复读档、每天跨天同步都不得重复写。
        Assert.Equal(0, store.EnsureSpouseAcceptance(new[] { "Sophia", "Abigail" }));
        Assert.Equal(2, store.State.Mediations.Count);

        // 只补新来的那个。
        Assert.Equal(1, store.EnsureSpouseAcceptance(new[] { "Sophia", "Leah" }));
        Assert.Equal(3, store.State.Mediations.Count);
    }

    /// <summary>
    /// 玩家真谈出来的结果比默认值权威：<c>conditional</c> 不能被「默认接受」抹平。
    /// </summary>
    [Fact]
    public void EnsureSpouseAcceptance_does_not_clobber_a_negotiated_outcome()
    {
        var store = new StoryStateStore();
        store.ResolveMediation("Sophia", "conditional", "希望周末留给家里");

        Assert.Equal(0, store.EnsureSpouseAcceptance(new[] { "Sophia" }));

        var mediation = Assert.Single(store.State.Mediations);
        Assert.Equal("conditional", mediation.Outcome);
        Assert.Equal("希望周末留给家里", mediation.NextStep);
    }

    private static InteractionProgress Progress(string npcId, string lastCountedOn) => new()
    {
        NpcId = npcId,
        Stage = "friend",
        LastCountedGameDate = lastCountedOn,
    };

    /// <summary>
    /// 第一道闸门（2026-10-04）：没有对话记录的角色不算「被冷落」。
    /// 少了它，读档后 17 个配偶里没聊过的那些会被一起判定成长期没人陪，
    /// 一觉醒来满镇子集体吃醋。
    /// </summary>
    [Fact]
    public void SettleDailyJealousy_skips_npcs_without_any_conversation_record()
    {
        var store = new StoryStateStore();

        var changes = store.SettleDailyJealousy(
            "fall 12",
            Array.Empty<InteractionProgress>(),
            new[] { "Sophia", "Abigail" });

        Assert.Empty(changes);
        Assert.Empty(store.State.Jealousies);
    }

    /// <summary>
    /// 第二道闸门：已经在吃醋的角色不叠加，否则每天都会重写一遍、强度还会无限刷。
    /// </summary>
    [Fact]
    public void SettleDailyJealousy_escalates_with_the_gap_then_stops_stacking()
    {
        var store = new StoryStateStore();

        // fall 12 = 68，summer 26 = 54，差 14 天 -> light
        var first = store.SettleDailyJealousy(
            "fall 12", new[] { Progress("Sophia", "summer 26") }, new[] { "Sophia" });
        Assert.Single(first);
        Assert.Equal("light", Assert.Single(store.State.Jealousies).Intensity);

        // 隔天仍没见面：保持原样，不重复记录也不升级。
        var second = store.SettleDailyJealousy(
            "fall 13", new[] { Progress("Sophia", "summer 26") }, new[] { "Sophia" });
        Assert.Empty(second);
        Assert.Single(store.State.Jealousies);

        // 另一个人更久没见（summer 12 = 40，差 28）-> 直接 high
        var high = store.SettleDailyJealousy(
            "fall 12", new[] { Progress("Leah", "summer 12") }, new[] { "Leah" });
        Assert.Single(high);
        Assert.Contains(store.State.Jealousies, item =>
            item.NpcId == "Leah" && item.Intensity == "high");
    }

    /// <summary>
    /// 情绪靠「真的聊过」恢复，而不是被强制重置。
    /// </summary>
    [Fact]
    public void SettleDailyJealousy_recovers_when_the_npc_was_talked_to_today()
    {
        var store = new StoryStateStore();
        store.RecordJealousy("Sophia", "companionship", "moderate", "固定的相处时间");

        var changes = store.SettleDailyJealousy(
            "fall 12", new[] { Progress("Sophia", "fall 12") }, new[] { "Sophia" });

        Assert.Single(changes);
        var jealousy = Assert.Single(store.State.Jealousies);
        Assert.False(jealousy.Active);
        Assert.Equal("companionship", jealousy.LastResolvedTrigger);
    }

    /// <summary>
    /// 拖着没兑现的约定比「只是没怎么见面」更具体，优先报 broken_promise。
    /// </summary>
    [Fact]
    public void SettleDailyJealousy_prefers_a_broken_promise_over_absence()
    {
        var store = new StoryStateStore();
        store.Replace(new StoryStateEnvelope
        {
            // ValidOpenLoop 的 CreatedOn 是 Spring 14 = 14。
            OpenLoops = new[] { ValidOpenLoop("Sophia", "loop-1", "open") },
        });

        var changes = store.SettleDailyJealousy(
            "fall 12", new[] { Progress("Sophia", "fall 10") }, new[] { "Sophia" });

        Assert.Single(changes);
        Assert.Equal("broken_promise", Assert.Single(store.State.Jealousies).Trigger);
    }

    /// <summary>
    /// 日期认不出来时一律跳过：宁可这次不算，也不能把坏数据当成「很久没见」。
    /// </summary>
    [Fact]
    public void SettleDailyJealousy_ignores_unparseable_dates()
    {
        var store = new StoryStateStore();

        Assert.Empty(store.SettleDailyJealousy(
            "not a date", new[] { Progress("Sophia", "summer 12") }, new[] { "Sophia" }));

        Assert.Empty(store.SettleDailyJealousy(
            "fall 12", new[] { Progress("Sophia", "someday") }, new[] { "Sophia" }));
        Assert.Empty(store.State.Jealousies);
    }
}
