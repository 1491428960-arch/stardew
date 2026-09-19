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
