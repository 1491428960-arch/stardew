using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class RelationshipRepairRulesTests
{
    [Fact]
    public void Ordinary_reassurance_does_not_count_as_relationship_repair()
    {
        var result = RelationshipRepairRules.IsValuableRelationshipRepair(
            playerMessage: "今天辛苦了，别想太多。",
            npcReply: "别难过，我会一直陪着你。",
            relationshipWorld: Snapshot(
                jealousy: new RelationshipJealousyRecord
                {
                    NpcId = "Sophia",
                    Active = true,
                    Trigger = "companionship",
                    Intensity = "light",
                }));

        Assert.False(result);
    }

    [Fact]
    public void Acknowledgement_and_explanation_of_active_jealousy_counts_as_repair()
    {
        var result = RelationshipRepairRules.IsValuableRelationshipRepair(
            playerMessage: "我知道你因为我同时和别人交往而吃醋，我们把话说开吧。",
            npcReply: "我承认这让你没有安全感。事情是我没有把自己的感受说清楚，我愿意解释，也会尊重你的选择。",
            relationshipWorld: Snapshot(
                jealousy: new RelationshipJealousyRecord
                {
                    NpcId = "Sophia",
                    Active = true,
                    Trigger = "comparison",
                    Intensity = "moderate",
                }));

        Assert.True(result);
    }

    [Fact]
    public void Giving_space_after_an_active_mediation_counts_as_repair()
    {
        var result = RelationshipRepairRules.IsValuableRelationshipRepair(
            playerMessage: "我想把这个误会说开。",
            npcReply: "我不该让你一个人猜，我会把事情解释清楚。你不必现在回答，我会给你空间。",
            relationshipWorld: Snapshot(
                mediation: new RelationshipMediationRecord
                {
                    NpcId = "Sophia",
                    Status = "active",
                }));

        Assert.True(result);
    }

    [Fact]
    public void Conflict_without_a_repair_does_not_count()
    {
        var result = RelationshipRepairRules.IsValuableRelationshipRepair(
            playerMessage: "你是不是因为我和别人交往而不安？",
            npcReply: "嗯，我有点难受，不过我们以后再说。",
            relationshipWorld: Snapshot(
                jealousy: new RelationshipJealousyRecord
                {
                    NpcId = "Sophia",
                    Active = true,
                    Trigger = "affection_imbalance",
                    Intensity = "moderate",
                }));

        Assert.False(result);
    }

    [Fact]
    public void Explicit_repair_can_count_when_the_conflict_is_new()
    {
        var result = RelationshipRepairRules.IsValuableRelationshipRepair(
            playerMessage: "我刚才失约让你难过，对不起。",
            npcReply: "我承认是我失约，我会说到做到，不再让你一个人猜。",
            relationshipWorld: Snapshot());

        Assert.True(result);
    }

    [Fact]
    public void Affectionate_words_alone_do_not_count_without_a_relationship_issue()
    {
        var result = RelationshipRepairRules.IsValuableRelationshipRepair(
            playerMessage: "我想你了。",
            npcReply: "我也想你，你对我很重要。",
            relationshipWorld: Snapshot());

        Assert.False(result);
    }

    [Fact]
    public void Resolved_relationship_issue_does_not_make_an_ordinary_chat_valuable()
    {
        var result = RelationshipRepairRules.IsValuableRelationshipRepair(
            playerMessage: "今天的天气真好。",
            npcReply: "是啊，和你聊天总让我心情很好。",
            relationshipWorld: Snapshot(
                mediation: new RelationshipMediationRecord
                {
                    NpcId = "Sophia",
                    Status = "resolved",
                    Outcome = "accepted",
                },
                jealousy: new RelationshipJealousyRecord
                {
                    NpcId = "Sophia",
                    Active = false,
                    LastResolvedTrigger = "comparison",
                }));

        Assert.False(result);
    }

    [Fact]
    public void A_reply_about_scheduling_does_not_unlock_a_kiss()
    {
        var result = RelationshipRepairRules.IsValuableRelationshipRepair(
            playerMessage: "我因为你总是把我和别人比较而难受。",
            npcReply: "我承认这让你很难受，我们明天安排时间轮流陪伴，把这件事解决掉。",
            relationshipWorld: Snapshot(
                jealousy: new RelationshipJealousyRecord
                {
                    NpcId = "Sophia",
                    Active = true,
                    Trigger = "comparison",
                    Intensity = "moderate",
                }));

        Assert.False(result);
    }

    [Fact]
    public void Fallback_reply_never_counts_as_relationship_repair()
    {
        var result = ChatSessionRules.IsValuableRelationshipRepair(
            new ConversationTurnResult(
                new BridgeDialogueResponse
                {
                    Reply = "我承认这让你难过，我会解释清楚。",
                    Fallback = true,
                },
                Recorded: false),
            playerMessage: "我们把这件事说开吧。",
            relationshipWorld: Snapshot(
                mediation: new RelationshipMediationRecord
                {
                    NpcId = "Sophia",
                    Status = "active",
                }));

        Assert.False(result);
    }

    [Fact]
    public void An_unrecorded_response_cannot_unlock_a_kiss_even_with_repair_words()
    {
        var result = ChatSessionRules.IsValuableRelationshipRepair(
            new ConversationTurnResult(
                new BridgeDialogueResponse
                {
                    Reply = "我承认这让你难过，我会解释清楚。",
                },
                Recorded: false),
            playerMessage: "我们把这件事说开吧。",
            relationshipWorld: Snapshot(
                mediation: new RelationshipMediationRecord
                {
                    NpcId = "Sophia",
                    Status = "active",
                }));

        Assert.False(result);
    }

    private static RelationshipWorldSnapshot Snapshot(
        RelationshipMediationRecord? mediation = null,
        RelationshipJealousyRecord? jealousy = null)
    {
        return new RelationshipWorldSnapshot(
            ViewerNpcId: "Sophia",
            ObjectiveRelationships: Array.Empty<RelationshipEdgeRecord>(),
            Views: Array.Empty<RelationshipViewRecord>(),
            Mediation: mediation,
            Jealousy: jealousy);
    }
}
