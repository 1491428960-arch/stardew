namespace StardewAI.NPC;

/// <summary>
/// 「群聊场次」的规则：写入、裁剪、读回（存档是外部可编辑的输入）、以及铺进 F8 时
/// 与私聊记录并成一条时间线。**纯函数、不依赖 SMAPI**，因此生产路径与测试路径共用同一份，
/// 存档那一头（读写 <c>helper.Data</c>）留在 <see cref="ModEntry"/>。
///
/// 一条不变式贯穿全篇：**场次里那串发言 == F9 界面当时真正画出来的那串气泡**。
/// 玩家说什么、NPC 按什么顺序回、谁在场，三处（F9 画面／存档／F8 回看）都出自
/// <see cref="AppendTurn"/> 一个函数，任何一处改规则另外两处不会各自漂移。
///
/// 与「发给模型的群聊上下文」的边界（**2026-09-22 改**）：
/// <see cref="GroupDialogueSession.PublicHistory"/> 由 <see cref="ToRequestHistory"/> 从场次发言
/// 投影而来，**玩家那一句也在里面** —— 两侧现在是同一串发言的两种投影，而不是「整串 vs 只剩 NPC」。
/// 理由见 <see cref="ToRequestHistory"/> 的注释（旧口径被真机实测证伪，不要再改回去）。
/// </summary>
public static class GroupSessionRules
{
    /// <summary>玩家发言的 <c>speakerType</c>／<c>speakerId</c>。与 Bridge 的
    /// <c>GroupHistoryItem.speaker_type: Literal["player","npc"]</c> 取值一致。</summary>
    public const string PlayerSpeakerType = "player";

    /// <summary>NPC 发言的 <c>speakerType</c>。</summary>
    public const string NpcSpeakerType = "npc";

    /// <summary>玩家发言的 <c>speakerId</c>：玩家没有 NPC id，用这个固定值。</summary>
    public const string PlayerSpeakerId = "player";

    /// <summary>
    /// 存档里最多留多少场。超出的丢**最旧的**（新场次才是玩家还想翻的）。
    /// 40 场 × 满 120 条 × 240 字 ≈ 3.5 MB，与私聊那份（满档 15 MB）同一量级；
    /// 实测数字打在 <c>GroupSessionArchiveTests</c> 的预算用例里备查。
    /// </summary>
    public const int MaxSessions = 40;

    /// <summary>单场最多留多少条发言，超出的丢最旧的（玩家翻的是这一场最近发生的部分）。</summary>
    public const int MaxLinesPerSession = 120;

    /// <summary>
    /// 一场里最多记多少位参与者。正常情况下就是 Bridge 允许的 2～3 位
    /// （<see cref="GroupInvitationRules.MaxParticipants"/>）；留宽是为了**读旧存档**时
    /// 不被一份手改过的名单撑爆，而不是允许写出更多人的场次。
    /// </summary>
    public const int MaxParticipants = 8;

    /// <summary>单条发言的长度上限：与私聊档案共用 <see cref="ChatHistoryRules.MaxContentLength"/>。</summary>
    public const int MaxLineLength = ChatHistoryRules.MaxContentLength;

    public const int MaxTitleLength = 120;
    public const int MaxTopicLength = 240;
    public const int MaxDateLabelLength = 40;

    /// <summary>抬头里主题最多显示多少字（再长就截断，它只是一行分节线的补充）。</summary>
    public const int MaxTopicInHeaderLength = 24;

    /// <summary>玩家这条发言（没有内容时返回 null：「开场」那一轮玩家一句话都没说）。</summary>
    public static GroupDialogueHistoryEntry? PlayerLine(string? message)
    {
        var text = message?.Trim();
        return string.IsNullOrEmpty(text)
            ? null
            : new GroupDialogueHistoryEntry(
                PlayerSpeakerType,
                PlayerSpeakerId,
                Truncate(text, MaxLineLength));
    }

    /// <summary>
    /// 把「这一轮的玩家发言 + NPC 回合」接到一串发言后面。F9 画面、场次记录、
    /// F8 回看三处都由它产出，顺序与内容因此不可能出现分歧。
    /// </summary>
    public static IReadOnlyList<GroupDialogueHistoryEntry> AppendTurn(
        IReadOnlyList<GroupDialogueHistoryEntry>? lines,
        string? playerMessage,
        IReadOnlyList<BridgeGroupTurn>? turns)
    {
        var next = (lines ?? Array.Empty<GroupDialogueHistoryEntry>()).ToList();
        if (PlayerLine(playerMessage) is { } playerLine)
        {
            next.Add(playerLine);
        }

        foreach (var turn in turns ?? Array.Empty<BridgeGroupTurn>())
        {
            if (turn is null)
            {
                continue;
            }

            var npcId = turn.SpeakerNpcId?.Trim();
            var content = turn.Content?.Trim();
            if (string.IsNullOrEmpty(npcId) || string.IsNullOrEmpty(content))
            {
                continue;
            }

            next.Add(new GroupDialogueHistoryEntry(
                NpcSpeakerType,
                npcId,
                Truncate(content, MaxLineLength),
                (turn.AddressedTo ?? Array.Empty<string>())
                    .Where(value => !string.IsNullOrWhiteSpace(value))
                    .Select(value => value.Trim())
                    .Take(GroupInvitationRules.MaxParticipants)
                    .ToArray()));
        }

        return next.Count > MaxLinesPerSession
            ? next.Skip(next.Count - MaxLinesPerSession).ToArray()
            : next.ToArray();
    }

    /// <summary>
    /// 开一场新的场次记录。**只有真的聊出东西时才会被调用**（见
    /// <see cref="Append"/>）：一个空场次不该在存档里占位，也不该在 F8 里露出一条
    /// 「进过这个界面但什么都没发生」的记录。
    /// </summary>
    public static GroupChatSessionRecord Create(
        GroupSessionContext context,
        IReadOnlyList<GroupDialogueParticipant>? participants,
        int? sequence = null)
    {
        ArgumentNullException.ThrowIfNull(context);
        var ids = new List<string>();
        var names = new List<string>();
        foreach (var participant in participants ?? Array.Empty<GroupDialogueParticipant>())
        {
            if (participant is null)
            {
                continue;
            }

            var npcId = participant.NpcId?.Trim();
            if (string.IsNullOrEmpty(npcId) ||
                ids.Contains(npcId, StringComparer.OrdinalIgnoreCase) ||
                ids.Count >= MaxParticipants)
            {
                continue;
            }

            ids.Add(npcId);
            names.Add(Truncate(
                string.IsNullOrWhiteSpace(participant.DisplayName) ? npcId : participant.DisplayName.Trim(),
                MaxTitleLength));
        }

        return new GroupChatSessionRecord
        {
            SessionId = context.SessionId?.Trim() ?? string.Empty,
            Title = Truncate(context.Title?.Trim() ?? string.Empty, MaxTitleLength),
            Topic = Truncate(context.Topic?.Trim() ?? string.Empty, MaxTopicLength),
            DateLabel = Truncate(context.DateLabel?.Trim() ?? string.Empty, MaxDateLabelLength),
            TotalDays = context.TotalDays,
            Participants = ids.ToArray(),
            ParticipantDisplayNames = names.ToArray(),
            Sequence = sequence,
        };
    }

    /// <summary>
    /// 这一轮要并入哪一场：已有同 id 的场次就接着写，没有就按 <paramref name="context"/>
    /// 新开一场。返回 null 表示这一轮**不该留痕**（结果不可用，或这一轮没有任何发言），
    /// 此时调用方连空场次都不该建。
    /// </summary>
    public static GroupChatSessionRecord? Append(
        GroupChatSessionRecord? existing,
        GroupSessionContext context,
        IReadOnlyList<GroupDialogueParticipant>? participants,
        string? playerMessage,
        IReadOnlyList<BridgeGroupTurn>? turns,
        bool fallback,
        int? sequence = null)
    {
        ArgumentNullException.ThrowIfNull(context);
        // 与 F9 界面的判据完全一致：fallback／没有可用回合时，菜单既不画气泡也不记档
        // （玩家那句仍留在输入状态里可以重试），所以这里同样一条都不写。
        if (fallback || turns is null || turns.Count == 0)
        {
            return existing;
        }

        var appended = AppendTurn(existing?.Lines, playerMessage, turns);
        var added = appended.Count - (existing?.Lines.Count ?? 0);
        if (added <= 0)
        {
            return existing;
        }

        var session = existing ?? Create(context, participants, sequence);
        if (string.IsNullOrEmpty(session.SessionId))
        {
            // 没有身份就没有「同一场」可言：宁可丢掉，也不要把两场并成一个越滚越大的桶
            // （空 sessionId 只会来自手改过的存档或漏传上下文的调用点）。
            return existing;
        }

        return session with { Lines = appended };
    }

    /// <summary>这一场有没有这位 NPC（在场名单优先，名单缺位时按发言兜底）。</summary>
    public static bool InvolvesNpc(GroupChatSessionRecord? session, string? npcId)
    {
        var normalized = npcId?.Trim();
        if (session is null || string.IsNullOrEmpty(normalized))
        {
            return false;
        }

        if (session.Participants.Any(id =>
                string.Equals(id?.Trim(), normalized, StringComparison.OrdinalIgnoreCase)))
        {
            return true;
        }

        return session.Lines.Any(line =>
            string.Equals(line?.SpeakerId?.Trim(), normalized, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>
    /// 场次发言 → 发给模型的 <see cref="GroupDialogueSession.PublicHistory"/>：
    /// **玩家与 NPC 都在里面，顺序照旧**。
    ///
    /// ## 它曾经叫 <c>ToPublicHistory</c>，只留 NPC 发言 —— 那条口径已被实测证伪（2026-09-22）
    ///
    /// 旧注释写的理由是：「玩家那句本来就由 <c>message</c> 单独送」。
    /// 那条理由**只在单轮下成立**：<c>message</c> 只带当轮那一句，
    /// 第 2 轮起，第 1 轮玩家说过的话一旦被这里滤掉就再也回不到请求里。
    /// 实测代价（真机 C1 第 1 轮）：Alex 反问「你呢，还去海滩吗？」——
    /// 而玩家从没提过海滩，因为模型手里根本没有玩家上一轮说过的话可以接。
    ///
    /// 「记了，但请求侧把它丢了」也是这件事的准确描述：玩家的话一直在存档里
    /// （<see cref="AppendTurn"/> 会写 <see cref="PlayerLine"/>），只是请求不读它。
    ///
    /// Bridge 侧本来就支持：<c>GroupHistoryItem.speaker_type: Literal["player","npc"]</c>
    /// 已含 <c>"player"</c>，名单归属只对 <c>npc</c> 行校验，因此这里不需要任何 Bridge 侧改动。
    ///
    /// ⚠️ **不要再改回「只留 NPC」**。要改之前先看 <c>GroupDialogueSessionRulesTests</c> 里
    /// 钉住多轮玩家行的用例：那边证明的是「第 2 轮的请求历史里必须有第 1 轮玩家那句」。
    /// </summary>
    public static IReadOnlyList<GroupDialogueHistoryEntry> ToRequestHistory(
        IEnumerable<GroupDialogueHistoryEntry>? lines)
    {
        var history = new List<GroupDialogueHistoryEntry>();
        foreach (var line in lines ?? Array.Empty<GroupDialogueHistoryEntry>())
        {
            if (line is null || string.IsNullOrWhiteSpace(line.Content))
            {
                continue;
            }

            // speakerType／speakerId 归一到 Bridge 认得的那两个取值（存档是外部可编辑的输入）：
            // 非 "player" 一律按 NPC 处理，与 NormalizeLine 同一条规矩；
            // 没有 speakerId 的 NPC 行直接丢（Bridge 侧 speakerId 要求非空，留着只会换来 422）。
            var isPlayer = string.Equals(
                line.SpeakerType?.Trim(),
                PlayerSpeakerType,
                StringComparison.OrdinalIgnoreCase);
            var speakerId = isPlayer ? PlayerSpeakerId : line.SpeakerId?.Trim();
            if (string.IsNullOrEmpty(speakerId))
            {
                continue;
            }

            history.Add(new GroupDialogueHistoryEntry(
                isPlayer ? PlayerSpeakerType : NpcSpeakerType,
                speakerId!,
                line.Content!,
                line.AddressedTo));
        }

        return history;
    }

    /// <summary>
    /// 场次里这位 NPC 在场时的显示名（抬头要写「都有谁在」）；查不到就退回 id。
    /// </summary>
    public static string DisplayNameOf(GroupChatSessionRecord session, string npcId)
    {
        ArgumentNullException.ThrowIfNull(session);
        for (var index = 0; index < session.Participants.Count; index++)
        {
            if (!string.Equals(
                    session.Participants[index]?.Trim(),
                    npcId?.Trim(),
                    StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var name = index < session.ParticipantDisplayNames.Count
                ? session.ParticipantDisplayNames[index]?.Trim()
                : null;
            return string.IsNullOrEmpty(name) ? session.Participants[index].Trim() : name;
        }

        return npcId?.Trim() ?? string.Empty;
    }

    /// <summary>
    /// 分节线抬头：<c>线上多人对话 · 阿比盖尔、艾米丽 · 秋 12 · 主题：…</c>。
    /// 「在场的有谁」就写在这一行里 —— 场上没说过话的人也在这里出现，
    /// 但不为它造一个空的气泡（见 <see cref="ToTimeline"/>）。
    /// </summary>
    public static string HeaderText(GroupChatSessionRecord session)
    {
        ArgumentNullException.ThrowIfNull(session);
        var names = new List<string>();
        for (var index = 0; index < session.Participants.Count; index++)
        {
            var id = session.Participants[index]?.Trim() ?? string.Empty;
            var name = index < session.ParticipantDisplayNames.Count
                ? session.ParticipantDisplayNames[index]?.Trim()
                : null;
            var display = string.IsNullOrEmpty(name) ? id : name!;
            if (display.Length > 0)
            {
                names.Add(display);
            }
        }

        var parts = new List<string> { "线上多人对话" };
        if (names.Count > 0)
        {
            parts.Add(string.Join("、", names));
        }

        if (!string.IsNullOrWhiteSpace(session.DateLabel))
        {
            parts.Add(session.DateLabel.Trim());
        }

        if (!string.IsNullOrWhiteSpace(session.Topic))
        {
            parts.Add($"主题：{Truncate(session.Topic.Trim(), MaxTopicInHeaderLength)}");
        }

        return string.Join(" · ", parts);
    }

    /// <summary>
    /// 场次 → F8 面板显示条目的转换：私聊记录 + 这位 NPC 在场的每一场群聊，
    /// 按 <see cref="ChatDisplayMessage.Sequence"/> 合在一起。
    ///
    /// ⚠ **2026-09-21 起没有生产调用点**：用户口径改成「F8 只显示私聊和私聊相关的记录，
    /// 群聊记录各归各位放到 F9 的邀约卡里」（见 <c>ConversationService.RecentMessages</c>
    /// 与 <c>GroupDialogueMenu</c> 的只读模式）。这一份连同分节线绘制
    /// （<see cref="ChatHistoryRules.SessionRole"/>、<c>ChatBubbleDrawing.DrawDivider</c>）
    /// 因此暂时只被测试使用，留着是为了「哪天要再并回 F8」时不必重写一遍。
    /// 新代码**不要**把它接回 F8 —— 那会与当前口径冲突。
    ///
    /// 排序规则（三种情况都要成立）：
    /// 1. 同一场里的发言前后顺序按记录里的顺序（分节线在该场第一条之前）；
    /// 2. 有号的一律排在没号的之后 —— 没号的来自老档案（那时还没有号），它必然更早；
    /// 3. 都没号时保持原顺序（老档案：私聊在前、场次在后）。
    /// </summary>
    public static IReadOnlyList<ChatDisplayMessage> ToTimeline(
        IEnumerable<BridgeDialogueHistoryItem>? privateHistory,
        IEnumerable<GroupChatSessionRecord>? sessions,
        string? viewerNpcId)
    {
        var entries = new List<ChatDisplayMessage>();
        foreach (var item in ChatHistoryRules.ToDisplayMessages(privateHistory))
        {
            entries.Add(item);
        }

        foreach (var session in sessions ?? Array.Empty<GroupChatSessionRecord>())
        {
            if (session is null || !InvolvesNpc(session, viewerNpcId))
            {
                continue;
            }

            var bubbles = new List<ChatDisplayMessage>();
            foreach (var line in session.Lines)
            {
                if (line is null || string.IsNullOrWhiteSpace(line.Content))
                {
                    continue;
                }

                var isPlayer = string.Equals(
                    line.SpeakerType?.Trim(),
                    PlayerSpeakerType,
                    StringComparison.OrdinalIgnoreCase);
                var speakerId = isPlayer
                    ? PlayerSpeakerId
                    : line.SpeakerId?.Trim() ?? string.Empty;
                if (speakerId.Length == 0)
                {
                    continue;
                }

                bubbles.Add(new ChatDisplayMessage(
                    isPlayer ? ChatHistoryRules.PlayerRole : ChatHistoryRules.NpcRole,
                    line.Content,
                    session.Sequence,
                    speakerId,
                    isPlayer ? null : DisplayNameOf(session, speakerId)));
            }

            // 一条发言都显示不出来的场次整场跳过：只留一行光秃秃的抬头比不显示更糟。
            if (bubbles.Count == 0)
            {
                continue;
            }

            entries.Add(new ChatDisplayMessage(
                ChatHistoryRules.SessionRole,
                HeaderText(session),
                session.Sequence));
            entries.AddRange(bubbles);
        }

        // OrderBy 是稳定排序，所以「同类之间」保持插入顺序（同一场的抬头必然在自己的气泡之前）。
        return entries
            .OrderBy(message => message.Sequence.HasValue)
            .ThenBy(message => message.Sequence ?? 0)
            .ToArray();
    }

    /// <summary>
    /// 存档里读回来的场次 → 内存档案。存档是可被外部编辑的输入，
    /// 所以规格外的内容在这里被裁掉；整条不成立时返回 null（丢掉它，而不是崩掉载入）。
    /// </summary>
    public static GroupChatSessionRecord? Normalize(GroupChatSessionRecord? session)
    {
        if (session is null)
        {
            return null;
        }

        var sessionId = session.SessionId?.Trim();
        var participants = NormalizeIds(session.Participants);
        if (string.IsNullOrEmpty(sessionId) || participants.Length == 0)
        {
            return null;
        }

        var names = new string[participants.Length];
        for (var index = 0; index < participants.Length; index++)
        {
            var indexInSource = IndexOf(session.Participants, participants[index]);
            var name = indexInSource >= 0 && indexInSource < session.ParticipantDisplayNames.Count
                ? session.ParticipantDisplayNames[indexInSource]?.Trim()
                : null;
            names[index] = string.IsNullOrEmpty(name)
                ? participants[index]
                : Truncate(name!, MaxTitleLength);
        }

        var lines = (session.Lines ?? Array.Empty<GroupDialogueHistoryEntry>())
            .Select(NormalizeLine)
            .Where(line => line is not null)
            .Select(line => line!)
            .ToArray();
        if (lines.Length == 0)
        {
            // 没有发言的场次就是一条空记录：F8 翻到它只会看到一行光秃秃的抬头。
            return null;
        }

        if (lines.Length > MaxLinesPerSession)
        {
            lines = lines.Skip(lines.Length - MaxLinesPerSession).ToArray();
        }

        return new GroupChatSessionRecord
        {
            SessionId = Truncate(sessionId!, MaxTitleLength),
            Title = Truncate(session.Title?.Trim() ?? string.Empty, MaxTitleLength),
            Topic = Truncate(session.Topic?.Trim() ?? string.Empty, MaxTopicLength),
            DateLabel = Truncate(session.DateLabel?.Trim() ?? string.Empty, MaxDateLabelLength),
            TotalDays = session.TotalDays,
            Participants = participants,
            ParticipantDisplayNames = names,
            Sequence = session.Sequence,
            Lines = lines,
        };
    }

    /// <summary>
    /// 一组场次的规格化 + 场次数上限（丢最旧的）。返回值与丢弃条数一并给出，
    /// 调用方据此决定要不要打一条降级警告。
    /// </summary>
    public static IReadOnlyList<GroupChatSessionRecord> NormalizeAll(
        IEnumerable<GroupChatSessionRecord>? sessions,
        out int dropped)
    {
        dropped = 0;
        var kept = new List<GroupChatSessionRecord>();
        foreach (var session in sessions ?? Array.Empty<GroupChatSessionRecord>())
        {
            var normalized = Normalize(session);
            if (normalized is null)
            {
                dropped++;
                continue;
            }

            kept.Add(normalized);
        }

        if (kept.Count > MaxSessions)
        {
            dropped += kept.Count - MaxSessions;
            kept = kept.Skip(kept.Count - MaxSessions).ToList();
        }

        return kept;
    }

    private static GroupDialogueHistoryEntry? NormalizeLine(GroupDialogueHistoryEntry? line)
    {
        var content = line?.Content;
        if (line is null || string.IsNullOrWhiteSpace(content))
        {
            return null;
        }

        var isPlayer = string.Equals(
            line.SpeakerType?.Trim(),
            PlayerSpeakerType,
            StringComparison.OrdinalIgnoreCase);
        var speakerId = isPlayer ? PlayerSpeakerId : line.SpeakerId?.Trim();
        if (string.IsNullOrEmpty(speakerId))
        {
            return null;
        }

        return new GroupDialogueHistoryEntry(
            isPlayer ? PlayerSpeakerType : NpcSpeakerType,
            speakerId!,
            Truncate(content!, MaxLineLength));
    }

    private static string[] NormalizeIds(IReadOnlyList<string>? values)
    {
        var ids = new List<string>();
        foreach (var value in values ?? Array.Empty<string>())
        {
            var id = value?.Trim();
            if (string.IsNullOrEmpty(id) ||
                ids.Contains(id, StringComparer.OrdinalIgnoreCase) ||
                ids.Count >= MaxParticipants)
            {
                continue;
            }

            ids.Add(id);
        }

        return ids.ToArray();
    }

    private static int IndexOf(IReadOnlyList<string>? values, string id)
    {
        for (var index = 0; index < (values?.Count ?? 0); index++)
        {
            if (string.Equals(values![index]?.Trim(), id, StringComparison.OrdinalIgnoreCase))
            {
                return index;
            }
        }

        return -1;
    }

    private static string Truncate(string value, int maxLength)
    {
        return value.Length > maxLength ? value[..maxLength] : value;
    }
}
