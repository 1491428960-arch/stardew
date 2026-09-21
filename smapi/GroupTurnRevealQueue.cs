namespace StardewAI.NPC;

/// <summary>
/// 群聊面板的「逐条揭示」队列：把一次响应里的 NPC 回合按固定间隔一条条交给面板，
/// 而不是一次全画上去。
///
/// **一条铁律：任何时刻退出都不能丢。** 队列里的东西是**已经发生过**的发言——
/// 它们此刻已经在存档场次里（那条路是 <c>BridgeClient</c> 一次性写完的，与播放无关），
/// 面板这边若因为玩家中途按 Esc、切场景或存档而没播完，丢掉的就只是**画面**，
/// 而画面丢了会让「面板发言数 == 存档场次条数」这条不变式当场破掉。
/// 所以退出路径一律走 <see cref="Drain"/>（一次交光），而不是 <see cref="Clear"/>。
///
/// 纯数据、不碰 <c>Game1</c>，时间由调用方按帧喂进来，因此整套时序可以单测。
/// </summary>
public sealed class GroupTurnRevealQueue
{
    private readonly Queue<BridgeGroupTurn> pending = new();
    private double secondsUntilNext;
    private bool skipRequested;

    /// <summary>还没交给面板的回合数。</summary>
    public int PendingCount => pending.Count;

    public bool HasPending => pending.Count > 0;

    /// <summary>
    /// 排入一轮回复。**第一条是立即的**：队列从空变成非空时把等待清零，
    /// 玩家等的是那一次请求，不该再为「动画」多等半秒。
    /// </summary>
    public void Enqueue(IReadOnlyList<BridgeGroupTurn>? turns)
    {
        if (turns is null || turns.Count == 0)
        {
            return;
        }

        var wasEmpty = pending.Count == 0;
        foreach (var turn in turns)
        {
            if (turn is not null)
            {
                pending.Enqueue(turn);
            }
        }

        if (wasEmpty && pending.Count > 0)
        {
            secondsUntilNext = 0d;
        }
    }

    /// <summary>
    /// 跳过：把剩下的**一次全部**交给下一次 <see cref="Advance"/>。
    /// 玩家点一下或按空格就走这条路——不要指望他等完动画。
    /// </summary>
    public void SkipAll()
    {
        skipRequested = true;
        secondsUntilNext = 0d;
    }

    /// <summary>
    /// 推进时钟，返回这一次该交给面板的回合（可能为空、也可能是多条——
    /// 掉帧时累积的时间会一次补上，宁可快一点也不要把播放拖长）。
    /// </summary>
    public IReadOnlyList<BridgeGroupTurn> Advance(double deltaSeconds, double intervalSeconds)
    {
        if (pending.Count == 0)
        {
            Reset();
            return Array.Empty<BridgeGroupTurn>();
        }

        if (skipRequested)
        {
            return Drain();
        }

        // 间隔是外部输入（视觉测试与将来的配置项都会传），夹一个下限免得
        // 0 或负数把 while 变成死循环。
        var interval = Math.Max(0.05d, intervalSeconds);
        var elapsed = double.IsFinite(deltaSeconds) && deltaSeconds > 0d ? deltaSeconds : 0d;
        secondsUntilNext -= elapsed;

        var revealed = new List<BridgeGroupTurn>();
        while (pending.Count > 0 && secondsUntilNext <= 0d)
        {
            revealed.Add(pending.Dequeue());
            secondsUntilNext += interval;
        }

        if (pending.Count == 0)
        {
            Reset();
        }

        return revealed;
    }

    /// <summary>
    /// 把剩下的全部交出去。**退出、切场景、存档都走这里**：宁可让它们一次性出现在
    /// 面板上，也不能留下「存档里有、画面上没有」的缺口。
    /// </summary>
    public IReadOnlyList<BridgeGroupTurn> Drain()
    {
        if (pending.Count == 0)
        {
            Reset();
            return Array.Empty<BridgeGroupTurn>();
        }

        var rest = pending.ToArray();
        pending.Clear();
        Reset();
        return rest;
    }

    private void Reset()
    {
        secondsUntilNext = 0d;
        skipRequested = false;
    }
}
