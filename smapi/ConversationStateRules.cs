using System.Text.RegularExpressions;

namespace StardewAI.NPC;

public static class ConversationStateRules
{
    // 上限与截断都来自 MemoryRules（审计 #44：此前两份实现靠注释人工同步）。
    private const int MaxMemoryCount = MemoryRules.MaxCount;
    private const int MaxMemoryTextLength = MemoryRules.MaxTextLength;
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
                Content = MemoryRules.Truncate(
                    $"玩家说：“{message}”；NPC回应：“{reply}”",
                    MaxMemoryTextLength),
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
        return MemoryRules.BuildId(
            kind: "chat",
            owner: npcId,
            payload: $"{npcId}\n{gameDate}\n{message}\n{reply}");
    }
}
