namespace StardewAI.NPC;

/// <summary>
/// 保存一个后台任务，并只在调用方明确轮询时取出已完成结果。
/// 这让游戏 UI 不依赖异步 continuation 是否能回到 SMAPI 的同步上下文。
/// </summary>
public sealed class TaskResultPump<T>
{
    private Task<T>? pending;

    public bool HasPending => pending is not null;

    public void Start(Task<T> task)
    {
        ArgumentNullException.ThrowIfNull(task);
        if (pending is not null)
        {
            throw new InvalidOperationException("已有请求正在等待完成。");
        }

        pending = task;
    }

    public bool TryTakeCompleted(out T result, out Exception? error)
    {
        result = default!;
        error = null;
        var task = pending;
        if (task is null || !task.IsCompleted)
        {
            return false;
        }

        pending = null;
        try
        {
            result = task.GetAwaiter().GetResult();
        }
        catch (Exception exception)
        {
            error = exception;
        }

        return true;
    }

    public void Clear()
    {
        pending = null;
    }
}
