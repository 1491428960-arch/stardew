using System.Collections;
using System.Globalization;
using System.Reflection;
using System.Security.Cryptography;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;
using StardewNpc = StardewValley.NPC;

namespace StardewAI.NPC;

public sealed record VisualTestOptions(
    bool Enabled,
    string SaveName,
    string OutputDirectory,
    string ScenarioId,
    int? BackBufferWidth = null,
    int? BackBufferHeight = null);

public static class VisualTestHarnessRules
{
    public const string EnabledVariable = "STARDEW_AI_NPC_VISUAL_TEST";
    public const string SaveNameVariable = "STARDEW_AI_NPC_VISUAL_SAVE_NAME";
    public const string OutputVariable = "STARDEW_AI_NPC_VISUAL_OUTPUT";
    public const string ScenarioVariable = "STARDEW_AI_NPC_VISUAL_SCENARIO";
    public const string BackBufferWidthVariable = "STARDEW_AI_NPC_VISUAL_BACKBUFFER_WIDTH";
    public const string BackBufferHeightVariable = "STARDEW_AI_NPC_VISUAL_BACKBUFFER_HEIGHT";
    public const string DefaultSaveName = "test_447101921";
    public const string DefaultScenarioId = "chat-empty";

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
            backBufferHeight);
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
    private readonly StoryStateStore storyStateStore;
    private readonly VisualTestOptions options;
    private ChatInputMenu? menu;
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
    private int lastStatusTick = -60;

    public VisualTestHarness(
        IModHelper helper,
        IMonitor monitor,
        Func<ConversationService?> getConversationService,
        Func<StardewNpc?> getNpc,
        StoryStateStore storyStateStore)
    {
        this.helper = helper ?? throw new ArgumentNullException(nameof(helper));
        this.monitor = monitor ?? throw new ArgumentNullException(nameof(monitor));
        this.getConversationService = getConversationService ??
            throw new ArgumentNullException(nameof(getConversationService));
        this.getNpc = getNpc ?? throw new ArgumentNullException(nameof(getNpc));
        this.storyStateStore = storyStateStore ??
            throw new ArgumentNullException(nameof(storyStateStore));
        options = VisualTestHarnessRules.Parse(ReadEnvironment());
        if (!options.Enabled)
        {
            return;
        }

        helper.Events.GameLoop.UpdateTicked += OnUpdateTicked;
        helper.Events.GameLoop.SaveLoaded += OnSaveLoaded;
        helper.Events.Display.RenderedActiveMenu += OnRenderedActiveMenu;
        helper.Events.Display.Rendered += OnRendered;
        helper.Events.GameLoop.ReturnedToTitle += OnReturnedToTitle;
        monitor.Log(
            $"视觉测试 harness 已启用：scenario={options.ScenarioId}；save={options.SaveName}",
            LogLevel.Info);
    }

    public void Dispose()
    {
        if (disposed)
        {
            return;
        }

        disposed = true;
        helper.Events.GameLoop.UpdateTicked -= OnUpdateTicked;
        helper.Events.GameLoop.SaveLoaded -= OnSaveLoaded;
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
        return VisualTestHarnessRules.IsGameReady(
            Game1.gameMode,
            Game1.player is not null,
            Game1.currentLocation is not null,
            GetGameLoadFlag("hasLoadedGame"));
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

        menu = new ChatInputMenu(
            npc,
            service,
            storyStateStore,
            () => monitor.Log("视觉测试聊天菜单已关闭。", LogLevel.Trace));
        Game1.activeClickableMenu = menu;
        menuOpened = true;
        monitor.Log("视觉测试已打开真实聊天菜单，等待 Rendered 帧。", LogLevel.Trace);
    }

    private void OnRenderedActiveMenu(object? sender, RenderedActiveMenuEventArgs e)
    {
        _ = sender;
        _ = e;
        if (completed || !menuOpened || menu is null ||
            !ReferenceEquals(Game1.activeClickableMenu, menu))
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
    }

    private void OnRendered(object? sender, RenderedEventArgs e)
    {
        _ = sender;
        _ = e;
        if (completed || !menuOpened || menu is null ||
            !ReferenceEquals(Game1.activeClickableMenu, menu) ||
            // 视觉目标必须在 SMAPI 完成存档上下文和 Content Patcher 资源注入
            // 后再读取；回退闸门可能先打开菜单，但不能先截半成品。
            !saveLoadedLogged ||
            activeMenuFrames == 0)
        {
            return;
        }

        renderedFrames++;
        // 让游戏再完整刷新几帧，避免在菜单第一次提交到目标纹理前截到半帧。
        if (renderedFrames < 6)
        {
            return;
        }

        try
        {
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
        var screenshotPath = Path.Combine(outputDirectory, screenshotFile);
        var manifestPath = Path.Combine(outputDirectory, manifestFile);
        var donePath = Path.Combine(outputDirectory, "visual-test.done");

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

        // ChatInputMenu.draw() 通过 Game1.drawDialogueBox 绘制原版对话框；该
        // 方法使用游戏自己的全局 SpriteBatch，而不是传入的任意新实例。使用
        // 全局 batch 在独立目标上重放一次菜单，才能保留完整的九宫格边框、字体
        // 和肖像，同时不把截图逻辑混入生产菜单。
        var spriteBatchField = typeof(Game1).GetField(
            "spriteBatch",
            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static) ??
            throw new InvalidOperationException("无法取得 Game1.spriteBatch 字段。");
        var originalSpriteBatch = spriteBatchField.GetValue(null) as SpriteBatch ??
            throw new InvalidOperationException("无法取得 Game1.spriteBatch。");
        using var isolatedSpriteBatch = new SpriteBatch(graphicsDevice);
        try
        {
            // Game1.drawDialogueBox 直接读取 Game1.spriteBatch。临时替换字段，
            // 使它与 ChatInputMenu.draw 使用的批次和目标纹理保持一致。
            spriteBatchField.SetValue(null, isolatedSpriteBatch);
            isolatedSpriteBatch.Begin(
                SpriteSortMode.Deferred,
                BlendState.AlphaBlend,
                SamplerState.PointClamp,
                DepthStencilState.None,
                RasterizerState.CullNone);
            menu!.draw(isolatedSpriteBatch);
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
            CaptureSource: "isolated-game-spritebatch-render-target");
        File.WriteAllText(manifestPath, manifest.ToJson());
        File.WriteAllText(donePath, $"{manifestFile}{Environment.NewLine}");
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

    private void Fail(string message)
    {
        if (completed)
        {
            return;
        }

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
