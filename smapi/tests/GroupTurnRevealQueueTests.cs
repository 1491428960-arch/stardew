using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 群聊 NPC 回复的**逐条揭示**时序（2026-09-21 用户口径：「NPC 回复不要同时蹦几条，
/// 要一条一条出现，稍微有点间隔」）。
///
/// 菜单要 Game1 才能构造，所以时序本身下沉到 <see cref="GroupTurnRevealQueue"/>；
/// 这里钉住三件事：**第一条不等**、**之后按间隔**、**任何退出路径都不丢**。
/// </summary>
public sealed class GroupTurnRevealQueueTests
{
    private static BridgeGroupTurn Turn(string npcId, string content) =>
        new() { SpeakerNpcId = npcId, Content = content };

    private static IReadOnlyList<string> Speakers(IReadOnlyList<BridgeGroupTurn> turns) =>
        turns.Select(turn => turn.SpeakerNpcId).ToArray();

    [Fact]
    public void The_first_turn_is_revealed_on_the_first_frame()
    {
        // 玩家已经等了整整一次请求（通常 5～15 秒），响应回来第一条就该出现——
        // 若第一条也要等半秒，等于把「慢」再放大一次。
        var queue = new GroupTurnRevealQueue();
        queue.Enqueue(new[] { Turn("Abigail", "第一句"), Turn("Emily", "第二句") });

        var revealed = queue.Advance(deltaSeconds: 0d, GroupTranscriptRules.TurnRevealIntervalSeconds);

        Assert.Single(revealed);
        Assert.Equal("Abigail", revealed[0].SpeakerNpcId);
        Assert.Equal(1, queue.PendingCount);
    }

    [Fact]
    public void Remaining_turns_wait_for_the_interval_and_then_come_one_by_one()
    {
        var queue = new GroupTurnRevealQueue();
        queue.Enqueue(new[]
        {
            Turn("Abigail", "一"),
            Turn("Emily", "二"),
            Turn("Abigail", "三"),
        });

        // 第一帧：第一条。
        Assert.Single(queue.Advance(0d, GroupTranscriptRules.TurnRevealIntervalSeconds));
        // 间隔没到：一条都不出。
        Assert.Empty(queue.Advance(0.2d, GroupTranscriptRules.TurnRevealIntervalSeconds));
        Assert.Equal(2, queue.PendingCount);
        // 间隔到了：恰好再出一条，**不是两条一起**。
        var second = queue.Advance(0.3d, GroupTranscriptRules.TurnRevealIntervalSeconds);
        Assert.Single(second);
        Assert.Equal("Emily", second[0].SpeakerNpcId);
        // 再来一个间隔：最后一条。
        var third = queue.Advance(0.5d, GroupTranscriptRules.TurnRevealIntervalSeconds);
        Assert.Single(third);
        Assert.Equal(0, queue.PendingCount);
        Assert.False(queue.HasPending);
    }

    /// <summary>
    /// 掉帧／暂停后一次性补上：宁可快一点，也不要把播放拖成「卡了」。
    /// 累积的时间按间隔整除，一次可以出多条。
    /// </summary>
    [Fact]
    public void A_long_frame_catches_up_with_the_elapsed_time()
    {
        var queue = new GroupTurnRevealQueue();
        queue.Enqueue(new[]
        {
            Turn("Abigail", "一"),
            Turn("Emily", "二"),
            Turn("Abigail", "三"),
        });

        queue.Advance(0d, GroupTranscriptRules.TurnRevealIntervalSeconds);
        // 卡了 1.6 秒：第一条之后的 1.6 秒够再走三条（1.6 / 0.5 = 3）。
        var caughtUp = queue.Advance(1.6d, GroupTranscriptRules.TurnRevealIntervalSeconds);

        Assert.Equal(2, caughtUp.Count);
        Assert.Equal(0, queue.PendingCount);
    }

    [Theory]
    [InlineData(0d)]
    [InlineData(-1d)]
    [InlineData(double.NaN)]
    public void A_useless_frame_never_reveals_anything_extra(double delta)
    {
        var queue = new GroupTurnRevealQueue();
        queue.Enqueue(new[] { Turn("Abigail", "一"), Turn("Emily", "二") });

        queue.Advance(0d, GroupTranscriptRules.TurnRevealIntervalSeconds);
        Assert.Empty(queue.Advance(delta, GroupTranscriptRules.TurnRevealIntervalSeconds));
        Assert.Equal(1, queue.PendingCount);
    }

    [Fact]
    public void Skipping_hands_over_everything_at_once()
    {
        // 玩家点一下消息区或按空格 =「剩下的都放出来」。
        var queue = new GroupTurnRevealQueue();
        queue.Enqueue(new[]
        {
            Turn("Abigail", "一"),
            Turn("Emily", "二"),
            Turn("Abigail", "三"),
        });

        queue.Advance(0d, GroupTranscriptRules.TurnRevealIntervalSeconds);
        queue.SkipAll();
        var rest = queue.Advance(0d, GroupTranscriptRules.TurnRevealIntervalSeconds);

        Assert.Equal(2, rest.Count);
        Assert.Equal(new[] { "Emily", "Abigail" }, Speakers(rest));
        Assert.False(queue.HasPending);
    }

    [Fact]
    public void Skipping_an_empty_queue_is_harmless()
    {
        var queue = new GroupTurnRevealQueue();
        queue.SkipAll();

        Assert.Empty(queue.Advance(1d, GroupTranscriptRules.TurnRevealIntervalSeconds));
    }

    /// <summary>
    /// **最要紧的那条**：中途退出、切场景、存档时把没播完的一次交给面板。
    /// 丢了它们，「面板发言数 == 存档场次条数」当场不成立。
    /// </summary>
    [Fact]
    public void Draining_never_loses_a_turn()
    {
        var queue = new GroupTurnRevealQueue();
        queue.Enqueue(new[]
        {
            Turn("Abigail", "一"),
            Turn("Emily", "二"),
            Turn("Abigail", "三"),
        });

        var first = queue.Advance(0d, GroupTranscriptRules.TurnRevealIntervalSeconds);
        var rest = queue.Drain();

        Assert.Single(first);
        Assert.Equal(2, rest.Count);
        Assert.Equal(
            new[] { "Abigail", "Emily", "Abigail" },
            Speakers(first.Concat(rest).ToArray()));
        Assert.False(queue.HasPending);
        // 排空之后再排空一次是安全的（退出路径可能被走两遍：Close + cleanupBeforeExit）。
        Assert.Empty(queue.Drain());
    }

    [Fact]
    public void Draining_a_queue_that_never_played_still_yields_everything()
    {
        // 玩家在响应刚回来的那一帧就按了 Esc：一条都还没播。
        var queue = new GroupTurnRevealQueue();
        queue.Enqueue(new[] { Turn("Abigail", "一"), Turn("Emily", "二") });

        Assert.Equal(2, queue.Drain().Count);
    }

    [Fact]
    public void An_empty_or_null_batch_changes_nothing()
    {
        var queue = new GroupTurnRevealQueue();
        queue.Enqueue(null);
        queue.Enqueue(Array.Empty<BridgeGroupTurn>());

        Assert.False(queue.HasPending);
        Assert.Empty(queue.Advance(0d, GroupTranscriptRules.TurnRevealIntervalSeconds));
        Assert.Empty(queue.Drain());
    }

    [Fact]
    public void A_second_batch_queues_behind_the_first_without_resetting_the_pace()
    {
        // 上一批还没播完就又来一批（快速连发）：两批按顺序接上，
        // 不能因为新批次入队就把等待清零——那会让两批的第一条挤在一起。
        var queue = new GroupTurnRevealQueue();
        queue.Enqueue(new[] { Turn("Abigail", "一"), Turn("Emily", "二") });
        queue.Advance(0d, GroupTranscriptRules.TurnRevealIntervalSeconds);

        queue.Enqueue(new[] { Turn("Lewis", "三") });

        Assert.Empty(queue.Advance(0.2d, GroupTranscriptRules.TurnRevealIntervalSeconds));
        Assert.Single(queue.Advance(0.3d, GroupTranscriptRules.TurnRevealIntervalSeconds));
    }

    [Fact]
    public void A_non_positive_interval_still_terminates_and_drops_nothing()
    {
        // 间隔是调用方传进来的（视觉测试与将来的配置项都会传），
        // 传 0 或负数时不能变成死循环，也不能把回合丢掉。
        var queue = new GroupTurnRevealQueue();
        queue.Enqueue(new[] { Turn("Abigail", "一"), Turn("Emily", "二") });

        var revealed = queue.Advance(1d, intervalSeconds: 0d);

        Assert.Equal(2, revealed.Count);
        Assert.False(queue.HasPending);
    }
}
