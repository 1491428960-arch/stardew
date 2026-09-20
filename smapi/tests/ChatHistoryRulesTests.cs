using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// F8 面板「往上翻历史」的显示规则（<see cref="ChatHistoryRules"/>）。
///
/// 2026-09-20：Bridge 侧一直在累积真实对话，但打开面板时没有铺进消息区——
/// 于是模型看得见、玩家看不见。这里钉住映射与裁剪，保证只补显示、不动发送。
/// </summary>
public sealed class ChatHistoryRulesTests
{
    [Fact]
    public void Maps_user_to_player_and_assistant_to_npc()
    {
        var messages = ChatHistoryRules.ToDisplayMessages(new[]
        {
            new BridgeDialogueHistoryItem { Role = "user", Content = "你好" },
            new BridgeDialogueHistoryItem { Role = "assistant", Content = "你也好" },
        });

        Assert.Equal(2, messages.Count);
        Assert.Equal(new ChatDisplayMessage("player", "你好"), messages[0]);
        Assert.Equal(new ChatDisplayMessage("npc", "你也好"), messages[1]);
    }

    [Fact]
    public void Group_summary_shows_up_as_an_npc_message()
    {
        // 群聊记录按「本人发言合并成一条」写进同一个历史，role 是 assistant。
        var messages = ChatHistoryRules.ToDisplayMessages(new[]
        {
            new BridgeDialogueHistoryItem
            {
                Role = "assistant",
                Content = "群里玩家说：“你们怎么看？”；我回应：“我觉得还行。”",
            },
        });

        var message = Assert.Single(messages);
        Assert.Equal("npc", message.Role);
        Assert.Contains("群里玩家说", message.Content);
    }

    [Fact]
    public void Blank_entries_are_dropped()
    {
        var messages = ChatHistoryRules.ToDisplayMessages(new[]
        {
            new BridgeDialogueHistoryItem { Role = "user", Content = "   " },
            new BridgeDialogueHistoryItem { Role = "assistant", Content = string.Empty },
            new BridgeDialogueHistoryItem { Role = "user", Content = "留下的一句" },
        });

        Assert.Equal("留下的一句", Assert.Single(messages).Content);
    }

    [Fact]
    public void Keeps_the_latest_entries_when_over_the_cap()
    {
        var history = Enumerable.Range(0, ChatHistoryRules.MaxDisplayMessages + 20)
            .Select(index => new BridgeDialogueHistoryItem
            {
                Role = "user",
                Content = $"第{index}句",
            })
            .ToArray();

        var messages = ChatHistoryRules.ToDisplayMessages(history);

        Assert.Equal(ChatHistoryRules.MaxDisplayMessages, messages.Count);
        Assert.Equal("第20句", messages[0].Content);
        Assert.Equal($"第{ChatHistoryRules.MaxDisplayMessages + 19}句", messages[^1].Content);
    }

    [Fact]
    public void Display_cap_is_longer_than_the_window_sent_to_the_model()
    {
        // 回看必须比发给模型的窗口（BridgeClient 的 6 条）长，
        // 否则「往上翻」翻不出任何东西。
        Assert.True(ChatHistoryRules.MaxDisplayMessages > 6);
    }

    [Fact]
    public void Display_cap_is_pinned_at_the_value_the_player_asked_for()
    {
        // 2026-09-21 用户拍板：60 条翻不回「上周那次」，先定 1000。
        // 这条断言是防回退的护栏——这个常量同时是存档体积的上限，
        // 改大改小都要重新量一遍（见 ChatHistoryArchiveTests 的两条预算用例）。
        Assert.Equal(1000, ChatHistoryRules.MaxDisplayMessages);
    }

    [Fact]
    public void Missing_or_empty_history_returns_nothing()
    {
        Assert.Empty(ChatHistoryRules.ToDisplayMessages(null));
        Assert.Empty(ChatHistoryRules.ToDisplayMessages(Array.Empty<BridgeDialogueHistoryItem>()));
        Assert.Empty(ChatHistoryRules.ToDisplayMessages(
            new[] { new BridgeDialogueHistoryItem { Role = "user", Content = "你好" } },
            maximumCount: 0));
    }
}
