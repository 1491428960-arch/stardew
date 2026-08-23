namespace StardewAI.NPC;

public static class StoryStateValidation
{
    public static IReadOnlyList<string> Validate(MemoryRecord? memory)
    {
        var errors = new List<string>();
        if (memory is null)
        {
            errors.Add("memory record is null");
            return errors;
        }

        if (string.IsNullOrWhiteSpace(memory.MemoryId))
        {
            errors.Add("memoryId is required");
        }

        if (string.IsNullOrWhiteSpace(memory.OwnerNpcId))
        {
            errors.Add("ownerNpcId is required");
        }

        if (string.IsNullOrWhiteSpace(memory.Content))
        {
            errors.Add("content is required");
        }

        if (memory.Source is null)
        {
            errors.Add("source is required");
        }

        if (memory.Confidence is null || memory.Confidence is < 0 or > 1)
        {
            errors.Add("confidence must be between 0 and 1");
        }

        if (string.IsNullOrWhiteSpace(memory.GameDate))
        {
            errors.Add("gameDate is required");
        }

        if (memory.Participants is null || memory.Participants.Count == 0 ||
            memory.Participants.Any(string.IsNullOrWhiteSpace))
        {
            errors.Add("participants must contain at least one NPC or player");
        }

        if (memory.KnowledgeScope is null)
        {
            errors.Add("knowledgeScope is required");
        }

        if (memory.Importance is < 0 or > 3)
        {
            errors.Add("importance must be between 0 and 3");
        }

        return errors;
    }
}
