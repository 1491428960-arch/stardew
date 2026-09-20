using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class InteractionProgressRulesTests
{
    [Fact]
    public void Ordinary_stage_requires_four_effective_sessions()
    {
        var progress = InteractionProgress.Create("Sophia", "朋友");

        Assert.Equal(4, progress.RequiredSessions);
        Assert.Equal(0, progress.EffectiveSessions);
    }

    [Fact]
    public void Major_stage_requires_five_effective_sessions()
    {
        var progress = InteractionProgress.Create("Sophia", "恋爱");

        Assert.Equal(5, progress.RequiredSessions);
    }

    /// <summary>
    /// 等价性证据（审计 #43）：重大阶段白名单从 <see cref="InteractionProgress"/> 下沉到
    /// <see cref="RelationshipStageRules"/> 并去掉死条目之后，**阶段名域内**每个名字的
    /// RequiredSessions 必须与改前一致（恋爱/婚后/育儿 = 5，其余 = 4）。
    /// </summary>
    [Theory]
    [InlineData("恋爱", 5)]
    [InlineData("婚后", 5)]
    [InlineData("育儿", 5)]
    [InlineData("亲近", 4)]
    [InlineData("朋友", 4)]
    [InlineData("熟悉", 4)]
    [InlineData("初识", 4)]
    public void Required_sessions_are_unchanged_for_every_stage_name_in_the_domain(
        string stage,
        int expectedSessions)
    {
        Assert.Equal(expectedSessions, InteractionProgress.Create("Sophia", stage).RequiredSessions);
        Assert.Equal(
            expectedSessions == 5,
            RelationshipStageRules.IsMajorStage(stage));
    }

    [Fact]
    public void Effective_session_counts_once_and_records_date_and_fingerprint()
    {
        var progress = InteractionProgress.Create("Sophia", "朋友");

        var updated = InteractionProgressRules.Record(
            progress,
            Attempt("Spring 14", "葡萄园最近怎么样？", "最近的葡萄长得不错。"));

        Assert.Equal(1, updated.EffectiveSessions);
        Assert.Equal("Spring 14", updated.LastCountedGameDate);
        Assert.False(string.IsNullOrWhiteSpace(updated.LastInteractionFingerprint));
    }

    [Fact]
    public void Fallback_empty_duplicate_and_second_session_same_day_do_not_count()
    {
        var progress = InteractionProgress.Create("Sophia", "朋友");

        progress = InteractionProgressRules.Record(
            progress,
            Attempt("Spring 14", "葡萄园最近怎么样？", "最近的葡萄长得不错。"));
        progress = InteractionProgressRules.Record(
            progress,
            Attempt("Spring 14", "你好", "备用回复", usedFallback: true));
        progress = InteractionProgressRules.Record(
            progress,
            Attempt("Spring 14", "", "这不应该计数。"));
        progress = InteractionProgressRules.Record(
            progress,
            Attempt("Spring 14", "葡萄园最近怎么样？", "重复消息不应再次计数。"));

        Assert.Equal(1, progress.EffectiveSessions);
    }

    [Fact]
    public void New_game_day_allows_one_more_effective_session()
    {
        var progress = InteractionProgress.Create("Sophia", "朋友");

        progress = InteractionProgressRules.Record(
            progress,
            Attempt("Spring 14", "葡萄园最近怎么样？", "最近的葡萄长得不错。"));
        progress = InteractionProgressRules.Record(
            progress,
            Attempt("Spring 15", "今天有下雨吗？", "早上刚下过。"));

        Assert.Equal(2, progress.EffectiveSessions);
        Assert.Equal("Spring 15", progress.LastCountedGameDate);
    }

    private static ConversationAttempt Attempt(
        string gameDate,
        string playerMessage,
        string npcReply,
        bool usedFallback = false) =>
        new(gameDate, playerMessage, npcReply, usedFallback);
}
