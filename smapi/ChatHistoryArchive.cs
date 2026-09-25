using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace StardewAI.NPC;

/// <summary>
/// 回看档案（F8 面板「往上翻」看到的那一份，每 NPC <see cref="ChatHistoryRules.MaxDisplayMessages"/> 条）
/// 在**当前存档**里的载荷形态。
///
/// 2026-09-20：这一份此前只活在进程内的内存字典里，关掉游戏就没了 —— 玩家第二天载入同一个存档，
/// 「往上翻」空空如也。玩家要的是「不跨存档共享，但同一个存档一直看得到」，这里定义它的落盘形态，
/// 由 ModEntry 在 SaveLoaded 读、Saving 写。
///
/// 三条边界：
/// 1. **随存档走**：数据经 SMAPI 的 <c>helper.Data.WriteSaveData</c> 写进当前存档的
///    <c>Game1.CustomData</c>（存档文件的一部分，不是我们自造的文件路径），因此天然按存档隔离：
///    换一个存档读到的就是另一份，不需要也不应该共享；
/// 2. **不碰发送窗口**：这里存的是回看档案；发给模型的 6 条窗口另有一份，两边各裁各的；
/// 3. **读不到就空手开局**：老存档没有这份数据是常态，<see cref="ChatHistoryArchive.Load"/>
///    返回空结果而不是抛异常。
/// </summary>
public sealed class ChatHistoryArchiveEnvelope
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = ChatHistoryArchive.CurrentSchemaVersion;

    /// <summary>
    /// 写入时所在存档的标识：当前存档文件夹名里 `_` 之后的那一段，
    /// 也就是星露谷的 <c>uniqueIDForThisGame</c>（<c>MyFarm_123456789</c> → <c>123456789</c>）。
    /// 同一个人可能有多个存档，载入时对不上就丢弃 —— 宁可空手开局，也不把别的存档里的话翻出来。
    ///
    /// 用存档 ID 而不是整个文件夹名，是因为玩家可以在载入界面给存档改名（只改前缀、ID 不变）：
    /// 改名不该让「往上翻」的历史凭空消失。取值见 <see cref="ChatHistoryArchive.SaveIdFromFolderName"/>。
    /// </summary>
    [JsonPropertyName("saveId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SaveId { get; init; }

    /// <summary>NPC id → 按时间先后排列的对话记录（最新的在最后）。</summary>
    [JsonPropertyName("byNpc")]
    public Dictionary<string, List<BridgeDialogueHistoryItem>>? ByNpc { get; init; }

    /// <summary>
    /// 群聊场次（2026-09-21 新增，见 <see cref="GroupChatSessionRecord"/>）：一场群聊一条，
    /// 内含完整发言序列。**加字段不升版本号**，理由见 <see cref="ChatHistoryArchive.CurrentSchemaVersion"/>。
    ///
    /// 没有场次时整个字段不写（<see cref="JsonIgnoreCondition.WhenWritingNull"/>）：这样
    /// 「从没开过群聊」的档案与加这个字段之前**逐字节相同**，体积预算用例的数字也不会漂。
    /// </summary>
    [JsonPropertyName("groupSessions")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public IReadOnlyList<GroupChatSessionRecord>? GroupSessions { get; init; }

    /// <summary>
    /// 「早上主动发来、玩家还没看」的 NPC id 列表（2026-09-26 新增）。
    ///
    /// **为什么放在聊天档案里、不放进故事状态**：它和 <see cref="ByNpc"/> 是同一个生命周期
    /// ——「有一条消息没看」这件事，在聊天记录被丢弃（换了存档）时必须一起丢弃。
    /// 放进故事状态就多出一处可能对不上的副本。
    ///
    /// 没有未读时整个字段不写（理由与 <see cref="GroupSessions"/> 相同）：这样
    /// 「没人在早上发过消息」的档案与加这个字段之前**逐字节相同**，
    /// 体积预算用例的数字也不会漂。
    /// </summary>
    [JsonPropertyName("unreadMorning")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public IReadOnlyList<string>? UnreadMorning { get; init; }
}

/// <summary>
/// 读回结果：能用的档案 + 降级原因。读不到数据是空结果、零警告；
/// 数据在但不可用（坏 JSON、版本不认识、属于别的存档）才是警告。
/// </summary>
public sealed class ChatHistoryArchiveLoadResult
{
    public static ChatHistoryArchiveLoadResult Empty { get; } = new(
        new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.OrdinalIgnoreCase),
        messageCount: 0,
        Array.Empty<string>(),
        Array.Empty<GroupChatSessionRecord>(),
        sessionLineCount: 0);

    internal ChatHistoryArchiveLoadResult(
        IReadOnlyDictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>> history,
        int messageCount,
        IReadOnlyList<string> warnings,
        IReadOnlyList<GroupChatSessionRecord> sessions,
        int sessionLineCount,
        IReadOnlyList<string>? unreadMorning = null)
    {
        History = history;
        MessageCount = messageCount;
        Warnings = warnings;
        Sessions = sessions;
        SessionLineCount = sessionLineCount;
        UnreadMorning = unreadMorning ?? Array.Empty<string>();
    }

    public IReadOnlyDictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>> History { get; }

    /// <summary>私聊档案的条数（不含场次里的发言——那两个数分开报，免得日志口径含糊）。</summary>
    public int MessageCount { get; }

    public IReadOnlyList<string> Warnings { get; }

    /// <summary>读回来的群聊场次，最早的在前。老档案没有这一段时是空列表，不是错误。</summary>
    public IReadOnlyList<GroupChatSessionRecord> Sessions { get; }

    /// <summary>场次里的发言总条数。</summary>
    public int SessionLineCount { get; }

    /// <summary>
    /// 早上发来、玩家还没看过的 NPC id。老档案没有这个字段时是**空列表**（不是错误）——
    /// 那时本来就没有这个功能，读不到未读是正确结果。
    /// </summary>
    public IReadOnlyList<string> UnreadMorning { get; }
}

/// <summary>
/// 回看档案的编解码规则。纯函数、不依赖 SMAPI，读写存档的那一头留在
/// <see cref="ModEntry"/>（它才知道 helper 与当前存档）。
/// </summary>
public static class ChatHistoryArchive
{
    /// <summary>
    /// 存档数据键。经 SMAPI 存进当前存档的 <c>CustomData</c>，
    /// 实际键名会被加上 <c>smapi/mod-data/stardew-ai-npc/</c> 前缀（见 SMAPI 的 DataHelper）。
    /// 取值只需满足 SMAPI 对 slug 的要求（字母、数字、点、下划线、连字符），
    /// 与故事状态那份互不覆盖。
    /// </summary>
    public const string StorageKey = "stardew-ai-npc.chat-history.v1";

    /// <summary>
    /// 载荷版本。**2026-09-21 加了群聊场次仍然写 1**：新增的是可选字段，读出端对缺失/多出来的
    /// 字段本来就宽容（缺失 → 空列表；多出来的字段 → 忽略），所以「老档案读得进、新档案老代码
    /// 也读得进」两头都成立。一旦升成 2，改前那份 DLL 载入新存档时会走
    /// <c>schema version unsupported</c> 分支把**整份档案**丢掉 —— 玩家回退版本就白丢历史，
    /// 而这次改动本身并没有破坏旧格式。真要做不兼容的改动时再升。
    /// </summary>
    public const int CurrentSchemaVersion = 1;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
        // 满档约 1 MB，默认编码器会把每个中文字转义成 \uXXXX（6 字节），体积几乎翻倍。
        // 这里按原文存：落点是存档 XML，转义由 XML 序列化器负责，不存在注入面。
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    /// <summary>
    /// 把内存里的回看档案编成存档载荷。超出规格的部分在这里裁掉，
    /// 所以写出去的档案一定满足「每 NPC ≤ <see cref="ChatHistoryRules.MaxDisplayMessages"/> 条、
    /// 每条 ≤ <see cref="ChatHistoryRules.MaxContentLength"/> 字」。
    /// </summary>
    public static string Serialize(
        IReadOnlyDictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>? history,
        string? saveFolder,
        IReadOnlyList<string>? unreadMorning = null)
    {
        return Serialize(history, null, saveFolder, unreadMorning);
    }

    /// <summary>
    /// 同上，外加**群聊场次**（<see cref="GroupChatSessionRecord"/>）。场次数与单场条数同样在这里裁
    /// （<see cref="GroupSessionRules.MaxSessions"/>／<see cref="GroupSessionRules.MaxLinesPerSession"/>），
    /// 一条不留时整个字段不写进 JSON。
    ///
    /// <paramref name="unreadMorning"/> 是「早上发来、还没看」的 NPC id；
    /// 空集合与 null 都表示没有未读，整个字段不写。
    /// </summary>
    public static string Serialize(
        IReadOnlyDictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>? history,
        IReadOnlyList<GroupChatSessionRecord>? sessions,
        string? saveFolder,
        IReadOnlyList<string>? unreadMorning = null)
    {
        var byNpc = new Dictionary<string, List<BridgeDialogueHistoryItem>>(StringComparer.Ordinal);
        if (history is not null)
        {
            foreach (var pair in history)
            {
                var npcId = pair.Key?.Trim();
                if (string.IsNullOrWhiteSpace(npcId) || pair.Value is null)
                {
                    continue;
                }

                var items = pair.Value
                    .Where(item => item is not null && !string.IsNullOrWhiteSpace(item.Content))
                    .TakeLast(ChatHistoryRules.MaxDisplayMessages)
                    .Select(Normalize)
                    .ToList();
                if (items.Count == 0)
                {
                    continue;
                }

                byNpc[npcId] = items;
            }
        }

        var normalizedSessions = GroupSessionRules.NormalizeAll(sessions, out _);
        return JsonSerializer.Serialize(
            new ChatHistoryArchiveEnvelope
            {
                SchemaVersion = CurrentSchemaVersion,
                SaveId = SaveIdFromFolderName(saveFolder),
                ByNpc = byNpc,
                GroupSessions = normalizedSessions.Count == 0 ? null : normalizedSessions,
                UnreadMorning = NormalizeUnreadMorning(unreadMorning),
            },
            JsonOptions);
    }

    /// <summary>
    /// 归一未读名单：去空白、去重（大小写不敏感）、保持传入顺序；空集合返回 null。
    ///
    /// 返回 null 而不是空列表，是为了让「没有未读」的档案**逐字节**等同于
    /// 加这个字段之前（<see cref="JsonIgnoreCondition.WhenWritingNull"/> 会整个字段不写）。
    /// </summary>
    internal static IReadOnlyList<string>? NormalizeUnreadMorning(
        IReadOnlyList<string>? unreadMorning)
    {
        if (unreadMorning is null || unreadMorning.Count == 0)
        {
            return null;
        }

        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var kept = new List<string>();
        foreach (var candidate in unreadMorning)
        {
            var npcId = candidate?.Trim();
            if (string.IsNullOrWhiteSpace(npcId) || !seen.Add(npcId))
            {
                continue;
            }

            kept.Add(npcId);
        }

        return kept.Count == 0 ? null : kept;
    }

    /// <summary>
    /// 解出一份可用的回看档案。任何一步不成立都退回空结果（外加一条降级原因），
    /// 绝不抛异常 —— 老存档、手改坏的存档、别的存档的数据都不该拦住游戏载入。
    /// </summary>
    /// <param name="json">存档里读到的原始文本；null/空白表示这份数据不存在。</param>
    /// <param name="saveFolder">当前存档的文件夹名（SMAPI 的 <c>Constants.SaveFolderName</c>），
    /// 用于确认这份数据确实属于它。</param>
    public static ChatHistoryArchiveLoadResult Load(string? json, string? saveFolder)
    {
        // 老存档没有这份数据是常态：安静空手开局，不刷警告。
        if (string.IsNullOrWhiteSpace(json))
        {
            return ChatHistoryArchiveLoadResult.Empty;
        }

        ChatHistoryArchiveEnvelope? envelope;
        try
        {
            envelope = JsonSerializer.Deserialize<ChatHistoryArchiveEnvelope>(json, JsonOptions);
        }
        catch (JsonException)
        {
            return Failure("chat history JSON is invalid");
        }

        if (envelope is null)
        {
            return ChatHistoryArchiveLoadResult.Empty;
        }

        if (envelope.SchemaVersion != CurrentSchemaVersion)
        {
            return Failure($"chat history schema version unsupported: {envelope.SchemaVersion}");
        }

        if (!SameSaveId(envelope.SaveId, saveFolder))
        {
            return Failure($"chat history belongs to another save: {envelope.SaveId}");
        }

        var history = new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(
            StringComparer.OrdinalIgnoreCase);
        var messageCount = 0;
        var skipped = 0;
        foreach (var pair in envelope.ByNpc ?? new Dictionary<string, List<BridgeDialogueHistoryItem>>())
        {
            var npcId = pair.Key?.Trim();
            if (string.IsNullOrWhiteSpace(npcId) || pair.Value is null)
            {
                skipped++;
                continue;
            }

            var items = pair.Value
                .Where(item => item is not null && !string.IsNullOrWhiteSpace(item.Content))
                .TakeLast(ChatHistoryRules.MaxDisplayMessages)
                .Select(Normalize)
                .ToArray();
            if (items.Length == 0)
            {
                skipped++;
                continue;
            }

            history[npcId] = items;
            messageCount += items.Length;
        }

        var warnings = new List<string>();
        if (skipped > 0)
        {
            warnings.Add($"chat history dropped {skipped} empty npc entries");
        }

        // 群聊场次：老档案（没有这个字段）在这里得到空列表，不刷警告 —— 那时还没有这个形态。
        var sessions = GroupSessionRules.NormalizeAll(envelope.GroupSessions, out var droppedSessions);
        if (droppedSessions > 0)
        {
            warnings.Add($"chat history dropped {droppedSessions} unusable group sessions");
        }

        return new ChatHistoryArchiveLoadResult(
            history,
            messageCount,
            warnings.ToArray(),
            sessions,
            sessions.Sum(session => session.Lines.Count),
            NormalizeUnreadMorning(envelope.UnreadMorning));
    }

    /// <summary>
    /// 单条记录的规格化：内容只裁长度、**不动文本**（首尾空白也一并保留）——
    /// 面板显示的必须是模型当时看到的那句话，这是 <see cref="ChatHistoryRules"/> 定下的边界。
    /// 存档是可被外部编辑的输入，裁剪保证内存里的档案规格恒定
    /// （每条 ≤ <see cref="ChatHistoryRules.MaxContentLength"/> 字），不是业务加工。
    /// </summary>
    private static BridgeDialogueHistoryItem Normalize(BridgeDialogueHistoryItem item)
    {
        var content = item.Content ?? string.Empty;
        return new BridgeDialogueHistoryItem
        {
            Role = item.Role?.Trim() ?? string.Empty,
            Content = content.Length > ChatHistoryRules.MaxContentLength
                ? content[..ChatHistoryRules.MaxContentLength]
                : content,
            Intent = item.Intent,
            RelationshipStage = item.RelationshipStage,
            // 显示序号要一起带上：丢了它，F8 里群聊场次就会从它原本的位置掉到时间线最前面
            // （见 GroupSessionRules.ToTimeline 的排序规则）。
            Sequence = item.Sequence,
        };
    }

    /// <summary>
    /// 从存档文件夹名里取出稳定的存档 ID：SMAPI 的 <c>Constants.SaveFolderName</c> 形如
    /// <c>{农场名}_{uniqueIDForThisGame}</c>，农场名自己可能含下划线，所以从右边第一个下划线切。
    /// 拿不到（未载入存档、名字为空）或格式不认识（没有下划线）时，退回整串/ null ——
    /// 那几种情况下比对会放宽，不会误伤玩家自己的记录。
    /// </summary>
    public static string? SaveIdFromFolderName(string? saveFolderName)
    {
        if (string.IsNullOrWhiteSpace(saveFolderName))
        {
            return null;
        }

        var trimmed = saveFolderName.Trim();
        var separator = trimmed.LastIndexOf('_');
        return separator >= 0 && separator < trimmed.Length - 1
            ? trimmed[(separator + 1)..]
            : trimmed;
    }

    /// <summary>
    /// 存档标识比对。任一侧拿不到标识就放行：宁可少一层保险，
    /// 也不要因为名字取不到就把玩家自己的记录丢掉。
    /// </summary>
    private static bool SameSaveId(string? archivedSaveId, string? currentSaveFolder)
    {
        var expected = SaveIdFromFolderName(currentSaveFolder);
        if (string.IsNullOrWhiteSpace(archivedSaveId) || string.IsNullOrWhiteSpace(expected))
        {
            return true;
        }

        return string.Equals(archivedSaveId.Trim(), expected, StringComparison.OrdinalIgnoreCase);
    }

    private static ChatHistoryArchiveLoadResult Failure(string warning)
    {
        return new ChatHistoryArchiveLoadResult(
            new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.OrdinalIgnoreCase),
            messageCount: 0,
            new[] { warning },
            Array.Empty<GroupChatSessionRecord>(),
            sessionLineCount: 0);
    }
}
