namespace StardewAI.NPC;

/// <summary>
/// 群聊**只读回看**模式的规则（2026-09-21 用户口径：邀约到期之后「不能继续聊，
/// 但可以点进去看记录」）。
///
/// 只读不是「暂时不能发言」，而是「这一场已经结束了」——所以界面上不能只把输入框
/// 变灰了事：输入框那里换成一句说明（<see cref="InputPlaceholderText"/>），
/// 发送/重试留在原位但置灰，键盘租约干脆不获取（否则玩家打字会进到一个
/// 根本没画出来的输入框里）。三处的取舍见 <c>GroupDialogueMenu</c>。
///
/// 判据与窗口计算都放在这里：菜单类要 Game1 才能构造，单测造不出来，于是
/// 「能不能发言」「这一屏画哪一段」这两件最容易出错的事下沉成纯函数。
/// </summary>
public static class GroupReadOnlyRules
{
    /// <summary>
    /// 邀约卡主按钮上「只读回看」那一档的文案。用两个字是为了与「接受」「继续」
    /// 同宽：卡片按钮只有 <see cref="GroupInvitationActionLayoutRules.ButtonWidth"/> 像素，
    /// 四个字（如「查看记录」）会顶到按钮边框上。
    /// </summary>
    public const string ActionLabel = "回看";

    /// <summary>
    /// 只读模式下玩家**任何**发言入口都必须被它挡住。之所以要有这个名字，
    /// 而不是在三个方法里各写一遍 <c>!readOnly</c>：发送按钮、回车、重试分散在三处，
    /// 漏掉任何一处「只读」就成了一句空话。
    /// </summary>
    public static bool CanSpeak(bool readOnly) => !readOnly;

    /// <summary>滚动到最新时 <c>startIndex</c> 的取值上限（不足一屏时为 0）。</summary>
    public static int MaxScrollStart(int totalCount, int maxVisible)
    {
        return Math.Max(0, totalCount - Math.Max(1, maxVisible));
    }

    /// <summary>
    /// 这一屏画哪一段。<paramref name="startIndex"/> 会被夹进合法区间，
    /// 返回值一定落在 <c>[0, totalCount]</c> 内；场次不足一屏时就是全部
    /// （等价于能发言时的 <c>TakeLast(MaxVisibleMessages)</c>）。
    /// </summary>
    public static (int Start, int Count) VisibleWindow(
        int totalCount,
        int maxVisible,
        int startIndex)
    {
        if (totalCount <= 0 || maxVisible <= 0)
        {
            return (0, 0);
        }

        var start = ChatScrollRules.ClampStartIndex(startIndex, MaxScrollStart(totalCount, maxVisible));
        return (start, Math.Min(maxVisible, totalCount - start));
    }

    /// <summary>
    /// 输入区那一行说明，**替代**输入框画出来。要写清「为什么不能说话」：
    /// 只读的原因是这一场到期了，而不是界面出了故障。
    /// </summary>
    public static string InputPlaceholderText(int expiresTotalDays)
    {
        return expiresTotalDays > 0
            ? $"这一场在第 {expiresTotalDays} 天到期，只能回看。"
            : "这一场已经结束，只能回看。";
    }

    /// <summary>只读模式打开时的常驻提示（画在标题旁那一行）。</summary>
    public static string ReadOnlyHintText(int lineCount)
    {
        return lineCount > 0
            ? $"回看模式：这一场已经结束，不能再发言（共 {lineCount} 条发言）；滚轮往上翻看更早的。"
            : "回看模式：这一场已经结束，不能再发言。";
    }

    /// <summary>滚动之后的位置提示：<c>回看中：第 11–20 条 / 共 34 条…</c>。</summary>
    public static string ScrollHintText(int start, int count, int totalCount)
    {
        if (totalCount <= 0)
        {
            return ReadOnlyHintText(0);
        }

        // 这里不用 Math.Clamp：它的 min > max 会抛异常，而 start 恰好落在末尾时
        // safeStart + 1 会超过 totalCount。逐段夹更省事，也不会在边界上炸掉。
        var safeStart = Math.Min(Math.Max(start, 0), totalCount - 1);
        var first = safeStart + 1;
        var last = Math.Min(totalCount, safeStart + Math.Max(1, count));
        return $"回看中：第 {first}–{last} 条 / 共 {totalCount} 条；滚轮往上翻看更早的。";
    }
}
