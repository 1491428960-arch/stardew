namespace StardewAI.NPC;

public interface IConversationTransport
{
    Task<BridgeDialogueResponse> SendAsync(
        ConversationRequest request,
        CancellationToken cancellationToken);
}
