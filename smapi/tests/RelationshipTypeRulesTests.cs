using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

/// <summary>
/// 审计 #39：<c>relationType</c> 白名单此前有三份（校验两份、亲吻一份），
/// 成员一致但比较口径不同。这里钉住收敛后的行为：**成员表只有一份，
/// 两个比较口径各自保持改前的语义**（含那句“同一句 Dating 校验拒绝、亲吻接受”）。
/// </summary>
public sealed class RelationshipTypeRulesTests
{
    [Theory]
    [InlineData("dating", true)]
    [InlineData("engaged", true)]
    [InlineData("married", true)]
    // 存档校验口径（StoryStateValidation / StoryStateStore 原本的 Ordinal 比较）
    [InlineData("Dating", false)]
    [InlineData("MARRIED", false)]
    [InlineData(" dating ", false)]
    [InlineData("friend", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    public void Supported_matches_the_original_ordinal_whitelist(string? relationType, bool expected)
    {
        Assert.Equal(expected, RelationshipTypeRules.IsSupported(relationType));
    }

    [Theory]
    [InlineData("dating", true)]
    [InlineData("engaged", true)]
    [InlineData("married", true)]
    // 亲吻口径（KissInteractionRules 原本的 OrdinalIgnoreCase + Trim）
    [InlineData("Dating", true)]
    [InlineData("MARRIED", true)]
    [InlineData(" dating ", true)]
    [InlineData("friend", false)]
    [InlineData("engaged ", true)]
    [InlineData("", false)]
    [InlineData(null, false)]
    public void Romantic_matches_the_original_case_insensitive_whitelist(string? relationType, bool expected)
    {
        Assert.Equal(expected, RelationshipTypeRules.IsRomantic(relationType));
    }

    /// <summary>
    /// 口径差异是**有意的保留**（改它会改变行为），因此必须有测试钉住，
    /// 免得后来者以为“已经统一成一个口径”而顺手改掉一侧。
    /// </summary>
    [Fact]
    public void The_documented_case_sensitivity_difference_survives()
    {
        Assert.False(RelationshipTypeRules.IsSupported("Dating"));
        Assert.True(RelationshipTypeRules.IsRomantic("Dating"));
    }

    [Fact]
    public void Validation_rejects_the_uppercase_form_while_the_kiss_gate_accepts_it()
    {
        var view = new RelationshipViewRecord
        {
            OwnerNpcId = "Abigail",
            SubjectNpcId = "player",
            RelationType = "Dating",
            Visibility = "known",
            Source = "player_statement",
        };

        Assert.Contains("relationType is invalid", StoryStateValidation.Validate(view));

        Assert.False(RelationshipTypeRules.IsSupported(view.RelationType));
        Assert.True(RelationshipTypeRules.IsRomantic(view.RelationType));
    }

    [Fact]
    public void Validation_accepts_the_canonical_form()
    {
        var view = new RelationshipViewRecord
        {
            OwnerNpcId = "Abigail",
            SubjectNpcId = "player",
            RelationType = "dating",
            Visibility = "known",
            Source = "player_statement",
        };

        Assert.DoesNotContain("relationType is invalid", StoryStateValidation.Validate(view));
    }
}
