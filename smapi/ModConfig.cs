namespace StardewAI.NPC;

public sealed class ModConfig
{
    public string DialogueKey { get; set; } = "F8";

    public static T ParseDialogueKey<T>(string? value, T fallback)
        where T : struct, Enum
    {
        return Enum.TryParse(value, ignoreCase: true, out T button) &&
            Enum.IsDefined(typeof(T), button)
            ? button
            : fallback;
    }
}
