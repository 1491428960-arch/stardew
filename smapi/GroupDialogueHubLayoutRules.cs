using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

public sealed record GroupDialogueHubLayout(
    Rectangle Panel,
    Rectangle FreeStartButton,
    Rectangle CloseButton);

public static class GroupDialogueHubLayoutRules
{
    public static GroupDialogueHubLayout Calculate(int viewportWidth, int viewportHeight)
    {
        if (viewportWidth <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(viewportWidth));
        }

        if (viewportHeight <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(viewportHeight));
        }

        var panelWidth = Math.Min(1080, Math.Max(680, viewportWidth - 48));
        var panelHeight = Math.Min(680, Math.Max(440, viewportHeight - 48));
        panelWidth = Math.Min(panelWidth, Math.Max(1, viewportWidth - 48));
        panelHeight = Math.Min(panelHeight, Math.Max(1, viewportHeight - 48));
        var panel = new Rectangle(
            Math.Max(0, (viewportWidth - panelWidth) / 2),
            Math.Max(0, (viewportHeight - panelHeight) / 2),
            panelWidth,
            panelHeight);

        var buttonY = panel.Bottom - 76;
        return new GroupDialogueHubLayout(
            panel,
            new Rectangle(panel.X + 32, buttonY, 220, 56),
            new Rectangle(panel.Right - 180, buttonY, 148, 56));
    }
}
