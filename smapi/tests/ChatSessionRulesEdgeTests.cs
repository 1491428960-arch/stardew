using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// <c>ChatSessionRules</c> 的两道门槛：一轮回复算不算“有效”，
/// 以及它能不能解锁亲吻（<c>ChatInputMenu</c> 只在这一步置 <c>hasValuableRelationshipRepair</c>）。
/// 已有 <c>ChatSessionRulesTests</c> 覆盖了 fallback 与空白回复，
/// <c>RelationshipRepairRulesTests</c> 覆盖了修复标记本身；
/// 这里补上它没碰的：两处 null 校验、桥接返回 <c>"reply": null</c> 时的兜底、
/// <c>Recorded</c> 与 fallback 的叠加门槛，以及新冲突下的**正面路径**
/// （此前 <c>ChatSessionRules.IsValuableRelationshipRepair</c> 没有任何返回 true 的用例）。
/// </summary>
public sealed class ChatSessionRulesEdgeTests
{
    private const string ConflictMessage = "我刚才失约让你难过，对不起。";

    private const string RepairReply = "我承认是我失约，我会说到做到，不再让你一个人猜。";

    [Fact]
    public void IsEffectiveResponse_rejects_a_null_result()
    {
        Assert.Throws<ArgumentNullException>(
            () => ChatSessionRules.IsEffectiveResponse(null!));
    }

    [Fact]
    public void IsValuableRelationshipRepair_rejects_a_null_result()
    {
        Assert.Throws<ArgumentNullException>(
            () => ChatSessionRules.IsValuableRelationshipRepair(
                null!,
                playerMessage: ConflictMessage,
                relationshipWorld: null));
    }

    [Fact]
    public void A_null_reply_from_the_bridge_does_not_count_as_effective()
    {
        // 桥接返回 {"reply": null} 时反序列化会把 Reply 置为 null，
        // 这条路径必须在“有效回复”判定里被挡掉，否则会触发一次空内容对话。
        var result = ChatSessionRules.IsEffectiveResponse(
            new ConversationTurnResult(
                new BridgeDialogueResponse { Reply = null!, Provider = "cloud" },
                Recorded: true));

        Assert.False(result);
    }

    [Fact]
    public void A_recorded_repair_reply_is_valuable_when_the_conflict_is_in_this_turn()
    {
        // 正面路径：本轮消息里就有冲突词、回复里有承认与修复承诺、且回复确实被记录。
        var result = ChatSessionRules.IsValuableRelationshipRepair(
            new ConversationTurnResult(
                new BridgeDialogueResponse { Reply = RepairReply },
                Recorded: true),
            playerMessage: ConflictMessage,
            relationshipWorld: null);

        Assert.True(result);
    }

    [Fact]
    public void A_recorded_but_fallback_reply_is_not_valuable()
    {
        // 与上一条只差 Fallback：即使 Recorded=true、文本里全是修复词，
        // 兜底回复也不能解锁亲吻（那句话不是 NPC 真的说的）。
        var result = ChatSessionRules.IsValuableRelationshipRepair(
            new ConversationTurnResult(
                new BridgeDialogueResponse { Reply = RepairReply, Fallback = true },
                Recorded: true),
            playerMessage: ConflictMessage,
            relationshipWorld: null);

        Assert.False(result);
    }

    [Fact]
    public void A_missing_player_message_never_unlocks_a_repair()
    {
        // pendingPlayerMessage 可能为空（例如玩家在收到回复前关掉输入），
        // 此时不能仅凭 NPC 回复里的修复词解锁亲吻。
        var result = ChatSessionRules.IsValuableRelationshipRepair(
            new ConversationTurnResult(
                new BridgeDialogueResponse { Reply = RepairReply },
                Recorded: true),
            playerMessage: null,
            relationshipWorld: null);

        Assert.False(result);
    }
}
