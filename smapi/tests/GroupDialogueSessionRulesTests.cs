using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class GroupDialogueSessionRulesTests
{
    [Fact]
    public void Successful_first_turn_completes_accepted_invitation()
    {
        var invitation = AcceptedInvitation();

        var next = GroupDialogueSessionRules.ApplyResult(
            invitation,
            new[]
            {
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Abigail",
                    Content = "我有点想知道。",
                },
            },
            fallback: false);

        Assert.Equal(GroupInvitationStatus.Completed, next.Status);
    }

    [Fact]
    public void Failed_turn_keeps_invitation_retryable_and_drops_history()
    {
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());

        var result = GroupDialogueSessionRules.ApplyResult(
            session,
            "你们怎么看？",
            Array.Empty<BridgeGroupTurn>(),
            fallback: true);

        // 失败轮连**玩家那句也不写**：面板这时会把自己的气泡撤回、存档也不建场次
        // （GroupSessionRules.Append 的同一条判据），请求历史若留着它，三者立刻不一致。
        Assert.Empty(result.PublicHistory);
        Assert.True(result.CanRetry);
        Assert.Equal(GroupInvitationStatus.Accepted, result.Invitation.Status);
    }

    [Fact]
    public void Multi_turn_replies_all_land_in_public_history_in_order()
    {
        // 策略切成 multi_turn 之后，一次请求返回 2～3 个回合是常态。
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());

        var result = GroupDialogueSessionRules.ApplyResult(
            session,
            "你们怎么看？",
            new[]
            {
                new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "我会放点吵的。" },
                new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "那我挑安静的。" },
                new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "那就一人一首。" },
            },
            fallback: false);

        // **原意图**：一次请求里的多个回合要按模型给出的顺序原样进历史，不能丢、不能重排。
        // **为什么新行为更对**：现在玩家那句也在序列最前面 —— 它就是这一轮里最先发生的事。
        // 旧断言（只有 3 条 NPC）钉住的是「玩家话不进历史」这个已被证伪的口径。
        Assert.Equal(
            new[] { "player", "Abigail", "Emily", "Abigail" },
            result.PublicHistory.Select(entry => entry.SpeakerId).ToArray());
        Assert.Equal("player", result.PublicHistory[0].SpeakerType);
        Assert.Equal("你们怎么看？", result.PublicHistory[0].Content);
        Assert.All(
            result.PublicHistory.Skip(1),
            entry => Assert.Equal("npc", entry.SpeakerType));
        Assert.Equal(GroupInvitationStatus.Completed, result.Invitation.Status);
        Assert.False(result.CanRetry);
    }

    [Fact]
    public void Opening_turn_adds_no_player_line()
    {
        // 开场那一轮玩家一句话都没说（Bridge 侧「空消息 ⇒ 开场」）：历史里不该凭空
        // 多出一条空的玩家行 —— Bridge 侧 content 要求非空，而且那等于替玩家编了一句话。
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());

        var result = GroupDialogueSessionRules.ApplyResult(
            session,
            playerMessage: null,
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "我先说个事。" } },
            fallback: false);

        Assert.Equal(
            new[] { "Abigail" },
            result.PublicHistory.Select(entry => entry.SpeakerId).ToArray());
    }

    [Fact]
    public void The_player_line_from_the_previous_turn_survives_into_the_next_request()
    {
        // ★ 本次修复的核心：多轮下，第 1 轮玩家说过的话必须在第 2 轮的请求历史里。
        // 改前 ApplyResult 只追加 NPC 回合，玩家那句从不进历史 —— 第 2 轮起模型
        // 就再也看不到玩家参与过这场对话（真机实测：NPC 反问玩家从没提过的事）。
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());
        var first = GroupDialogueSessionRules.ApplyResult(
            session,
            "我最近在攒钱买鸡舍。",
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "养鸡好玩。" } },
            fallback: false);

        var second = GroupDialogueSessionRules.ApplyResult(
            first,
            "那你们呢？",
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "我在挑布料。" } },
            fallback: false);

        Assert.Equal(
            new[] { "player", "Abigail", "player", "Emily" },
            second.PublicHistory.Select(entry => entry.SpeakerId).ToArray());
        Assert.Contains(
            second.PublicHistory,
            entry => entry.SpeakerType == "player" &&
                     entry.Content == "我最近在攒钱买鸡舍。");
    }

    [Fact]
    public void One_unknown_speaker_rejects_the_whole_batch()
    {
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());

        var result = GroupDialogueSessionRules.ApplyResult(
            session,
            "你们怎么看？",
            new[]
            {
                new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "我先说。" },
                new BridgeGroupTurn { SpeakerNpcId = "Lewis", Content = "名单外的人不该出现。" },
            },
            fallback: false);

        // 整批拒绝时**连玩家那句都不进**：这一轮在面板上等于没发生（玩家气泡被撤回，
        // 存档一条不写），历史里留一句玩家话会让模型以为玩家说过、NPC 没接。
        Assert.Empty(result.PublicHistory);
        Assert.True(result.CanRetry);
        Assert.Equal(GroupInvitationStatus.Accepted, result.Invitation.Status);
    }

    [Fact]
    public void Addressed_targets_outside_the_roster_are_dropped_but_kept_in_order()
    {
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());

        var result = GroupDialogueSessionRules.ApplyResult(
            session,
            "你们怎么看？",
            new[]
            {
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Abigail",
                    Content = "Emily 你呢？",
                    AddressedTo = new[] { "Emily", "outsider", "emily" },
                },
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Emily",
                    Content = "我在挑布料。",
                    AddressedTo = new[] { "player" },
                },
            },
            fallback: false);

        // **原意图**：addressedTo 要按在场名单归一化 —— 名单外的目标丢掉，
        // 同一个人写成 "Emily"/"emily" 两种拼法只留一份规范写法。
        // **为什么索引变了**：历史里现在多了一条玩家行（它在最前面），
        // 归一化这件事本身一点没变，所以下面比对的是 `…[1]`／`…[2]`。
        Assert.Equal("player", result.PublicHistory[0].SpeakerType);
        Assert.Equal(new[] { "Emily" }, result.PublicHistory[1].AddressedTo);
        Assert.Empty(result.PublicHistory[2].AddressedTo!);
    }

    [Fact]
    public void A_second_batch_appends_to_the_existing_public_history()
    {
        var session = GroupDialogueSessionRules.Create(AcceptedInvitation());
        var first = GroupDialogueSessionRules.ApplyResult(
            session,
            "第一轮玩家话。",
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Abigail", Content = "第一轮。" } },
            fallback: false);

        var second = GroupDialogueSessionRules.ApplyResult(
            first,
            "第二轮玩家话。",
            new[] { new BridgeGroupTurn { SpeakerNpcId = "Emily", Content = "第二轮。" } },
            fallback: false);

        // **原意图**：第二次结果要**接在**已有历史后面，而不是把前面的覆盖掉。
        // **为什么新行为更对**：接着写的东西现在包括两轮的玩家话 —— 覆盖轮数虽然变多，
        // 但顺序仍是真实的发言顺序（玩家先说、NPC 后接）。
        Assert.Equal(
            new[] { "player", "Abigail", "player", "Emily" },
            second.PublicHistory.Select(entry => entry.SpeakerId).ToArray());
    }

    [Fact]
    public void Reopening_a_session_restores_the_history_from_the_archive()
    {
        // 2026-09-21（群聊场次）：关掉 F9 再进来接的是同一场，不再是空白。
        var restored = new[]
        {
            new GroupDialogueHistoryEntry("player", "player", "你们怎么看？"),
            new GroupDialogueHistoryEntry("npc", "Abigail", "我有点想知道。"),
            new GroupDialogueHistoryEntry("npc", "Emily", "我也想听。"),
        };

        var session = GroupDialogueSessionRules.Create(AcceptedInvitation(), restored);

        // **原意图**：续读要接回**同一串发言**，不是从空开始；顺序与内容都不能被改写。
        // **为什么新行为更对**：续读前玩家说过的话也要接回来 —— 旧断言钉的是
        // 「续读时把玩家行滤掉」，于是一关菜单再进来，玩家此前说过的话在请求里全丢，
        // 而存档里明明还留着（"记了，但请求侧把它丢了"）。
        // 面板那份来自 visibleMessages（构造时 AddRange(restored)），与这里读的
        // PublicHistory 是两个容器 ⇒ 玩家那句仍然只画一次。
        Assert.Equal(
            new[] { "player", "Abigail", "Emily" },
            session.PublicHistory.Select(entry => entry.SpeakerId).ToArray());
        Assert.Equal(
            new[] { "player", "npc", "npc" },
            session.PublicHistory.Select(entry => entry.SpeakerType).ToArray());
        // 已经有历史了，就不要再自动开场（否则重开一次就会多出一次 NPC 起头）。
        Assert.False(GroupDialogueSessionRules.ShouldOpenWithNpc(session, openingAlreadyRequested: false));
        Assert.True(GroupDialogueSessionRules.ShouldOpenWithNpc(
            GroupDialogueSessionRules.Create(AcceptedInvitation()),
            openingAlreadyRequested: false));
    }

    [Fact]
    public void A_restored_session_with_only_a_player_line_still_counts_as_history()
    {
        // 边界：存档里只有玩家行（手改过的存档也可能这样）时，历史非空 ⇒ 不该再自动开场
        // ——否则会在玩家已经说过话的场次里让 NPC 重新起一次头。
        var session = GroupDialogueSessionRules.Create(
            AcceptedInvitation(),
            new[] { new GroupDialogueHistoryEntry("player", "player", "我先说一句。") });

        Assert.Single(session.PublicHistory);
        Assert.False(GroupDialogueSessionRules.ShouldOpenWithNpc(session, openingAlreadyRequested: false));
    }

    private static GroupDialogueInvitationRecord AcceptedInvitation() => new()
    {
        InvitationId = "invite-1",
        TemplateId = "neutral-public-topic",
        Participants = new[] { "Abigail", "Emily" },
        ParticipantDisplayNames = new[] { "Abigail", "Emily" },
        Title = "公共话题",
        Topic = "最近的公共小事",
        Guidance = "只作为讨论方向。",
        CreatedOn = "Spring 20",
        ExpiresOn = "Spring 27",
        CreatedTotalDays = 20,
        ExpiresTotalDays = 27,
        Source = "periodic",
        Status = GroupInvitationStatus.Accepted,
    };
}
