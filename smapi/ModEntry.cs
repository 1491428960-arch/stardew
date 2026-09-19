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
    private readonly StoryStateStore storyStateStore = new();
    private readonly ShareFriendshipLedger shareFriendshipLedger = new();
    private readonly EventAuditObserver eventAuditObserver = new();
    private HouseAccessController? houseAccessController;
    private FaceToFaceConversationCoordinator? faceToFaceCoordinator;
    private VisualTestHarness? visualTestHarness;
    private StardewNpc? testNpc;
    private FrameRateSampler? frameRateSampler;
    private GroupDialogueCoordinator? groupDialogueCoordinator;

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
        helper.Events.Input.ButtonPressed += OnButtonPressed;
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
            storyStateStore.Load(Helper.Data.ReadSaveData<string>(StoryStateSerializer.StorageKey));
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

        EnsureTestNpc();
    }

    private void OnSaving(object? sender, SavingEventArgs e)
    {
        try
        {
            Helper.Data.WriteSaveData(
                StoryStateSerializer.StorageKey,
                storyStateStore.Serialize());
        }
        catch (Exception exception)
        {
            Monitor.Log($"保存故事状态失败，已跳过本次写入：{exception.Message}", LogLevel.Warn);
        }

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

    private void OnDayStarted(object? sender, DayStartedEventArgs e)
    {
        faceToFaceCoordinator?.ResetRepeatTarget();
        if (Context.IsWorldReady)
        {
            groupDialogueCoordinator?.OnDayStarted();
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

        if (!config.EnableDialogue)
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
        }
        faceToFaceCoordinator?.UpdateService(conversationService);
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
        var gameReady = VisualTestHarnessRules.IsGameReady(
            Game1.gameMode,
            Game1.player is not null,
            Game1.currentLocation is not null);
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
            GroupParticipantMenu or
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

        var friendshipData = ReadMember(Game1.player, "friendshipData");
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

    private static object? ReadMember(object source, string memberName)
    {
        try
        {
            var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
            var property = source.GetType().GetProperty(memberName, flags);
            if (property is not null)
            {
                return property.GetValue(source);
            }

            return source.GetType().GetField(memberName, flags)?.GetValue(source);
        }
        catch
        {
            return null;
        }
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
                    HasFriendshipRecord(npc.Name) ||
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

    private static bool HasFriendshipRecord(string? npcId)
    {
        if (string.IsNullOrWhiteSpace(npcId) || Game1.player is null)
        {
            return false;
        }

        try
        {
            var flags = System.Reflection.BindingFlags.Public |
                System.Reflection.BindingFlags.NonPublic |
                System.Reflection.BindingFlags.Instance;
            var playerType = Game1.player.GetType();
            var property = playerType.GetProperty("friendshipData", flags);
            var data = property?.GetValue(Game1.player) ??
                playerType.GetField("friendshipData", flags)?.GetValue(Game1.player);
            return FriendshipDataAccessor.ContainsKey(data, npcId);
        }
        catch
        {
            return false;
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
