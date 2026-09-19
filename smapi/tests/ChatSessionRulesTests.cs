using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class ChatSessionRulesTests
{
    [Fact]
    public void Non_fallback_non_empty_response_counts_as_effective()
    {
        var response = new BridgeDialogueResponse
        {
            Reply = "我听到了。",
            Provider = "cloud",
        };

        Assert.True(ChatSessionRules.IsEffectiveResponse(
            new ConversationTurnResult(response, Recorded: false)));
    }

    [Fact]
    public void Fallback_response_does_not_count_even_when_it_contains_text()
    {
        var response = new BridgeDialogueResponse
        {
            Reply = "暂时联系不上她，可以稍后重试。",
            Provider = "offline",
            Fallback = true,
        };

        Assert.False(ChatSessionRules.IsEffectiveResponse(
            new ConversationTurnResult(response, Recorded: false)));
    }

    [Fact]
    public void Empty_response_does_not_count()
    {
        var response = new BridgeDialogueResponse
        {
            Reply = "   ",
            Provider = "cloud",
        };

        Assert.False(ChatSessionRules.IsEffectiveResponse(
            new ConversationTurnResult(response, Recorded: false)));
    }
}
