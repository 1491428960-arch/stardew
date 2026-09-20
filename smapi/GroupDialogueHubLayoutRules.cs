using Microsoft.Xna.Framework;

namespace StardewAI.NPC;

public sealed record GroupDialogueHubLayout(
    Rectangle Panel,
    Rectangle CloseButton);

public static class GroupDialogueHubLayoutRules
{
    private const int SafeMargin = MenuPanelRules.SafeMargin;

    public static GroupDialogueHubLayout Calculate(int viewportWidth, int viewportHeight)
    {
        var panelWidth = Math.Min(1080, Math.Max(680, viewportWidth - (SafeMargin * 2)));
        var panelHeight = Math.Min(680, Math.Max(440, viewportHeight - (SafeMargin * 2)));
        panelWidth = Math.Min(panelWidth, Math.Max(1, viewportWidth - (SafeMargin * 2)));
        panelHeight = Math.Min(panelHeight, Math.Max(1, viewportHeight - (SafeMargin * 2)));
        var panel = MenuPanelRules.CenteredInViewport(
            viewportWidth,
            viewportHeight,
            panelWidth,
            panelHeight,
            floorOriginAtZero: true);

        var buttonY = panel.Bottom - 76;
        return new GroupDialogueHubLayout(
            panel,
            new Rectangle(panel.Right - 180, buttonY, 148, 56));
    }
}
