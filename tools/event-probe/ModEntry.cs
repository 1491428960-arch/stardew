using StardewModdingAPI;
using StardewModdingAPI.Events;

namespace StardewAI.EventProbe;

/// <summary>
/// 往 <c>Data/Events/Farm</c> 注入一条**没有任何前置条件**的事件（2026-09-27）。
///
/// <para>
/// **为什么需要它**：「事件后晨间消息」要求玩家**刚完成一个剧情事件**，
/// 而真实事件全都带门槛 —— 心级（<c>/f Shane 1000</c>）、时间窗（<c>/t 600 800</c>）、
/// 季节（<c>/z winter</c>）、前置事件（<c>/e 321777</c>）。要在游戏里按需凑齐一条
/// 几乎不可能，尤其是已经玩到很深、事件几乎全完成的存档。
/// </para>
///
/// <para>
/// **为什么这样等价**：这条事件只在**第一次**从农舍走进农场时触发，完成后由游戏
/// 写进 <c>player.eventsSeen</c> —— 这一点与真实事件**完全相同**，而被测链路
/// （<c>eventsSeen</c> 跨天差异 → <c>recentEventIds</c> → 事件型预设）关心的
/// 正是这个写入。它不关心剧情内容。
/// </para>
///
/// <para>
/// ⚠ **事件 id 是刻意挑的**：<c>9990001</c>。原版事件用小数字（<c>13</c>、<c>20</c>、<c>92</c>）
/// 和不规则的七位数（<c>3910674</c>）；SVE 与 RomRas 占 <c>1000001</c>–<c>1000038</c>。
/// 9 开头这一段语料里一条都没有，不会和任何 mod 撞。
/// </para>
///
/// <para>
/// ⚠ **这不是产品代码**，只是测试夹具。它的存在不影响 <c>StardewAI.NPC</c>：
/// 独立 DLL、独立 UniqueID、可以随时从 Mods 里删掉。
/// </para>
/// </summary>
public sealed class ModEntry : Mod
{
    /// <summary>
    /// 注入的事件 id。**Bridge 侧那条探针预设的 <c>eventId</c> 必须与它逐字一致**——
    /// 事件 id 大小写敏感，且 Bridge 是靠字符串精确匹配认出「这个事件刚完成」的。
    ///
    /// ⚠ 它是**脚本第一个 token**，也是写进 <c>eventsSeen</c> 的那个值，
    /// **不含下面 <see cref="ProbeEventKey"/> 里的前提条件部分**。
    /// </summary>
    public const string ProbeEventId = "9990001";

    /// <summary>
    /// `Data/Events/Farm` 里的字典 **key**，形如 <c>"&lt;id&gt;/&lt;前提条件&gt;"</c>。
    ///
    /// ⚠ **必须带那个 <c>/</c>。** 2026-09-27 实测踩到：最初写成光秃秃的
    /// <c>"9990001"</c>，事件**从未触发**（`eventsSeen` 里查无此 id）。
    /// 回头核对原版才发现，没有任何前提条件的 key 在原版里**全是名字**
    /// （<c>mysteryBook</c>、<c>arrogantJosh</c>、<c>NoToElliott</c>…），
    /// 而**纯数字 id 一律写成 <c>"&lt;id&gt;/&lt;条件&gt;"</c>**——光秃秃的数字形态
    /// 在原版里一次都没出现过。
    ///
    /// 这里用 `y 1`（第 1 年及以后）当恒真条件：它必定满足，又让 key 落回原版见过的形态。
    /// </summary>
    public const string ProbeEventKey = ProbeEventId + "/y 1";

    /// <summary>事件里显示的文字，用来在游戏里肉眼确认它真的触发了。</summary>
    public const string ProbeText = "[事件探针] 9990001 已触发 / probe fired";

    /// <summary>
    /// 要注入的地图资产。**只放农舍**。
    ///
    /// ⚠ **为什么不放 Farm**：事件脚本的第 3 段是**角色位置**（见
    /// <see cref="ProbeScript"/> 的注释），而两个地图的合法坐标完全不同。
    /// 玩家**每天起床都在农舍**，所以只放这里就够，且坐标是确定的
    /// （存档里的 `lastSleepPoint` 就是 10, 9）。多放一个地图只会多一处可能写错的地方。
    /// </summary>
    public static readonly string[] TargetAssets =
    {
        "Data/Events/FarmHouse",
    };

    /// <summary>
    /// 事件脚本。段落格式是 **`&lt;音乐&gt; / &lt;viewport x y&gt; / &lt;角色位置&gt; / &lt;命令...&gt;`**。
    ///
    /// ⚠ 2026-09-27 实测踩到：第 3 段**必须**是角色位置。我最初写成
    /// <c>continue/-1000 -1000/message "..."</c>，游戏把 `message "..."` 当成角色位置解析，
    /// 直接报错：
    /// <code>
    /// Event '9990001' has character positions 'message "..."' which couldn't be parsed:
    /// required index 1 (Point tile > x) has value '"[事件探针]"'
    /// </code>
    /// 对照原版 <c>continue/64 15/farmer 64 16 2 Abigail 64 18 0/pause 1500/...</c>
    /// 才看清：`64 15` 是 viewport，**`farmer ... Abigail ...` 那一段才是位置**。
    ///
    /// 各段的取舍：
    /// <list type="bullet">
    /// <item><c>continue</c> —— 无音乐。放音乐会盖掉玩家正在听的上下文。</item>
    /// <item><c>-2000 -1000</c> —— 镜头不移动（照抄原版爷爷事件的写法），
    ///       避免和玩家自己的视角打架。</item>
    /// <item><c>farmer 10 9 2</c> —— 玩家放在**床边**（10, 9，取自存档的 `lastSleepPoint`），
    ///       朝下。他本来就在那儿，所以这一步等于不动。</item>
    /// <item><c>message</c> —— 原版命令（语料里出现 124 次），不是自定义指令。</item>
    /// </list>
    /// </summary>
    public const string ProbeScript =
        "continue/-2000 -1000/farmer 10 9 2/message \"" + ProbeText + "\"/pause 500/end";

    /// <summary>
    /// 诊断用：记录已经打过日志的资产名，避免同一条反复刷屏。
    /// 只在排查期有意义，链路确认后可以整个删掉。
    /// </summary>
    private readonly HashSet<string> requestedAssets = new();

    public override void Entry(IModHelper helper)
    {
        // ⚠ 这条**无条件**日志是必须的：它是判断「新版 DLL 到底有没有被加载」的唯一可靠手段。
        // 没有它，`[probe]` 一条不出现时我分不清两种完全不同的故障：
        //   (a) 新版已加载，但资产没被请求 → 注入回调没机会跑
        //   (b) 旧版还在跑 → 代码根本没换上去
        // 这两者的修法完全相反，不能靠猜。
        Monitor.Log("[probe] mod 已激活（新版双地图版），开始监听 Content.AssetRequested", LogLevel.Info);
        helper.Events.Content.AssetRequested += OnAssetRequested;
    }

    private void OnAssetRequested(object? sender, AssetRequestedEventArgs e)
    {
        // ⚠ 诊断用：把收到的 **Data/Events/*** 请求全记下来（去重，上限 60 条防刷屏）。
        // 目的只有一个——回答「农舍那个资产到底有没有被请求」。
        // 只要 `Data/Events/FarmHouse` 在这里出现过、而下面那条注入日志没出现，
        // 问题就锁死在匹配/编辑逻辑；如果连它都没出现，那就是资产压根没加载。
        var assetName = e.NameWithoutLocale.Name;
        if (assetName.StartsWith("Data/Events/", StringComparison.Ordinal)
            && requestedAssets.Count < 60
            && requestedAssets.Add(assetName))
        {
            Monitor.Log($"[probe] 资产请求 #{requestedAssets.Count}: {assetName}", LogLevel.Info);
        }

        // ⚠ 用循环而不是手写两个 if：`IsEquivalentTo` 的参数是 `IAssetName`，
        // 直接比字符串会在带 locale 后缀（如 `Data/Events/Farm.zh-CN`）时不匹配，
        // 而那种资产名在中文游戏里是会出现的。
        string? matched = null;
        foreach (var target in TargetAssets)
        {
            // ⚠ 2026-09-27 实测：这里**必须**用 `NameWithoutLocale`。
            //
            // 资产在中文游戏里的真实名字带 locale 后缀（`Data/Events/FarmHouse.zh-CN`），
            // 而 `e.Name.IsEquivalentTo(...)` **没有**像文档暗示的那样忽略它 ——
            // 匹配失败，`e.Edit` 就根本不会被注册，lambda 不跑，日志里一行都没有。
            //
            // 这个症状是**彻底的静默**，比抛异常难查得多：注入根本没发生，
            // 游戏里当然也没反应，而所有日志看起来都「正常」。
            //
            // 打印出来的 `NameWithoutLocale.Name` 正是 `Data/Events/FarmHouse`，
            // 所以直接做忽略大小写的字符串比较，比依赖扩展方法的语义更可靠。
            if (string.Equals(e.NameWithoutLocale.Name, target, StringComparison.OrdinalIgnoreCase))
            {
                matched = target;
                break;
            }
        }

        if (matched is null)
        {
            return;
        }

        e.Edit(
            asset =>
            {
                var events = asset.AsDictionary<string, string>().Data;

                // ⚠ key 见 `ProbeEventKey` 的注释：那个 `/y 1` 不是装饰，是必须的。
                //
                // ⚠ value 的三个选择都是为了「不打扰其他事件」：
                //   `continue`        —— 无音乐。放音乐会盖掉玩家正在听的上下文。
                //   `-1000 -1000`     —— viewport 不移动、不缩放。原版事件常带
                //                        `viewport 8 7 clamp true`，用那个会和它们抢镜头。
                //   不写 `farmer x y`  —— 不搬动玩家。搬动会在事件结束后把玩家留在原地。
                // `message` 用的是原版命令（语料里出现 124 次），不是自定义指令。
                events[ProbeEventKey] = ProbeScript;

                // ⚠ 这行证明**编辑动作真的执行了**（`e.Edit` 的 lambda 是延迟调用的，
                // 订阅成功不等于它跑过）。症状与「事件写对了但没人走到那儿」完全一样，
                // 有这行才能在 SMAPI 控制台一眼区分。
                Monitor.Log(
                    $"[probe] 已注入 {ProbeEventKey} → {matched}（该地图现有事件 {events.Count} 条）",
                    LogLevel.Info);
            },
            // Late：让别的 mod 先改。原版事件仍然完整可见，我们只是追加一条。
            AssetEditPriority.Late);
    }
}
