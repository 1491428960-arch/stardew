using StardewValley;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

public enum DialogueStatus
{
    Idle,
    Sending,
    Success,
    Failed,
}

/// <summary>
/// 旧入口的兼容外壳；实际绘制和输入交给 <see cref="ChatInputMenu"/>。
/// </summary>
public sealed class DialogueMenu : ChatInputMenu
{
    public DialogueMenu(
        StardewNpc npc,
        BridgeClient bridgeClient,
        StoryStateStore? storyStateStore = null)
        : this(npc, CreateDependencies(bridgeClient, storyStateStore))
    {
    }

    private DialogueMenu(
        StardewNpc npc,
        Dependencies dependencies)
        : base(
            npc,
            dependencies.Service,
            dependencies.Store,
            onClosed: static () => { })
    {
    }

    public DialogueStatus Status { get; private set; } = DialogueStatus.Idle;

    /// <summary>
    /// 保留旧调用方使用的发送方法；新界面使用输入框和发送按钮。
    /// </summary>
    public async Task SendAsync(string message, CancellationToken cancellationToken = default)
    {
        Status = DialogueStatus.Sending;
        try
        {
            var result = await Service.SendAsync(
                GameStateCollector.Collect(Npc),
                message,
                cancellationToken);
            Status = result.Fallback ? DialogueStatus.Failed : DialogueStatus.Success;
        }
        catch (OperationCanceledException)
        {
            Status = DialogueStatus.Failed;
            throw;
        }
        catch
        {
            Status = DialogueStatus.Failed;
            throw;
        }
    }

    private static Dependencies CreateDependencies(
        BridgeClient bridgeClient,
        StoryStateStore? storyStateStore)
    {
        var store = storyStateStore ?? new StoryStateStore();
        return new Dependencies(new ConversationService(bridgeClient, store), store);
    }

    private sealed record Dependencies(ConversationService Service, StoryStateStore Store);
}
