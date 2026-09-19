using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace StardewAI.NPC;

public static class ConversationStateRules
{
    private const int MaxMemoryCount = 200;
    private const int MaxMemoryTextLength = 240;
    private static readonly Regex Whitespace = new(@"\s+", RegexOptions.Compiled);

    public static StoryStateEnvelope RecordConversation(
        StoryStateEnvelope state,
        NpcGameState gameState,
        string playerMessage,
        string npcReply,
        bool usedFallback)
    {
        ArgumentNullException.ThrowIfNull(state);
        ArgumentNullException.ThrowIfNull(gameState);

        var npcId = Normalize(gameState.NpcId);
        var gameDate = Normalize(gameState.Date);
        var message = Normalize(playerMessage);
        var reply = Normalize(npcReply);
        if (usedFallback || npcId.Length == 0 || gameDate.Length == 0 ||
            message.Length == 0 || reply.Length == 0)
        {
            return state;
        }

        var memoryId = BuildMemoryId(npcId, gameDate, message, reply);
        var memories = state.Memories?.ToList() ?? new List<MemoryRecord>();
        if (memories.All(memory => !string.Equals(memory.MemoryId, memoryId, StringComparison.Ordinal)))
        {
            memories.Add(new MemoryRecord
            {
                MemoryId = memoryId,
                OwnerNpcId = npcId,
                Kind = "fact",
                Content = Truncate($"玩家说：“{message}”；NPC回应：“{reply}”", MaxMemoryTextLength),
                Source = MemorySource.PlayerChat,
                Confidence = 0.75,
                GameDate = gameDate,
                Participants = new[] { npcId, "player" },
                KnowledgeScope = MemoryKnowledgeScope.Participants,
                KnownBy = new[] { npcId, "player" },
                Importance = 1,
                Canonical = false,
                Status = MemoryStatus.Active,
                Evidence = "bridge-dialogue",
            });
        }

        if (memories.Count > MaxMemoryCount)
        {
            memories = memories.TakeLast(MaxMemoryCount).ToList();
        }

        var stage = RelationshipStageRules.Resolve(gameState);
        var progresses = state.InteractionProgresses?.ToList() ?? new List<InteractionProgress>();
        var progressIndex = progresses.FindIndex(progress =>
            string.Equals(progress.NpcId, npcId, StringComparison.OrdinalIgnoreCase));
        var progress = progressIndex >= 0 &&
                       string.Equals(progresses[progressIndex].Stage, stage, StringComparison.Ordinal)
            ? progresses[progressIndex]
            : InteractionProgress.Create(npcId, stage);
        progress = InteractionProgressRules.Record(
            progress,
            new ConversationAttempt(gameDate, message, reply, usedFallback));
        if (progressIndex >= 0)
        {
            progresses[progressIndex] = progress;
        }
        else
        {
            progresses.Add(progress);
        }

        return state with
        {
            Memories = memories,
            InteractionProgresses = progresses,
        };
    }

    private static string Normalize(string? value)
    {
        return string.IsNullOrWhiteSpace(value)
            ? string.Empty
            : Whitespace.Replace(value.Trim(), " ");
    }

    private static string BuildMemoryId(
        string npcId,
        string gameDate,
        string message,
        string reply)
    {
        var input = $"{npcId}\n{gameDate}\n{message}\n{reply}";
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return $"chat:{npcId}:{Convert.ToHexString(hash)[..24]}";
    }

    private static string Truncate(string value, int maxLength)
    {
        if (value.Length <= maxLength)
        {
            return value;
        }

        // 不要把 UTF-16 代理对切成两半：孤立的代理项会被序列化成替换字符，
        // 让写进存档的记忆文本出现乱码。
        var length = maxLength;
        if (char.IsHighSurrogate(value[length - 1]))
        {
            length -= 1;
        }

        return value[..length];
    }
}
