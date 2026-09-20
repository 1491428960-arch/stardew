using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 审计 #42：住宅门「放行」参数此前有两个编码形态、四份字面量。
/// 这里钉住收敛后的取值，并锁住两条路径确实取自同一份定义。
/// </summary>
public sealed class ResidentialDoorGateRulesTests
{
    [Fact]
    public void Relaxed_values_match_the_literals_used_before()
    {
        var previousNpcToken = string.Empty;
        var previousFriendshipToken = "0";
        var relaxedNpcToken = ResidentialDoorGateRules.RelaxedRequiredNpcToken;
        var relaxedFriendshipToken = ResidentialDoorGateRules.RelaxedMinimumFriendshipToken;

        Assert.Equal(600, ResidentialDoorGateRules.RelaxedOpenTime);
        Assert.Equal(2600, ResidentialDoorGateRules.RelaxedCloseTime);
        Assert.Null(ResidentialDoorGateRules.RelaxedRequiredNpcArgument);
        Assert.Equal(-1, ResidentialDoorGateRules.RelaxedMinimumFriendshipArgument);
        Assert.Equal(previousNpcToken, relaxedNpcToken);
        Assert.Equal(previousFriendshipToken, relaxedFriendshipToken);
    }

    [Fact]
    public void Action_token_rewrite_writes_exactly_the_shared_values()
    {
        var tokens = new[]
        {
            "LockedDoorWarp", "5", "9", "WizardHouse",
            "900", "2300", "Wizard", "500",
        };

        Assert.True(DoorActionParser.RelaxResidentialGate(tokens));

        Assert.Equal(
            ResidentialDoorGateRules.RelaxedOpenTime.ToString(System.Globalization.CultureInfo.InvariantCulture),
            tokens[4]);
        Assert.Equal(
            ResidentialDoorGateRules.RelaxedCloseTime.ToString(System.Globalization.CultureInfo.InvariantCulture),
            tokens[5]);
        Assert.Equal(ResidentialDoorGateRules.RelaxedRequiredNpcToken, tokens[6]);
        Assert.Equal(ResidentialDoorGateRules.RelaxedMinimumFriendshipToken, tokens[7]);
    }

    /// <summary>
    /// 放行后 token[6] 被清空，因此**再解析**会失败——这是改动前就有的既有行为
    /// （<see cref="DoorActionParser.TryParse"/> 要求居民 token 非空白），
    /// 这里把它记录下来，避免以后被误当作回归。
    /// </summary>
    [Fact]
    public void Relaxed_action_is_no_longer_re_parsable_because_the_resident_token_is_cleared()
    {
        var tokens = new[]
        {
            "LockedDoorWarp", "5", "9", "WizardHouse",
            "900", "2300", "Wizard", "500",
        };

        Assert.True(DoorActionParser.TryParse(tokens, out _));
        Assert.True(DoorActionParser.RelaxResidentialGate(tokens));
        Assert.False(DoorActionParser.TryParse(tokens, out _));
    }

    [Fact]
    public void Six_token_actions_keep_their_length()
    {
        var tokens = new[] { "LockedDoorWarp", "5", "9", "WizardHouse", "900", "2300" };

        Assert.True(DoorActionParser.RelaxResidentialGate(tokens));

        Assert.Equal(6, tokens.Length);
        Assert.Equal(
            ResidentialDoorGateRules.RelaxedOpenTime.ToString(System.Globalization.CultureInfo.InvariantCulture),
            tokens[4]);
        Assert.Equal(
            ResidentialDoorGateRules.RelaxedCloseTime.ToString(System.Globalization.CultureInfo.InvariantCulture),
            tokens[5]);
    }
}
