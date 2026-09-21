using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 「群聊场次」的规则（<see cref="GroupSessionRules"/>）：一场群聊怎么攒起来、
/// 存档里读回来怎么归一化、以及铺进 F8 时怎么与私聊记录并成一条时间线。
///
/// 存档往返那一头（JSON、老档案、降级、体积）在 <see cref="GroupSessionArchiveTests"/>。
/// </summary>
public sealed class GroupSessionRulesTests
{
    private static readonly GroupDialogueParticipant[] Roster =
    {
        new("Abigail", "阿比盖尔"),
        new("Emily", "艾米丽"),
    };

    // ── 攒一场 ────────────────────────────────────────────────────────────────

    [Fact]
    public void AppendTurn_puts_the_player_line_first_then_npc_turns_in_order()
    {
        var lines = GroupSessionRules.AppendTurn(
            null,
            "你们怎么看？",
            new[]
            {
                new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "我觉得挺好。" },
                new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "我还在想。" },
            });

        Assert.Equal(
            new[] { "你们怎么看？", "我觉得挺好。", "我还在想。" },
            lines.Select(line => line.Content).ToArray());
        Assert.Equal(
            new[] { "player", "npc", "npc" },
            lines.Select(line => line.SpeakerType).ToArray());
        Assert.Equal(
            new[] { "player", "Abigail", "Emily" },
            lines.Select(line => line.SpeakerId).ToArray());
    }

    [Fact]
    public void AppendTurn_omits_the_player_line_when_the_round_is_an_opening()
    {
        // 自动开场那一轮玩家一句话都没说（Bridge 把空消息当开场语义），
        // 所以不该凭空出现一个玩家的空气泡。
        var lines = GroupSessionRules.AppendTurn(
            null,
            "   ",
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "那我先说。" } });

        var line = Assert.Single(lines);
        Assert.Equal("Abigail", line.SpeakerId);
    }

    [Fact]
    public void AppendTurn_drops_blank_turns_and_trims_content()
    {
        var lines = GroupSessionRules.AppendTurn(
            null,
            "  玩家说的话  ",
            new[]
            {
                new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "  第一句  " },
                new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "   " },
                new BridgeGroupTurn { SpeakerNpcId = "   ", Content = "没有发言人。" },
            });

        Assert.Equal(
            new[] { "玩家说的话", "第一句" },
            lines.Select(line => line.Content).ToArray());
    }

    [Fact]
    public void AppendTurn_truncates_oversized_lines_to_the_shared_limit()
    {
        var lines = GroupSessionRules.AppendTurn(
            null,
            new string('长', GroupSessionRules.MaxLineLength + 80),
            null);

        Assert.Equal(GroupSessionRules.MaxLineLength, Assert.Single(lines).Content.Length);
    }

    [Fact]
    public void Append_keeps_one_session_per_invitation_and_appends_later_rounds()
    {
        var context = Context("invite-1");
        var first = GroupSessionRules.Append(
            null,
            context,
            Roster,
            "第一轮",
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "回第一轮。" } },
            fallback: false,
            sequence: 1);
        var second = GroupSessionRules.Append(
            first,
            context,
            Roster,
            "第二轮",
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "回第二轮。" } },
            fallback: false,
            sequence: 2);

        Assert.NotNull(second);
        Assert.Equal(first!.SessionId, second!.SessionId);
        Assert.Equal(1, second.Sequence);  // 序号是「这一场什么时候开的」，不随轮次变
        Assert.Equal(
            new[] { "第一轮", "回第一轮。", "第二轮", "回第二轮。" },
            second.Lines.Select(line => line.Content).ToArray());
    }

    [Fact]
    public void Append_leaves_the_session_untouched_when_the_round_said_nothing()
    {
        // fallback（Bridge 不可用／回合不合法）与「没有可用回合」在 F9 界面上同样不画气泡，
        // 所以这里也一条都不该写 —— 两者必须是同一个判据。
        var existing = Session("invite-1");
        var turns = new[] { new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "说了。" } };

        Assert.Same(
            existing,
            GroupSessionRules.Append(existing, Context("invite-1"), Roster, "玩家", turns, fallback: true));
        Assert.Same(
            existing,
            GroupSessionRules.Append(
                existing,
                Context("invite-1"),
                Roster,
                "玩家",
                Array.Empty<BridgeGroupTurn>(),
                fallback: false));
        Assert.Null(GroupSessionRules.Append(
            null,
            Context("invite-1"),
            Roster,
            "",
            Array.Empty<BridgeGroupTurn>(),
            fallback: false));
    }

    [Fact]
    public void Append_refuses_a_session_without_an_identity()
    {
        // 没有场次 id 就没有「同一场」可言：宁可丢掉，也不要把两场并成一个越滚越大的桶。
        var appended = GroupSessionRules.Append(
            null,
            new GroupSessionContext("   "),
            Roster,
            "玩家",
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "回应。" } },
            fallback: false);

        Assert.Null(appended);
    }

    [Fact]
    public void MaxLinesPerSession_keeps_the_latest_lines()
    {
        var lines = new List<GroupDialogueHistoryEntry>();
        for (var index = 0; index < GroupSessionRules.MaxLinesPerSession + 5; index++)
        {
            lines = GroupSessionRules
                .AppendTurn(lines, $"第{index}句", null)
                .ToList();
        }

        Assert.Equal(GroupSessionRules.MaxLinesPerSession, lines.Count);
        Assert.Equal("第5句", lines[0].Content);
        Assert.Equal(
            $"第{GroupSessionRules.MaxLinesPerSession + 4}句",
            lines[^1].Content);
    }

    // ── 存档读回 ──────────────────────────────────────────────────────────────

    [Fact]
    public void Normalize_drops_sessions_without_identity_participants_or_lines()
    {
        // 一条发言都没有
        Assert.Null(GroupSessionRules.Normalize(
            Session("invite-1") with { Lines = Array.Empty<GroupDialogueHistoryEntry>() }));
        Assert.Null(GroupSessionRules.Normalize(new GroupChatSessionRecord
        {
            SessionId = "  ",
            Participants = new[] { "Abigail" },
            Lines = new[] { Line("Abigail", "在。") },
        }));
        Assert.Null(GroupSessionRules.Normalize(new GroupChatSessionRecord
        {
            SessionId = "invite-1",
            Participants = Array.Empty<string>(),
            Lines = new[] { Line("Abigail", "在。") },
        }));
        Assert.Null(GroupSessionRules.Normalize(new GroupChatSessionRecord
        {
            SessionId = "invite-1",
            Participants = new[] { "Abigail" },
            Lines = new[] { Line("Abigail", "   ") },
        }));
    }

    [Fact]
    public void Normalize_keeps_participants_aligned_with_their_display_names()
    {
        var normalized = GroupSessionRules.Normalize(new GroupChatSessionRecord
        {
            SessionId = "invite-1",
            Participants = new[] { "Abigail", "   ", "abigail", "Emily" },
            ParticipantDisplayNames = new[] { "阿比盖尔", "多余", "重复", "艾米丽" },
            Lines = new[] { Line("Abigail", "在。") },
        });

        Assert.NotNull(normalized);
        Assert.Equal(new[] { "Abigail", "Emily" }, normalized!.Participants);
        Assert.Equal(new[] { "阿比盖尔", "艾米丽" }, normalized.ParticipantDisplayNames);
    }

    [Fact]
    public void Normalize_falls_back_to_the_id_when_a_display_name_is_missing()
    {
        var normalized = GroupSessionRules.Normalize(new GroupChatSessionRecord
        {
            SessionId = "invite-1",
            Participants = new[] { "Abigail", "Emily" },
            ParticipantDisplayNames = new[] { "阿比盖尔" },
            Lines = new[] { Line("Abigail", "在。") },
        });

        Assert.Equal(new[] { "阿比盖尔", "Emily" }, normalized!.ParticipantDisplayNames);
    }

    [Fact]
    public void Normalize_rewrites_player_lines_to_the_protocol_pair()
    {
        var normalized = GroupSessionRules.Normalize(new GroupChatSessionRecord
        {
            SessionId = "invite-1",
            Participants = new[] { "Abigail" },
            Lines = new[]
            {
                new GroupDialogueHistoryEntry("  PLAYER  ", "  me  ", "  玩家问的话  "),
                Line("Abigail", "回应。"),
            },
        });

        Assert.Equal("player", normalized!.Lines[0].SpeakerType);
        Assert.Equal("player", normalized.Lines[0].SpeakerId);
        // 文本不动（首尾空白也保留）——与私聊档案同一条边界：面板显示的必须是当时那句话。
        Assert.Equal("  玩家问的话  ", normalized.Lines[0].Content);
    }

    [Fact]
    public void Normalize_trims_a_session_to_the_line_cap_keeping_the_latest()
    {
        var lines = Enumerable.Range(0, GroupSessionRules.MaxLinesPerSession + 3)
            .Select(index => Line("Abigail", $"第{index}句"))
            .ToArray();
        var normalized = GroupSessionRules.Normalize(new GroupChatSessionRecord
        {
            SessionId = "invite-1",
            Participants = new[] { "Abigail" },
            Lines = lines,
        });

        Assert.Equal(GroupSessionRules.MaxLinesPerSession, normalized!.Lines.Count);
        Assert.Equal("第3句", normalized.Lines[0].Content);
    }

    [Fact]
    public void NormalizeAll_drops_the_oldest_sessions_beyond_the_cap()
    {
        var sessions = Enumerable.Range(0, GroupSessionRules.MaxSessions + 2)
            .Select(index => new GroupChatSessionRecord
            {
                SessionId = $"invite-{index}",
                Participants = new[] { "Abigail" },
                Lines = new[] { Line("Abigail", $"第{index}场") },
            })
            .ToArray();

        var kept = GroupSessionRules.NormalizeAll(sessions, out var dropped);

        Assert.Equal(GroupSessionRules.MaxSessions, kept.Count);
        Assert.Equal(2, dropped);
        Assert.Equal("invite-2", kept[0].SessionId);
    }

    // ── 归属与抬头 ────────────────────────────────────────────────────────────

    [Fact]
    public void InvolvesNpc_matches_participants_and_falls_back_to_speakers()
    {
        var session = Session("invite-1");

        Assert.True(GroupSessionRules.InvolvesNpc(session, "Abigail"));
        Assert.True(GroupSessionRules.InvolvesNpc(session, "emily"));   // 大小写不敏感
        Assert.False(GroupSessionRules.InvolvesNpc(session, "Penny"));
        Assert.False(GroupSessionRules.InvolvesNpc(session, "  "));
        Assert.False(GroupSessionRules.InvolvesNpc(null, "Abigail"));

        // 名单被手改丢了的旧档案：按「谁说过话」兜底，不至于整场翻不到。
        var orphan = new GroupChatSessionRecord
        {
            SessionId = "invite-2",
            Participants = Array.Empty<string>(),
            Lines = new[] { Line("Abigail", "我说过话。") },
        };
        Assert.True(GroupSessionRules.InvolvesNpc(orphan, "Abigail"));
    }

    [Fact]
    public void HeaderText_names_every_participant_including_the_silent_one()
    {
        // 场上没说过话的人也必须在抬头里出现 —— 那是「谁在场」的唯一出口
        // （不为它造空气泡，见 ToTimeline）。
        var header = GroupSessionRules.HeaderText(Session("invite-1"));

        Assert.Contains("阿比盖尔", header);
        Assert.Contains("艾米丽", header);
        Assert.Contains("秋 12", header);
        Assert.Contains("主题：最近的小事", header);
        Assert.StartsWith("线上多人对话", header);
    }

    [Fact]
    public void HeaderText_survives_a_session_without_topic_or_date()
    {
        var header = GroupSessionRules.HeaderText(new GroupChatSessionRecord
        {
            SessionId = "invite-1",
            Participants = new[] { "Abigail" },
            Lines = new[] { Line("Abigail", "在。") },
        });

        Assert.Equal("线上多人对话 · Abigail", header);
    }

    // ── F8 时间线 ─────────────────────────────────────────────────────────────

    [Fact]
    public void ToRequestHistory_keeps_the_player_line_and_the_npc_lines_in_order()
    {
        var session = Session("invite-1");

        var history = GroupSessionRules.ToRequestHistory(session.Lines);

        // **原意图**：「面板上画出来的整串」与「发给模型的那一份」要有明确边界，
        // 不能把面板私有的东西（显示序号、空条目）漏进请求体。
        // **为什么新行为更对**：旧行为把这个边界划在「丢玩家行」上（函数名 ToPublicHistory，
        // 只留 NPC），理由是「玩家那句由 message 单独送」——那只在单轮下成立，
        // 第 2 轮起第 1 轮玩家说过的话就再也回不到请求里，模型因此看不到玩家参与过
        // （实测：NPC 会反问玩家从没提过的事）。现在边界改划在「丢掉不可用的行」上：
        // 玩家行与 NPC 行都进，顺序照旧，Bridge 侧本来就支持 speakerType="player"。
        Assert.Equal(
            new[] { "player", "Abigail" },
            history.Select(entry => entry.SpeakerId).ToArray());
        Assert.Equal(
            new[] { "player", "npc" },
            history.Select(entry => entry.SpeakerType).ToArray());
    }

    [Fact]
    public void ToRequestHistory_drops_lines_the_bridge_would_reject()
    {
        // 存档是**外部可编辑的输入**：speakerType 只认 player／npc（Bridge 侧是 Literal），
        // 其余一律按 NPC 处理；没有内容的行与没有 speakerId 的 NPC 行直接丢
        // （Bridge 侧 content／speakerId 都要求非空，留着只会换来 422）。
        var history = GroupSessionRules.ToRequestHistory(new[]
        {
            new GroupDialogueHistoryEntry("PLAYER", "player", "大写也算玩家。"),
            new GroupDialogueHistoryEntry("手改过的值", "Abigail", "未知 speakerType 按 NPC 处理。"),
            new GroupDialogueHistoryEntry("npc", "Abigail", "   "),
            new GroupDialogueHistoryEntry("npc", "  ", "没有 speakerId。"),
            new GroupDialogueHistoryEntry("npc", "Emily", "正常一条。"),
        });

        Assert.Equal(
            new[] { "player", "Abigail", "Emily" },
            history.Select(entry => entry.SpeakerId).ToArray());
        Assert.Equal(
            new[] { "player", "npc", "npc" },
            history.Select(entry => entry.SpeakerType).ToArray());
    }

    [Fact]
    public void Timeline_marks_the_session_start_then_every_line_with_its_speaker()
    {
        var timeline = GroupSessionRules.ToTimeline(
            null,
            new[] { Session("invite-1") },
            "Abigail");

        Assert.Equal(
            new[]
            {
                ChatHistoryRules.SessionRole,
                ChatHistoryRules.PlayerRole,
                ChatHistoryRules.NpcRole,
            },
            timeline.Select(message => message.Role).ToArray());
        // 玩家自己的话有独立气泡（不再是塞进 NPC 转述里的引文）。
        Assert.Equal("你们怎么看？", timeline[1].Content);
        Assert.Equal("player", timeline[1].SpeakerId);
        // 别人的话也在，并且带自己的名字与配色来源。
        Assert.Equal("阿比盖尔", timeline[2].SpeakerName);
        Assert.Equal("Abigail", timeline[2].SpeakerId);
    }

    [Fact]
    public void Timeline_keeps_only_sessions_this_npc_was_in()
    {
        var timeline = GroupSessionRules.ToTimeline(
            null,
            new[]
            {
                Session("invite-1"),
                Session("invite-2") with { Participants = new[] { "Penny" }, Lines = new[] { Line("Penny", "只有我。") } },
            },
            "Abigail");

        Assert.DoesNotContain(timeline, message => message.Content.Contains("只有我。"));
        Assert.Contains(timeline, message => message.Content == "你们怎么看？");
    }

    [Fact]
    public void Timeline_merges_private_history_and_sessions_in_sequence_order()
    {
        var privateHistory = new[]
        {
            Private("user", "私聊第一句", sequence: 1),
            Private("assistant", "私聊第三句", sequence: 3),
        };
        var session = Session("invite-1") with { Sequence = 2 };

        var timeline = GroupSessionRules.ToTimeline(privateHistory, new[] { session }, "Abigail");

        Assert.Equal(
            new[]
            {
                "私聊第一句",
                "线上多人对话 · 阿比盖尔、艾米丽 · 秋 12 · 主题：最近的小事",
                "你们怎么看？",
                "我也这么想。",
                "私聊第三句",
            },
            timeline.Select(message => message.Content).ToArray());
    }

    [Fact]
    public void Timeline_puts_unsequenced_entries_from_old_archives_first()
    {
        // 老档案里没有序号（那时还没有这个概念），它必然比有序号的那批更早。
        var privateHistory = new[]
        {
            Private("user", "老档案里的第一句"),
            Private("assistant", "老档案里的第二句", sequence: 9),
        };

        var timeline = GroupSessionRules.ToTimeline(
            privateHistory,
            new[] { Session("invite-1") with { Sequence = 5 } },
            "Abigail");

        Assert.Equal("老档案里的第一句", timeline[0].Content);
        Assert.Contains(timeline, message => message.Content.Contains("线上多人对话"));
        Assert.Equal("老档案里的第二句", timeline[^1].Content);
    }

    [Fact]
    public void Timeline_drops_blank_content_and_stays_empty_without_any_source()
    {
        Assert.Empty(GroupSessionRules.ToTimeline(null, null, "Abigail"));
        Assert.Empty(GroupSessionRules.ToTimeline(
            new[] { Private("user", "   ") },
            Array.Empty<GroupChatSessionRecord>(),
            "Abigail"));
        // 空场次（一条发言都没有）不该在面板上留下一行光秃秃的抬头。
        Assert.Empty(GroupSessionRules.ToTimeline(
            null,
            new[] { Session("invite-1") with { Lines = Array.Empty<GroupDialogueHistoryEntry>() } },
            "Abigail"));
    }

    private static GroupSessionContext Context(string sessionId) =>
        new(sessionId, "公共话题", "最近的小事", "秋 12", 132);

    // ── 分步揭示（2026-09-21 用户口径）────────────────────────────────────────
    //
    // 用户报了两件事，都落在同一段时序上：
    //   ① 「玩家发一句 → 要**立刻**上屏，像 F8 私聊那样」（改前它和 NPC 回复
    //      挤在同一批追加里，自己刚发的话要等十几秒响应回来才出现）；
    //   ② 「NPC 回复不要同时蹦几条，要一条一条出现，稍微有点间隔」。
    //
    // 于是面板改成两步：玩家那句在发出去之后立刻追加，NPC 回合由
    // GroupTurnRevealQueue 逐条接上。**但最终画面必须与改前那一次调用逐条相同** ——
    // 否则 GroupSessionRules 类注释里那条「场次里那串发言 == F9 界面当时真正画出来的
    // 那串气泡」当场就不成立了（存档那条路是 BridgeClient 一次性写完的，与播放无关）。
    // 下面三条把这条等价性钉死。

    [Fact]
    public void The_player_line_can_be_appended_on_its_own()
    {
        var lines = GroupSessionRules.AppendTurn(
            Array.Empty<GroupDialogueHistoryEntry>(),
            "我先说一句。",
            turns: null);

        var only = Assert.Single(lines);
        Assert.Equal(GroupSessionRules.PlayerSpeakerType, only.SpeakerType);
        Assert.Equal(GroupSessionRules.PlayerSpeakerId, only.SpeakerId);
        Assert.Equal("我先说一句。", only.Content);
    }

    [Fact]
    public void AppendTurn_in_steps_matches_a_single_call()
    {
        var turns = new[]
        {
            new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "我在练鼓。" },
            new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "我在改裙子！" },
        };

        var once = GroupSessionRules.AppendTurn(null, "你们最近忙什么？", turns);

        // 第一步：玩家那句立刻上屏。
        var stepByStep = GroupSessionRules.AppendTurn(null, "你们最近忙什么？", turns: null);
        // 第二步：NPC 回合逐条接上（间隔播放的每一拍各调一次）。
        foreach (var turn in turns)
        {
            stepByStep = GroupSessionRules.AppendTurn(stepByStep, null, new[] { turn });
        }

        Assert.Equal(once.Count, stepByStep.Count);
        Assert.Equal(
            once.Select(line => (line.SpeakerType, line.SpeakerId, line.Content)),
            stepByStep.Select(line => (line.SpeakerType, line.SpeakerId, line.Content)));
    }

    [Fact]
    public void Step_by_step_appending_truncates_exactly_like_a_single_call()
    {
        // 已经满档：单场上限是 120 条，再多就丢最旧的。分步追加每一步都会重做这条
        // 裁剪，所以最终结果必须与一次调用逐条相同（否则逐条播放会把画面越播越错）。
        var existing = Enumerable.Range(0, GroupSessionRules.MaxLinesPerSession)
            .Select(index => Line("Abigail", $"第 {index} 条"))
            .ToArray();
        var turns = new[]
        {
            new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "新的一句。" },
            new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "新的两句。" },
        };

        var once = GroupSessionRules.AppendTurn(existing, "玩家一句。", turns);
        var stepByStep = GroupSessionRules.AppendTurn(existing, "玩家一句。", turns: null);
        foreach (var turn in turns)
        {
            stepByStep = GroupSessionRules.AppendTurn(stepByStep, null, new[] { turn });
        }

        Assert.Equal(GroupSessionRules.MaxLinesPerSession, once.Count);
        Assert.Equal(once.Count, stepByStep.Count);
        Assert.Equal(
            once.Select(line => line.Content),
            stepByStep.Select(line => line.Content));
    }

    /// <summary>
    /// 撤回：这一轮拿不到可用回复时，面板要把先上屏的那句自己收回去
    /// （存档那条路在这种轮次里一条都不写，见
    /// <see cref="GroupSessionRules.Append"/> 的第一个 return）。
    /// 玩家行是纯追加，所以去掉尾部即还原。
    /// </summary>
    [Fact]
    public void Taking_the_player_line_back_restores_the_previous_transcript()
    {
        var before = GroupSessionRules.AppendTurn(
            null,
            "上一轮。",
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "上一轮回复。" } });

        var afterReveal = GroupSessionRules.AppendTurn(before, "这一轮发不出去。", turns: null);
        Assert.Equal(before.Count + 1, afterReveal.Count);

        var rolledBack = afterReveal.Take(before.Count).ToArray();
        Assert.Equal(
            before.Select(line => line.Content),
            rolledBack.Select(line => line.Content));
    }

    private static GroupChatSessionRecord Session(string sessionId)
    {
        return new GroupChatSessionRecord
        {
            SessionId = sessionId,
            Title = "公共话题",
            Topic = "最近的小事",
            DateLabel = "秋 12",
            TotalDays = 132,
            Participants = new[] { "Abigail", "Emily" },
            ParticipantDisplayNames = new[] { "阿比盖尔", "艾米丽" },
            Lines = new[]
            {
                new GroupDialogueHistoryEntry("player", "player", "你们怎么看？"),
                Line("Abigail", "我也这么想。"),
            },
        };
    }

    private static GroupDialogueHistoryEntry Line(string speakerId, string content) =>
        new("npc", speakerId, content);

    private static BridgeDialogueHistoryItem Private(string role, string content, int? sequence = null) =>
        new() { Role = role, Content = content, Sequence = sequence };
}
