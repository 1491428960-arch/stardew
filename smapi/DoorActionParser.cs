using System.Globalization;

namespace StardewAI.NPC;

/// <summary>
/// Parsed representation of a map <c>LockedDoorWarp</c> action.
/// </summary>
public sealed record LockedDoorWarpData(
    int DestinationX,
    int DestinationY,
    string TargetLocationName,
    int OpenTime,
    int CloseTime,
    string? RequiredNpcId,
    int? MinimumFriendship);

/// <summary>
/// Parses the vanilla map action without changing the game's event or map state.
/// </summary>
public static class DoorActionParser
{
    private const string ActionName = "LockedDoorWarp";

    public static bool TryParse(
        string? actionText,
        out LockedDoorWarpData? action)
    {
        if (string.IsNullOrWhiteSpace(actionText))
        {
            action = null;
            return false;
        }

        var tokens = actionText
            .Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);

        return TryParse(tokens, out action);
    }

    public static bool TryParse(
        string[]? tokens,
        out LockedDoorWarpData? action)
    {
        action = null;

        if (tokens is null
            || tokens.Length < 6
            || !string.Equals(tokens[0], ActionName, StringComparison.OrdinalIgnoreCase)
            || !TryParseInt(tokens[1], out var destinationX)
            || !TryParseInt(tokens[2], out var destinationY)
            || string.IsNullOrWhiteSpace(tokens[3])
            || !TryParseInt(tokens[4], out var openTime)
            || !TryParseInt(tokens[5], out var closeTime)
            || tokens.Length > 8)
        {
            return false;
        }

        string? requiredNpcId = null;
        int? minimumFriendship = null;

        if (tokens.Length >= 7)
        {
            if (string.IsNullOrWhiteSpace(tokens[6]))
                return false;

            requiredNpcId = tokens[6];
        }

        if (tokens.Length == 8)
        {
            if (!TryParseInt(tokens[7], out var parsedFriendship)
                || parsedFriendship < 0)
            {
                return false;
            }

            minimumFriendship = parsedFriendship;
        }

        action = new LockedDoorWarpData(
            destinationX,
            destinationY,
            tokens[3],
            openTime,
            closeTime,
            requiredNpcId,
            minimumFriendship);
        return true;
    }

    public static bool RelaxResidentialGate(string[]? actionTokens)
    {
        if (!TryParse(actionTokens, out _))
        {
            return false;
        }

        // 放行参数只有一份定义：ResidentialDoorGateRules（审计 #42）。
        actionTokens![4] = ResidentialDoorGateRules.RelaxedOpenTime.ToString(CultureInfo.InvariantCulture);
        actionTokens[5] = ResidentialDoorGateRules.RelaxedCloseTime.ToString(CultureInfo.InvariantCulture);
        if (actionTokens.Length >= 7)
        {
            actionTokens[6] = ResidentialDoorGateRules.RelaxedRequiredNpcToken;
        }
        if (actionTokens.Length >= 8)
        {
            actionTokens[7] = ResidentialDoorGateRules.RelaxedMinimumFriendshipToken;
        }

        return true;
    }

    public static bool IsDoorOrWarpAction(string? actionName)
    {
        return !string.IsNullOrWhiteSpace(actionName) &&
            (actionName.Contains("door", StringComparison.OrdinalIgnoreCase) ||
                actionName.Contains("warp", StringComparison.OrdinalIgnoreCase));
    }

    private static bool TryParseInt(string value, out int result)
    {
        return int.TryParse(
            value,
            NumberStyles.Integer,
            CultureInfo.InvariantCulture,
            out result);
    }
}
