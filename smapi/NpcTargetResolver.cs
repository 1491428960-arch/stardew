namespace StardewAI.NPC;

public static class NpcTargetResolver
{
    private static readonly string[] CandidateNames = { "Rasmodia", "Wizard" };

    public static string? ResolveTargetName(Func<string, bool> isAvailable)
    {
        return CandidateNames.FirstOrDefault(isAvailable);
    }
}
