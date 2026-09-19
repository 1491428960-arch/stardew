using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class KnownNpcResolverTests
{
    private static KnownNpc? ResolveTarget(string npcId) => npcId switch
    {
        "Abigail" => new KnownNpc("Abigail", "阿比盖尔"),
        "Emily" => new KnownNpc("Emily", "艾米丽"),
        "Throws" => throw new InvalidOperationException("解析失败"),
        "NoDisplay" => new KnownNpc("NoDisplay", "   "),
        _ => null,
    };

    [Fact]
    public void Null_keys_yield_an_empty_list()
    {
        Assert.Empty(KnownNpcResolver.Resolve(null, ResolveTarget));
    }

    [Fact]
    public void Blank_player_and_test_npc_keys_are_skipped()
    {
        var result = KnownNpcResolver.Resolve(
            // 不传 null 元素：集合本身可空由另一条测试覆盖，元素的可空性已被参数签名排除
            // （传 null 会触发 CS8620 可空性警告，而实现也不接受 null 元素）。
            new[] { "player", "PLAYER", "   ", TestNpcPlacementRules.InternalName, "Abigail" },
            ResolveTarget);

        Assert.Equal(new[] { "Abigail" }, result.Select(item => item.NpcId).ToArray());
    }

    [Fact]
    public void Duplicate_keys_are_collapsed_case_insensitively()
    {
        var result = KnownNpcResolver.Resolve(
            new[] { "Abigail", "  abigail ", "Emily", "emily" },
            ResolveTarget);

        Assert.Equal(new[] { "Abigail", "Emily" }, result.Select(item => item.NpcId).ToArray());
    }

    [Fact]
    public void Unresolvable_throwing_and_incomplete_targets_are_skipped()
    {
        // 解析返回 null、抛异常、或结果缺显示名时都不能进入名单。
        var result = KnownNpcResolver.Resolve(
            new[] { "Unknown", "Throws", "NoDisplay", "Emily" },
            ResolveTarget);

        Assert.Equal(new[] { "Emily" }, result.Select(item => item.NpcId).ToArray());
    }

    [Fact]
    public void Resolved_identifiers_and_display_names_are_trimmed()
    {
        var result = KnownNpcResolver.Resolve(
            new[] { "  Abigail  " },
            _ => new KnownNpc("  Abigail  ", "  阿比盖尔  "));

        var known = Assert.Single(result);
        Assert.Equal("Abigail", known.NpcId);
        Assert.Equal("阿比盖尔", known.DisplayName);
    }
}
