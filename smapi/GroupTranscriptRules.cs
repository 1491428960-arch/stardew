namespace StardewAI.NPC;

/// <summary>
/// 群聊面板的**显示时序**规则（2026-09-21 用户口径）：
/// 玩家自己的话立刻上屏、NPC 的回复一条一条出现、对话进行中也能往上翻记录。
///
/// 三件事都要能脱离 <c>Game1</c> 被验证——菜单类要 Game1 才能构造，单测造不出来，
/// 所以「下一条隔多久揭示」「翻页之后视口落在哪」「提示行写什么」都下沉成纯函数
/// （与 <see cref="GroupReadOnlyRules"/> 同一套做法）。
///
/// ⚠ 视口算术**不在这里**：仍然只有 <see cref="GroupReadOnlyRules.VisibleWindow"/> 一份，
/// 这里只负责决定喂给它的那个起点。翻页因此不是第二套实现，而是同一套算术换了输入。
/// </summary>
public static class GroupTranscriptRules
{
    /// <summary>
    /// 相邻两条 NPC 回复之间的间隔（秒）。
    ///
    /// **取值理由**：中文默读约每秒 6～9 字，一条 15～25 字的回复扫完要 2 秒上下，
    /// 所以这个间隔的作用**不是**等玩家读完，而是让「这是两个人先后说的」看得出来。
    /// 0.2 秒以下人眼分辨不出先后，等于没做；1 秒以上则 4 条回复要多等 4 秒，会烦。
    /// 0.5 秒落在中间：能明确看出逐条，最坏情况（4 条，Bridge 的回合上限）也只多等 1.5 秒。
    ///
    /// **第一条不等**：玩家已经等了整整一次请求（通常 5～15 秒），响应回来第一条就该出现。
    /// </summary>
    public const double TurnRevealIntervalSeconds = 0.5;

    /// <summary>
    /// 要不要一条一条揭示。**回看模式（只读）不播**：那一场已经结束，玩家要的是
    /// 一次看到全部记录，逐条动画只会让他多等（用户口径：回看应立刻全显示）。
    /// </summary>
    public static bool ShouldRevealOneByOne(bool readOnly) => !readOnly;

    /// <summary>
    /// 按住 Shift 时的揭示间隔——「加速」而不是「跳过」：留一点点间隔让
    /// 「这是几条不同的发言」仍然看得出来，同时快到几乎等于立刻全部出现。
    ///
    /// 为什么加速键选 Shift：它**不产生任何文本**，所以不会像空格那样在玩家
    /// 打空格时既触发加速又往输入框里塞一个空格（那条路试过，是错的）。
    /// 为什么不把「跳过」也绑到某个字母键上：字母键全都会被输入框吃掉。
    /// 想要一次到位就用**鼠标点消息区**（见 <c>GroupDialogueMenu.receiveLeftClick</c>），
    /// 那个手势没有歧义。
    /// </summary>
    public const double FastForwardIntervalSeconds = 0.05;

    /// <summary>
    /// 喂给 <see cref="GroupReadOnlyRules.VisibleWindow"/> 的起点：跟随最新时给一个
    /// 「必然被夹到末尾」的值（夹取规则在 <see cref="ChatScrollRules.ClampStartIndex"/>）。
    /// </summary>
    public static int WindowStartIndex(bool followLatest, int scrollStartIndex) =>
        followLatest ? int.MaxValue : scrollStartIndex;

    /// <summary>
    /// 滚轮/翻页之后视口落在哪。与原版一致：<paramref name="direction"/> &gt; 0 是往上滚
    /// = 看**更早**的发言。装得下一屏（<c>maxStart == 0</c>）时不动，并保持跟随。
    /// </summary>
    /// <param name="step">
    /// 一次移动几条。滚轮传 1（逐条），PageUp/PageDown 传**当前一屏的容量**
    /// （2026-09-21 修正：改前 PageUp/PageDown 也只移 1 条，与 F8 私聊的
    /// <c>ScrollPageStep = 3</c> 不是一回事，视觉上近乎没动）。
    /// 步长取实测容量而不是照抄 F8 的常量，是为了与「一屏」同源——
    /// 容量已经是算出来的，步长再写一个固定值就会再次漂移。
    /// </param>
    public static (int Start, bool FollowLatest) Scroll(
        bool followLatest,
        int scrollStartIndex,
        int direction,
        int totalCount,
        int maxVisible,
        int step = 1)
    {
        var maxStart = GroupReadOnlyRules.MaxScrollStart(totalCount, maxVisible);
        if (direction == 0 || maxStart <= 0)
        {
            return (0, true);
        }

        // 步长至少 1：传 0 或负数会让 PageUp/PageDown 变成「按了没反应」，
        // 那正是这一次要修掉的现象，不能从参数上再放进来。
        var delta = Math.Max(1, step);
        var current = followLatest
            ? maxStart
            : ChatScrollRules.ClampStartIndex(scrollStartIndex, maxStart);
        var next = ChatScrollRules.MoveStartIndex(
            current,
            direction > 0 ? -delta : delta,
            maxStart);
        // 滚到底就恢复跟随，玩家不用再按一次「回到底部」。
        return (next, next >= maxStart);
    }

    /// <summary>
    /// 对话进行中翻看历史时的位置提示。与只读那条
    /// （<see cref="GroupReadOnlyRules.ScrollHintText"/>）**结构一致**，只是没有「回看中」
    /// 前缀，且在看历史时把「下面还有几条没看」一并说出来。
    /// </summary>
    /// <param name="newMessageCount">
    /// 视口之外、玩家还没看到的新消息条数。翻到历史里之后它是唯一的信号——
    /// 没有它，新消息会在下面悄悄出现，玩家不知道该不该翻回来
    /// （那等于把「翻页」做成了「看不见」）。
    /// </param>
    public static string ChatScrollHintText(
        int start,
        int count,
        int totalCount,
        int newMessageCount)
    {
        if (totalCount <= 0)
        {
            return string.Empty;
        }

        // 与只读那份同一个理由不用 Math.Clamp：start 落在末尾时 safeStart + 1 会超过
        // totalCount，而 Clamp 的 min > max 会抛异常。逐段夹更省事，边界上也不会炸。
        var safeStart = Math.Min(Math.Max(start, 0), totalCount - 1);
        var first = safeStart + 1;
        var last = Math.Min(totalCount, safeStart + Math.Max(1, count));
        var tail = newMessageCount > 0
            ? $"；↓ 下面还有 {newMessageCount} 条新消息（End 或滚到底回到底部）"
            : "；滚轮往上翻看更早的，End 回到底部";
        return $"第 {first}–{last} 条 / 共 {totalCount} 条{tail}";
    }
}
