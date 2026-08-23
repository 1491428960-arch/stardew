namespace StardewAI.NPC;

/// <summary>
/// 保存当前存档对应的故事状态；不直接修改 Stardew Valley 的原版状态。
/// </summary>
public sealed class StoryStateStore
{
    public StoryStateEnvelope State { get; private set; } = StoryStateEnvelope.Empty;

    public IReadOnlyList<string> LastWarnings { get; private set; } = Array.Empty<string>();

    public void Load(string? json)
    {
        var result = StoryStateSerializer.Load(json);
        State = result.State;
        LastWarnings = result.Warnings;
    }

    public string Serialize()
    {
        return StoryStateSerializer.Serialize(State);
    }

    public void RecordConversation(
        NpcGameState gameState,
        string playerMessage,
        string npcReply,
        bool usedFallback)
    {
        Replace(ConversationStateRules.RecordConversation(
            State,
            gameState,
            playerMessage,
            npcReply,
            usedFallback));
    }

    public void Replace(StoryStateEnvelope state)
    {
        ArgumentNullException.ThrowIfNull(state);
        _ = StoryStateSerializer.Serialize(state);
        State = state;
        LastWarnings = Array.Empty<string>();
    }

    public void Reset()
    {
        State = StoryStateEnvelope.Empty;
        LastWarnings = Array.Empty<string>();
    }
}
