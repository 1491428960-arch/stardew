using HarmonyLib;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using System.Reflection;
using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewModdingAPI.Utilities;
using StardewValley;
using StardewValley.Locations;
using StardewValley.Menus;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

public sealed class ModEntry : Mod
{
    private ModConfig config = ModConfig.CreateDefault();
    private BridgeClient? bridgeClient;
    private ConversationService? conversationService;
    private KeybindList dialogueKey = new(SButton.F8);
    private KeybindList groupDialogueKey = new(SButton.F9);

    /// <summary>
    /// 开发用示例记录的三组按键（内容与边界见 <see cref="SampleChatHistory"/>）。
    /// 键位写死、不进 config：它是验收工具，不该出现在玩家的配置面板里；
    /// 带 Ctrl 是刻意的——单键容易误触，而误触会把示例灌进玩家自己的存档
    /// （虽然 Ctrl+F9 能一键清掉，但不误触更好）。
    /// </summary>
    private static readonly KeybindList SampleHistoryKey =
        new(new Keybind(SButton.LeftControl, SButton.F8));

    private static readonly KeybindList SampleHistoryStressKey =
        new(new Keybind(SButton.LeftControl, SButton.LeftShift, SButton.F8));

    private static readonly KeybindList SampleHistoryClearKey =
        new(new Keybind(SButton.LeftControl, SButton.F9));

    private const string SampleHistoryCommand = "ainpc_sample";
    private readonly StoryStateStore storyStateStore = new();
    private readonly ShareFriendshipLedger shareFriendshipLedger = new();
    private readonly EventAuditObserver eventAuditObserver = new();
    private HouseAccessController? houseAccessController;
    private FaceToFaceConversationCoordinator? faceToFaceCoordinator;
    private VisualTestHarness? visualTestHarness;
    private StardewNpc? testNpc;
    private FrameRateSampler? frameRateSampler;
    private GroupDialogueCoordinator? groupDialogueCoordinator;
    // 当前存档已读到的回看档案原文。重建 BridgeClient（改配置、重新载入存档）时用它回灌，
    // 免得一次配置变更就把玩家翻得到的历史抹掉；回标题时清空，避免串到下一个存档。
    private string? chatHistoryArchiveJson;

    public override void Entry(IModHelper helper)
    {
        config = helper.ReadConfig<ModConfig>().Normalize();
        ApplyConfig();
        groupDialogueCoordinator = new GroupDialogueCoordinator(
            storyStateStore,
            new GroupInvitationGenerator(GroupInvitationTemplates.All),
            GetKnownGroupParticipants,
            () => Game1.Date.TotalDays,
            () => $"{Game1.currentSeason} {Game1.dayOfMonth}",
            TryOpenGroupHub,
            CloseGroupMenu);
        faceToFaceCoordinator = new FaceToFaceConversationCoordinator(
            conversationService,
            storyStateStore,
            speaker => RuntimeDialogueSampler.Observe(Monitor, speaker),
            shareFriendshipLedger);
        houseAccessController = new HouseAccessController(
            Monitor,
            GetHouseAccessOptions);
        houseAccessController.Apply();
        visualTestHarness = new VisualTestHarness(
            helper,
            Monitor,
            () => conversationService,
            ResolveVisualTestNpc,
            storyStateStore,
            TryOpenGroupHubForVisualTest,
            () => bridgeClient);
        GameStateCollector.ConfigureModRegistry(new SmapiModRegistryStatus(helper.ModRegistry));
        // 角色气泡素材来自 DLL 内的嵌入资源。必须等 GraphicsDevice 就绪
        // （Entry 阶段常为 null），所以挂到 GameLaunched；失败只降级为纯配色，
        // 不能让一张缺失的图把整个 mod 拦在启动阶段。
        Texture2D? LoadSheet(string resourceName)
        {
            try
            {
                using var stream = typeof(ModEntry).Assembly
                    .GetManifestResourceStream(resourceName);
                return stream is null
                    ? null
                    : Texture2D.FromStream(Game1.graphics.GraphicsDevice, stream);
            }
            catch (Exception exception)
            {
                Monitor.Log(
                    $"气泡素材 {resourceName} 加载失败，退回纯配色绘制：{exception.Message}",
                    LogLevel.Warn);
                return null;
            }
        }

        helper.Events.GameLoop.GameLaunched += (_, _) =>
        {
            NpcBubbleStyle.Sheet = LoadSheet("StardewAI.NPC.assets.npc_bubbles.png");
            NpcBubbleStyle.FrameSheet =
                LoadSheet("StardewAI.NPC.assets.npc_bubble_frames.png");
            if (NpcBubbleStyle.Sheet is null)
            {
                Monitor.Log("角色气泡图集缺失，退回纯配色绘制。", LogLevel.Warn);
            }

            // 角色气泡底的描边归一变体：同样要等图形设备与 Maps\MenuTiles 就绪，
            // 拿不到就回退原图（观感同改前），不阻塞启动。理由见 NpcBubblePanelRules。
            NpcBubblePanelTexture.EnsureCreated(Monitor);
        };
        helper.Events.Input.ButtonPressed += OnButtonPressed;
        // 开发用示例记录：SMAPI 控制台命令与上面那三组按键共用同一份实现。
        // 命令需要 Console Commands（SMAPI 安装包自带）；按键那一路不依赖任何东西。
        helper.ConsoleCommands.Add(
            SampleHistoryCommand,
            "开发用：往 F8 回看档案注入示例聊天记录（只进内存，玩家保存后才随存档落盘）。"
                + $"用法：{SampleHistoryCommand} [inject|stress [npcId]|clear|status]，不带参数等于 inject。",
            OnSampleHistoryCommand);
        helper.Events.GameLoop.UpdateTicked += faceToFaceCoordinator.OnUpdateTicked;
        helper.Events.Player.Warped += OnPlayerWarped;
        helper.Events.Display.MenuChanged += faceToFaceCoordinator.OnMenuChanged;
        if (config.EnablePerformanceDiagnostics)
        {
            frameRateSampler = new FrameRateSampler(
                sample => Monitor.Log(
                    $"[StardewAI.Perf] windowMs={sample.WindowMilliseconds}; " +
                    $"renderedFrames={sample.RenderedFrames}; " +
                    $"fps={sample.FramesPerSecond:0.0}",
                    LogLevel.Info));
            helper.Events.Display.Rendered += OnRendered;
        }
        helper.Events.GameLoop.GameLaunched += OnGameLaunched;
        helper.Events.GameLoop.SaveLoaded += OnSaveLoaded;
        helper.Events.GameLoop.DayStarted += OnDayStarted;
        helper.Events.GameLoop.Saving += OnSaving;
        helper.Events.GameLoop.Saved += OnSaved;
        helper.Events.GameLoop.ReturnedToTitle += OnReturnedToTitle;
        Monitor.Log(
            $"AI NPC 原型已加载。按 {dialogueKey} 与当前地点 NPC 进行单人对话，按 {groupDialogueKey} 打开线上多人对话。",
            LogLevel.Info);
    }

    private void OnSaveLoaded(object? sender, SaveLoadedEventArgs e)
    {
        shareFriendshipLedger.Reset();
        eventAuditObserver.Reset();
        houseAccessController?.ResetMapCache();
        houseAccessController?.Apply();

        if (config.EnableDialogue && conversationService is null)
        {
            ApplyConfig();
        }

        try
        {
            var loaded = Helper.Data.ReadSaveData<string>(StoryStateSerializer.StorageKey);
            storyStateStore.Load(loaded);
            Monitor.Log(
                $"[StardewAI.State] 已载入存档数据：key={StoryStateSerializer.StorageKey} " +
                $"长度={loaded?.Length ?? 0} 邀约={storyStateStore.State.GroupDialogueInvitations.Count} 张",
                LogLevel.Info);
            foreach (var warning in storyStateStore.LastWarnings)
            {
                Monitor.Log($"故事状态已降级：{warning}", LogLevel.Warn);
            }
        }
        catch (Exception exception)
        {
            storyStateStore.Reset();
            Monitor.Log($"读取故事状态失败，已使用空状态：{exception.Message}", LogLevel.Warn);
        }

        // 回看档案必须在 ApplyConfig 之后读：上面那次 ApplyConfig 可能刚重建了 BridgeClient，
        // 而档案是灌进客户端内存的。
        LoadChatHistoryArchive();

        EnsureTestNpc();
    }

    private void OnSaving(object? sender, SavingEventArgs e)
    {
        try
        {
            var json = storyStateStore.Serialize();
            Helper.Data.WriteSaveData(StoryStateSerializer.StorageKey, json);
            Monitor.Log(
                $"[StardewAI.State] 已写入存档数据：key={StoryStateSerializer.StorageKey} " +
                $"长度={json.Length} 邀约={storyStateStore.State.GroupDialogueInvitations.Count} 张",
                LogLevel.Info);
        }
        catch (Exception exception)
        {
            Monitor.Log($"保存故事状态失败，已跳过本次写入：{exception.Message}", LogLevel.Warn);
        }

        SaveChatHistoryArchive();

        var testNpcLifecycle = TestNpcPlacementRules.GetLifecyclePolicy();
        if (testNpcLifecycle.ResetRepeatTargetBeforeSave)
        {
            faceToFaceCoordinator?.ResetRepeatTarget();
        }
        if (testNpcLifecycle.RemoveBeforeSave)
        {
            RemoveTestNpc();
        }
    }

    private void OnSaved(object? sender, SavedEventArgs e)
    {
        if (TestNpcPlacementRules.GetLifecyclePolicy().RecreateAfterSave)
        {
            EnsureTestNpc();
        }
    }

    /// <summary>
    /// 当前存档的文件夹名（SMAPI 的 <c>Constants.SaveFolderName</c>，形如 <c>农场名_123456789</c>）。
    /// 存档数据本身就存在当前存档里，这个标识是第二道保险：万一数据落到别的存档上，
    /// 读回时能认出来并丢掉。实际比对的是其中不随改名变化的存档 ID
    /// （见 <see cref="ChatHistoryArchive.SaveIdFromFolderName"/>）。
    /// 载入存档前或取不到存档信息时为 null。
    /// </summary>
    private static string? CurrentSaveFolderName => Constants.SaveFolderName;

    /// <summary>
    /// 载入**回看档案**（F8 面板「往上翻」的那一份）。读不到就空手开局——
    /// 老存档没有这份数据是常态，不是错误。
    ///
    /// 时机选 SaveLoaded：只有到这一步存档才算载入（SMAPI 的存档数据 API 在此之前会直接抛异常），
    /// 而玩家随时可能按 F8，档案必须在他第一次按键之前就装进内存。
    /// </summary>
    private void LoadChatHistoryArchive()
    {
        if (bridgeClient is null)
        {
            return;
        }

        var saveFolder = CurrentSaveFolderName;
        try
        {
            var json = Helper.Data.ReadSaveData<string>(ChatHistoryArchive.StorageKey);
            var loaded = bridgeClient.LoadDisplayHistory(json, saveFolder);
            chatHistoryArchiveJson = json;
            Monitor.Log(
                $"[StardewAI.History] 已载入回看档案：key={ChatHistoryArchive.StorageKey} " +
                $"存档={saveFolder ?? "<unknown>"} NPC={loaded.History.Count} " +
                $"条={loaded.MessageCount} 长度={json?.Length ?? 0}",
                LogLevel.Info);
            foreach (var warning in loaded.Warnings)
            {
                Monitor.Log($"回看档案已降级：{warning}", LogLevel.Warn);
            }
        }
        catch (Exception exception)
        {
            // 读不到就空手开局：不能因为一份历史把存档载入搞崩
            // （非主玩家、存档尚未载入等情况下 SMAPI 会直接抛异常）。
            chatHistoryArchiveJson = null;
            bridgeClient.LoadDisplayHistory(null, saveFolder);
            Monitor.Log($"读取回看档案失败，已从空档案开始：{exception.Message}", LogLevel.Warn);
        }
    }

    /// <summary>
    /// 把**回看档案**写进当前存档。
    ///
    /// 时机选 Saving（与故事状态同一处）：它在游戏真正落盘之前触发，写入的数据随存档一起被序列化，
    /// 所以「手动保存」「睡觉过夜」「退出到标题」三条路都覆盖得到；DayEnding 只在睡觉时触发
    /// （白天直接退游戏就丢），SaveCreating 只在新档创建时触发一次（那时还没有任何历史）。
    ///
    /// 这里**不**在每追加一条对话时就写：写一次的代价是把整份档案序列化成十几 MB 文本
    /// （满档 = 二十位 NPC 各 1000 条，实测 15.23 MB / 28 ms；现实规模——只跟五六位深聊——
    /// 是 0.89 MB / 1.7 ms，见 ChatHistoryArchiveTests 的两条预算用例），
    /// 一天下来几十轮对话就是几十次白干；
    /// 而 SMAPI 的 WriteSaveData 写的是内存里的 CustomData，本来也不落盘，多写毫无收益。
    /// </summary>
    private void SaveChatHistoryArchive()
    {
        if (bridgeClient is null)
        {
            return;
        }

        try
        {
            var json = bridgeClient.SerializeDisplayHistory(CurrentSaveFolderName);
            Helper.Data.WriteSaveData(ChatHistoryArchive.StorageKey, json);
            chatHistoryArchiveJson = json;
            Monitor.Log(
                $"[StardewAI.History] 已写入回看档案：key={ChatHistoryArchive.StorageKey} " +
                $"长度={json.Length}",
                LogLevel.Info);
        }
        catch (Exception exception)
        {
            Monitor.Log($"保存回看档案失败，已跳过本次写入：{exception.Message}", LogLevel.Warn);
        }
    }

    private void OnDayStarted(object? sender, DayStartedEventArgs e)
    {
        faceToFaceCoordinator?.ResetRepeatTarget();
        if (Context.IsWorldReady)
        {
            groupDialogueCoordinator?.OnDayStarted();
            Monitor.Log($"[StardewAI.Invite] {groupDialogueCoordinator?.LastDiagnostics}", LogLevel.Info);
        }
    }

    private void OnReturnedToTitle(object? sender, ReturnedToTitleEventArgs e)
    {
        shareFriendshipLedger.Reset();
        eventAuditObserver.Reset();
        houseAccessController?.ResetMapCache();
        houseAccessController?.Dispose();
        visualTestHarness?.Dispose();
        visualTestHarness = null;
        Helper.Events.Display.Rendered -= OnRendered;
        frameRateSampler = null;

        if (Game1.activeClickableMenu is ChatInputMenu)
        {
            Game1.activeClickableMenu.exitThisMenuNoSound();
        }
        groupDialogueCoordinator?.CloseIfOpen();

        RemoveTestNpc();

        conversationService?.Cancel();
        conversationService?.Dispose();
        conversationService = null;
        faceToFaceCoordinator?.UpdateService(null);
        groupDialogueCoordinator?.CloseIfOpen();
        bridgeClient?.Dispose();
        bridgeClient = null;
        storyStateStore.Reset();
        chatHistoryArchiveJson = null;
    }

    private void OnRendered(object? sender, RenderedEventArgs e)
    {
        _ = sender;
        _ = e;
        frameRateSampler?.OnRendered();
    }

    private void OnPlayerWarped(object? sender, WarpedEventArgs e)
    {
        if (!e.IsLocalPlayer || !Context.IsWorldReady)
        {
            return;
        }

        faceToFaceCoordinator?.ResetRepeatTarget();

        // FarmHouse can finish loading after SaveLoaded on some custom farm
        // maps. Retry when the player actually enters it so the test NPC is
        // available even when the location was not ready during SaveLoaded.
        if (e.NewLocation is FarmHouse)
        {
            EnsureTestNpc();
        }

        var observation = eventAuditObserver.Observe(
            EventAuditSnapshotReader.Read(e.NewLocation));
        var newEvents = observation.NewSeenEventIds.Count == 0
            ? "-"
            : string.Join(",", observation.NewSeenEventIds);
        var entryEvents = observation.EventIdsSinceLocationChange.Count == 0
            ? "-"
            : string.Join(",", observation.EventIdsSinceLocationChange);

        Monitor.Log(
            $"事件审计：地点={observation.LocationName ?? "<unknown>"}；" +
            $"时间={observation.Time?.ToString() ?? "<unknown>"}；" +
            $"活动事件={observation.CurrentEventId ?? (observation.EventIsActive ? "<active>" : "-" )}；" +
            $"本次新增={newEvents}；地点进入事件={entryEvents}；" +
            $"本Mod直接写入状态={observation.ModWouldMutateGameState}",
            LogLevel.Trace);
    }

    private void EnsureTestNpc()
    {
        if (!Context.IsWorldReady)
        {
            return;
        }

        // 关掉对话、或没打开测试 NPC 注入时，都走同一条清理路径：
        // 关闭注入不只是「不生成」，还要把旧版本可能已经序列化进存档的
        // 那个克隆体移掉——否则老档里那个「（测试）」角色会一直留在农舍里。
        if (!config.EnableDialogue || !ShouldInjectTestNpc())
        {
            RemoveTestNpc();
            return;
        }

        if (testNpc is not null)
        {
            return;
        }

        var farmhouse = Game1.getLocationFromName("FarmHouse") as FarmHouse;
        if (farmhouse is null)
        {
            Monitor.Log("未找到 FarmHouse，暂不生成床边测试 NPC。", LogLevel.Trace);
            return;
        }

        var bedSpot = farmhouse.GetPlayerBedSpot();
        if (!TestNpcPlacementRules.IsUsableBedSpot(bedSpot))
        {
            Monitor.Log(
                $"FarmHouse 尚未完成床位加载（bed={bedSpot.X},{bedSpot.Y}），" +
                "暂不生成床边测试 NPC。进入 FarmHouse 后会重试。",
                LogLevel.Trace);
            return;
        }

        var spawnTile = TestNpcPlacementRules.GetSpawnTile(bedSpot);
        var existing = farmhouse.getCharacterFromName(TestNpcPlacementRules.InternalName);
        if (existing is not null)
        {
            var lifecycle = TestNpcPlacementRules.GetLifecyclePolicy();
            if (!lifecycle.ReplaceExistingNpcOnLoad)
            {
                testNpc = existing;
                return;
            }

            // Old builds could serialize this runtime-only NPC. Replace it
            // completely so its non-serialized portrait/sprite overrides and
            // interactive dialogue are always restored.
            farmhouse.characters.Remove(existing);
            Monitor.Log("已移除存档中的旧测试 NPC，正在按当前配置重建。", LogLevel.Trace);
        }

        var templateName = NpcTargetResolver.ResolveTargetName(
            candidate => Game1.getCharacterFromName(candidate) is not null);
        var template = templateName is null
            ? null
            : Game1.getCharacterFromName(templateName);
        if (template is null)
        {
            Monitor.Log("未找到 Rasmodia/Wizard，暂不生成床边测试 NPC。", LogLevel.Trace);
            return;
        }

        try
        {
            var appearance = TestNpcPlacementRules.GetAppearancePolicy();
            var sprite = new AnimatedSprite(
                appearance.SpriteAssetName,
                currentFrame: 0,
                spriteWidth: 16,
                spriteHeight: 32);
            var portrait = Helper.GameContent.Load<Texture2D>(
                appearance.PortraitAssetName);
            var clone = new StardewNpc(
                sprite,
                Vector2.Zero,
                farmhouse.NameOrUniqueName,
                facingDirection: 2,
                TestNpcPlacementRules.InternalName,
                false,
                portrait)
            {
                displayName = $"{template.displayName}（测试）",
                Speed = 0,
                SimpleNonVillagerNPC = appearance.UseSimpleNonVillagerNpc,
            };
            PreserveInjectedTestNpcAppearance(clone, appearance);
            // NPC.Position is pixel-based, but setTilePosition also updates
            // the collision/bounding box consistently with vanilla NPCs.
            clone.setTilePosition(new Point(spawnTile.X, spawnTile.Y));
            clone.setNewDialogue(
                new Dialogue(
                    clone,
                    "StardewAI.NPC.TestGreeting",
                    "早上好！我是床边测试用 NPC。按交互键后可以测试原版寒暄和 AI 聊天。"),
                add: false,
                clearOnMovement: false);
            farmhouse.addCharacter(clone);
            testNpc = clone;
            Monitor.Log(
                $"已在 FarmHouse 床边生成测试 NPC：tile={spawnTile.X},{spawnTile.Y}",
                LogLevel.Info);
        }
        catch (Exception exception)
        {
            Monitor.Log($"生成床边测试 NPC 失败：{exception.Message}", LogLevel.Warn);
        }
    }

    /// <summary>
    /// 是否注入床边测试 NPC：配置开关（<see cref="ModConfig.InjectTestNpc"/>，默认关闭）
    /// 或视觉 harness 正在运行。
    ///
    /// harness 用的是它本来就有的 <see cref="VisualTestHarnessRules.EnabledVariable"/> 变量，
    /// 由 <c>scripts/start_visual_test.ps1</c> 在启动 SMAPI 前设进进程环境，
    /// 所以 harness 不需要额外写 config，行为与改动前一致。
    /// </summary>
    private bool ShouldInjectTestNpc()
    {
        return TestNpcPlacementRules.ShouldInject(
            config.InjectTestNpc,
            VisualTestHarnessRules.IsEnabled(
                Environment.GetEnvironmentVariable(
                    VisualTestHarnessRules.EnabledVariable)));
    }

    private static void PreserveInjectedTestNpcAppearance(
        StardewNpc npc,
        TestNpcAppearancePolicy appearance)
    {
        if (appearance.PreserveInjectedSprite)
        {
            var spriteOverride = AccessTools.Field(
                typeof(StardewNpc),
                "spriteOverridden") ?? throw new MissingFieldException(
                    typeof(StardewNpc).FullName,
                    "spriteOverridden");
            spriteOverride.SetValue(npc, true);
        }

        if (appearance.PreserveInjectedPortrait)
        {
            var portraitOverride = AccessTools.Field(
                typeof(StardewNpc),
                "portraitOverridden") ?? throw new MissingFieldException(
                    typeof(StardewNpc).FullName,
                    "portraitOverridden");
            portraitOverride.SetValue(npc, true);
        }
    }

    private void RemoveTestNpc()
    {
        try
        {
            var farmhouse = Game1.getLocationFromName("FarmHouse") as FarmHouse;
            if (farmhouse is not null)
            {
                for (var index = farmhouse.characters.Count - 1; index >= 0; index--)
                {
                    if (string.Equals(
                            farmhouse.characters[index].Name,
                            TestNpcPlacementRules.InternalName,
                            StringComparison.Ordinal))
                    {
                        farmhouse.characters.RemoveAt(index);
                    }
                }
            }
        }
        catch (Exception exception)
        {
            Monitor.Log($"清理床边测试 NPC 失败：{exception.Message}", LogLevel.Trace);
        }
        finally
        {
            testNpc = null;
        }
    }

    private void OnGameLaunched(object? sender, GameLaunchedEventArgs e)
    {
        var api = Helper.ModRegistry.GetApi<IGenericModConfigMenuApi>("spacechase0.GenericModConfigMenu");
        if (api is null)
        {
            return;
        }

        api.Register(ModManifest, ResetConfig, SaveConfig);
        api.AddKeybindList(
            ModManifest,
            () => config.DialogueKey,
            value => config.DialogueKey = value.IsBound ? value : new KeybindList(SButton.F8),
            () => "Dialogue key",
            () => "启动与当前地点有好感度记录的 NPC 对话。",
            "DialogueKey");
        api.AddBoolOption(
            ModManifest,
            () => config.EnableDialogue,
            value => config.EnableDialogue = value,
            () => "Enable dialogue",
            () => "是否启用 AI NPC 对话。",
            "EnableDialogue");
        api.AddBoolOption(
            ModManifest,
            () => config.InjectTestNpc,
            value => config.InjectTestNpc = value,
            () => "Inject bedside test NPC",
            () => "在农舍床边放一个名为「XX（测试）」的克隆 NPC，用于床边陪测。"
                + "默认关闭：它不在角色表里，没有专属配色和气泡装饰，"
                + "婚后角色都在屋里时直接跟真角色聊即可。",
            "InjectTestNpc");
        api.AddBoolOption(
            ModManifest,
            () => config.EnableHouseAccess,
            value => config.EnableHouseAccess = value,
            () => "Enable residential door access",
            () => "只放宽已确认属于 NPC 住宅的外门；个人测试档默认开启。",
            "EnableHouseAccess");
        api.AddBoolOption(
            ModManifest,
            () => config.AllowMixedBuildingAccess,
            value => config.AllowMixedBuildingAccess = value,
            () => "Allow mixed building access",
            () => "允许住宅与商店共用建筑放行；可能提前进入商店，个人测试档默认开启。",
            "AllowMixedBuildingAccess");
        api.AddTextOption(
            ModManifest,
            () => config.BridgeEndpoint,
            value => config.BridgeEndpoint = value,
            () => "Bridge endpoint",
            () => "仅允许本机回环 HTTP(S) 地址。",
            fieldId: "BridgeEndpoint");
        api.AddNumberOption(
            ModManifest,
            () => config.BridgeTimeoutSeconds,
            value => config.BridgeTimeoutSeconds = value,
            () => "Bridge timeout (seconds)",
            () => "请求超时秒数，范围为 1 到 120。",
            ModConfig.MinBridgeTimeoutSeconds,
            ModConfig.MaxBridgeTimeoutSeconds,
            1,
            fieldId: "BridgeTimeoutSeconds");
        api.AddTextOption(
            ModManifest,
            () => config.GroupDialogueStrategy,
            value => config.GroupDialogueStrategy = value,
            () => "Group dialogue strategy",
            () => "multi_turn 为自然接话流（名单里多人可依次发言，默认）；turn_based 只让当前发言人回一句。",
            new[] { ModConfig.MultiTurnGroupStrategy, ModConfig.TurnBasedGroupStrategy },
            value => value == ModConfig.TurnBasedGroupStrategy ? "一人一轮（回退）" : "自然接话流（默认）",
            fieldId: "GroupDialogueStrategy");
    }

    private void ResetConfig()
    {
        config = ModConfig.CreateDefault();
        ApplyConfig();
    }

    private void SaveConfig()
    {
        config = config.Normalize();
        Helper.WriteConfig(config);
        ApplyConfig();
    }

    private void ApplyConfig()
    {
        config = config.Normalize();
        conversationService?.Cancel();
        conversationService?.Dispose();
        conversationService = null;
        dialogueKey = config.DialogueKey;
        groupDialogueKey = config.GroupDialogueKey;
        groupDialogueCoordinator?.CloseIfOpen();
        bridgeClient?.Dispose();
        bridgeClient = config.EnableDialogue
            ? new BridgeClient(
                endpoint: new Uri(config.BridgeEndpoint),
                timeout: TimeSpan.FromSeconds(config.BridgeTimeoutSeconds),
                diagnosticLogger: message => Monitor.Log(message, LogLevel.Trace),
                groupStrategy: config.GroupDialogueStrategy)
            : null;
        if (bridgeClient is not null)
        {
            conversationService = new ConversationService(bridgeClient, storyStateStore);
            // 新客户端的内存是空的：把当前存档已读到的回看档案灌回去。
            // 在游戏里改配置（会走到这里）不该把玩家翻得到的历史弄丢。
            bridgeClient.LoadDisplayHistory(chatHistoryArchiveJson, CurrentSaveFolderName);
        }
        faceToFaceCoordinator?.UpdateService(conversationService);
        RefreshTestNpcForCurrentConfig();
    }

    /// <summary>
    /// 配置刚变过（GMCM 里改开关、重置配置）时让测试 NPC 立刻跟上：
    /// 否则玩家在面板里关掉注入之后，农舍里那个克隆体要等到下次载入存档才消失。
    /// 未载入存档时什么都不做——<see cref="Context.IsWorldReady"/> 为假时
    /// 连 Game1 都还没就绪，等 SaveLoaded 那次 <see cref="EnsureTestNpc"/> 自然会处理。
    /// 两个方法各自幂等：已在场就不会重复生成，不在场也不会报错。
    /// </summary>
    private void RefreshTestNpcForCurrentConfig()
    {
        if (!Context.IsWorldReady)
        {
            return;
        }

        if (ShouldInjectTestNpc())
        {
            EnsureTestNpc();
        }
        else
        {
            RemoveTestNpc();
        }
    }

    private bool TryOpenGroupHub()
    {
        if (!DialogueEntryRules.CanOpenGroup(
                config.EnableDialogue,
                Context.IsWorldReady,
                Game1.activeClickableMenu is not null,
                bridgeClient is not null))
        {
            return false;
        }

        return OpenGroupHubMenu();
    }

    private bool TryOpenGroupHubForVisualTest()
    {
        // VisualTestHarness loads a save directly through SaveGame.Load, so
        // SMAPI's normal SaveLoaded/Context.IsWorldReady flag is not raised.
        // The harness invokes this only after the same game-mode/player/location
        // readiness check used to open its other real menus.
        // 取值与 harness 内部共用 VisualTestHarnessRules.IsGameReadyFromGameState
        // （审计 #41：此前两处各拼一次同一批游戏状态）。
        var gameReady = VisualTestHarnessRules.IsGameReadyFromGameState();
        if (Game1.activeClickableMenu is TitleMenu titleMenu)
        {
            // Direct SaveGame.Load leaves the title menu attached even after
            // gameMode reaches 3. Normal F9 input never needs this cleanup;
            // it is only the visual harness's load-path residue.
            titleMenu.exitThisMenuNoSound();
            Game1.activeClickableMenu = null;
        }
        Monitor.Log(
            $"视觉测试 F9 入口门槛：enabled={config.EnableDialogue}; gameReady={gameReady}; " +
            $"activeMenu={Game1.activeClickableMenu?.GetType().Name ?? "null"}; " +
            $"bridgeClient={(bridgeClient is null ? "null" : "ok")}",
            LogLevel.Trace);
        if (!DialogueEntryRules.CanOpenGroup(
                config.EnableDialogue,
                gameReady,
                Game1.activeClickableMenu is not null,
                bridgeClient is not null))
        {
            return false;
        }

        return OpenGroupHubMenu();
    }

    private bool OpenGroupHubMenu()
    {
        Game1.activeClickableMenu = new GroupDialogueHubMenu(
            storyStateStore,
            bridgeClient,
            GetKnownGroupParticipants,
            CloseGroupMenu);
        return true;
    }

    private void CloseGroupMenu()
    {
        if (Game1.activeClickableMenu is GroupDialogueHubMenu or
            GroupDialogueMenu)
        {
            Game1.activeClickableMenu.exitThisMenuNoSound();
        }
    }

    private IReadOnlyList<GroupParticipantCandidate> GetKnownGroupParticipants()
    {
        if (Game1.player is null)
        {
            return Array.Empty<GroupParticipantCandidate>();
        }

        var friendshipData = FriendshipDataAccessor.ReadData(Game1.player);
        var known = KnownNpcResolver.Resolve(
            FriendshipDataAccessor.Keys(friendshipData),
            npcId =>
            {
                var npc = Game1.getCharacterFromName(npcId);
                return npc is null ? null : new KnownNpc(npc.Name, npc.displayName);
            });
        return known
            .Select(npc => new GroupParticipantCandidate(npc.NpcId, npc.DisplayName, true))
            .ToArray();
    }

    private HouseAccessOptions GetHouseAccessOptions()
    {
        return new HouseAccessOptions(
            Enabled: config.EnableHouseAccess,
            AllowMixedBuildings: config.AllowMixedBuildingAccess,
            AllowFestivalAccess: false,
            AllowMultiplayerAccess: false);
    }

    private StardewNpc? ResolveVisualTestNpc()
    {
        var targetName = NpcTargetResolver.ResolveTargetName(
            candidate => Game1.getCharacterFromName(candidate) is not null);
        return targetName is null ? null : Game1.getCharacterFromName(targetName);
    }

    private void OnButtonPressed(object? sender, ButtonPressedEventArgs e)
    {
        // 示例记录入口放在最前面：这三组键都带 Ctrl，命中后要把 F8 / F9 吃掉，
        // 免得同一次按键又去开对话或群聊面板。先查更具体的 Ctrl+Shift+F8，再查 Ctrl+F8
        // —— 前者的按键集合是后者的超集，反过来的话压力注入永远轮不到。
        if (SampleHistoryStressKey.JustPressed())
        {
            Helper.Input.Suppress(e.Button);
            InjectSampleHistory(stress: true);
            return;
        }

        if (SampleHistoryClearKey.JustPressed())
        {
            Helper.Input.Suppress(e.Button);
            ClearSampleHistory();
            return;
        }

        if (SampleHistoryKey.JustPressed())
        {
            Helper.Input.Suppress(e.Button);
            InjectSampleHistory(stress: false);
            return;
        }

        if (e.Button.IsActionButton() && Context.IsWorldReady)
        {
            houseAccessController?.TraceInteractionTarget(
                Game1.currentLocation,
                e.Cursor.GrabTile);
        }

        if (e.Button.IsActionButton() &&
            faceToFaceCoordinator?.TryConsumePendingKiss(e.Cursor.GrabTile) == true)
        {
            Helper.Input.Suppress(e.Button);
            return;
        }

        if (e.Button.IsActionButton() &&
            faceToFaceCoordinator?.TryOpenRepeatChat(e.Cursor.GrabTile) == true)
        {
            Helper.Input.Suppress(e.Button);
            return;
        }

        if (groupDialogueKey.JustPressed())
        {
            if (groupDialogueCoordinator?.TryOpen() == true)
            {
                Helper.Input.Suppress(e.Button);
            }

            return;
        }

        if (!dialogueKey.JustPressed() || !DialogueEntryRules.CanOpen(
                config.EnableDialogue,
                Context.IsWorldReady,
                Game1.activeClickableMenu is not null,
                conversationService is not null))
        {
            return;
        }

        var target = ResolveFriendshipTarget(e.Cursor.GrabTile);
        if (target is null)
        {
            Monitor.Log(
                "当前地点没有可聊天的友谊 NPC；请走近一个存在好感度记录的 NPC。",
                LogLevel.Warn);
            return;
        }

        if (faceToFaceCoordinator is null ||
            !faceToFaceCoordinator.TryOpenChat(target))
        {
            return;
        }
    }

    private static StardewNpc? ResolveFriendshipTarget(Vector2 interactionTile)
    {
        var location = Game1.currentLocation;
        if (location is null || Game1.player is null)
        {
            return null;
        }

        var candidates = location.characters
            .Select(npc => new
            {
                Npc = npc,
                Candidate = new NpcTargetCandidate(
                    npc.Name,
                    FriendshipDataAccessor.HasRecord(Game1.player, npc.Name) ||
                        TestNpcPlacementRules.IsDialogueTargetWithoutFriendshipRecord(npc.Name),
                    ReferenceEquals(npc.currentLocation, location),
                    Vector2.Distance(Game1.player.Position, npc.Position) / Game1.tileSize,
                    FaceToFaceStateRules.InteractionTargetsRememberedNpc(
                        npc.GetBoundingBox(),
                        interactionTile,
                        Game1.tileSize)),
            })
            .ToArray();

        var selected = NpcTargetResolver.SelectFriendshipTarget(
            candidates.Select(item => item.Candidate));
        return selected is null
            ? null
            : candidates.First(item =>
                string.Equals(
                    item.Candidate.NpcId,
                    selected.NpcId,
                    StringComparison.OrdinalIgnoreCase) &&
                item.Candidate.Distance == selected.Distance).Npc;
    }

    /// <summary>
    /// 开发用：往内存里的回看档案灌一批示例聊天记录
    /// （内容与边界见 <see cref="SampleChatHistory"/>）。
    ///
    /// 这里**只改内存**：存档文件一个字节都不动，落盘交给玩家自己那次保存
    /// （<see cref="OnSaving"/> 会把回看档案连同真实记录一起写进当前存档）。
    /// 玩家按 Ctrl+F8 触发；控制台 <c>ainpc_sample inject|stress</c> 走同一条路。
    /// </summary>
    private void InjectSampleHistory(bool stress, string? npcId = null)
    {
        if (bridgeClient is null || !Context.IsWorldReady)
        {
            var reason = bridgeClient is null ? "对话功能未开启" : "还没进入存档";
            Monitor.Log($"[StardewAI.Sample] 未注入示例记录：{reason}。", LogLevel.Warn);
            NotifyPlayer($"示例记录未注入：{reason}");
            return;
        }

        var samples = stress
            ? SampleChatHistory.BuildStress(
                string.IsNullOrWhiteSpace(npcId) ? SampleChatHistory.StressNpcId : npcId.Trim())
            : SampleChatHistory.Build();
        var change = bridgeClient.InjectSampleHistory(samples);
        Monitor.Log(
            $"[StardewAI.Sample] 已注入示例聊天记录：{change}；角色={string.Join("/", samples.Keys)}；" +
            (stress
                ? $"压力注入 {SampleChatHistory.StressMessageCount} 条（超出回看上限的部分已按规则裁掉）"
                : "常规注入") +
            "。只进内存回看档案：发给模型的窗口不受影响；保存后随存档落盘。",
            LogLevel.Info);
        NotifyPlayer(stress
            ? $"已注入压力示例：{change}；翻到最上面应是「{SampleChatHistory.StressFirstKeptStamp}」"
            : $"已注入示例聊天记录：{change}；按 F8 往上翻，Ctrl+F9 清除");
    }

    /// <summary>
    /// 开发用：清掉内存档案里的示例记录（玩家真实聊过的记录一条不动）。
    /// 清完要**再保存一次**才算把存档里那份也覆盖掉 —— 存档里写的是上一次保存的内容。
    /// </summary>
    private void ClearSampleHistory()
    {
        if (bridgeClient is null)
        {
            Monitor.Log("[StardewAI.Sample] 未清除示例记录：对话功能未开启。", LogLevel.Warn);
            NotifyPlayer("示例记录未清除：对话功能未开启");
            return;
        }

        var removed = bridgeClient.ClearSampleHistory();
        Monitor.Log(
            removed == 0
                ? "[StardewAI.Sample] 内存里没有示例记录可清。"
                : $"[StardewAI.Sample] 已清除示例记录 {removed} 条（玩家真实聊天记录一条未动）。"
                    + "要让存档里那份也消失，请再保存一次（睡觉过夜、退出到标题或手动保存）。",
            LogLevel.Info);
        NotifyPlayer(removed == 0
            ? "内存里没有示例记录可清"
            : $"已清除示例记录 {removed} 条；再保存一次才会从存档里消失");
    }

    /// <summary>开发用：把内存回看档案的现状打一行日志（示例多少条、各角色共多少条）。</summary>
    private void LogSampleHistoryStatus()
    {
        if (bridgeClient is null)
        {
            Monitor.Log("[StardewAI.Sample] 对话功能未开启，没有回看档案可查。", LogLevel.Warn);
            return;
        }

        var samples = bridgeClient.CountSampleHistory();
        var perNpc = string.Join(
            "；",
            SampleChatHistory.NpcIds.Select(
                npcId => $"{npcId}={bridgeClient.RecentHistory(npcId).Count}"));
        Monitor.Log(
            $"[StardewAI.Sample] 内存回看档案：示例 {samples}；各角色档案总条数 {perNpc}；" +
            $"存档={CurrentSaveFolderName ?? "<unknown>"}。",
            LogLevel.Info);
    }

    /// <summary>控制台命令 <c>ainpc_sample</c> 的分发：与按键共用上面三个方法。</summary>
    private void OnSampleHistoryCommand(string command, string[] args)
    {
        _ = command;
        var action = args.Length == 0 ? "inject" : args[0].Trim().ToLowerInvariant();
        switch (action)
        {
            case "inject":
                InjectSampleHistory(stress: false);
                break;
            case "stress":
                InjectSampleHistory(stress: true, args.Length > 1 ? args[1] : null);
                break;
            case "clear":
                ClearSampleHistory();
                break;
            case "status":
                LogSampleHistoryStatus();
                break;
            default:
                Monitor.Log(
                    $"用法：{SampleHistoryCommand} [inject|stress [npcId]|clear|status]；不带参数等于 inject。",
                    LogLevel.Info);
                break;
        }
    }

    /// <summary>
    /// 给玩家一条屏幕提示。按键是"盲操作"——光写日志他在游戏里看不见。
    /// 提示失败不影响注入本身（HUD 队列属于游戏对象，极端情况下可能拒绝）。
    /// </summary>
    private void NotifyPlayer(string message)
    {
        try
        {
            Game1.addHUDMessage(new HUDMessage(message, HUDMessage.newQuest_type));
        }
        catch (Exception exception)
        {
            Monitor.Log($"[StardewAI.Sample] 屏幕提示失败（不影响注入）：{exception.Message}", LogLevel.Trace);
        }
    }

    private sealed class SmapiModRegistryStatus : IModRegistryStatus
    {
        private readonly IModRegistry registry;

        public SmapiModRegistryStatus(IModRegistry registry)
        {
            this.registry = registry;
        }

        public bool IsLoaded(string uniqueId)
        {
            try
            {
                return registry.IsLoaded(uniqueId);
            }
            catch
            {
                return false;
            }
        }
    }
}
