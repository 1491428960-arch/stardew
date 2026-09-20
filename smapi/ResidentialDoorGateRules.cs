namespace StardewAI.NPC;

/// <summary>
/// 「住宅门放行」时写入的门控参数。
///
/// 2026-09-20（语义层审计 #42）：同一件事有两个编码形态，此前各写一份字面量：
/// ① Harmony prefix 直接改写原版方法的 ref 参数（<see cref="HouseAccessController"/>）——
///    <c>600 / 2600 / null / -1</c>；
/// ② performAction 上游改写 map action 的 token 数组
///    （<see cref="DoorActionParser.RelaxResidentialGate"/>）——<c>"600" / "2600" / "" / "0"</c>。
/// 两种形态在各自 API 里语义等价（不要求 NPC、不做好感判定、全天放行），但写法不同：
/// 直接赋值用 <c>null</c> 与 <c>-1</c>，action 字符串用空串与 <c>"0"</c>。
/// 这里把四个值收敛到一处，并显式记录两种形态的对应关系，改一处即可同时生效。
/// </summary>
public static class ResidentialDoorGateRules
{
    /// <summary>放行后的开门时间（原版方法参数形态）。</summary>
    public const int RelaxedOpenTime = 600;

    /// <summary>放行后的关门时间（原版方法参数形态）。</summary>
    public const int RelaxedCloseTime = 2600;

    /// <summary>放行后的 npcName：直接赋值形态用 null 表示不要求 NPC。</summary>
    public const string? RelaxedRequiredNpcArgument = null;

    /// <summary>放行后的 minFriendship：直接赋值形态用 -1 表示不做好感判定。</summary>
    public const int RelaxedMinimumFriendshipArgument = -1;

    /// <summary>放行后的 npcName token：action 字符串形态用空串表示不要求 NPC。</summary>
    public const string RelaxedRequiredNpcToken = "";

    /// <summary>放行后的 minFriendship token：action 字符串形态用 "0" 表示 0 心即可。</summary>
    public const string RelaxedMinimumFriendshipToken = "0";
}
