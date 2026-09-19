using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// <c>TaskResultPump</c> 的边界。它是“后台任务 → 游戏主线程轮询”的唯一通道
/// （刻意不依赖 continuation 能否回到 SMAPI 的同步上下文），出问题会直接卡住对话流程。
///
/// 原有的两条测试只覆盖“任务完成”和“任务抛异常”两种正常结局，
/// 这里补上并发契约：重复 Start、无任务时取、Clear 丢弃、取消、以及只能取一次。
/// </summary>
public sealed class TaskResultPumpEdgeTests
{
    [Fact]
    public void Start_rejects_a_second_task_while_one_is_pending()
    {
        var pump = new TaskResultPump<string>();
        pump.Start(new TaskCompletionSource<string>().Task);

        Assert.Throws<InvalidOperationException>(
            () => pump.Start(Task.FromResult("另一个")));
        // 抛错后原有的等待任务不受影响
        Assert.True(pump.HasPending);
    }

    [Fact]
    public void Start_rejects_null()
    {
        var pump = new TaskResultPump<string>();

        Assert.Throws<ArgumentNullException>(() => pump.Start(null!));
        Assert.False(pump.HasPending);
    }

    [Fact]
    public void Taking_without_a_pending_task_reports_nothing_and_stays_empty()
    {
        var pump = new TaskResultPump<int>();

        Assert.False(pump.HasPending);
        Assert.False(pump.TryTakeCompleted(out var result, out var error));
        Assert.Equal(0, result);   // 值类型保持 default
        Assert.Null(error);

        // 连续调用不应改变状态
        Assert.False(pump.TryTakeCompleted(out _, out _));
    }

    [Fact]
    public void Clear_drops_the_pending_task_and_allows_a_new_one()
    {
        var abandoned = new TaskCompletionSource<string>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        var pump = new TaskResultPump<string>();
        pump.Start(abandoned.Task);

        pump.Clear();

        Assert.False(pump.HasPending);
        Assert.False(pump.TryTakeCompleted(out _, out _));

        // 清空后必须能开始新任务，否则会一直撞上“已有请求正在等待完成”
        pump.Start(Task.FromResult("新的"));
        Assert.True(pump.TryTakeCompleted(out var result, out var error));
        Assert.Equal("新的", result);
        Assert.Null(error);

        // 被丢弃的旧任务即使随后完成，也不该再被取走
        abandoned.SetResult("旧的");
        Assert.False(pump.TryTakeCompleted(out _, out _));
    }

    [Fact]
    public void Canceled_task_is_reported_as_an_error()
    {
        var pump = new TaskResultPump<string>();
        pump.Start(Task.FromCanceled<string>(new CancellationToken(canceled: true)));

        Assert.True(pump.TryTakeCompleted(out _, out var error));
        Assert.IsAssignableFrom<OperationCanceledException>(error);
        Assert.False(pump.HasPending);
    }

    [Fact]
    public void A_completed_task_can_be_taken_only_once()
    {
        var pump = new TaskResultPump<string>();
        pump.Start(Task.FromResult("结果"));

        Assert.True(pump.TryTakeCompleted(out var first, out var error));
        Assert.Equal("结果", first);
        Assert.Null(error);
        // 取走之后状态必须清空，避免同一结果被反复消费
        Assert.False(pump.HasPending);
        Assert.False(pump.TryTakeCompleted(out _, out _));
    }
}
