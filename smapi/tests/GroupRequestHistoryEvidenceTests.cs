using System.Text.Json;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// **离线证据**：把「群聊两轮下来，SMAPI 真正会发给模型的 request history」导出成 JSON，
/// 供 `bridge` 侧的离线脚本拼进真实 prompt（`.tmp/group-cloud-verify/
/// verify_player_history_in_group_prompt.py`，0 次云端请求）。
///
/// 断点 1 的修复（玩家的话进群聊历史）牵涉两侧：C# 决定**请求体里的 history 长什么样**，
/// Bridge 决定**它最终怎么进 prompt**。只断言 C# 这一侧不足以证明「玩家那几行真的到了模型面前」，
/// 所以这里把 C# 的产物落成文件，让 Bridge 侧用**同一份真实数据**走完
/// `build_group_messages` → messages 这条路，再断言玩家行在 `group_scene` 卡里。
///
/// 写入 `.tmp/`（已 gitignore），不参与断言之外的任何流程；文件缺失也不会让测试失败以外的事发生。
/// </summary>
public sealed class GroupRequestHistoryEvidenceTests
{
    private const string EvidenceRelativePath =
        ".tmp/group-cloud-verify/group-request-history-from-smapi.json";

    private static GroupDialogueInvitationRecord Invitation() => new()
    {
        InvitationId = "invite-cloud-c1",
        TemplateId = "neutral-public-topic",
        Participants = new[] { "Alex", "Shane", "Victor" },
        ParticipantDisplayNames = new[] { "Alex", "Shane", "Victor" },
        Title = "镇上的小事",
        Topic = "最近大家各自忙什么",
        Guidance = "只作为讨论方向。",
        CreatedOn = "Fall 12",
        ExpiresOn = "Fall 19",
        CreatedTotalDays = 132,
        ExpiresTotalDays = 139,
        Source = "periodic",
        Status = GroupInvitationStatus.Accepted,
    };

    [Fact]
    public void The_two_round_request_history_is_exported_for_the_offline_prompt_proof()
    {
        var session = GroupDialogueSessionRules.Create(Invitation());

        // 第 1 轮：玩家问一句，两个 NPC 各接一句（multi_turn 的常态）。
        var round1Message = "你们最近都在忙什么？我这边在攒钱买鸡舍。";
        var afterRound1 = GroupDialogueSessionRules.ApplyResult(
            session,
            round1Message,
            new[]
            {
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Alex",
                    Content = "我最近天天在练球，秋天比赛要来了。",
                    // NPC 把话递回玩家：这一条**会**被名单归一化剔掉（addressedTo 只表达
                    // 「递给了名单里的哪位 NPC」，与 Bridge 侧 `_normalize_addressed_to`
                    // 把 "player" 去掉是同一条口径），所以导出文件里它是空数组 —— 不是丢数据。
                    AddressedTo = new[] { "player" },
                },
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Shane",
                    Content = "鸡舍啊……我那几只够我忙的。",
                    AddressedTo = new[] { "player" },
                },
            },
            fallback: false);

        // 第 2 轮：玩家接着上一轮的话往下说 —— 这一轮请求体里必须能看到第 1 轮玩家那句。
        var round2Message = "那你都喂它们什么？";
        var afterRound2 = GroupDialogueSessionRules.ApplyResult(
            afterRound1,
            round2Message,
            new[]
            {
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Victor",
                    Content = "我插一句：饲料配比其实有讲究。",
                    AddressedTo = new[] { "Shane" },
                },
            },
            fallback: false);

        var payload = new
        {
            generatedBy = "smapi/tests/GroupRequestHistoryEvidenceTests.cs",
            note = "SMAPI 侧真实产物：第二轮请求体里的 history（GroupDialogueSession.PublicHistory）。"
                + "供 Bridge 离线脚本拼进真实 prompt，验证玩家行进了 group_scene 卡。",
            participants = Invitation().Participants,
            invitationTopic = Invitation().Topic,
            round1PlayerMessage = round1Message,
            round2PlayerMessage = round2Message,
            round2RequestHistory = afterRound2.PublicHistory
                .Select(entry => new
                {
                    speakerType = entry.SpeakerType,
                    speakerId = entry.SpeakerId,
                    content = entry.Content,
                    addressedTo = entry.AddressedTo ?? Array.Empty<string>(),
                })
                .ToArray(),
        };

        var path = Path.Combine(RepositoryRoot(), EvidenceRelativePath.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(
            path,
            JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));

        // 导出本身也要钉住形态：第 2 轮的请求历史 = 两轮的玩家话 + 三条 NPC 回合，顺序照旧。
        Assert.Equal(
            new[] { "player", "npc", "npc", "player", "npc" },
            afterRound2.PublicHistory.Select(entry => entry.SpeakerType).ToArray());
        Assert.Equal("player", afterRound2.PublicHistory[3].SpeakerId);
        Assert.Equal(round2Message, afterRound2.PublicHistory[3].Content);
        Assert.True(File.Exists(path), $"证据文件未写出：{path}");
    }

    /// <summary>从测试输出目录往上找到仓库根（含 <c>scripts/verify_project.ps1</c> 的那一层）。</summary>
    private static string RepositoryRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null &&
               !File.Exists(Path.Combine(directory.FullName, "scripts", "verify_project.ps1")))
        {
            directory = directory.Parent;
        }

        return directory?.FullName ?? AppContext.BaseDirectory;
    }
}
