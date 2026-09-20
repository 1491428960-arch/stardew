using System.Collections;
using System.Reflection;

namespace StardewAI.NPC;

/// <summary>
/// Reads the player's friendship collection without depending on one concrete
/// Stardew Valley dictionary implementation.
/// </summary>
public static class FriendshipDataAccessor
{
    private const BindingFlags InstanceFlags = BindingFlags.Public |
                                                BindingFlags.NonPublic |
                                                BindingFlags.Instance;

    /// <summary>
    /// 读取玩家对象上的 <c>friendshipData</c> 集合（属性优先、字段兜底）。
    /// 反射写法只此一处：此前它有四个调用点各写一份（审计 #40 的「改反射策略要改三处」）。
    /// </summary>
    public static object? ReadData(object? player)
    {
        if (player is null)
        {
            return null;
        }

        try
        {
            var playerType = player.GetType();
            return playerType.GetProperty("friendshipData", InstanceFlags)?.GetValue(player) ??
                playerType.GetField("friendshipData", InstanceFlags)?.GetValue(player);
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// 某个玩家对象（Farmer）是否已存在该 NPC 的好感度记录。
    ///
    /// 2026-09-20（语义层审计 #40）：本方法此前在 <see cref="ModEntry"/> 与
    /// <see cref="VanillaGiftHandler"/> 里各有一份同名同义的实现（各自用反射读
    /// <c>friendshipData</c>），改反射策略要改三处。现在只此一处。
    /// 取保守口径：反射失败即视为没有记录，不向上抛。
    /// </summary>
    public static bool HasRecord(object? player, string? npcId)
    {
        return !string.IsNullOrWhiteSpace(npcId) &&
            ContainsKey(ReadData(player), npcId);
    }

    public static bool ContainsKey(object? data, string? key)
    {
        if (data is null || string.IsNullOrWhiteSpace(key))
        {
            return false;
        }

        if (data is IDictionary dictionary)
        {
            return dictionary.Contains(key);
        }

        var method = FindMethod(
            data.GetType(),
            "ContainsKey",
            parameters => parameters.Length == 1 &&
                          parameters[0].ParameterType == typeof(string));
        if (method is null || method.ReturnType != typeof(bool))
        {
            return TryGetValue(data, key, out _);
        }

        try
        {
            return method.Invoke(data, new object?[] { key }) is true;
        }
        catch
        {
            return false;
        }
    }

    public static bool TryGetValue(object? data, string? key, out object? value)
    {
        value = null;
        if (data is null || string.IsNullOrWhiteSpace(key))
        {
            return false;
        }

        if (data is IDictionary dictionary)
        {
            if (!dictionary.Contains(key))
            {
                return false;
            }

            value = dictionary[key];
            return true;
        }

        var method = FindMethod(
            data.GetType(),
            "TryGetValue",
            parameters => parameters.Length == 2 &&
                          parameters[0].ParameterType == typeof(string) &&
                          parameters[1].ParameterType.IsByRef);
        if (method is not null)
        {
            try
            {
                var arguments = new object?[] { key, null };
                var found = method.Invoke(data, arguments) is true;
                value = arguments[1];
                return found;
            }
            catch
            {
                value = null;
                return false;
            }
        }

        var indexer = data.GetType().GetProperty(
            "Item",
            InstanceFlags,
            binder: null,
            returnType: null,
            types: new[] { typeof(string) },
            modifiers: null);
        if (indexer is null)
        {
            return false;
        }

        try
        {
            value = indexer.GetValue(data, new object?[] { key });
            return true;
        }
        catch
        {
            value = null;
            return false;
        }
    }

    public static IReadOnlyList<string> Keys(object? data)
    {
        if (data is null || data is string)
        {
            return Array.Empty<string>();
        }

        if (data is IDictionary dictionary)
        {
            return NormalizeKeys(dictionary.Keys);
        }

        var keysProperty = data.GetType().GetProperty("Keys", InstanceFlags);
        if (keysProperty is not null)
        {
            try
            {
                return NormalizeKeys(keysProperty.GetValue(data));
            }
            catch
            {
                return Array.Empty<string>();
            }
        }

        if (data is IEnumerable values)
        {
            var keys = new List<string>();
            foreach (var item in values)
            {
                var key = ReadKeyMember(item);
                if (!string.IsNullOrWhiteSpace(key))
                {
                    AddUniqueKey(keys, key);
                }
            }

            return keys;
        }

        return Array.Empty<string>();
    }

    private static IReadOnlyList<string> NormalizeKeys(object? values)
    {
        if (values is not IEnumerable enumerable || values is string)
        {
            return Array.Empty<string>();
        }

        var keys = new List<string>();
        foreach (var value in enumerable)
        {
            var key = value?.ToString()?.Trim();
            if (!string.IsNullOrWhiteSpace(key))
            {
                AddUniqueKey(keys, key);
            }
        }

        return keys;
    }

    private static string? ReadKeyMember(object? item)
    {
        if (item is null)
        {
            return null;
        }

        try
        {
            var property = item.GetType().GetProperty("Key", InstanceFlags);
            return property?.GetValue(item)?.ToString()?.Trim();
        }
        catch
        {
            return null;
        }
    }

    private static void AddUniqueKey(ICollection<string> keys, string key)
    {
        if (!keys.Contains(key, StringComparer.OrdinalIgnoreCase))
        {
            keys.Add(key);
        }
    }

    private static MethodInfo? FindMethod(
        Type type,
        string name,
        Func<ParameterInfo[], bool> matches)
    {
        return type
            .GetMethods(InstanceFlags)
            .FirstOrDefault(method =>
                string.Equals(method.Name, name, StringComparison.Ordinal) &&
                matches(method.GetParameters()));
    }
}
