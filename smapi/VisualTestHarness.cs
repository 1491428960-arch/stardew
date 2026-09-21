using System.Collections;
using System.Globalization;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;
using StardewValley.Menus;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

public sealed record VisualTestOptions(
    bool Enabled,
    string SaveName,
    string OutputDirectory,
    string ScenarioId,
    int? BackBufferWidth = null,
    int? BackBufferHeight = null,
    string ActionId = "capture");

public sealed record VisualTestScenarioContent(
    IReadOnlyList<ChatDisplayMessage> InitialMessages,
    int? FriendshipHearts);

public static class VisualTestHarnessRules
{
    public const string EnabledVariable = "STARDEW_AI_NPC_VISUAL_TEST";
    public const string SaveNameVariable = "STARDEW_AI_NPC_VISUAL_SAVE_NAME";
    public const string OutputVariable = "STARDEW_AI_NPC_VISUAL_OUTPUT";
    public const string ScenarioVariable = "STARDEW_AI_NPC_VISUAL_SCENARIO";
    public const string ActionVariable = "STARDEW_AI_NPC_VISUAL_ACTION";
    public const string BackBufferWidthVariable = "STARDEW_AI_NPC_VISUAL_BACKBUFFER_WIDTH";
    public const string BackBufferHeightVariable = "STARDEW_AI_NPC_VISUAL_BACKBUFFER_HEIGHT";
    public const string DefaultSaveName = "test_447101921";
    public const string DefaultScenarioId = "chat-empty";
    public const string DefaultActionId = "capture";
    public const string TopicActionId = "topic";
    public const string GroupHubActionId = "group-hub";
    public const string GroupMessageActionId = "group-message";
    public const string GroupSendActionId = "group-send";
    /// <summary>F9 全流程之一：多人对话中心 → 点接受邀约卡 → 群聊菜单。</summary>
    public const string GroupAcceptActionId = "group-accept";
    public const string WideContentScenarioId = "chat-profile-strip-wide-content";

    /// <summary>真实发送场景用的玩家消息：写得像日常闲聊，避免触发任何特殊分支。</summary>
    public const string GroupSendPlayerMessage = "视觉测试：你们最近都在忙什么？";

    private static readonly VisualTestScenarioContent EmptyScenarioContent =
        new(Array.Empty<ChatDisplayMessage>(), null);

    private static readonly VisualTestScenarioContent WideContentScenario =
        new(
            new[]
            {
                new ChatDisplayMessage(
                    "npc",
                    "今天的风很舒服，像是从山谷一路带着松木和薄荷的味道吹过来。"),
                new ChatDisplayMessage(
                    "player",
                    "最近在整理农场，也在试着把每天遇到的小事记下来。"),
                new ChatDisplayMessage(
                    "npc",
                    "这听起来不错。记忆不会因为写得简短就失去温度，反而更容易在以后重新找到当时的心情。" +
                    "等你下次回头看的时候，也许会发现今天的自己已经悄悄走了很远。" +
                    "所以不用急着把每件事都解释清楚，先把真正想留下的片段记下来，时间会帮你把它们串成一段温柔的故事。"),
                new ChatDisplayMessage(
                    "player",
                    "那我先记下：今天早上和你聊了这件事，也记得给自己留一点休息的时间。"),
            },
            5);

    public static bool IsEnabled(string? value)
    {
        return string.Equals(value, "1", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(value, "true", StringComparison.OrdinalIgnoreCase);
    }

    public static bool IsGameReady(byte gameMode, bool hasPlayer, bool hasLocation)
    {
        // Direct SaveGame.Load reaches playingGameMode before SMAPI raises
        // Context.IsWorldReady, so use the game state itself for this opt-in
        // harness instead of waiting for the normal menu-driven event.
        return gameMode == 3 && hasPlayer && hasLocation;
    }

    public static bool IsGameReady(
        byte gameMode,
        bool hasPlayer,
        bool hasLocation,
        bool hasLoadedGame)
    {
        return IsGameReady(gameMode, hasPlayer, hasLocation) &&
            hasLoadedGame;
    }

    /// <summary>
    /// 从 Game1 现况取「世界就绪」的三项判据。
    ///
    /// 2026-09-20（语义层审计 #41）：同一批取值（gameMode / player / location）
    /// 此前在 <see cref="ModEntry"/> 的视觉测试入口与 harness 内部各拼一次，
    /// 且填进的是同一个「worldReady」形参位。现在拼装只此一处；
    /// 是否额外要求 <c>hasLoadedGame</c> 由调用方决定（两个入口的差异是有意的）。
    /// </summary>
    public static bool IsGameReadyFromGameState()
    {
        return IsGameReady(
            Game1.gameMode,
            Game1.player is not null,
            Game1.currentLocation is not null);
    }

    public static bool CanOpenMenu(
        bool loadGateSatisfied,
        bool fadeClear,
        bool menuOpened,
        bool gameReady,
        int ticks,
        int openAtTick)
    {
        return loadGateSatisfied && fadeClear && !menuOpened && gameReady &&
            openAtTick >= 0 && ticks >= openAtTick;
    }

    public static VisualTestScenarioContent GetScenarioContent(string? scenarioId)
    {
        return string.Equals(
                scenarioId,
                WideContentScenarioId,
                StringComparison.OrdinalIgnoreCase)
            ? WideContentScenario
            : EmptyScenarioContent;
    }

    public static GroupDialogueInvitationRecord CreateGroupHubInvitation(int currentTotalDays)
    {
        if (currentTotalDays < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(currentTotalDays));
        }

        var expiresTotalDays = currentTotalDays + GroupInvitationRules.ExpirationDays;
        return new GroupDialogueInvitationRecord
        {
            InvitationId = "visual-test-group-hub",
            TemplateId = "neutral-public-topic",
            Participants = new[] { "Abigail", "Emily" },
            ParticipantDisplayNames = new[] { "Abigail", "Emily" },
            Title = "视觉测试邀约",
            Topic = "最近在镇上发生的一件小事",
            Guidance = "仅用于检查邀约卡布局，不会发起线上请求。",
            CreatedOn = "visual-test",
            ExpiresOn = $"day {expiresTotalDays}",
            CreatedTotalDays = currentTotalDays,
            ExpiresTotalDays = expiresTotalDays,
            Source = "story",
            Status = GroupInvitationStatus.Unread,
        };
    }

    public static IReadOnlyList<GroupDialogueParticipant> CreateGroupMessageParticipants()
    {
        return new[]
        {
            new GroupDialogueParticipant("Abigail", "Abigail"),
            new GroupDialogueParticipant("Emily", "Emily"),
        };
    }

    /// <summary>
    /// 真实发送场景用三人名单：两人场在回合上限为 2 时必然都开口，看不出
    /// “名单里每个人都要有机会说话”有没有生效，三人场才有区分度。
    /// </summary>
    public static IReadOnlyList<GroupDialogueParticipant> CreateGroupSendParticipants()
    {
        return new[]
        {
            new GroupDialogueParticipant("Abigail", "Abigail"),
            new GroupDialogueParticipant("Emily", "Emily"),
            // 用原版角色而不是 SVE 角色：FastTest 存档未装 SVE，Sophia 解析不到
            // gameState，会让 groupRequestStateCount 停在 2，看不出“三人各自状态”。
            new GroupDialogueParticipant("Sebastian", "Sebastian"),
        };
    }

    /// <summary>真实发送场景的邀约：参与者必须与 <see cref="CreateGroupSendParticipants"/> 一致。</summary>
    public static GroupDialogueInvitationRecord CreateGroupSendInvitation(int currentTotalDays)
    {
        var invitation = CreateGroupHubInvitation(currentTotalDays);
        return invitation with
        {
            InvitationId = "visual-test-group-send",
            Participants = new[] { "Abigail", "Emily", "Sebastian" },
            ParticipantDisplayNames = new[] { "Abigail", "Emily", "Sebastian" },
        };
    }

    /// <summary>
    /// 群聊端到端场景用的模拟 Bridge 响应：回合合法、含一条长期记忆高亮，
    /// 但完全不联网——它只用来验证“响应 → 会话 → 存档记忆”这条链路。
    /// </summary>
    public static BridgeGroupDialogueResponse CreateGroupMessageResponse()
    {
        return new BridgeGroupDialogueResponse
        {
            Strategy = "multi_turn",
            Channel = ConversationChannel.Remote,
            Provider = "visual-test",
            Turns = new[]
            {
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Abigail",
                    Content = "视觉测试： Abigail 先说一句，用来检查群聊菜单的排版。",
                    AddressedTo = new[] { "Emily" },
                },
                new BridgeGroupTurn
                {
                    SpeakerNpcId = "Emily",
                    Content = "视觉测试： Emily 接住这一句，气泡应当各自独立。",
                    AddressedTo = Array.Empty<string>(),
                },
            },
            MemoryHighlights = new[] { "玩家下周要交一份报告。" },
        };
    }

    public static VisualTestOptions Parse(IReadOnlyDictionary<string, string?> environment)
    {
        ArgumentNullException.ThrowIfNull(environment);
        var enabled = environment.TryGetValue(EnabledVariable, out var enabledValue) &&
            IsEnabled(enabledValue);
        if (!enabled)
        {
            return new VisualTestOptions(false, DefaultSaveName, string.Empty, DefaultScenarioId);
        }

        var saveName = GetValue(environment, SaveNameVariable, DefaultSaveName);
        VisualTestManifest.ValidateFileName(saveName);
        var outputDirectory = GetValue(environment, OutputVariable, string.Empty);
        if (string.IsNullOrWhiteSpace(outputDirectory))
        {
            throw new ArgumentException(
                $"启用视觉测试时必须设置 {OutputVariable}。",
                nameof(environment));
        }

        var scenarioId = GetValue(environment, ScenarioVariable, DefaultScenarioId);
        VisualTestManifest.ValidateFileName(scenarioId);
        var actionId = GetValue(environment, ActionVariable, DefaultActionId)
            .ToLowerInvariant();
        if (actionId is not DefaultActionId and not TopicActionId and not GroupHubActionId and not GroupMessageActionId and not GroupSendActionId and not GroupAcceptActionId)
        {
            throw new ArgumentException(
                $"{ActionVariable} 只支持 {DefaultActionId}、{TopicActionId}、{GroupHubActionId}、{GroupMessageActionId}、{GroupSendActionId} 或 {GroupAcceptActionId}。",
                nameof(environment));
        }
        var backBufferWidth = ParseDimension(environment, BackBufferWidthVariable);
        var backBufferHeight = ParseDimension(environment, BackBufferHeightVariable);
        if (backBufferWidth.HasValue != backBufferHeight.HasValue)
        {
            throw new ArgumentException(
                $"启用宽屏视觉测试时必须同时设置 {BackBufferWidthVariable} 和 {BackBufferHeightVariable}。",
                nameof(environment));
        }

        return new VisualTestOptions(
            true,
            saveName,
            outputDirectory,
            scenarioId,
            backBufferWidth,
            backBufferHeight,
            actionId);
    }

    public static bool CanTriggerTopicAction(
        string actionId,
        bool menuReady,
        bool actionTriggered,
        int activeMenuFrames)
    {
        return string.Equals(actionId, TopicActionId, StringComparison.Ordinal) &&
            menuReady &&
            !actionTriggered &&
            activeMenuFrames >= 3;
    }

    public static bool CanTriggerGroupHubAction(
        string actionId,
        bool menuReady,
        bool actionTriggered,
        int activeMenuFrames)
    {
        return string.Equals(actionId, GroupHubActionId, StringComparison.Ordinal) &&
            menuReady &&
            !actionTriggered &&
            activeMenuFrames >= 3;
    }

    private static int? ParseDimension(
        IReadOnlyDictionary<string, string?> environment,
        string name)
    {
        if (!environment.TryGetValue(name, out var raw) ||
            string.IsNullOrWhiteSpace(raw))
        {
            return null;
        }

        if (!int.TryParse(
                raw.Trim(),
                NumberStyles.Integer,
                CultureInfo.InvariantCulture,
                out var value) ||
            value < 320 ||
            value > 7680)
        {
            throw new ArgumentException(
                $"{name} 必须是 320 到 7680 之间的整数。",
                nameof(environment));
        }

        return value;
    }

    private static string GetValue(
        IReadOnlyDictionary<string, string?> environment,
        string name,
        string fallback)
    {
        return environment.TryGetValue(name, out var value) &&
            !string.IsNullOrWhiteSpace(value)
            ? value.Trim()
            : fallback;
    }
}

public sealed class VisualTestHarness
{
    // 正常存档在 world-ready 后还会异步完成 NPC/Portraits 资源注入；给
    // SaveLoaded 留出约 30 秒，避免在资源稳定前提前创建聊天菜单。正常
    // FastTest 存档通常在 16 秒内完成；只有异常情况下才会走这个回退。
    private const int FallbackReadyTicks = 1800;
    private readonly IModHelper helper;
    private readonly IMonitor monitor;
    private readonly Func<ConversationService?> getConversationService;
    private readonly Func<StardewNpc?> getNpc;
    private readonly Func<bool> openGroupHub;
    private readonly Func<BridgeClient?> getBridgeClient;
    private readonly StoryStateStore storyStateStore;
    private readonly VisualTestOptions options;
    private ChatInputMenu? menu;
    private IClickableMenu? activeMenu;
    private StoryStateEnvelope? groupHubStateBeforeTest;
    private int ticks;
    private int worldReadyAtTick = -1;
    private int openAtTick = -1;
    private int renderedFrames;
    private int activeMenuFrames;
    private bool loadRequested;
    private bool menuOpened;
    private bool completed;
    private bool disposed;
    private bool worldReadyLogged;
    private bool saveLoadedLogged;
    private bool fallbackGateLogged;
    private bool renderLogged;
    private bool backBufferApplied;
    private bool actionTriggered;
    private bool actionEvidenceLogged;
    private int initialMessageCount;
    private int topicActionWaitFrames;
    private int groupMessageWaitFrames;
    private int lastStatusTick = -60;
    private int lastMenuRenderWarningTick = -300;
    // 群聊端到端场景的证据快照：manifest 与诊断 JSON 都读这一份，
    // 因为截图完成后 harness 会立刻还原测试前的存档状态。
    private int? groupResponseTurns;
    private int? groupMemoryCount;
    private int? groupMemoryNpcCount;
    private string? groupInvitationStatus;
    private IReadOnlyList<string> groupParticipantIds = Array.Empty<string>();
    private IReadOnlyList<GroupMemoryWrite> groupMemoryWrites = Array.Empty<GroupMemoryWrite>();
    // 真实发送场景：请求侧证据与内存层记忆的前后对照。
    private BridgeClient? activeBridgeClient;
    private int? groupRequestStateCount;
    private IReadOnlyList<string> groupRequestParticipantIds = Array.Empty<string>();
    private IReadOnlyList<string> groupHistoryEvidence = Array.Empty<string>();
    private int? groupMemoryLayerCount;
    private int? groupMemoryLayerGainCount;
    private string? groupRequestParticipantsJson;
    private string? groupLastResponseJson;
    // F9 全流程场景：当前步骤、中途截图与流程证据。
    private string groupFlowStage = string.Empty;
    private string? groupFlowSummary;
    private int groupFlowWaitFrames;
    private bool groupFlowDeferLogged;
    // 视觉测试静音：只改本次进程的运行时音量，避免后台跑测试时打扰用户。
    private bool audioMuteLogged;
    private bool audioMuted;
    private string audioMuteEvidence = "(未应用)";
    private readonly List<string> intermediateScreenshots = new();
    private IReadOnlyList<(string NpcId, int Count)> groupHistoryBefore =
        Array.Empty<(string, int)>();

    public VisualTestHarness(
        IModHelper helper,
        IMonitor monitor,
        Func<ConversationService?> getConversationService,
        Func<StardewNpc?> getNpc,
        StoryStateStore storyStateStore,
        Func<bool> openGroupHub,
        Func<BridgeClient?>? getBridgeClient = null)
    {
        this.helper = helper ?? throw new ArgumentNullException(nameof(helper));
        this.monitor = monitor ?? throw new ArgumentNullException(nameof(monitor));
        this.getConversationService = getConversationService ??
            throw new ArgumentNullException(nameof(getConversationService));
        this.getNpc = getNpc ?? throw new ArgumentNullException(nameof(getNpc));
        this.storyStateStore = storyStateStore ??
            throw new ArgumentNullException(nameof(storyStateStore));
        this.openGroupHub = openGroupHub ?? throw new ArgumentNullException(nameof(openGroupHub));
        this.getBridgeClient = getBridgeClient ?? (() => null);
        options = VisualTestHarnessRules.Parse(ReadEnvironment());
        if (!options.Enabled)
        {
            return;
        }

        helper.Events.GameLoop.UpdateTicked += OnUpdateTicked;
        helper.Events.GameLoop.SaveLoaded += OnSaveLoaded;
        helper.Events.GameLoop.GameLaunched += OnGameLaunched;
        helper.Events.Display.RenderedActiveMenu += OnRenderedActiveMenu;
        helper.Events.Display.Rendered += OnRendered;
        helper.Events.GameLoop.ReturnedToTitle += OnReturnedToTitle;
        // 尽早静音：GameLaunched 之前主菜单音乐可能已经起头，所以 Mod 加载时
        // 就先试一次（此时 Game1.options 若已存在，音频引擎初始化时会直接读到 0）。
        MuteAudio("Entry");
        monitor.Log(
            $"视觉测试 harness 已启用：scenario={options.ScenarioId}；save={options.SaveName}",
            LogLevel.Info);
    }

    /// <summary>
    /// 视觉测试全程静音。游戏在标题界面就会开始放音乐，所以这里尽量早地设置，
    /// 并在几个时间点重复应用（存档加载等阶段可能重新应用音量设置）。
    /// 只改本次进程的运行时音量字段与音频分类，**不写任何设置文件**，
    /// 因此不影响用户正常游戏的音量。
    /// </summary>
    private void MuteAudio(string reason)
    {
        try
        {
            var options = Game1.options;
            if (options is null)
            {
                return;
            }

            options.musicVolumeLevel = 0f;
            options.soundVolumeLevel = 0f;
            options.ambientVolumeLevel = 0f;
            options.footstepVolumeLevel = 0f;

            // 关键一步：游戏把 options 的等级换算成分类音量与
            // musicPlayerVolume / ambientPlayerVolume 缓存在 initializeVolumeLevels()
            // 里。只改字段不调用它，正在播放的音乐仍按旧缓存音量出声（实测如此）。
            var applied = ApplyGameVolumeLevels();

            // 音频分类的具体类型随游戏版本变化，用反射调用 SetVolume，
            // 失败时只记录、不影响场景。
            var categories = 0;
            foreach (var fieldName in new[]
                     {
                         "musicCategory", "ambientCategory", "soundCategory", "footstepCategory",
                     })
            {
                if (ApplyCategoryVolume(fieldName, 0f))
                {
                    categories++;
                }
            }

            audioMuted = true;
            audioMuteEvidence =
                $"{reason}：音量字段=0，initializeVolumeLevels={applied}，音频分类 {categories}/4";
            if (!audioMuteLogged)
            {
                audioMuteLogged = true;
                monitor.Log(
                    $"视觉测试已静音（{audioMuteEvidence}）；只改本次进程的运行时音量，不写设置文件。",
                    LogLevel.Info);
            }
        }
        catch (Exception exception)
        {
            audioMuteEvidence = $"{reason}：静音失败 {exception.GetType().Name}: {exception.Message}";
            if (!audioMuteLogged)
            {
                audioMuteLogged = true;
                monitor.Log($"视觉测试静音失败：{exception.Message}", LogLevel.Warn);
            }
        }
    }

    /// <summary>调用游戏自己的音量应用逻辑（private static void initializeVolumeLevels()）。</summary>
    private static bool ApplyGameVolumeLevels()
    {
        var method = typeof(Game1).GetMethod(
            "initializeVolumeLevels",
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
        if (method is null)
        {
            return false;
        }

        method.Invoke(null, null);
        return true;
    }

    private static bool ApplyCategoryVolume(string fieldName, float volume)
    {
        var field = typeof(Game1).GetField(
            fieldName,
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
        var category = field?.GetValue(null);
        if (category is null)
        {
            return false;
        }

        var setter = category.GetType().GetMethod("SetVolume", new[] { typeof(float) });
        if (setter is null)
        {
            return false;
        }

        setter.Invoke(category, new object[] { volume });
        return true;
    }

    private void OnGameLaunched(object? sender, GameLaunchedEventArgs e)
    {
        _ = sender;
        _ = e;
        MuteAudio("GameLaunched");
    }

    public void Dispose()
    {
        if (disposed)
        {
            return;
        }

        disposed = true;
        RestoreGroupHubState();
        helper.Events.GameLoop.UpdateTicked -= OnUpdateTicked;
        helper.Events.GameLoop.SaveLoaded -= OnSaveLoaded;
        helper.Events.GameLoop.GameLaunched -= OnGameLaunched;
        helper.Events.Display.RenderedActiveMenu -= OnRenderedActiveMenu;
        helper.Events.Display.Rendered -= OnRendered;
        helper.Events.GameLoop.ReturnedToTitle -= OnReturnedToTitle;
    }

    private void OnUpdateTicked(object? sender, UpdateTickedEventArgs e)
    {
        _ = sender;
        if (completed || disposed)
        {
            return;
        }

        ticks++;
        try
        {
            // 存档加载等阶段可能重新应用音量设置，这里在几个时间点补一次静音；
            // 第 1 帧那次是为了压住标题界面刚开始的音乐。
            if (ticks is 1 or 30 or 300 or 1800)
            {
                MuteAudio($"tick-{ticks}");
            }

            ApplyRequestedBackBuffer();
            var gameReady = IsGameReady();
            if (!gameReady && !loadRequested && ticks >= 30)
            {
                loadRequested = true;
                SaveGame.Load(options.SaveName);
                monitor.Log($"视觉测试正在加载存档：{options.SaveName}", LogLevel.Trace);
            }

            if (gameReady && !worldReadyLogged)
            {
                worldReadyLogged = true;
                worldReadyAtTick = ticks;
                monitor.Log($"视觉测试检测到世界已就绪：tick={ticks}；等待 SaveLoaded 后打开菜单", LogLevel.Trace);
            }

            if (gameReady &&
                !saveLoadedLogged &&
                !fallbackGateLogged &&
                worldReadyAtTick >= 0 &&
                ticks - worldReadyAtTick >= FallbackReadyTicks)
            {
                fallbackGateLogged = true;
                openAtTick = ticks + 30;
                monitor.Log($"视觉测试未收到 SaveLoaded，启用长稳定回退闸门：tick={ticks}；预定打开菜单={openAtTick}", LogLevel.Trace);
            }

            if (VisualTestHarnessRules.CanOpenMenu(
                    saveLoadedLogged || fallbackGateLogged,
                    IsFadeClear(),
                    menuOpened,
                    gameReady,
                    ticks,
                    openAtTick))
            {
                OpenMenu();
            }

            // 菜单已挂上但迟迟没有渲染帧时给出可诊断的线索：绝大多数情况是
            // activeMenu 与 Game1.activeClickableMenu 不一致（截图闸门会静默跳过）。
            if (menuOpened &&
                activeMenuFrames == 0 &&
                openAtTick >= 0 &&
                ticks - openAtTick >= 300 &&
                ticks - lastMenuRenderWarningTick >= 300)
            {
                lastMenuRenderWarningTick = ticks;
                monitor.Log(
                    $"视觉测试仍在等待活动菜单渲染帧：ticks={ticks}；" +
                    $"harnessMenu={activeMenu?.GetType().Name ?? "null"}；" +
                    $"gameActiveMenu={Game1.activeClickableMenu?.GetType().Name ?? "null"}",
                    LogLevel.Trace);
            }

            if (loadRequested &&
                (!gameReady || (!saveLoadedLogged && !fallbackGateLogged)) &&
                ticks - lastStatusTick >= 60)
            {
                lastStatusTick = ticks;
                monitor.Log(
                    $"视觉测试等待世界就绪：tick={ticks}；gameMode={Game1.gameMode}; " +
                    $"hasLoadedGame={GetGameLoadFlag("hasLoadedGame")}; " +
                    $"firstLoad={GetGameLoadFlag("FinishedFirstLoadContent")}; " +
                    $"incrementalLoad={GetGameLoadFlag("FinishedIncrementalLoad")}; " +
                    $"saveObject={HasLoadedSaveObject()}; " +
                    $"location={Game1.currentLocation?.Name ?? "null"}; " +
                    $"fadeClear={IsFadeClear()}",
                    LogLevel.Trace);
            }
        }
        catch (Exception exception)
        {
            Fail($"启动视觉测试场景失败：{exception.Message}");
        }
    }

    private void ApplyRequestedBackBuffer()
    {
        if (backBufferApplied)
        {
            return;
        }

        backBufferApplied = true;
        if (options.BackBufferWidth is not { } width ||
            options.BackBufferHeight is not { } height)
        {
            return;
        }

        Game1.graphics.PreferredBackBufferWidth = width;
        Game1.graphics.PreferredBackBufferHeight = height;
        Game1.graphics.ApplyChanges();
        monitor.Log(
            $"视觉测试已应用请求的 backbuffer：{width}×{height}",
            LogLevel.Info);
    }

    private static bool IsGameReady()
    {
        return VisualTestHarnessRules.IsGameReadyFromGameState() &&
            GetGameLoadFlag("hasLoadedGame");
    }

    private static bool GetGameLoadFlag(string fieldName)
    {
        var field = typeof(Game1).GetField(
            fieldName,
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
        return field?.GetValue(null) as bool? ?? false;
    }

    private static bool HasLoadedSaveObject()
    {
        var field = typeof(SaveGame).GetField(
            "loaded",
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
        return field?.GetValue(null) is not null;
    }

    private static bool IsFadeClear()
    {
        var screenFadeField = typeof(Game1).GetField(
            "screenFade",
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
        var screenFade = screenFadeField?.GetValue(null);
        if (screenFade is null)
        {
            return false;
        }

        var fadeType = screenFade.GetType();
        var alphaField = fadeType.GetField(
            "fadeToBlackAlpha",
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
        var fadeToBlackField = fadeType.GetField(
            "fadeToBlack",
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
        var alpha = alphaField?.GetValue(screenFade) as float? ?? 1f;
        var fadingToBlack = fadeToBlackField?.GetValue(screenFade) as bool? ?? true;
        return !fadingToBlack && alpha <= 0.01f;
    }

    private void OnSaveLoaded(object? sender, SaveLoadedEventArgs e)
    {
        _ = sender;
        _ = e;
        openAtTick = ticks + 30;
        if (!saveLoadedLogged)
        {
            saveLoadedLogged = true;
            monitor.Log($"视觉测试收到 SaveLoaded：tick={ticks}", LogLevel.Trace);
        }
    }

    private void OpenMenu()
    {
        if (options.ActionId == VisualTestHarnessRules.GroupHubActionId)
        {
            OpenGroupHub();
            return;
        }

        if (options.ActionId == VisualTestHarnessRules.GroupMessageActionId)
        {
            OpenGroupMessage();
            return;
        }

        if (options.ActionId == VisualTestHarnessRules.GroupSendActionId)
        {
            OpenGroupSend();
            return;
        }

        if (options.ActionId == VisualTestHarnessRules.GroupAcceptActionId)
        {
            OpenGroupFlow();
            return;
        }

        var service = getConversationService();
        var npc = getNpc();
        monitor.Log(
            $"视觉测试准备打开菜单：service={(service is null ? "null" : "ok")}；npc={(npc?.Name ?? "null")}",
            LogLevel.Trace);
        if (service is null || npc is null)
        {
            Fail("视觉测试无法取得 ConversationService 或目标 NPC。");
            return;
        }

        var scenario = VisualTestHarnessRules.GetScenarioContent(options.ScenarioId);
        menu = new ChatInputMenu(
            npc,
            service,
            storyStateStore,
            _ => monitor.Log("视觉测试聊天菜单已关闭。", LogLevel.Trace),
            scenario.InitialMessages,
            scenario.FriendshipHearts);
        activeMenu = menu;
        initialMessageCount = menu.Messages.Count;
        Game1.activeClickableMenu = menu;
        menuOpened = true;
        monitor.Log(
            $"视觉测试已打开真实聊天菜单，预置消息={scenario.InitialMessages.Count}；" +
            $"好感度覆盖={(scenario.FriendshipHearts?.ToString() ?? "无")}；等待 Rendered 帧。",
            LogLevel.Trace);
    }

    private void OpenGroupHub()
    {
        groupHubStateBeforeTest = storyStateStore.State;
        var invitation = VisualTestHarnessRules.CreateGroupHubInvitation(Game1.Date.TotalDays);
        storyStateStore.Replace(storyStateStore.State with
        {
            GroupDialogueInvitations = new[] { invitation },
        });

        try
        {
            if (!openGroupHub())
            {
                RestoreGroupHubState();
                Fail("视觉测试无法通过生产入口打开线上多人对话中心。");
                return;
            }

            if (Game1.activeClickableMenu is not GroupDialogueHubMenu groupHubMenu)
            {
                RestoreGroupHubState();
                Fail("视觉测试生产入口打开的不是 GroupDialogueHubMenu。");
                return;
            }

            activeMenu = groupHubMenu;
            menuOpened = true;
            monitor.Log(
                "视觉测试已通过生产 F9 入口打开真实线上多人对话中心；仅使用内存测试邀约，不发起 Bridge 请求。",
                LogLevel.Info);
        }
        catch (Exception exception)
        {
            RestoreGroupHubState();
            Fail($"视觉测试打开线上多人对话中心失败：{exception.Message}");
        }
    }

    /// <summary>
    /// 群聊端到端场景：走真实生产入口创建 <see cref="GroupDialogueMenu"/>，
    /// 再把一条模拟的 Bridge 响应交给菜单自己的 pendingRequest 管线。
    /// 本场景不发起任何 Bridge 请求，只验证“响应 → 会话 → 存档长期记忆”这条链路。
    /// </summary>
    private void OpenGroupMessage()
    {
        groupHubStateBeforeTest = storyStateStore.State;
        var invitation = VisualTestHarnessRules.CreateGroupHubInvitation(Game1.Date.TotalDays);
        storyStateStore.Replace(storyStateStore.State with
        {
            GroupDialogueInvitations = new[] { invitation },
        });

        try
        {
            var participants = VisualTestHarnessRules.CreateGroupMessageParticipants();
            if (Game1.activeClickableMenu is TitleMenu titleMenu)
            {
                // 直接 SaveGame.Load 的加载路径会把标题菜单留在原位；与生产 F9
                // 入口一样先清掉它，再把真实群聊菜单挂成活动菜单。
                titleMenu.exitThisMenuNoSound();
                Game1.activeClickableMenu = null;
            }

            // bridgeClient 传 null：本场景不发请求；万一有人点了发送，
            // 也只会得到“Bridge 当前不可用”，不会悄悄联网。
            var groupMenu = new GroupDialogueMenu(
                bridgeClient: null,
                storyStateStore,
                invitation,
                participants);
            // 必须挂成游戏的活动菜单，否则 Rendered/RenderedActiveMenu 的
            // ReferenceEquals 闸门会静默跳过，永远等不到截图时机。
            Game1.activeClickableMenu = groupMenu;
            activeMenu = groupMenu;
            menuOpened = true;
            groupParticipantIds = participants
                .Select(item => item.NpcId)
                .ToArray();
            groupMenu.QueueResponseForVisualTest(
                VisualTestHarnessRules.CreateGroupMessageResponse(),
                "视觉测试：这条群聊消息不会发往 Bridge。");
            monitor.Log(
                "视觉测试已打开真实群聊菜单，并排入一条模拟响应；" +
                "等待 update/draw 里的真实 PumpPendingRequest 应用它。",
                LogLevel.Info);
        }
        catch (Exception exception)
        {
            RestoreGroupHubState();
            Fail($"视觉测试打开群聊菜单失败：{exception.Message}");
        }
    }

    /// <summary>
    /// 记录群聊场景的证据。必须在截图完成后、存档状态还原前取值，
    /// 因此这里一次性把 manifest 与诊断需要的字段都存下来。
    /// </summary>
    private void RecordGroupMessageEvidence(GroupDialogueMenu groupMenu)
    {
        var groupMemories = storyStateStore.State.Memories
            .Where(memory => memory.MemoryId.StartsWith("group:", StringComparison.Ordinal))
            .ToArray();
        groupResponseTurns = groupMenu.Session.PublicHistory
            .Count(entry => string.Equals(entry.SpeakerType, "npc", StringComparison.Ordinal));
        groupInvitationStatus = groupMenu.Session.Invitation.Status.ToString();
        groupMemoryCount = groupMemories.Length;
        groupMemoryNpcCount = groupMemories
            .Select(memory => memory.OwnerNpcId)
            .Where(owner => !string.IsNullOrWhiteSpace(owner))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Count();
        groupMemoryWrites = groupMemories
            .Select(memory => new GroupMemoryWrite(
                memory.OwnerNpcId,
                memory.Content))
            .ToArray();
        monitor.Log(
            $"视觉测试群聊响应已应用：turns={groupResponseTurns}；" +
            $"invitation={groupInvitationStatus}；" +
            $"groupMemories={groupMemoryCount}；记忆归属NPC={groupMemoryNpcCount}",
            LogLevel.Info);
    }

    /// <summary>
    /// 群聊真实发送场景：走生产入口创建 <see cref="GroupDialogueMenu"/>，填好输入框
    /// 并点击“发送”，真的发一次 Bridge 群聊请求。它覆盖模拟响应场景覆盖不到的两处：
    /// <see cref="BridgeClient.SendGroupAsync"/> 成功路径里的内存层一条式记忆，
    /// 以及每个参与者各自 gameState 的转发。
    /// </summary>
    private void OpenGroupSend()
    {
        groupHubStateBeforeTest = storyStateStore.State;
        var invitation = VisualTestHarnessRules.CreateGroupSendInvitation(Game1.Date.TotalDays);
        storyStateStore.Replace(storyStateStore.State with
        {
            GroupDialogueInvitations = new[] { invitation },
        });

        var client = getBridgeClient();
        if (client is null)
        {
            RestoreGroupHubState();
            Fail("视觉测试群聊真实发送需要一个可用的 BridgeClient，当前为 null。");
            return;
        }

        try
        {
            var participants = VisualTestHarnessRules.CreateGroupSendParticipants();
            if (Game1.activeClickableMenu is TitleMenu titleMenu)
            {
                titleMenu.exitThisMenuNoSound();
                Game1.activeClickableMenu = null;
            }

            activeBridgeClient = client;
            groupParticipantIds = participants.Select(item => item.NpcId).ToArray();
            groupHistoryBefore = participants
                .Select(item => (item.NpcId, Count: client.VisualTestHistoryCount(item.NpcId)))
                .ToArray();

            var groupMenu = new GroupDialogueMenu(
                client,
                storyStateStore,
                invitation,
                participants);
            Game1.activeClickableMenu = groupMenu;
            activeMenu = groupMenu;
            menuOpened = true;
            groupMenu.PressSendForVisualTest(VisualTestHarnessRules.GroupSendPlayerMessage);
            monitor.Log(
                $"视觉测试已通过生产菜单发送真实群聊消息：\"{VisualTestHarnessRules.GroupSendPlayerMessage}\"；等待 Bridge 回复。",
                LogLevel.Info);
        }
        catch (Exception exception)
        {
            RestoreGroupHubState();
            Fail($"视觉测试群聊真实发送失败：{exception.Message}");
        }
    }

    /// <summary>
    /// F9 全流程场景：走真实生产入口打开线上多人对话中心，再按真实的点击路径
    /// 走完“接受邀约卡 → 群聊菜单”。全程不发起 Bridge 请求，
    /// 只验证菜单流转、参与者名单与邀约状态。
    /// </summary>
    private void OpenGroupFlow()
    {
        // 直接 SaveGame.Load 的路径下，存档加载晚于长稳定回退闸门（实测闸门在
        // tick 1861 打开，SaveLoaded 在 1865 才到），而 OnSaveLoaded 会用存档里的
        // 故事状态整体覆盖 store——早于它写入的测试邀约会被冲掉，表现为点击
        // “接受”时 TrySetGroupInvitationStatus 找不到那张卡、菜单不切换。
        // 因此这里先等 SaveLoaded（最多再等 30 秒），再写邀约并打开中心。
        if (!saveLoadedLogged && ticks - openAtTick < 1800)
        {
            if (!groupFlowDeferLogged)
            {
                groupFlowDeferLogged = true;
                monitor.Log(
                    "视觉测试 F9 全流程：等待 SaveLoaded 后再写入测试邀约并打开多人对话中心。",
                    LogLevel.Trace);
            }

            return;
        }

        groupHubStateBeforeTest = storyStateStore.State;
        var invitation = VisualTestHarnessRules.CreateGroupHubInvitation(Game1.Date.TotalDays);
        storyStateStore.Replace(storyStateStore.State with
        {
            GroupDialogueInvitations = new[] { invitation },
        });

        try
        {
            if (!openGroupHub())
            {
                RestoreGroupHubState();
                Fail("视觉测试无法通过生产入口打开线上多人对话中心。");
                return;
            }

            if (Game1.activeClickableMenu is not GroupDialogueHubMenu hub)
            {
                RestoreGroupHubState();
                Fail("视觉测试生产入口打开的不是 GroupDialogueHubMenu。");
                return;
            }

            activeMenu = hub;
            menuOpened = true;
            groupFlowStage = "hub-accept";
            monitor.Log(
                "视觉测试 F9 全流程：已打开多人对话中心，等待点击邀约卡的“接受”。",
                LogLevel.Info);
        }
        catch (Exception exception)
        {
            RestoreGroupHubState();
            Fail($"视觉测试 F9 全流程打开多人对话中心失败：{exception.Message}");
        }
    }

    /// <summary>按当前步骤推进 F9 全流程；每一步都在菜单渲染稳定后进行。</summary>
    private void AdvanceGroupFlow()
    {
        if (actionTriggered)
        {
            return;
        }

        switch (groupFlowStage)
        {
            case "hub-accept":
            {
                if (activeMenuFrames < 3 || activeMenu is not GroupDialogueHubMenu hub)
                {
                    return;
                }

                var rows = hub.VisualTestInvitationRows;
                if (rows.Count == 0)
                {
                    return;
                }

                var accept = GroupDialogueHubMenu.VisualTestAcceptButton(rows[0]);
                groupFlowStage = "dialogue";
                activeMenuFrames = 0;
                var invitationId = hub.VisualTestPendingInvitationId;
                EnsureInvitationPresent(invitationId);
                monitor.Log(
                    $"视觉测试 F9 全流程：点击邀约卡“接受”，x={accept.Center.X}；y={accept.Center.Y}" +
                    $"；行={rows[0]}；邀约={invitationId ?? "(无)"}；" +
                    $"点击前 state=[{DescribeInvitations()}]",
                    LogLevel.Info);
                try
                {
                    hub.receiveLeftClick(accept.Center.X, accept.Center.Y);
                }
                catch (Exception exception)
                {
                    Fail($"视觉测试 F9 全流程点击邀约卡失败：{exception.Message}");
                    return;
                }

                monitor.Log(
                    $"视觉测试 F9 全流程：点击后 hint=“{hub.VisualTestHint}”；" +
                    $"state=[{DescribeInvitations()}]",
                    LogLevel.Info);
                PromoteGroupFlowMenu();
                return;
            }

            case "dialogue":
            {
                if (activeMenuFrames < 3 || activeMenu is not GroupDialogueMenu dialogue)
                {
                    return;
                }

                RecordGroupFlowEvidence(dialogue);
                actionTriggered = true;
                return;
            }
        }
    }

    /// <summary>点击后活动菜单会被同步替换，这里把 harness 的观察对象跟着换过去。</summary>
    private void PromoteGroupFlowMenu()
    {
        var active = Game1.activeClickableMenu;
        monitor.Log(
            $"视觉测试 F9 全流程：点击后活动菜单 = {active?.GetType().Name ?? "null"}",
            LogLevel.Info);
        switch (active)
        {
            case GroupDialogueMenu dialogue:
                activeMenu = dialogue;
                return;
            case GroupDialogueHubMenu hub:
                activeMenu = hub;
                return;
            default:
                Fail(
                    "视觉测试 F9 全流程：点击后活动菜单不是预期的多人对话菜单" +
                    $"（实际 {Game1.activeClickableMenu?.GetType().Name ?? "null"}）。");
                return;
        }
    }

    /// <summary>
    /// 确保 hub 正在显示的那张测试邀约仍存在于 store 里。
    /// 直接 SaveGame.Load 的路径下，存档的故事状态会在中心打开之后才灌进
    /// store（harness 的 SaveLoaded 订阅早于 ModEntry），于是 hub 的列表快照
    /// 与 store 内容会短暂不一致，点击“接受”时 TrySetGroupInvitationStatus
    /// 会因找不到该卡而失败。真实玩家不会遇到这个时序，它只影响测试脚手架。
    /// </summary>
    private void EnsureInvitationPresent(string? invitationId)
    {
        if (string.IsNullOrWhiteSpace(invitationId))
        {
            return;
        }

        var state = storyStateStore.State;
        if (state.GroupDialogueInvitations.Any(item =>
                string.Equals(item.InvitationId, invitationId, StringComparison.Ordinal)))
        {
            return;
        }

        var restored = VisualTestHarnessRules.CreateGroupHubInvitation(Game1.Date.TotalDays);
        storyStateStore.Replace(state with
        {
            GroupDialogueInvitations = state.GroupDialogueInvitations
                .Concat(new[] { restored })
                .ToArray(),
        });
        monitor.Log(
            "视觉测试 F9 全流程：存档状态在中心打开后灌入、测试邀约被挤出 store，已在点击前补回。",
            LogLevel.Info);
    }

    /// <summary>诊断用：store 里所有邀约的 ID 与状态。</summary>
    private string DescribeInvitations()
    {
        var invitations = storyStateStore.State.GroupDialogueInvitations;
        return invitations.Count == 0
            ? "空"
            : string.Join(
                "，",
                invitations.Select(item => $"{item.InvitationId}:{item.Status}"));
    }

    private void RecordGroupFlowEvidence(GroupDialogueMenu dialogue)
    {
        var invitation = dialogue.Session.Invitation;
        groupInvitationStatus = invitation.Status.ToString();
        groupParticipantIds = invitation.Participants.ToArray();
        // 与 RecordGroupMessageEvidence 同一个口径：只数 NPC 回合。
        // 2026-09-22 起群聊的 PublicHistory 里也有玩家行（玩家发言进请求历史），
        // 这个字段名叫「响应回合数」，若把玩家行算进去，两处证据行会给出两个不同的数。
        groupResponseTurns = dialogue.Session.PublicHistory
            .Count(entry => string.Equals(entry.SpeakerType, "npc", StringComparison.Ordinal));
        groupFlowSummary =
            $"{(string.IsNullOrWhiteSpace(invitation.Title) ? "（无标题）" : invitation.Title)}" +
            $" · 参与者 {string.Join("、", groupParticipantIds)}" +
            $" · 状态 {groupInvitationStatus}" +
            $" · 话题 {(string.IsNullOrWhiteSpace(invitation.Topic) ? "（无）" : invitation.Topic)}";
        monitor.Log($"视觉测试 F9 全流程到达群聊菜单：{groupFlowSummary}", LogLevel.Info);
    }

    private void WriteGroupFlowDiagnostics(string outputDirectory)
    {
        if (options.ActionId is not VisualTestHarnessRules.GroupAcceptActionId)
        {
            return;
        }

        var diagnostics = new
        {
            action = options.ActionId,
            flow = groupFlowSummary,
            flowStage = groupFlowStage,
            participants = groupParticipantIds,
            invitationStatus = groupInvitationStatus,
            intermediateScreenshots,
        };
        var path = Path.Combine(outputDirectory, $"{options.ScenarioId}-diagnostics.json");
        File.WriteAllText(path, JsonSerializer.Serialize(diagnostics));
    }

    /// <summary>真实发送场景的证据：请求侧状态转发 + 内存层记忆前后对照。</summary>
    private void RecordGroupSendEvidence(GroupDialogueMenu groupMenu)
    {
        RecordGroupMessageEvidence(groupMenu);
        groupRequestStateCount = groupMenu.LastRequestStateCount;
        groupRequestParticipantIds = groupMenu.LastRequestParticipantIds;
        groupRequestParticipantsJson = JsonSerializer.Serialize(
            groupMenu.LastRequestParticipants);
        groupLastResponseJson = groupMenu.LastResponseJson;

        var client = activeBridgeClient;
        if (client is null)
        {
            return;
        }

        var after = groupParticipantIds
            .Select(npcId => (NpcId: npcId, Count: client.VisualTestHistoryCount(npcId)))
            .ToArray();
        groupHistoryEvidence = after
            .Select(item =>
            {
                var before = groupHistoryBefore
                    .Where(entry => string.Equals(entry.NpcId, item.NpcId, StringComparison.OrdinalIgnoreCase))
                    .Select(entry => entry.Count)
                    .FirstOrDefault();
                return $"{item.NpcId}:{before}->{item.Count}";
            })
            .ToArray();
        groupMemoryLayerCount = after.Sum(item => item.Count);
        groupMemoryLayerGainCount = after.Sum(item =>
            item.Count - groupHistoryBefore
                .Where(entry => string.Equals(entry.NpcId, item.NpcId, StringComparison.OrdinalIgnoreCase))
                .Select(entry => entry.Count)
                .FirstOrDefault());
        monitor.Log(
            $"视觉测试群聊真实发送证据：请求参与者={string.Join("、", groupRequestParticipantIds)}；" +
            $"带各自状态={groupRequestStateCount}；" +
            $"内存层记忆 {string.Join("；", groupHistoryEvidence)}；净增={groupMemoryLayerGainCount}",
            LogLevel.Info);
        // 群聊场次（2026-09-21）：面板上真正画出来的发言条数，与存档里那一场的发言条数应当一致
        // ——「F9 画面 = 存档场次 = F8 回看」这条链的证据就打在下一行里。
        var sessionEvidence = groupParticipantIds
            .Select(npcId => $"{npcId}={client.RecentGroupSessions(npcId)
                .Sum(session => session.Lines.Count)}")
            .ToArray();
        monitor.Log(
            $"视觉测试群聊场次证据：面板发言={groupMenu.VisibleMessages.Count}；" +
            $"存档场次 {string.Join("；", sessionEvidence)}",
            LogLevel.Info);
    }

    private void OnRenderedActiveMenu(object? sender, RenderedActiveMenuEventArgs e)
    {
        _ = sender;
        _ = e;
        if (completed || !menuOpened || activeMenu is null ||
            !ReferenceEquals(Game1.activeClickableMenu, activeMenu))
        {
            return;
        }

        if (!renderLogged)
        {
            renderLogged = true;
            monitor.Log("视觉测试已收到首个真实 Rendered 帧。", LogLevel.Trace);
        }
        // 该事件用于确认活动菜单 pass 已经执行；实际截图在 Rendered
        // 事件中读取，此时 SpriteBatch 已经结束并把命令刷新到目标纹理。
        activeMenuFrames++;

        if (VisualTestHarnessRules.CanTriggerTopicAction(
                options.ActionId,
                menuReady: true,
                actionTriggered,
                activeMenuFrames))
        {
            TriggerTopicAction();
        }

        if (VisualTestHarnessRules.CanTriggerGroupHubAction(
                options.ActionId,
                menuReady: true,
                actionTriggered,
                activeMenuFrames))
        {
            actionTriggered = true;
            monitor.Log(
                $"视觉测试已确认线上多人对话中心稳定渲染：activeMenuFrames={activeMenuFrames}",
                LogLevel.Info);
        }

        if (options.ActionId == VisualTestHarnessRules.TopicActionId &&
            actionTriggered &&
            !HasTopicResponse())
        {
            topicActionWaitFrames++;
            if (topicActionWaitFrames > 1800)
            {
                Fail("视觉测试自动点击找话题后，30 秒内没有收到 NPC 回复。" );
            }
        }

        if (options.ActionId == VisualTestHarnessRules.GroupMessageActionId)
        {
            if (!actionTriggered &&
                activeMenu is GroupDialogueMenu groupMenu &&
                groupMenu.Session.Invitation.Status == GroupInvitationStatus.Completed)
            {
                // 菜单的 update/draw 已经通过真实 PumpPendingRequest 处理了模拟响应，
                // 此时才允许截图，并立刻取走存档记忆的证据。
                actionTriggered = true;
                RecordGroupMessageEvidence(groupMenu);
                return;
            }

            if (!actionTriggered)
            {
                groupMessageWaitFrames++;
                if (groupMessageWaitFrames > 1800)
                {
                    Fail("视觉测试群聊场景在 30 秒内没有把模拟响应应用到会话。");
                }
            }
        }

        if (options.ActionId is VisualTestHarnessRules.GroupAcceptActionId)
        {
            AdvanceGroupFlow();
            if (!actionTriggered && !completed)
            {
                groupFlowWaitFrames++;
                if (groupFlowWaitFrames > 3600)
                {
                    Fail($"视觉测试 F9 全流程在 60 秒内没有走完（当前步骤 {groupFlowStage}）。");
                }
            }
        }

        if (options.ActionId == VisualTestHarnessRules.GroupSendActionId)
        {
            if (!actionTriggered && activeMenu is GroupDialogueMenu sendMenu)
            {
                if (sendMenu.Session.Invitation.Status == GroupInvitationStatus.Completed)
                {
                    actionTriggered = true;
                    RecordGroupSendEvidence(sendMenu);
                    return;
                }

                if (sendMenu.Session.CanRetry)
                {
                    // Bridge 失败或回合不合法：如实记录，不让场景假装通过。
                    actionTriggered = true;
                    RecordGroupSendEvidence(sendMenu);
                    Fail("视觉测试群聊真实请求返回了不可用回复（fallback 或名单外发言人），未写入记忆。");
                    return;
                }
            }

            if (!actionTriggered)
            {
                // 真实云端 multi_turn 比模拟响应慢得多，给到约 120 秒。
                groupMessageWaitFrames++;
                if (groupMessageWaitFrames > 7200)
                {
                    Fail("视觉测试群聊真实请求在 120 秒内没有返回可用回复。");
                }
            }
        }
    }

    private void TriggerTopicAction()
    {
        var topicButton = ChatLayoutRules.Calculate(
            Game1.viewport.Width,
            Game1.viewport.Height).TopicButton;
        actionTriggered = true;
        monitor.Log(
            $"视觉测试自动点击找话题：x={topicButton.Center.X}；y={topicButton.Center.Y}；" +
            $"activeMenuFrames={activeMenuFrames}",
            LogLevel.Info);
        try
        {
            menu!.receiveLeftClick(
                topicButton.Center.X,
                topicButton.Center.Y,
                playSound: false);
            monitor.Log("视觉测试找话题动作已发送，等待真实 Bridge 回复。", LogLevel.Trace);
        }
        catch (Exception exception)
        {
            Fail($"视觉测试自动点击找话题失败：{exception.Message}");
        }
    }

    private bool HasTopicResponse()
    {
        return menu is not null &&
            !menu.IsSending &&
            menu.Messages.Count > initialMessageCount;
    }

    private void LogTopicActionEvidence()
    {
        if (actionEvidenceLogged || menu is null || !HasTopicResponse())
        {
            return;
        }

        var replies = menu.Messages
            .Skip(initialMessageCount)
            .Where(message => string.Equals(message.Role, "npc", StringComparison.Ordinal))
            .Select(message => message.Content.Trim())
            .Where(content => content.Length > 0)
            .ToArray();
        if (replies.Length == 0)
        {
            Fail("视觉测试找话题动作完成，但没有可记录的 NPC 回复。");
            return;
        }

        actionEvidenceLogged = true;
        var replyText = string.Join(" | ", replies);
        monitor.Log(
            $"视觉测试找话题动作完成：新增 NPC 回复={replyText}",
            LogLevel.Info);
    }

    private void OnRendered(object? sender, RenderedEventArgs e)
    {
        _ = sender;
        _ = e;
        if (completed || !menuOpened || activeMenu is null ||
            !ReferenceEquals(Game1.activeClickableMenu, activeMenu) ||
            // 视觉目标必须在 SMAPI 完成存档上下文和 Content Patcher 资源注入
            // 后再读取；回退闸门可能先打开菜单，但不能先截半成品。
            !saveLoadedLogged ||
            activeMenuFrames == 0)
        {
            return;
        }

        renderedFrames++;
        if (options.ActionId == VisualTestHarnessRules.TopicActionId &&
            !HasTopicResponse())
        {
            renderedFrames = 0;
            return;
        }

        if (options.ActionId == VisualTestHarnessRules.GroupHubActionId &&
            !actionTriggered)
        {
            renderedFrames = 0;
            return;
        }

        if (options.ActionId == VisualTestHarnessRules.GroupMessageActionId &&
            !actionTriggered)
        {
            // 截图必须晚于“模拟响应已写进会话与存档记忆中”的那一刻。
            renderedFrames = 0;
            return;
        }

        if (options.ActionId is VisualTestHarnessRules.GroupSendActionId)
        {
            // 真实发送同理：要等 Bridge 回来、会话与内存层都落地后再截图。
            if (!actionTriggered)
            {
                renderedFrames = 0;
                return;
            }
        }

        if (options.ActionId is VisualTestHarnessRules.GroupAcceptActionId)
        {
            // F9 全流程：走到群聊菜单才算完成，中途截图由流程自己负责。
            if (!actionTriggered)
            {
                renderedFrames = 0;
                return;
            }
        }

        // 让游戏再完整刷新几帧，避免在菜单第一次提交到目标纹理前截到半帧。
        if (renderedFrames < 6)
        {
            return;
        }

        try
        {
            LogTopicActionEvidence();
            if (options.ActionId == VisualTestHarnessRules.TopicActionId &&
                !actionEvidenceLogged)
            {
                return;
            }
            LogRenderTargets();
            CaptureMenuRenderTarget();
        }
        catch (Exception exception)
        {
            Fail($"截图失败：{exception.Message}");
        }
    }

    private void CaptureMenuRenderTarget()
    {
        var outputDirectory = Path.GetFullPath(options.OutputDirectory);
        Directory.CreateDirectory(outputDirectory);
        var screenshotFile = $"{options.ScenarioId}.png";
        var manifestFile = $"{options.ScenarioId}.json";
        var manifestPath = Path.Combine(outputDirectory, manifestFile);
        var donePath = Path.Combine(outputDirectory, "visual-test.done");

        var capture = CaptureMenuToPng(activeMenu!, screenshotFile);
        var screenshotPath = capture.Path;
        var width = capture.Width;
        var height = capture.Height;

        var manifest = new VisualTestManifest(
            SchemaVersion: 1,
            ScenarioId: options.ScenarioId,
            GameVersion: Game1.version,
            SmapiVersion: Constants.ApiVersion.ToString(),
            ModDllSha256: ComputeAssemblySha256(),
            Locale: LocalizedContentManager.CurrentLanguageCode.ToString(),
            BackBufferWidth: width,
            BackBufferHeight: height,
            UiViewportWidth: Game1.uiViewport.Width,
            UiViewportHeight: Game1.uiViewport.Height,
            UiScale: Game1.options.uiScale,
            Zoom: Game1.options.zoomLevel,
            ScreenshotFile: screenshotFile,
            CaptureSource: "isolated-game-spritebatch-render-target",
            GroupResponseTurns: groupResponseTurns,
            GroupMemoryCount: groupMemoryCount,
            GroupMemoryNpcCount: groupMemoryNpcCount,
            GroupInvitationStatus: groupInvitationStatus,
            GroupRequestStateCount: groupRequestStateCount,
            GroupMemoryLayerCount: groupMemoryLayerCount,
            GroupMemoryLayerGainCount: groupMemoryLayerGainCount);
        File.WriteAllText(manifestPath, manifest.ToJson());
        WriteGroupHubDiagnostics(outputDirectory);
        WriteGroupMessageDiagnostics(outputDirectory);
        WriteGroupFlowDiagnostics(outputDirectory);
        File.WriteAllText(
            Path.Combine(outputDirectory, "audio-mute.json"),
            JsonSerializer.Serialize(new
            {
                muted = audioMuted,
                evidence = audioMuteEvidence,
            }));
        File.WriteAllText(donePath, $"{manifestFile}{Environment.NewLine}");
        RestoreGroupHubState();
        completed = true;
        monitor.Log(
            $"视觉测试截图完成：{screenshotPath}；manifest={manifestPath}",
            LogLevel.Info);
    }

    private void LogRenderTargets()
    {
        var targets = Game1.graphics.GraphicsDevice.GetRenderTargets();
        if (targets.Length == 0)
        {
            monitor.Log("视觉测试 RenderedActiveMenu 当前没有绑定 RenderTarget。", LogLevel.Trace);
            return;
        }

        var descriptions = targets
            .Select(binding => binding.RenderTarget is Texture2D texture
                ? $"{texture.GetType().Name}:{texture.Width}x{texture.Height}"
                : binding.RenderTarget?.GetType().Name ?? "null")
            .ToArray();
        monitor.Log(
            $"视觉测试 RenderedActiveMenu RenderTarget：{string.Join(",", descriptions)}",
            LogLevel.Trace);
    }

    /// <summary>
    /// 把某个菜单重放到独立 RenderTarget 并存成 PNG，返回路径与实际像素尺寸。
    /// 终点截图与流程中途截图共用这一段；中途截图不会结束整个场景。
    /// </summary>
    private (string Path, int Width, int Height) CaptureMenuToPng(
        IClickableMenu menu,
        string screenshotFile)
    {
        ArgumentNullException.ThrowIfNull(menu);
        var outputDirectory = Path.GetFullPath(options.OutputDirectory);
        Directory.CreateDirectory(outputDirectory);
        var screenshotPath = Path.Combine(outputDirectory, screenshotFile);

        var graphicsDevice = Game1.graphics.GraphicsDevice;
        var parameters = graphicsDevice.PresentationParameters;
        var width = parameters.BackBufferWidth;
        var height = parameters.BackBufferHeight;
        if (width <= 0 || height <= 0)
        {
            throw new InvalidOperationException("backbuffer 尺寸无效。");
        }

        var previousTargets = graphicsDevice.GetRenderTargets();
        using var target = new RenderTarget2D(
            graphicsDevice,
            width,
            height,
            mipMap: false,
            preferredFormat: SurfaceFormat.Color,
            preferredDepthFormat: DepthFormat.None,
            preferredMultiSampleCount: 0,
            usage: RenderTargetUsage.PreserveContents);
        graphicsDevice.SetRenderTarget(target);

        // 原版菜单通过 Game1.drawDialogueBox 绘制对话框；该方法使用游戏自己的
        // 全局 SpriteBatch，而不是传入的任意新实例。使用全局 batch 在独立目标上
        // 重放一次菜单，才能保留完整的九宫格边框、字体和肖像，同时不把截图逻辑
        // 混入生产菜单。
        var spriteBatchField = typeof(Game1).GetField(
            "spriteBatch",
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static) ??
            throw new InvalidOperationException("无法取得 Game1.spriteBatch 字段。");
        var originalSpriteBatch = spriteBatchField.GetValue(null) as SpriteBatch ??
            throw new InvalidOperationException("无法取得 Game1.spriteBatch。");
        using var isolatedSpriteBatch = new SpriteBatch(graphicsDevice);
        try
        {
            spriteBatchField.SetValue(null, isolatedSpriteBatch);
            isolatedSpriteBatch.Begin(
                SpriteSortMode.Deferred,
                BlendState.AlphaBlend,
                SamplerState.PointClamp,
                DepthStencilState.None,
                RasterizerState.CullNone);
            menu.draw(isolatedSpriteBatch);
            isolatedSpriteBatch.End();
        }
        finally
        {
            spriteBatchField.SetValue(null, originalSpriteBatch);
            graphicsDevice.SetRenderTargets(previousTargets);
        }

        var pixels = new Color[width * height];
        target.GetData(pixels);
        graphicsDevice.SetRenderTargets(previousTargets);
        using (var texture = new Texture2D(graphicsDevice, width, height))
        {
            texture.SetData(pixels);
            using var stream = File.Create(screenshotPath);
            texture.SaveAsPng(stream, width, height);
        }

        return (screenshotPath, width, height);
    }

    /// <summary>多步流程的中途截图：只存图并登记文件名，不写 manifest、不结束场景。</summary>
    private void CaptureIntermediateFrame(string label)
    {
        if (activeMenu is null)
        {
            return;
        }

        try
        {
            var file = $"{options.ScenarioId}-{label}.png";
            var capture = CaptureMenuToPng(activeMenu, file);
            intermediateScreenshots.Add(file);
            monitor.Log($"视觉测试流程中途截图：{capture.Path}", LogLevel.Info);
        }
        catch (Exception exception)
        {
            Fail($"视觉测试流程中途截图失败：{exception.Message}");
        }
    }

    private void WriteGroupHubDiagnostics(string outputDirectory)
    {
        if (activeMenu is not GroupDialogueHubMenu groupHubMenu)
        {
            return;
        }

        var layout = groupHubMenu.VisualTestLayout;
        var diagnostics = new
        {
            gameViewport = new { width = Game1.viewport.Width, height = Game1.viewport.Height },
            uiViewport = new { width = Game1.uiViewport.Width, height = Game1.uiViewport.Height },
            backBuffer = new
            {
                width = Game1.graphics.GraphicsDevice.PresentationParameters.BackBufferWidth,
                height = Game1.graphics.GraphicsDevice.PresentationParameters.BackBufferHeight,
            },
            panel = ToDiagnosticRectangle(layout.Panel),
            closeButton = ToDiagnosticRectangle(layout.CloseButton),
        };
        var path = Path.Combine(outputDirectory, $"{options.ScenarioId}-diagnostics.json");
        File.WriteAllText(path, JsonSerializer.Serialize(diagnostics));
    }

    private void WriteGroupMessageDiagnostics(string outputDirectory)
    {
        if (options.ActionId is not VisualTestHarnessRules.GroupMessageActionId and
            not VisualTestHarnessRules.GroupSendActionId)
        {
            return;
        }

        var diagnostics = new
        {
            action = options.ActionId,
            participants = groupParticipantIds,
            invitationStatus = groupInvitationStatus,
            responseTurns = groupResponseTurns,
            groupMemoryCount = groupMemoryCount,
            groupMemoryNpcCount = groupMemoryNpcCount,
            groupMemories = groupMemoryWrites.Select(write => new
            {
                npcId = write.NpcId,
                content = write.Content,
            }),
            requestParticipantIds = groupRequestParticipantIds,
            requestStateCount = groupRequestStateCount,
            requestParticipants = groupRequestParticipantsJson,
            lastResponse = groupLastResponseJson,
            memoryLayerHistory = groupHistoryEvidence,
            memoryLayerCount = groupMemoryLayerCount,
            memoryLayerGainCount = groupMemoryLayerGainCount,
        };
        var path = Path.Combine(outputDirectory, $"{options.ScenarioId}-diagnostics.json");
        File.WriteAllText(path, JsonSerializer.Serialize(diagnostics));
    }

    private static object ToDiagnosticRectangle(Rectangle rectangle)
    {
        return new
        {
            x = rectangle.X,
            y = rectangle.Y,
            width = rectangle.Width,
            height = rectangle.Height,
        };
    }

    private void Fail(string message)
    {
        if (completed)
        {
            return;
        }

        RestoreGroupHubState();
        completed = true;
        try
        {
            var outputDirectory = Path.GetFullPath(options.OutputDirectory);
            Directory.CreateDirectory(outputDirectory);
            File.WriteAllText(
                Path.Combine(outputDirectory, "visual-test.failed"),
                message + Environment.NewLine);
        }
        catch (Exception writeException)
        {
            message += $"；写入失败标记也失败：{writeException.Message}";
        }

        monitor.Log(message, LogLevel.Error);
    }

    private void OnReturnedToTitle(object? sender, ReturnedToTitleEventArgs e)
    {
        _ = sender;
        _ = e;
        Dispose();
    }

    private void RestoreGroupHubState()
    {
        if (groupHubStateBeforeTest is null)
        {
            return;
        }

        storyStateStore.Replace(groupHubStateBeforeTest);
        groupHubStateBeforeTest = null;
    }

    private static Dictionary<string, string?> ReadEnvironment()
    {
        var values = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        foreach (DictionaryEntry entry in Environment.GetEnvironmentVariables())
        {
            if (entry.Key is not null)
            {
                values[entry.Key.ToString()!] = entry.Value?.ToString();
            }
        }

        return values;
    }

    private static string ComputeAssemblySha256()
    {
        var path = Assembly.GetExecutingAssembly().Location;
        using var stream = File.OpenRead(path);
        using var sha256 = SHA256.Create();
        return Convert.ToHexString(sha256.ComputeHash(stream));
    }
}
