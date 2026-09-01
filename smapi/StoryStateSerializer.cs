using System.Text.Json;
using System.Text.Json.Serialization;

namespace StardewAI.NPC;

public static class StoryStateSerializer
{
    public const string StorageKey = "stardew-ai-npc.story-state.v1";

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
    };

    public static string Serialize(StoryStateEnvelope state)
    {
        ArgumentNullException.ThrowIfNull(state);
        if (state.SchemaVersion != StoryStateEnvelope.CurrentSchemaVersion)
        {
            throw new ArgumentException(
                $"不支持的故事状态版本：{state.SchemaVersion}。",
                nameof(state));
        }

        var errors = ValidateMemories(state.Memories);
        if (errors.Count > 0)
        {
            throw new ArgumentException(
                $"故事状态包含无效记忆：{string.Join("；", errors)}。",
                nameof(state));
        }

        return JsonSerializer.Serialize(state, JsonOptions);
    }

    public static StoryStateLoadResult Load(string? json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return EmptyWithWarning("story state JSON is empty");
        }

        StoryStateEnvelope? state;
        try
        {
            state = JsonSerializer.Deserialize<StoryStateEnvelope>(json, JsonOptions);
        }
        catch (JsonException)
        {
            return EmptyWithWarning("story state JSON is invalid");
        }

        if (state is null)
        {
            return EmptyWithWarning("story state JSON contains no state");
        }

        if (state.SchemaVersion != StoryStateEnvelope.CurrentSchemaVersion)
        {
            return EmptyWithWarning(
                $"story state schema {state.SchemaVersion} is unsupported");
        }

        var warnings = new List<string>();
        var validMemories = new List<MemoryRecord>();
        foreach (var memory in state.Memories ?? Array.Empty<MemoryRecord>())
        {
            var errors = StoryStateValidation.Validate(memory);
            if (errors.Count == 0)
            {
                validMemories.Add(memory);
                continue;
            }

            var memoryId = memory is null || string.IsNullOrWhiteSpace(memory.MemoryId)
                ? "unknown"
                : memory.MemoryId.Trim();
            warnings.Add($"memory {memoryId} skipped: {string.Join(", ", errors)}");
        }

        return new StoryStateLoadResult(
            state with
            {
                Memories = validMemories,
                StoryEvents = state.StoryEvents ?? Array.Empty<StoryEventRecord>(),
                Knowledge = state.Knowledge ?? Array.Empty<KnowledgeRecord>(),
                Relationships = state.Relationships ?? Array.Empty<RelationshipEdgeRecord>(),
                InteractionProgresses = state.InteractionProgresses ?? Array.Empty<InteractionProgress>(),
            },
            warnings);
    }

    private static IReadOnlyList<string> ValidateMemories(
        IEnumerable<MemoryRecord>? memories)
    {
        var errors = new List<string>();
        foreach (var memory in memories ?? Array.Empty<MemoryRecord>())
        {
            var memoryErrors = StoryStateValidation.Validate(memory);
            if (memoryErrors.Count > 0)
            {
                var memoryId = memory is null || string.IsNullOrWhiteSpace(memory.MemoryId)
                    ? "unknown"
                    : memory.MemoryId.Trim();
                errors.Add($"{memoryId}: {string.Join(", ", memoryErrors)}");
            }
        }

        return errors;
    }

    private static StoryStateLoadResult EmptyWithWarning(string warning)
    {
        return new StoryStateLoadResult(
            StoryStateEnvelope.Empty,
            new[] { warning });
    }
}
