# 原生风格 AI 聊天界面实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `subagent-driven-development`（推荐）或 `executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）来跟踪进度。

**目标：** 将当前固定发送「你好」的 `DialogueMenu` 改造成复用 Stardew Valley 原生资源、支持中文输入、连续对话、主动话题和背包物品互动的正式聊天界面。

**架构：** 以 `ConversationService` 统一 Bridge 请求、短期历史和故事状态写入；以 `ChatInputMenu` 负责绘制和输入；以 `FaceToFaceConversationCoordinator` 负责原版寒暄结束后的续聊选择；以 `InventoryItemPicker` 负责物品选择。面对面入口和 F8 入口共用服务与菜单，原版对白仍由游戏负责。

**技术栈：** C# / .NET 6、SMAPI 4.2、Stardew Valley 1.6 原生 `IClickableMenu`、`DialogueBox`、`TextBox` 和 `ClickableTextureComponent`；Python 3.12、FastAPI、Pydantic、pytest；现有 `BridgeClient`、`StoryStateStore` 和 Fake Provider。

---

## 1. 文件清单与职责

### 新建文件

| 文件 | 职责 |
|---|---|
| `smapi/ConversationModels.cs` | 定义消息、请求意图、物品上下文和会话结果的纯数据类型 |
| `smapi/IConversationTransport.cs` | 为 `ConversationService` 提供可测试的传输接口 |
| `smapi/ConversationService.cs` | 统一普通消息、主动话题、物品互动、历史和记忆写入 |
| `smapi/ChatLayoutRules.cs` | 根据视口计算窗口、消息区、输入区和按钮矩形 |
| `smapi/ChatInputMenu.cs` | 原生风格聊天菜单、中文输入、发送、等待、错误和连续会话 |
| `smapi/DialogueEntryRules.cs` | F8 入口安全条件的纯规则 |
| `smapi/FaceToFaceConversationCoordinator.cs` | 追踪原版 NPC 对话并在结束后显示续聊选择 |
| `smapi/FaceToFaceStateRules.cs` | 面对面状态机的纯规则，供单元测试使用 |
| `smapi/InventoryItemPicker.cs` | 原生风格背包物品选择和展示、分享、赠送动作 |
| `smapi/ItemInteractionModels.cs` | 物品互动动作和安全的物品上下文模型 |
| `smapi/ItemInteractionRules.cs` | 物品确认、消耗和原版赠送调用条件 |
| `smapi/VanillaGiftHandler.cs` | 将确认的赠送动作交给原版 NPC 送礼入口 |
| `smapi/tests/ConversationServiceTests.cs` | 会话服务测试替身、历史和回退测试 |
| `smapi/tests/ChatLayoutRulesTests.cs` | 自适应布局和按钮不重叠测试 |
| `smapi/tests/FaceToFaceStateRulesTests.cs` | 面对面续聊状态机测试 |
| `smapi/tests/ItemInteractionRulesTests.cs` | 物品动作、偏好和不消耗规则测试 |
| `bridge/tests/test_chat_intents.py` | Bridge 意图、物品上下文和 Prompt 测试 |

### 修改文件

| 文件 | 职责变化 |
|---|---|
| `smapi/BridgeClient.cs` | 支持 `intent`、`itemContext`，保留旧 `SendAsync` 调用兼容性 |
| `smapi/DialogueMenu.cs` | 迁移为兼容壳，移除固定问候和直接调试绘制 |
| `smapi/ModEntry.cs` | 注册聊天服务、F8 新入口、原版菜单生命周期和存档清理事件 |
| `bridge/src/stardew_ai_bridge/models.py` | 接收意图和物品上下文，缺省时保持普通聊天行为 |
| `bridge/src/stardew_ai_bridge/app.py` | 将新字段纳入安全白名单并传给上下文/Prompt 构建器 |
| `bridge/src/stardew_ai_bridge/prompts.py` | 为主动话题和物品互动生成独立、受限的上下文消息 |
| `bridge/tests/test_api.py` | 增加新字段的接口回归和旧请求兼容测试 |
| `bridge/tests/test_game_context_contract.py` | 增加新意图和物品上下文的 Prompt 契约测试 |
| `README.md` | 更新正式聊天 UI、F8 和面对面流程说明 |
| `docs/test-cases.md` | 增加原版寒暄、中文输入、主动话题和物品选择验收项 |
| `docs/handoff-2026-08-23.md` | 记录新 UI 状态、验证命令和实际游戏边界 |

---

## 2. 任务 1：建立会话服务和 Bridge 意图契约

**目标：** 让 UI 不再直接调用 `BridgeClient`，同时为普通聊天、主动话题和物品互动定义稳定请求格式。

**文件：**

- 创建：`smapi/ConversationModels.cs`、`smapi/IConversationTransport.cs`、`smapi/ConversationService.cs`
- 修改：`smapi/BridgeClient.cs`
- 测试：`smapi/tests/ConversationServiceTests.cs`、`smapi/tests/BridgeClientTests.cs`

- [x] **步骤 1：编写失败的 C# 测试**

在 `ConversationServiceTests.cs` 先定义传输替身和最小行为：

```csharp
private sealed class FakeTransport : IConversationTransport
{
    public ConversationRequest? LastRequest { get; private set; }
    public BridgeDialogueResponse Response { get; set; } = new()
    {
        Reply = "收到。",
        Provider = "fake",
    };

    public Task<BridgeDialogueResponse> SendAsync(
        ConversationRequest request,
        CancellationToken cancellationToken)
    {
        LastRequest = request;
        return Task.FromResult(Response);
    }
}

[Fact]
public async Task TopicRequestDoesNotWriteMemoryUntilPlayerReplies()
{
    var transport = new FakeTransport();
    var store = new StoryStateStore();
    var service = new ConversationService(transport, store);

    var topic = await service.RequestTopicAsync(TestNpcState(), CancellationToken.None);

    Assert.Equal(ConversationIntent.Topic, transport.LastRequest!.Intent);
    Assert.Empty(store.State.Memories);
    Assert.Equal("收到。", topic.Reply);
}
```

在 `BridgeClientTests.cs` 增加 JSON 契约断言：普通旧调用使用 `intent=chat`，物品调用同时发送 `intent=item` 和 `itemContext`，请求中不出现绝对路径或凭据字段。

- [x] **步骤 2：运行测试确认失败**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter "FullyQualifiedName~ConversationServiceTests|FullyQualifiedName~BridgeClientTests"
```

预期：新增测试因 `ConversationService`、`ConversationIntent` 和 `itemContext` 尚未定义而失败；既有测试仍可编译。

- [x] **步骤 3：实现最小契约和服务**

在 `ConversationModels.cs` 中固定字段名和意图值：

```csharp
public static class ConversationIntent
{
    public const string Chat = "chat";
    public const string Topic = "topic";
    public const string Item = "item";
}

public sealed record ItemConversationContext(
    string ItemId,
    string DisplayName,
    string Category,
    int Quality,
    string Action,
    int GiftTaste);

public sealed record ConversationRequest(
    string NpcId,
    string Message,
    string Intent,
    NpcGameState? GameState,
    IReadOnlyList<string> RecentFacts,
    ItemConversationContext? ItemContext);
```

`IConversationTransport` 只暴露一个方法：

```csharp
Task<BridgeDialogueResponse> SendAsync(
    ConversationRequest request,
    CancellationToken cancellationToken);
```

`ConversationService` 的公开方法固定为：

```csharp
Task<ConversationTurnResult> SendAsync(
    NpcGameState state,
    string message,
    CancellationToken cancellationToken,
    ItemConversationContext? itemContext = null);

Task<ConversationTurnResult> RequestTopicAsync(
    NpcGameState state,
    CancellationToken cancellationToken);
```

普通消息和物品互动成功后调用现有 `StoryStateStore.RecordConversation`；主动话题只返回 NPC 开场，不写记忆、不增加有效互动次数。`BridgeClient` 实现 `IConversationTransport`，原有 `SendAsync(npcId, message, ...)` 保留并内部使用 `intent=chat`。

- [x] **步骤 4：运行测试确认通过**

运行同一条 `dotnet test` 命令，预期新增和既有 Bridge 测试全部通过。

- [x] **步骤 5：提交**

```powershell
git add smapi/ConversationModels.cs smapi/IConversationTransport.cs smapi/ConversationService.cs smapi/BridgeClient.cs smapi/tests/ConversationServiceTests.cs smapi/tests/BridgeClientTests.cs
git commit -m "feat(会话): 统一聊天意图和服务层"
```

## 3. 任务 2：实现自适应布局和消息显示规则

**目标：** 先把当前 600 × 360 调试窗口变成可测试的自适应布局，再让正式菜单只消费这些矩形和消息规则。

**文件：**

- 创建：`smapi/ChatLayoutRules.cs`
- 测试：`smapi/tests/ChatLayoutRulesTests.cs`

- [x] **步骤 1：编写失败的布局测试**

```csharp
[Theory]
[InlineData(1280, 720)]
[InlineData(1920, 1080)]
[InlineData(2560, 1440)]
public void LayoutFitsViewportAndKeepsActionButtonsSeparated(int viewportWidth, int viewportHeight)
{
    var layout = ChatLayoutRules.Calculate(viewportWidth, viewportHeight);

    Assert.InRange(layout.Panel.Width, viewportWidth * 0.60f, viewportWidth * 0.72f);
    Assert.InRange(layout.Panel.Height, viewportHeight * 0.48f, viewportHeight * 0.62f);
    Assert.True(layout.Panel.Left >= 24);
    Assert.True(layout.Panel.Right <= viewportWidth - 24);
    Assert.False(layout.SendButton.Intersects(layout.TopicButton));
    Assert.False(layout.TopicButton.Intersects(layout.InventoryButton));
    Assert.False(layout.InventoryButton.Intersects(layout.CloseButton));
}
```

同时测试 `ChatLayoutRules.VisibleMessages` 只保留最近消息，不能返回空消息或超过消息区高度。

- [x] **步骤 2：运行测试确认失败**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter FullyQualifiedName~ChatLayoutRulesTests
```

预期：因布局类型和计算方法尚未存在而失败。

- [x] **步骤 3：实现布局规则**

实现 `ChatLayout` 记录和 `ChatLayoutRules.Calculate`：面板宽度取 `Clamp(viewportWidth * 0.68f, 760, viewportWidth - 48)`，高度取 `Clamp(viewportHeight * 0.55f, 420, viewportHeight - 48)`；操作区按固定间距从右向左排列，输入框占剩余宽度。小窗口下优先缩短输入框，不允许按钮互相覆盖。

消息显示只负责布局，不负责修改故事状态：

```csharp
public sealed record ChatLayout(
    Rectangle Panel,
    Rectangle Header,
    Rectangle MessageArea,
    Rectangle InputBox,
    Rectangle SendButton,
    Rectangle TopicButton,
    Rectangle InventoryButton,
    Rectangle CloseButton);
```

- [x] **步骤 4：运行测试确认通过**

运行同一条 `dotnet test` 命令，预期所有布局测试通过。

- [x] **步骤 5：提交**

```powershell
git add smapi/ChatLayoutRules.cs smapi/tests/ChatLayoutRulesTests.cs
git commit -m "feat(UI): 添加自适应聊天布局规则"
```

## 4. 任务 3：替换调试菜单为正式聊天菜单

**目标：** 使用原生贴图和输入分发机制完成可用的连续聊天界面；所有 Bridge 调用通过 `ConversationService`。

**文件：**

- 创建：`smapi/ChatInputMenu.cs`
- 修改：`smapi/DialogueMenu.cs`
- 测试：沿用 `ChatLayoutRulesTests.cs`，在 `ConversationServiceTests.cs` 增加菜单关闭和重复发送场景的服务测试

- [x] **步骤 1：编写失败的服务状态测试**

```csharp
[Fact]
public async Task SendingSecondMessageWhileFirstIsPendingIsRejected()
{
    var transport = new BlockingTransport();
    var service = new ConversationService(transport, new StoryStateStore());

    var first = service.SendAsync(TestNpcState(), "第一句", CancellationToken.None);
    await Assert.ThrowsAsync<InvalidOperationException>(() =>
        service.SendAsync(TestNpcState(), "第二句", CancellationToken.None));

    transport.Release();
    await first;
}
```

菜单的行为由这些可观察状态固定：`Idle`、`Sending`、`ShowingReply`、`Failed`、`Closed`。关闭时必须取消令牌并阻止异步回调再次写入菜单。

- [x] **步骤 2：运行测试确认失败**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter FullyQualifiedName~ConversationServiceTests
```

预期：并发发送测试失败。

- [x] **步骤 3：实现 `ChatInputMenu`**

构造函数固定为：

```csharp
public ChatInputMenu(
    StardewNpc npc,
    ConversationService conversationService,
    StoryStateStore storyStateStore,
    Action onClosed)
```

实现要求：

- `Game1.drawDialogueBox` 绘制面板；`Game1.drawTextureBox` 绘制按钮和输入框；使用 NPC 原生头像纹理和 `Game1.dialogueFont`。
- 订阅 `Game1.keyboardDispatcher`，将 `TextBox` 的文本、光标、退格和 Enter 发送接入菜单；`exitThisMenu` 和 `Dispose` 时解除订阅。
- `receiveLeftClick` 只命中实际按钮矩形；发送期间禁用发送、主动话题和背包按钮，保留结束按钮。
- 消息区只绘制当前会话消息；文字用 `SpriteFont.MeasureString` 换行，超出消息区时显示最近可见消息。
- 等待状态显示「正在思考……」；离线状态显示「暂时联系不上她。」和「重试/结束」，异常详情只写日志。
- `drawMouse` 保留原版鼠标光标；不再显示 `状态：成功`、provider 名称或固定「你好」。

`DialogueMenu` 改为转发到 `ChatInputMenu` 的兼容入口，确保旧构造调用不会继续绘制旧 UI；新代码不直接在 `DialogueMenu` 中调用 `BridgeClient`。

- [x] **步骤 4：运行 C# 全量测试和构建**

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" /p:EnableModDeploy=false /p:EnableModZip=false /p:BundleExtraAssemblies=Game
dotnet build smapi/StardewAI.NPC.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" /p:EnableModDeploy=false /p:EnableModZip=false /p:BundleExtraAssemblies=Game
```

预期：C# 测试通过，Mod DLL 构建成功；不得出现未释放的 `KeyboardDispatcher` 订阅编译错误。

- [x] **步骤 5：提交**

```powershell
git add smapi/ChatInputMenu.cs smapi/DialogueMenu.cs smapi/tests/ConversationServiceTests.cs
git commit -m "feat(UI): 替换调试菜单为原生聊天界面"
```

## 5. 任务 4：切换 F8 入口并接入菜单生命周期

**目标：** F8 使用正式聊天菜单，Bridge、存档和返回标题时的资源释放保持安全。

**文件：**

- 修改：`smapi/ModEntry.cs`、`smapi/DialogueMenu.cs`
- 测试：`smapi/tests/NpcTargetResolverTests.cs`、`smapi/tests/ConversationServiceTests.cs`

- [ ] **步骤 1：编写入口回归测试**

增加纯规则断言：禁用配置、非世界状态、已有菜单、Bridge 为空时不得创建聊天菜单；F8 目标仍按现有 Rasmodia/Wizard 双 ID 规则解析。

```csharp
[Theory]
[InlineData(false, false, false, false)]
[InlineData(true, false, false, false)]
[InlineData(true, true, true, false)]
public void HotkeyGuardRejectsUnsafeEntry(
    bool enabled,
    bool worldReady,
    bool hasMenu,
    bool hasBridge)
{
    Assert.False(DialogueEntryRules.CanOpen(enabled, worldReady, hasMenu, hasBridge));
}
```

- [ ] **步骤 2：运行测试确认失败**

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter FullyQualifiedName~NpcTargetResolverTests
```

预期：新增入口保护规则尚未定义而失败。

- [ ] **步骤 3：实现入口迁移**

在 `ModEntry` 中创建一次 `ConversationService`，`ApplyConfig` 时更新 Bridge 传输；`OnButtonPressed` 只负责检查配置、解析 NPC 并创建 `ChatInputMenu`：

```csharp
if (!DialogueEntryRules.CanOpen(
        config.EnableDialogue,
        Context.IsWorldReady,
        Game1.activeClickableMenu is not null,
        conversationService is not null))
{
    return;
}

Game1.activeClickableMenu = new ChatInputMenu(
    npc,
    conversationService,
    storyStateStore,
    () => Monitor.Log("AI 聊天已结束。", LogLevel.Trace));
```

`OnReturnedToTitle`、`OnSaveLoaded` 和 `ApplyConfig` 必须调用服务的 `Cancel`/`Dispose`，避免退出后异步回调访问旧菜单或旧 HTTP 客户端。

- [ ] **步骤 4：运行全量测试和差异检查**

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" /p:EnableModDeploy=false /p:EnableModZip=false /p:BundleExtraAssemblies=Game
git diff --check
```

- [ ] **步骤 5：提交**

```powershell
git add smapi/ModEntry.cs smapi/DialogueMenu.cs smapi/tests/NpcTargetResolverTests.cs
git commit -m "feat(入口): 接入正式聊天菜单和生命周期"
```

## 6. 任务 5：实现原版寒暄后的面对面续聊

**目标：** 不拦截原版 NPC 对话，只在原版对话自然结束后提供一次续聊选择。

**文件：**

- 创建：`smapi/FaceToFaceConversationCoordinator.cs`、`smapi/FaceToFaceStateRules.cs`
- 修改：`smapi/ModEntry.cs`
- 测试：`smapi/tests/FaceToFaceStateRulesTests.cs`

- [ ] **步骤 1：编写失败的状态机测试**

```csharp
[Fact]
public void VanillaDialogueClosingOffersContinuationOnlyOnce()
{
    var state = FaceToFaceStateRules.StartForNpc("Rasmodia");
    state = FaceToFaceStateRules.ObserveDialogueOpened(state);
    state = FaceToFaceStateRules.ObserveDialogueClosed(state);
    Assert.Equal(FaceToFaceState.AwaitingContinuationChoice, state.State);

    state = FaceToFaceStateRules.ChooseContinuation(state, continueChat: true);
    Assert.Equal(FaceToFaceState.Composing, state.State);
    Assert.Equal(
        FaceToFaceState.Idle,
        FaceToFaceStateRules.ObserveDialogueClosed(state).State);
}

[Fact]
public void EventAndFestivalNeverOfferContinuation()
{
    var state = FaceToFaceStateRules.StartForNpc("Rasmodia", eventUp: true, festival: false);
    Assert.Equal(FaceToFaceState.Idle, state.State);
}
```

- [ ] **步骤 2：运行测试确认失败**

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter FullyQualifiedName~FaceToFaceStateRulesTests
```

预期：状态和规则类型尚未定义而失败。

- [ ] **步骤 3：实现协调器**

`FaceToFaceConversationCoordinator` 通过 `Display.MenuChanged` 观察 `DialogueBox` 的打开和关闭，并读取 `Game1.currentSpeaker` 作为 NPC；只在世界已加载、非事件、非节日、没有其他菜单接管时进入候选状态。原版菜单打开期间不替换 `Game1.activeClickableMenu`。

对话关闭时调用 `Game1.currentLocation.createQuestionDialogue`，选项固定为「继续聊聊」和「先告辞」；回调只改变状态，不直接发送 Bridge 请求。续聊菜单关闭、存档、返回标题、NPC 失效时清理协调器。

- [ ] **步骤 4：运行状态机测试和构建**

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter FullyQualifiedName~FaceToFaceStateRulesTests
dotnet build smapi/StardewAI.NPC.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" /p:EnableModDeploy=false /p:EnableModZip=false /p:BundleExtraAssemblies=Game
```

- [ ] **步骤 5：提交**

```powershell
git add smapi/FaceToFaceConversationCoordinator.cs smapi/FaceToFaceStateRules.cs smapi/ModEntry.cs smapi/tests/FaceToFaceStateRulesTests.cs
git commit -m "feat(面对面): 添加原版寒暄后的续聊选择"
```

## 7. 任务 6：接入背包物品展示、分享和原版赠送

**目标：** 复用原版背包视觉和 NPC 礼物偏好，确保预览不扣物品，确认赠送才进入原版送礼流程。

**文件：**

- 创建：`smapi/ItemInteractionModels.cs`、`smapi/InventoryItemPicker.cs`、`smapi/VanillaGiftHandler.cs`
- 修改：`smapi/ChatInputMenu.cs`、`smapi/ConversationService.cs`、`smapi/BridgeClient.cs`
- 测试：`smapi/tests/ItemInteractionRulesTests.cs`、`smapi/tests/BridgeClientTests.cs`

- [ ] **步骤 1：编写失败的物品规则测试**

```csharp
[Fact]
public void PreviewAndShareNeverConsumeItem()
{
    var action = ItemInteractionRules.CreatePreview(
        new ItemSnapshot("74", "黄金南瓜", "礼物", 0),
        ItemInteractionAction.Share);

    Assert.Equal(ItemInteractionAction.Share, action.Action);
    Assert.False(action.ConsumesItem);
}

[Fact]
public void GiftRequiresExplicitConfirmation()
{
    var pending = ItemInteractionRules.CreatePreview(
        new ItemSnapshot("74", "黄金南瓜", "礼物", 0),
        ItemInteractionAction.Gift);

    Assert.False(pending.ConsumesItem);
    Assert.False(ItemInteractionRules.ShouldInvokeVanillaGift(pending, confirmed: false));
    Assert.True(ItemInteractionRules.ShouldInvokeVanillaGift(pending, confirmed: true));
}
```

- [ ] **步骤 2：运行测试确认失败**

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter FullyQualifiedName~ItemInteractionRulesTests
```

- [ ] **步骤 3：实现选择器和原版适配器**

`InventoryItemPicker` 使用 `Game1.player.Items` 绘制原版物品格，点击后返回不可变 `ItemSnapshot`，再显示「展示」「分享」「赠送」「取消」。选中阶段不修改背包；只有确认赠送后才调用 `VanillaGiftHandler`。`VanillaGiftHandler` 封装 Stardew Valley 1.6 的公开 NPC 接收物品入口，禁止在 Mod 中自行扣除 `Item.Stack`。

`ItemSnapshot` 只包含 `itemId`、显示名、类别、品质和本次动作。NPC 偏好通过原版 `npc.getGiftTasteForThisItem(item)` 读取，映射到 `GiftTaste` 整数后传给 Bridge；Bridge 不负责决定是否扣物品。

`ChatInputMenu` 的背包按钮打开选择器；选择展示或分享后回到聊天菜单并发送 `intent=item`；赠送确认成功后再发送一条结果消息，失败和取消均不写记忆。

- [ ] **步骤 4：运行 C# 全量测试和构建**

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" /p:EnableModDeploy=false /p:EnableModZip=false /p:BundleExtraAssemblies=Game
dotnet build smapi/StardewAI.NPC.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" /p:EnableModDeploy=false /p:EnableModZip=false /p:BundleExtraAssemblies=Game
```

- [ ] **步骤 5：提交**

```powershell
git add smapi/ItemInteractionModels.cs smapi/InventoryItemPicker.cs smapi/VanillaGiftHandler.cs smapi/ChatInputMenu.cs smapi/ConversationService.cs smapi/BridgeClient.cs smapi/tests/ItemInteractionRulesTests.cs smapi/tests/BridgeClientTests.cs
git commit -m "feat(物品): 添加背包展示分享和原版赠送"
```

## 8. 任务 7：扩展 Python Bridge 的主动话题和物品上下文

**目标：** 让 Bridge 能区分普通聊天、NPC 主动开场和物品互动，同时保持旧 JSON 请求可用。

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/models.py`、`bridge/src/stardew_ai_bridge/app.py`、`bridge/src/stardew_ai_bridge/prompts.py`
- 测试：`bridge/tests/test_chat_intents.py`、`bridge/tests/test_api.py`、`bridge/tests/test_game_context_contract.py`

- [ ] **步骤 1：编写失败的 Python 测试**

```python
def test_topic_intent_adds_active_opening_instruction(client: TestClient) -> None:
    preview = client.post(
        "/api/context/preview",
        json={
            "npcId": "Rasmodia",
            "message": "请主动找一个自然的话题。",
            "intent": "topic",
        },
    )
    assert preview.status_code == 200
    assert preview.json()["interaction"]["intent"] == "topic"


def test_item_context_is_allowlisted_and_does_not_accept_unknown_fields(client):
    response = client.post(
        "/api/dialogue/test",
        json={
            "npcId": "Rasmodia",
            "message": "我想给你看看这个。",
            "intent": "item",
            "itemContext": {
                "itemId": "74",
                "displayName": "黄金南瓜",
                "category": "礼物",
                "quality": 0,
                "action": "share",
                "giftTaste": 4,
            },
        },
    )
    assert response.status_code == 200
```

测试还要确认缺少 `intent` 时默认为 `chat`，非法意图和未知物品字段返回 422，Prompt 不出现绝对路径、Token 或完整原始 Mod 文本。

- [ ] **步骤 2：运行测试确认失败**

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests/test_chat_intents.py bridge/tests/test_api.py bridge/tests/test_game_context_contract.py -q -p no:cacheprovider
```

预期：新测试因 `intent`、`itemContext` 和 Prompt 摘要字段尚未定义而失败。

- [ ] **步骤 3：实现 Pydantic 契约和 Prompt 分支**

在 `models.py` 中新增：

```python
class ItemContext(ApiModel):
    item_id: str = Field(alias="itemId", min_length=1, max_length=100)
    display_name: str = Field(alias="displayName", min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    quality: int = Field(ge=0, le=4)
    action: Literal["display", "share", "gift"]
    gift_taste: int = Field(alias="giftTaste", ge=-4, le=8)


class DialogueTestRequest(ApiModel):
    intent: Literal["chat", "topic", "item"] = "chat"
    item_context: ItemContext | None = Field(default=None, alias="itemContext")
```

`app.py` 将 `intent` 和 `itemContext` 加入 `_DIALOGUE_FIELDS`，`ContextBuilder` 和 `PromptBuilder` 只读取上述白名单。`/api/context/preview` 额外返回 `interaction` 摘要（只含 `intent` 和经过白名单过滤的 `itemContext`），不返回原始请求或绝对路径。`PromptBuilder` 为 `topic` 添加「请主动提出一个符合当前关系和场景的自然话题」的独立上下文消息；为 `item` 添加物品动作、类别、品质和原版偏好结果；普通聊天的消息顺序和旧请求保持不变。

`/api/dialogue/test` 的 Fake Provider 继续返回固定测试回复，不改变现有回退行为。

- [ ] **步骤 4：运行 Bridge 全量测试**

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests -q -p no:cacheprovider
```

预期：全部通过，允许保留现有 Starlette/httpx 弃用警告。

- [ ] **步骤 5：提交**

```powershell
git add bridge/src/stardew_ai_bridge/models.py bridge/src/stardew_ai_bridge/app.py bridge/src/stardew_ai_bridge/prompts.py bridge/tests/test_chat_intents.py bridge/tests/test_api.py bridge/tests/test_game_context_contract.py
git commit -m "feat(Bridge): 支持主动话题和物品上下文"
```

## 9. 任务 8：文档、profile 和真实游戏验证

**目标：** 让文档、快速 profile 和验收清单与正式 UI 一致，并用自动化和真实游戏证据收尾。

**文件：**

- 修改：`README.md`、`docs/test-cases.md`、`docs/handoff-2026-08-23.md`
- 不修改：源 Mods 仓库和主分支

- [ ] **步骤 1：更新文档**

README 和测试用例必须明确：F8 与面对面共用 `ChatInputMenu`；原版寒暄先显示；主动话题和背包按钮属于正式 UI；Smartphone 不属于当前方案；Bridge 离线时只显示可理解的短提示。交接文档记录新增 C# 测试数量、实际游戏验证边界和最新提交。

- [ ] **步骤 2：运行静态和单元验证**

```powershell
git diff --check
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" /p:EnableModDeploy=false /p:EnableModZip=false /p:BundleExtraAssemblies=Game
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest bridge/tests -q -p no:cacheprovider
```

预期：`git diff --check` 无输出，C# 和 Bridge 均为 0 失败。

- [ ] **步骤 3：同步独立快速 profile**

```powershell
.\scripts\start_fast_test.ps1 -IncludeRasmodia -NoLaunch
```

预期：输出 `StardewAI.NPC`、Generic Mod Config Menu、Content Patcher、CrossModCompatibilityTokens 和 Rasmodia 五个 Mod；脚本不启动游戏、不修改源 Mods、不覆盖存档。

- [ ] **步骤 4：执行真实游戏验收**

启动 Bridge 和独立快速 profile，使用独立测试存档依次验证：原版寒暄→续聊选择、F8 聊天、中文 Enter 发送、连续 3～4 轮、NPC 主动找话题、背包展示/分享、确认赠送、关闭 Bridge 后重试/退出、保存/读档/返回标题。记录 SMAPI 日志中 Mod 加载、Bridge 请求、无异常和菜单清理证据；不把 Fake Provider 回复误判为真实模型质量。

- [ ] **步骤 5：提交文档和验证记录**

```powershell
git add README.md docs/test-cases.md docs/handoff-2026-08-23.md
git commit -m "docs(聊天界面): 更新验收流程和交接记录"
```

## 10. 计划自检

- **规格覆盖度：** 原生资产和自适应布局由任务 2、3 覆盖；中文输入、连续对话和错误状态由任务 3 覆盖；F8 入口由任务 4 覆盖；原版寒暄后的续聊由任务 5 覆盖；主动话题由任务 1 和任务 7 覆盖；背包展示、分享、赠送和原版偏好由任务 6 覆盖；Bridge 离线、生命周期和存档清理由任务 1、3、4 覆盖；文档和真实游戏验收由任务 8 覆盖。
- **完整性扫描：** 本计划未留下未完成标记或未定义的任务引用；每个代码变更任务都有测试、失败验证、实现、通过验证和提交步骤。
- **类型一致性：** `ConversationIntent`、`ItemConversationContext`、`ConversationRequest` 在任务 1 定义，任务 7、8 均沿用相同字段名；Python 使用 `intent`、`itemContext` 与 C# JSON 属性完全对应。
- **范围边界：** 不接入 Smartphone、不修改原版日常对白、不让 AI 直接改关系数值或物品数量；每项均在任务 3、5、6 和 8 中有明确约束。
