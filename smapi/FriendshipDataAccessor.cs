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
