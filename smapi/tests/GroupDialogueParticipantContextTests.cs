using System;
using System.Linq;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 群聊「每人一份」私有上下文（2026-10-05）—— C# 协议层。
///
/// 背景：`GroupDialogueMenu` 从 2026-09-22 起就给请求顶层的
/// `recentFacts` / `relationshipWorld` 传 null，因为场景卡里那两个槽位**没有归属**，
/// 多人场里放谁的都会让另外两人读到不属于自己的私事（越界知识，比空更糟）。
/// 改法是把槽位下移到参与者身上，由 Bridge 渲染成带归属的卡。
/// </summary>
public sealed class GroupDialogueParticipantContextTests
{
    private static RelationshipWorldSnapshot Snapshot(string viewer)
    {
        return new RelationshipWorldSnapshot(
            viewer,
            Array.Empty<RelationshipEdgeRecord>(),
            Array.Empty<RelationshipViewRecord>(),
            null,
            null);
    }

    [Fact]
    public void Participant_CarriesItsOwnRelationshipWorldAndFacts()
    {
        var snapshot = Snapshot("Abigail");

        var participant = new GroupDialogueParticipant(
            "Abigail",
            "Abigail",
            null,
            snapshot,
            new[] { "玩家上周说要去矿洞" });

        Assert.Same(snapshot, participant.RelationshipWorld);
        Assert.Equal(new[] { "玩家上周说要去矿洞" }, participant.RecentFacts);
    }

    [Fact]
    public void Participant_DefaultsToNoPrivateContext()
    {
        var participant = new GroupDialogueParticipant("Abigail", "Abigail");

        Assert.Null(participant.RelationshipWorld);
        Assert.Null(participant.RecentFacts);
    }

    [Fact]
    public void Request_KeepsTopLevelContextUnattributed()
    {
        // 顶层字段没有归属，必须保持 null：私有上下文只在 participants 里，
        // 一人一份。这条断言是「别再顺手把快照塞回顶层」的契约锚点。
        var request = new GroupDialogueRequest(
            "你们谁更喜欢夜市？",
            new[]
            {
                new GroupDialogueParticipant(
                    "Abigail",
                    "Abigail",
                    null,
                    Snapshot("Abigail"),
                    new[] { "玩家上周说要去矿洞" }),
                new GroupDialogueParticipant("Emily", "Emily"),
            },
            null,
            null,
            Array.Empty<GroupDialogueHistoryEntry>(),
            "Abigail");

        Assert.Null(request.RelationshipWorld);
        Assert.Null(request.RecentFacts);
        Assert.NotNull(request.Participants[0].RelationshipWorld);
        Assert.Null(request.Participants[1].RelationshipWorld);
    }
}
