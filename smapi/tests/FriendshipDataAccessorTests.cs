using System.Collections;
using StardewAI.NPC;
using Xunit;

namespace StardewAI.NPC.Tests;

public sealed class FriendshipDataAccessorTests
{
    [Fact]
    public void Reads_a_key_from_the_generic_dictionary_shape_used_by_the_game()
    {
        var data = new GenericDictionaryShape();
        data.Set("Caroline", "friendship-record");

        Assert.True(FriendshipDataAccessor.ContainsKey(data, "Caroline"));
        Assert.True(FriendshipDataAccessor.TryGetValue(data, "Caroline", out var value));
        Assert.Equal("friendship-record", value);
    }

    [Fact]
    public void Keeps_support_for_the_legacy_non_generic_dictionary_shape()
    {
        IDictionary data = new Hashtable
        {
            ["Marnie"] = "friendship-record",
        };

        Assert.True(FriendshipDataAccessor.ContainsKey(data, "Marnie"));
        Assert.True(FriendshipDataAccessor.TryGetValue(data, "Marnie", out var value));
        Assert.Equal("friendship-record", value);
    }

    [Fact]
    public void Returns_false_for_a_missing_key_or_null_collection()
    {
        var data = new GenericDictionaryShape();

        Assert.False(FriendshipDataAccessor.ContainsKey(data, "Willy"));
        Assert.False(FriendshipDataAccessor.TryGetValue(data, "Willy", out _));
        Assert.False(FriendshipDataAccessor.ContainsKey(null, "Willy"));
        Assert.False(FriendshipDataAccessor.TryGetValue(null, "Willy", out _));
    }

    [Fact]
    public void Reads_friendship_keys_from_a_keys_property_without_exposing_values()
    {
        var data = new KeysPropertyShape("Abigail", "Emily");

        var keys = FriendshipDataAccessor.Keys(data);

        Assert.Equal(new[] { "Abigail", "Emily" }, keys);
    }

    /// <summary>
    /// 审计 #40：<c>HasFriendshipRecord</c> 此前在 ModEntry 与 VanillaGiftHandler 各有一份。
    /// 收敛后这里同时覆盖属性形态、字段形态与各种失败路径。
    /// </summary>
    [Fact]
    public void HasRecord_reads_the_friendship_collection_from_a_property()
    {
        var data = new GenericDictionaryShape();
        data.Set("Abigail", "friendship-record");

        Assert.True(FriendshipDataAccessor.HasRecord(new PlayerPropertyShape(data), "Abigail"));
        Assert.False(FriendshipDataAccessor.HasRecord(new PlayerPropertyShape(data), "Willy"));
    }

    [Fact]
    public void HasRecord_falls_back_to_the_private_field_shape()
    {
        var data = new GenericDictionaryShape();
        data.Set("Caroline", "friendship-record");

        Assert.True(FriendshipDataAccessor.HasRecord(new PlayerFieldShape(data), "Caroline"));
        Assert.False(FriendshipDataAccessor.HasRecord(new PlayerFieldShape(null), "Caroline"));
    }

    [Fact]
    public void HasRecord_returns_false_instead_of_throwing_for_invalid_input()
    {
        Assert.False(FriendshipDataAccessor.HasRecord(null, "Abigail"));
        Assert.False(FriendshipDataAccessor.HasRecord(new PlayerPropertyShape(null), "Abigail"));
        Assert.False(FriendshipDataAccessor.HasRecord(new PlayerPropertyShape(new object()), "Abigail"));
        Assert.False(FriendshipDataAccessor.HasRecord(new PlayerPropertyShape(null), " "));
        Assert.False(FriendshipDataAccessor.HasRecord(new PlayerPropertyShape(null), null));
        // 完全没有 friendshipData 成员的对象：反射失败按“没有记录”处理，不向上抛。
        Assert.False(FriendshipDataAccessor.HasRecord(new object(), "Abigail"));
    }

    [Fact]
    public void ReadData_returns_the_same_object_that_ContainsKey_consumes()
    {
        var data = new GenericDictionaryShape();
        data.Set("Marnie", "friendship-record");

        var read = FriendshipDataAccessor.ReadData(new PlayerPropertyShape(data));

        Assert.Same(data, read);
        Assert.True(FriendshipDataAccessor.ContainsKey(read, "Marnie"));
        Assert.Null(FriendshipDataAccessor.ReadData(null));
        Assert.Null(FriendshipDataAccessor.ReadData(new object()));
    }

    private sealed class PlayerPropertyShape
    {
        public PlayerPropertyShape(object? friendshipData)
        {
            this.friendshipData = friendshipData;
        }

        // 名称与游戏里的成员一致；反射访问器按名字查找。
        public object? friendshipData { get; }
    }

    private sealed class PlayerFieldShape
    {
        private readonly object? friendshipData;

        public PlayerFieldShape(object? friendshipData)
        {
            this.friendshipData = friendshipData;
        }
    }

    private sealed class GenericDictionaryShape
    {
        private readonly Dictionary<string, object?> values = new(StringComparer.Ordinal);

        public bool ContainsKey(string key) => values.ContainsKey(key);

        public bool TryGetValue(string key, out object? value) =>
            values.TryGetValue(key, out value);

        public object? this[string key] => values[key];

        public void Set(string key, object? value) => values[key] = value;
    }

    private sealed class KeysPropertyShape
    {
        public KeysPropertyShape(params string[] keys)
        {
            Keys = keys;
        }

        public IReadOnlyList<string> Keys { get; }
    }
}
