using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class TaskResultPumpTests
{
    [Fact]
    public void Does_not_take_an_incomplete_task_then_takes_result_after_completion()
    {
        var completion = new TaskCompletionSource<string>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        var pump = new TaskResultPump<string>();
        pump.Start(completion.Task);

        Assert.True(pump.HasPending);
        Assert.False(pump.TryTakeCompleted(out _, out _));

        completion.SetResult("完成");

        Assert.True(pump.TryTakeCompleted(out var result, out var error));
        Assert.Equal("完成", result);
        Assert.Null(error);
        Assert.False(pump.HasPending);
    }

    [Fact]
    public void Takes_task_exception_without_wrapping_it()
    {
        var expected = new InvalidOperationException("失败");
        var pump = new TaskResultPump<string>();
        pump.Start(Task.FromException<string>(expected));

        Assert.True(pump.TryTakeCompleted(out _, out var error));
        Assert.Same(expected, error);
        Assert.False(pump.HasPending);
    }
}
