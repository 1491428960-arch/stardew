using System.Diagnostics;
using System.Text;
using StardewAI.NPC;
using Xunit;
using Xunit.Abstractions;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 回看档案的存档载荷（<see cref="ChatHistoryArchive"/>）。
///
/// 2026-09-20：这一份此前只活在内存里，关掉游戏就没了。这里钉住它的落盘往返、
/// 老存档的空手开局、以及「同一个人多个存档之间不串数据」。
/// </summary>
public sealed class ChatHistoryArchiveTests
{
    private readonly ITestOutputHelper output;

    public ChatHistoryArchiveTests(ITestOutputHelper output)
    {
        this.output = output;
    }

    [Fact]
    public void Round_trip_keeps_every_message_in_order()
    {
        var history = new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
        {
            ["Abigail"] = new[]
            {
                new BridgeDialogueHistoryItem { Role = "user", Content = "早上好" },
                new BridgeDialogueHistoryItem
                {
                    Role = "assistant",
                    Content = "早呀，今天去哪儿？",
                    Intent = "chat",
                    RelationshipStage = "friendly",
                },
            },
            ["Emily"] = new[]
            {
                new BridgeDialogueHistoryItem { Role = "assistant", Content = "群里玩家说：“你们怎么看？”" },
            },
        };

        var json = ChatHistoryArchive.Serialize(history, "MyFarm_123456789");
        var loaded = ChatHistoryArchive.Load(json, "MyFarm_123456789");

        Assert.Empty(loaded.Warnings);
        Assert.Equal(2, loaded.History.Count);
        Assert.Equal(3, loaded.MessageCount);

        var abigail = loaded.History["Abigail"];
        Assert.Equal(2, abigail.Count);
        Assert.Equal("user", abigail[0].Role);
        Assert.Equal("早上好", abigail[0].Content);
        Assert.Equal("assistant", abigail[1].Role);
        Assert.Equal("早呀，今天去哪儿？", abigail[1].Content);
        Assert.Equal("chat", abigail[1].Intent);
        Assert.Equal("friendly", abigail[1].RelationshipStage);
    }

    [Fact]
    public void Round_trip_does_not_rewrite_message_text()
    {
        // 面板显示的必须是模型当时看到的那句话：往返不得改动文本（首尾空白也算）。
        var json = ChatHistoryArchive.Serialize(
            new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
            {
                ["Abigail"] = new[]
                {
                    new BridgeDialogueHistoryItem { Role = "user", Content = "  带空格的问句  " },
                },
            },
            "MyFarm_1");

        var spoken = ChatHistoryArchive.Load(json, "MyFarm_1").History["Abigail"];

        Assert.Equal("  带空格的问句  ", Assert.Single(spoken).Content);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Old_save_without_this_data_starts_empty_and_silent(string? json)
    {
        // 老存档没有这份数据是常态：空手开局，而且不该刷降级警告。
        var loaded = ChatHistoryArchive.Load(json, "MyFarm_1");

        Assert.Empty(loaded.History);
        Assert.Equal(0, loaded.MessageCount);
        Assert.Empty(loaded.Warnings);
    }

    [Theory]
    [InlineData("{ this is not json")]
    [InlineData("[]")]
    [InlineData("42")]
    public void Broken_payload_degrades_to_empty_with_a_warning(string json)
    {
        var loaded = ChatHistoryArchive.Load(json, "MyFarm_1");

        Assert.Empty(loaded.History);
        Assert.Single(loaded.Warnings);
        Assert.Equal(0, loaded.MessageCount);
    }

    [Fact]
    public void Json_null_literal_degrades_to_empty()
    {
        var loaded = ChatHistoryArchive.Load("null", "MyFarm_1");

        Assert.Empty(loaded.History);
        Assert.Empty(loaded.Warnings);
    }

    [Fact]
    public void Unsupported_schema_version_is_rejected()
    {
        var loaded = ChatHistoryArchive.Load(
            "{\"schemaVersion\":99,\"saveId\":\"1\",\"byNpc\":{}}",
            "MyFarm_1");

        Assert.Empty(loaded.History);
        Assert.Contains(loaded.Warnings, warning => warning.Contains("schema version"));
    }

    [Fact]
    public void Archive_from_another_save_is_dropped()
    {
        // 同一个人可能有多个存档：A 存档的记录不能翻到 B 存档里去。
        var json = ChatHistoryArchive.Serialize(HistoryFor("Abigail", 3), "MyFarm_111");

        var loaded = ChatHistoryArchive.Load(json, "OtherFarm_222");

        Assert.Empty(loaded.History);
        Assert.Equal(0, loaded.MessageCount);
        Assert.Contains(loaded.Warnings, warning => warning.Contains("another save"));
    }

    [Fact]
    public void Renaming_a_save_keeps_its_history()
    {
        // 玩家可以在载入界面给存档改名（文件夹名 MyFarm_111 → 星空农场_111）。
        // 标识取的是下划线之后的存档 ID，改名不该把历史判成「别的存档」。
        var json = ChatHistoryArchive.Serialize(HistoryFor("Abigail", 3), "MyFarm_111");

        var loaded = ChatHistoryArchive.Load(json, "星空农场_111");

        Assert.Empty(loaded.Warnings);
        Assert.Equal(3, loaded.MessageCount);
    }

    [Theory]
    [InlineData("MyFarm_123456789", "123456789")]
    [InlineData("My_Farm_987", "987")]
    [InlineData("NoSeparator", "NoSeparator")]
    [InlineData(null, null)]
    [InlineData("   ", null)]
    public void Save_id_is_read_from_the_folder_name(string? folderName, string? expected)
    {
        Assert.Equal(expected, ChatHistoryArchive.SaveIdFromFolderName(folderName));
    }

    [Fact]
    public void Archive_still_loads_when_a_save_folder_is_unknown()
    {
        // 存档标识是第二道保险，不是门禁：任一侧拿不到名字时放行，
        // 免得因为取不到名字把玩家自己的记录丢掉。
        var withoutFolder = ChatHistoryArchive.Serialize(HistoryFor("Abigail", 3), null);
        Assert.Equal(3, ChatHistoryArchive.Load(withoutFolder, "FarmB_222").MessageCount);

        var withFolder = ChatHistoryArchive.Serialize(HistoryFor("Abigail", 3), "FarmA_111");
        Assert.Equal(3, ChatHistoryArchive.Load(withFolder, null).MessageCount);
    }

    [Fact]
    public void Load_trims_each_npc_to_the_display_limit_keeping_the_latest()
    {
        var items = Enumerable.Range(0, ChatHistoryRules.MaxDisplayMessages + 15)
            .Select(index => new BridgeDialogueHistoryItem { Role = "user", Content = $"第{index}句" })
            .ToArray();
        var json = ChatHistoryArchive.Serialize(
            new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
            {
                ["Abigail"] = items,
            },
            "MyFarm_1");

        var spoken = ChatHistoryArchive.Load(json, "MyFarm_1").History["Abigail"];

        Assert.Equal(ChatHistoryRules.MaxDisplayMessages, spoken.Count);
        Assert.Equal("第15句", spoken[0].Content);
        Assert.Equal($"第{ChatHistoryRules.MaxDisplayMessages + 14}句", spoken[^1].Content);
    }

    [Fact]
    public void Blank_entries_are_dropped_and_oversized_content_is_trimmed()
    {
        // 存档是可被外部编辑的输入：规格外的内容在载入时被裁掉，不能让一条脏数据撑爆面板。
        var oversized = new string('长', ChatHistoryRules.MaxContentLength + 260);
        var json = "{\"schemaVersion\":1,\"saveId\":\"1\",\"byNpc\":{\"Abigail\":["
            + "{\"role\":\"user\",\"content\":\"   \"},"
            + "{\"role\":\"assistant\",\"content\":\"" + oversized + "\"},"
            + "{\"role\":\"user\",\"content\":\"留下的一句\"}]}}";

        var spoken = ChatHistoryArchive.Load(json, "MyFarm_1").History["Abigail"];

        Assert.Equal(2, spoken.Count);
        Assert.Equal(ChatHistoryRules.MaxContentLength, spoken[0].Content.Length);
        Assert.Equal("留下的一句", spoken[1].Content);
    }

    [Fact]
    public void Empty_and_null_history_serialize_into_a_loadable_payload()
    {
        var json = ChatHistoryArchive.Serialize(null, null);
        var loaded = ChatHistoryArchive.Load(json, "MyFarm_1");

        Assert.False(string.IsNullOrWhiteSpace(json));
        Assert.Empty(loaded.History);
        Assert.Empty(loaded.Warnings);
    }

    [Fact]
    public void Chinese_stays_readable_instead_of_being_escaped()
    {
        // 满档约 1 MB，默认编码器会把每个中文字转义成 \uXXXX（6 字节），体积几乎翻倍。
        var json = ChatHistoryArchive.Serialize(HistoryFor("Abigail", 2), "MyFarm_1");

        Assert.Contains("早上好", json);
        Assert.DoesNotContain("\\u", json);
    }

    [Fact]
    public void Full_capacity_archive_stays_within_the_size_and_time_budget()
    {
        // 满档：20 位 NPC × 1000 条 × 240 字 —— 写入端能达到的上限，
        // 直接决定存档会长大多少、Saving 时要多花多久。数字打在测试输出里备查。
        // 2026-09-21 上限由 60 提到 1000：这个用例的绝对体积也跟着涨了约 16 倍。
        const int npcCount = 20;
        var content = new string('聊', ChatHistoryRules.MaxContentLength);
        var history = new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal);
        for (var npc = 0; npc < npcCount; npc++)
        {
            history[$"Npc{npc}"] = Enumerable.Range(0, ChatHistoryRules.MaxDisplayMessages)
                .Select(index => new BridgeDialogueHistoryItem
                {
                    Role = index % 2 == 0 ? "user" : "assistant",
                    Content = content,
                    Intent = "chat",
                    RelationshipStage = "friendly",
                })
                .ToArray();
        }

        // 预热一次：首轮包含 JIT，量出来的是冷启动成本而不是这份数据的成本。
        // 正式测量取三轮里最快的一轮，避开机器上其它任务的干扰（量的是量级，不做性能门禁）。
        var warmup = ChatHistoryArchive.Serialize(history, "MyFarm_123456789");
        _ = ChatHistoryArchive.Load(warmup, "MyFarm_123456789");

        string json = warmup;
        var serializeMs = double.MaxValue;
        var loadMs = double.MaxValue;
        for (var round = 0; round < 3; round++)
        {
            var serializeWatch = Stopwatch.StartNew();
            json = ChatHistoryArchive.Serialize(history, "MyFarm_123456789");
            serializeWatch.Stop();

            var loadWatch = Stopwatch.StartNew();
            _ = ChatHistoryArchive.Load(json, "MyFarm_123456789");
            loadWatch.Stop();

            serializeMs = Math.Min(serializeMs, serializeWatch.Elapsed.TotalMilliseconds);
            loadMs = Math.Min(loadMs, loadWatch.Elapsed.TotalMilliseconds);
        }

        var loaded = ChatHistoryArchive.Load(json, "MyFarm_123456789");

        var bytes = Encoding.UTF8.GetByteCount(json);
        output.WriteLine(
            $"满档回看档案：NPC={npcCount}；条数={loaded.MessageCount}；"
            + $"JSON 字符={json.Length}；UTF8 字节={bytes}（{bytes / 1024.0 / 1024.0:0.00} MB）；"
            + $"序列化={serializeMs:0.0} ms；反序列化={loadMs:0.0} ms（各取三轮最快）");

        Assert.Equal(npcCount * ChatHistoryRules.MaxDisplayMessages, loaded.MessageCount);
        Assert.Equal(npcCount, loaded.History.Count);

        // 15 MB 量级：涨到几十 MB 说明规格变了，宁可在这里红一次，也别到存档里才发现。
        Assert.InRange(bytes, 13 * 1024 * 1024, 20 * 1024 * 1024);

        // 宽松上限：这里量的是量级不是性能门禁（机器会抖），卡住的是「别写成秒级」。
        Assert.True(serializeMs < 5000);
        Assert.True(loadMs < 5000);
    }

    [Fact]
    public void Realistic_five_npc_archive_stays_within_the_size_and_time_budget()
    {
        // 现实规模：只跟 5 位 NPC 深聊到 1000 条，且单条长度取真实分布
        // （玩家提问约 12 字、NPC 回应约 60 字），而不是 240 字的极端值。
        // 满档用例量的是上限，这一条量的是「玩家真这么聊会长多大」。
        const int npcCount = 5;
        const int playerMessageLength = 12;
        const int npcMessageLength = 60;
        var playerMessage = new string('问', playerMessageLength);
        var npcMessage = new string('答', npcMessageLength);
        var history = new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal);
        for (var npc = 0; npc < npcCount; npc++)
        {
            history[$"Npc{npc}"] = Enumerable.Range(0, ChatHistoryRules.MaxDisplayMessages)
                .Select(index => new BridgeDialogueHistoryItem
                {
                    Role = index % 2 == 0 ? "user" : "assistant",
                    Content = index % 2 == 0 ? playerMessage : npcMessage,
                    Intent = "chat",
                    RelationshipStage = "friendly",
                })
                .ToArray();
        }

        var warmup = ChatHistoryArchive.Serialize(history, "MyFarm_123456789");
        _ = ChatHistoryArchive.Load(warmup, "MyFarm_123456789");

        string json = warmup;
        var serializeMs = double.MaxValue;
        var loadMs = double.MaxValue;
        for (var round = 0; round < 3; round++)
        {
            var serializeWatch = Stopwatch.StartNew();
            json = ChatHistoryArchive.Serialize(history, "MyFarm_123456789");
            serializeWatch.Stop();

            var loadWatch = Stopwatch.StartNew();
            _ = ChatHistoryArchive.Load(json, "MyFarm_123456789");
            loadWatch.Stop();

            serializeMs = Math.Min(serializeMs, serializeWatch.Elapsed.TotalMilliseconds);
            loadMs = Math.Min(loadMs, loadWatch.Elapsed.TotalMilliseconds);
        }

        var loaded = ChatHistoryArchive.Load(json, "MyFarm_123456789");
        var bytes = Encoding.UTF8.GetByteCount(json);
        output.WriteLine(
            $"现实规模回看档案（{npcCount} 位 NPC 满 1000 条、玩家 {playerMessageLength} 字 / NPC {npcMessageLength} 字）："
            + $"条数={loaded.MessageCount}；UTF8 字节={bytes}（{bytes / 1024.0 / 1024.0:0.00} MB）；"
            + $"序列化={serializeMs:0.0} ms；反序列化={loadMs:0.0} ms（各取三轮最快）");

        Assert.Equal(npcCount * ChatHistoryRules.MaxDisplayMessages, loaded.MessageCount);

        // 1 MB 量级：五位 NPC 聊满也只是一部手机照片的大小，属于「存档能承受」的那一档。
        Assert.InRange(bytes, 600 * 1024, 2 * 1024 * 1024);
        Assert.True(serializeMs < 2000);
        Assert.True(loadMs < 2000);
    }

    private static Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>> HistoryFor(
        string npcId,
        int count)
    {
        return new Dictionary<string, IReadOnlyList<BridgeDialogueHistoryItem>>(StringComparer.Ordinal)
        {
            [npcId] = Enumerable.Range(0, count)
                .Select(index => new BridgeDialogueHistoryItem
                {
                    Role = index % 2 == 0 ? "user" : "assistant",
                    Content = index % 2 == 0 ? $"早上好{index}" : $"你也好{index}",
                })
                .ToArray(),
        };
    }
}
