using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace StardewAI.NPC;

public static class InteractionProgressRules
{
    private static readonly Regex Whitespace = new(@"\s+", RegexOptions.Compiled);

    public static InteractionProgress Record(
        InteractionProgress progress,
        ConversationAttempt attempt)
    {
        ArgumentNullException.ThrowIfNull(progress);
        ArgumentNullException.ThrowIfNull(attempt);

        var gameDate = attempt.GameDate?.Trim() ?? string.Empty;
        var playerMessage = Normalize(attempt.PlayerMessage);
        var npcReply = Normalize(attempt.NpcReply);
        if (attempt.UsedFallback ||
            gameDate.Length == 0 ||
            playerMessage.Length == 0 ||
            npcReply.Length == 0)
        {
            return progress;
        }

        if (string.Equals(
                progress.LastCountedGameDate,
                gameDate,
                StringComparison.Ordinal))
        {
            return progress;
        }

        var fingerprint = Fingerprint(playerMessage);
        if (string.Equals(
                progress.LastInteractionFingerprint,
                fingerprint,
                StringComparison.Ordinal))
        {
            return progress;
        }

        return progress with
        {
            EffectiveSessions = progress.EffectiveSessions + 1,
            LastCountedGameDate = gameDate,
            LastInteractionFingerprint = fingerprint,
        };
    }

    private static string Normalize(string? text)
    {
        return string.IsNullOrWhiteSpace(text)
            ? string.Empty
            : Whitespace.Replace(text.Trim(), " ");
    }

    private static string Fingerprint(string normalizedMessage)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(normalizedMessage));
        return Convert.ToHexString(bytes);
    }
}
