using System.Text.Json;
using StardewModdingAPI;
using StardewValley;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

/// <summary>
/// 只观察已经打开的原版 DialogueBox，并输出可由离线导入器消费的 JSON 标记。
/// 不写存档、不改对话，只在 Trace 日志中保留当前实际解析文本。
/// </summary>
public static class RuntimeDialogueSampler
{
    public const string Marker = "[StardewAI.RuntimeDialogueSample]";

    public static void Observe(IMonitor monitor, StardewNpc? speaker)
    {
        if (speaker is null || monitor is null || speaker.CurrentDialogue is null ||
            speaker.CurrentDialogue.Count == 0)
        {
            return;
        }

        var dialogue = speaker.CurrentDialogue.Peek();
        if (dialogue is null)
        {
            return;
        }

        string text;
        try
        {
            text = dialogue.getCurrentDialogue();
        }
        catch (Exception exception)
        {
            monitor.Log($"运行时对白采样读取失败：{exception.Message}", LogLevel.Trace);
            return;
        }

        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }

        var sourceKey = string.IsNullOrWhiteSpace(dialogue.TranslationKey)
            ? "runtime-dialogue"
            : dialogue.TranslationKey.Trim();
        var payload = new
        {
            schemaVersion = 1,
            sourceSampleId = $"runtime:{speaker.Name}:{sourceKey}",
            npcId = speaker.Name,
            sourceMod = "runtime.unattributed",
            sourcePath = "runtime/dialogue",
            sourceKey,
            candidateKey = sourceKey,
            text = text.Trim(),
            evidenceKind = "runtime_dialogue",
            gameState = new
            {
                season = Game1.currentSeason,
                day = Game1.dayOfMonth,
                time = Game1.timeOfDay,
                location = Game1.currentLocation?.NameOrUniqueName,
            },
        };

        var json = JsonSerializer.Serialize(payload);
        monitor.Log($"{Marker} {json}", LogLevel.Trace);
    }
}

