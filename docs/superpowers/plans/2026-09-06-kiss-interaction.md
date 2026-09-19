# AI 聊天后的亲吻交互实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 按顺序执行；每个步骤先验证，再进入下一步，并保留本计划中的边界。

**目标：** 在确实完成有价值关系修复的 AI 聊天结束后，把第一次同 NPC 右键转换为一次原版亲吻，动画完成后第二次右键再打开继续聊天。

**架构：** `ChatInputMenu` 保存玩家输入与 NPC 回复配对，并只报告本菜单是否完成过有价值关系修复；`FaceToFaceConversationCoordinator` 管理待亲吻和右键优先级；`RelationshipRepairRules` 负责窄语义修复判定，其他纯规则类负责阶段和生命周期判定；动画控制器调用 `Farmer.PerformKiss` 并临时复用 NPC 的 `KissSpriteIndex`。一次性状态只保存在内存中，不修改原版关系或日程。

**技术栈：** C# / .NET 6、SMAPI、Stardew Valley 1.6.15、xUnit、MonoGame `GameTime`。

---

### 任务 1：补充可测试的规则和状态机红灯

**文件：**
- 创建：`smapi/KissInteractionRules.cs`
- 修改：`smapi/FaceToFaceStateRules.cs`
- 修改：`smapi/tests/FaceToFaceStateRulesTests.cs`
- 创建：`smapi/tests/KissInteractionRulesTests.cs`

- [x] **步骤 1：编写失败测试**

覆盖以下行为：

```csharp
Assert.True(KissInteractionRules.CanArmAfterReply(
    effectiveReply: true,
    relationshipStage: "dating",
    customRelationshipType: null));
Assert.False(KissInteractionRules.CanArmAfterReply(
    effectiveReply: true,
    relationshipStage: "friend",
    customRelationshipType: null));
Assert.True(KissInteractionRules.CanArmAfterReply(
    effectiveReply: true,
    relationshipStage: "friend",
    customRelationshipType: "married"));

var state = FaceToFaceStateRules.ArmKissAfterReply(
    new FaceToFaceConversationState(FaceToFaceState.Composing, "Sophia"));
Assert.Equal(FaceToFaceState.AwaitingKiss, state.State);
state = FaceToFaceStateRules.BeginKiss(state);
Assert.Equal(FaceToFaceState.Kissing, state.State);
state = FaceToFaceStateRules.CompleteKiss(state);
Assert.Equal(FaceToFaceState.Idle, state.State);
```

另测 `CanTriggerKiss` 拒绝菜单、事件、节日、不同日期、不同地点、远距离和不可移动玩家；测 `ShouldCompleteKiss` 在最短展示时长前为 false、可移动且达到最短时长后为 true、达到最大时长后兜底为 true。

- [x] **步骤 2：运行红灯测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~FaceToFaceStateRulesTests -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~KissInteractionRulesTests -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：因新枚举、规则类和状态转换尚不存在而失败；若测试在实现前通过，先修正测试使其确实覆盖缺失行为。

- [x] **步骤 3：实现最少纯规则代码**

增加 `AwaitingKiss` / `Kissing` 状态和以下最小接口：

```csharp
public static bool CanArmAfterReply(bool effectiveReply, string? relationshipStage, string? customRelationshipType);
public static bool CanTriggerKiss(bool worldReady, bool menuOpen, bool sameDay, bool sameLocation, bool npcNearby, bool eventUp, bool festival, bool playerCanMove, bool usingTool, bool ridingHorse, bool sitting);
public static bool ShouldCompleteKiss(double elapsedMilliseconds, bool playerCanMove);
```

状态转换只接受预期状态，非法状态保持原值或返回 `Idle`，不扩散到存档模型。

- [x] **步骤 4：运行规则绿灯**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter 'FullyQualifiedName~FaceToFaceStateRulesTests|FullyQualifiedName~KissInteractionRulesTests' -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：新增规则测试与既有续聊测试全部通过。

### 任务 2：把有价值关系修复接入聊天关闭回调

**文件：**
- 修改：`smapi/ChatInputMenu.cs`
- 修改：`smapi/FaceToFaceConversationCoordinator.cs`
- 修改：`smapi/ModEntry.cs`
- 修改：`smapi/VisualTestHarness.cs`
- 修改：`smapi/DialogueMenu.cs`
- 创建：`smapi/ChatSessionRules.cs`
- 创建：`smapi/tests/ChatSessionRulesTests.cs`
- 修改：`smapi/tests/FaceToFaceStateRulesTests.cs`

- [x] **步骤 1：编写聊天结果红灯**

为会话规则增加最小纯辅助测试：普通有效回复、普通安慰、亲密表达、已解决问题和具体排期都不能挂起；当前存在活动嫉妒/调解且回复明确承认并解释、修复/履约或给空间时才挂起；本轮新出现明确冲突并完成修复也可挂起；fallback 不标记。为 coordinator 状态保留第一次右键亲吻、动画期间抑制右键和第二次右键续聊回归。

- [x] **步骤 2：运行红灯测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~FaceToFaceStateRulesTests -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：关闭回调缺少有效回复结果，状态无法进入 `AwaitingKiss`。

- [x] **步骤 3：实现最少回调接线**

在 `ChatInputMenu` 中记录当前玩家输入，并用 `RelationshipRepairRules` 累计 `hasValuableRelationshipRepair`；fallback、异常、空输入和 topic 请求不标记。`Close()` 只回调一次；把现有 `Action` 回调扩展为 `Action<bool>`，保留 `VisualTestHarness`、`DialogueMenu` 和 `ModEntry` 的现有用途。

coordinator 在有价值关系修复关闭时：

1. 用 `GameStateCollector.Collect(npc)` 和 `StoryStateStore.State.Relationships` 取得当前 NPC 的 vanilla/custom 恋爱阶段；
2. 通过 `KissInteractionRules.CanArmAfterReply` 后保存短期 `kissNpc` / `kissDay`，状态设为 `AwaitingKiss`；
3. 不创建继续聊天问题；没有关系修复证据、没有阶段资格或没有有效回复时继续使用原流程。

`ModEntry` 把 `TryConsumePendingKiss` 放到 `TryOpenRepeatChat` 之前；`OnPlayerWarped` 清除重复聊天和待亲吻短期状态；注册并转发 `UpdateTicked`。

- [x] **步骤 4：运行接线绿灯**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter 'FullyQualifiedName~FaceToFaceStateRulesTests|FullyQualifiedName~ConversationServiceTests' -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：编译通过，旧菜单生命周期和新状态契约通过。

### 任务 3：复用原版资源实现一次亲吻和动画生命周期

**文件：**
- 创建：`smapi/NpcKissAnimationController.cs`
- 修改：`smapi/FaceToFaceConversationCoordinator.cs`
- 修改：`smapi/ModEntry.cs`
- 创建：`smapi/tests/NpcKissAnimationRulesTests.cs`（若任务 1 的规则测试尚未覆盖动画边界则补充）

- [x] **步骤 1：编写动画控制红灯**

覆盖：一次待亲吻只能启动一个控制器；动画最短时长前右键不允许继续聊天；玩家恢复 `CanMove` 且超过最短时长或超过 2 秒上限后才完成；重置可以释放活动状态。

- [x] **步骤 2：运行红灯测试**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~NpcKissAnimationRulesTests -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：控制器和动画规则接口尚不存在而失败。

- [x] **步骤 3：实现最小控制器**

`TryStart` 先检查 `Game1.player`、`Game1.currentLocation`、事件/节日、菜单、距离和玩家动作前置条件；通过后调用 `Game1.player.PerformKiss(Game1.player.FacingDirection)`。读取 `npc.GetData()`，若 `KissSpriteIndex >= 0`，保存原方向、按 `KissSpriteFacingRight` 设置临时朝向，再用一个 `FarmerSprite.AnimationFrame(index, 1000)` 调用 `npc.Sprite.setCurrentAnimation(...)`。

`Update(GameTime)` 累加 `ElapsedGameTime`，满足 `KissInteractionRules.ShouldCompleteKiss` 后调用 `StopAnimation()`、恢复 NPC 方向，并通知 coordinator 完成。`Reset()` 做同样恢复但不通知继续聊天。

coordinator 在第一次目标右键消费挂起状态后切换 `Kissing`；控制器完成后记住同日同地点 NPC 并切回 `Idle`。动画中的右键直接返回已处理。

- [x] **步骤 4：运行控制器绿灯**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter 'FullyQualifiedName~NpcKissAnimationRulesTests|FullyQualifiedName~FaceToFaceStateRulesTests' -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：纯规则和 coordinator 状态测试通过；控制器依赖真实游戏对象的路径由编译和后续实机验证覆盖。

### 任务 4：定向回归、构建和边界扫描

**文件：**
- 修改：`docs/active-work.md`

- [x] **步骤 1：运行 C# 定向回归**

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter 'FullyQualifiedName~FaceToFaceStateRulesTests|FullyQualifiedName~KissInteractionRulesTests|FullyQualifiedName~NpcKissAnimationRulesTests|FullyQualifiedName~ConversationServiceTests' -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false -p:BundleExtraAssemblies=Game
```

- [x] **步骤 2：运行 SMAPI 全量测试和构建**

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false -p:BundleExtraAssemblies=Game
dotnet build smapi/StardewAI.NPC.csproj --no-restore -p:OS=Windows_NT -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
git diff --check
```

- [x] **步骤 3：检查边界**

确认 `git diff` 只包含亲吻实现、相关测试、设计/计划和活动记录；确认没有新增 `PerformKiss` 以外的日程/坐标/`spouse`/`datingFarmer` 写入，没有 Key/Token/Cookie 内容，没有 Stardew 或 SMAPI 进程，也没有部署 DLL。

- [x] **步骤 4：更新活动记录**

用实际测试输出记录红灯、绿灯、定向回归、全量测试和构建结果；明确写出本轮没有启动游戏，因此未对最终动画姿态做实机声明。
