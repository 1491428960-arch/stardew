# 游戏内 F9 多人中心视觉测试实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 在当前 worktree 内逐任务执行，按每个任务的验证命令设置检查点；不创建 Git commit。

**目标：** 在不操作用户键盘鼠标、不发起 Bridge 请求、不写入测试存档的前提下，使用 FastTest 启动真实 Stardew/SMAPI，打开生产路径的 F9 多人中心并生成可检查的截图与 manifest。

**架构：** 视觉 harness 增加 `group-hub` 动作，复用 `ModEntry.TryOpenGroupHub()` 和真实 `GroupDialogueHubMenu`，不复制一套测试菜单。harness 在内存故事状态中临时放入一张邀约卡，截图完成或异常退出前恢复原状态；不会调用存档保存接口。脚本只同步到 `Mods-AI-FastTest`，通过唯一输出目录和 DLL SHA-256 防止误读历史截图。

**技术栈：** C#/.NET 6、SMAPI、MonoGame SpriteBatch、xUnit、PowerShell FastTest 脚本。

---

### 任务 1：为 `group-hub` 动作建立失败测试

**文件：**
- 修改：`smapi/tests/VisualTestHarnessRulesTests.cs`
- 参考：`smapi/VisualTestHarness.cs`

- [ ] **步骤 1：编写失败测试**

新增测试覆盖：

```csharp
[Fact]
public void EnabledEnvironmentAcceptsExplicitGroupHubAction()
{
    var options = VisualTestHarnessRules.Parse(new Dictionary<string, string?>
    {
        ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
        ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
        ["STARDEW_AI_NPC_VISUAL_ACTION"] = "group-hub",
    });

    Assert.Equal("group-hub", options.ActionId);
}

[Fact]
public void GroupHubActionWaitsForStableMenuBeforeTriggering()
{
    Assert.False(VisualTestHarnessRules.CanTriggerGroupHubAction("group-hub", false, false, 3));
    Assert.False(VisualTestHarnessRules.CanTriggerGroupHubAction("group-hub", true, true, 3));
    Assert.False(VisualTestHarnessRules.CanTriggerGroupHubAction("group-hub", true, false, 2));
    Assert.True(VisualTestHarnessRules.CanTriggerGroupHubAction("group-hub", true, false, 3));
    Assert.False(VisualTestHarnessRules.CanTriggerGroupHubAction("capture", true, false, 3));
}
```

- [ ] **步骤 2：运行测试确认是预期失败**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~VisualTestHarnessRulesTests
```

预期：编译失败，原因是 `group-hub` 尚未被动作解析器接受，且 `CanTriggerGroupHubAction` 尚不存在。

### 任务 2：实现受控 `group-hub` harness 动作

**文件：**
- 修改：`smapi/VisualTestHarness.cs`
- 修改：`smapi/ModEntry.cs`

- [ ] **步骤 1：扩展动作解析和触发规则**

在 `VisualTestHarnessRules` 中增加 `GroupHubActionId = "group-hub"`，让 `Parse` 接受 `capture`、`topic`、`group-hub`，并增加只允许稳定菜单帧触发一次的 `CanTriggerGroupHubAction`。

- [ ] **步骤 2：注入生产 F9 入口**

将 `VisualTestHarness` 构造函数增加 `Func<bool> openGroupHub` 参数；`ModEntry.Entry` 传入已有的 `TryOpenGroupHub`。harness 仅在 `group-hub` 动作下调用该回调，并验证 `Game1.activeClickableMenu` 实际为 `GroupDialogueHubMenu`。

- [ ] **步骤 3：准备和恢复内存邀约状态**

在打开菜单前保存 `storyStateStore.State`，插入 `source="visual-test"`、`status=Unread`、`Abigail/Emily`、固定主题和 `ExpiresTotalDays=int.MaxValue` 的单张邀约；截图成功或 `Fail`、`Dispose`、返回标题时恢复原状态。测试过程不调用 `Helper.Data.WriteSaveData`，不触发真实邀约生成器，不发送 Bridge 请求。

- [ ] **步骤 4：让截图逻辑支持真实多人中心**

将截图目标从只允许 `ChatInputMenu` 改为当前 harness 打开的 `IClickableMenu`，但保留 `topic` 专用的回复等待和日志逻辑。截图 manifest 继续记录当前运行 DLL SHA-256、游戏版本、SMAPI 版本、viewport 和输出路径。

- [ ] **步骤 5：运行定向测试确认通过**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~VisualTestHarnessRulesTests
```

预期：视觉 harness 规则测试全部通过，且 `capture/topic` 原有测试不变。

### 任务 3：扩展视觉测试脚本参数并做静态验证

**文件：**
- 修改：`scripts/start_visual_test.ps1`
- 测试：`scripts/test_start_visual_test.ps1`（仅在现有脚本测试需要新增断言时修改）

- [ ] **步骤 1：允许 `-ActionId group-hub`**

将脚本动作白名单从 `capture/topic` 扩展为 `capture/topic/group-hub`，保持输出目录必须是新目录、路径不能指向正式 Mods 或项目目录的保护逻辑。

- [ ] **步骤 2：运行 PowerShell 语法和脚本回归**

运行：

```powershell
pwsh.exe -NoProfile -File scripts/test_start_fast_test.ps1
```

预期：FastTest 同步脚本测试通过；不会修改任何 ExecutionPolicy。

- [ ] **步骤 3：构建当前 Mod 但禁止部署**

运行：

```powershell
dotnet build smapi/StardewAI.NPC.csproj --no-restore -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：0 warning、0 error；不把 DLL 写入正式 `Mods`。

### 任务 4：启动隔离 FastTest 并检查真实 F9 截图

**文件：**
- 输出：`artifacts/visual-tests/<本次唯一目录>/group-hub.png`
- 输出：`artifacts/visual-tests/<本次唯一目录>/group-hub.json`
- 输出：`artifacts/visual-tests/<本次唯一目录>/visual-test.done` 或 `visual-test.failed`

- [ ] **步骤 1：启动前检查**

确认 `StardewModdingAPI.exe`、`Mods-AI-FastTest`、`test_447101921` 存在，且当前没有已经运行的 Stardew/SMAPI 进程；不读取或打印任何密钥和完整存档内容。

- [ ] **步骤 2：启动真实引擎视觉测试**

运行：

```powershell
pwsh.exe -NoProfile -File scripts/start_visual_test.ps1 `
  -ActionId group-hub `
  -ScenarioId group-hub `
  -SaveName test_447101921 `
  -OutputPath artifacts/visual-tests/<本次唯一目录>
```

预期：输出 `VISUAL_TEST_DONE`，生成 PNG、JSON 和完成标记；脚本结束时只清理由它启动的 SMAPI 进程树。

- [ ] **步骤 3：验证工件和视觉结果**

读取 manifest，确认 `scenarioId=group-hub`，并确认 `modDllSha256` 与 FastTest profile 中同步 DLL 的 SHA-256 一致；使用图片查看工具检查标题、邀约卡、参与者、主题和按钮没有裁切或越界。

- [ ] **步骤 4：记录边界**

报告只能覆盖真实 F9 菜单的入口、渲染和生命周期；不把这次截图当作键盘输入、中文 IME、真实 Bridge 回复或多人质量评测证据。需要物理输入时，先向用户单独请求一次确认，再进行 F9、鼠标点击和文本输入。

---

## 计划自检

- 规格覆盖：包含动作解析、生产入口复用、临时故事状态、脚本参数、真实启动、截图检查和输入边界。
- 占位符检查：`<本次唯一目录>` 是命令调用时生成的具体输出目录名，不是代码实现占位符；实现步骤没有 TODO 或待定项。
- 类型一致性：动作名统一为 `group-hub`；入口统一为 `Func<bool> openGroupHub`；现有 `capture/topic` 路径保持原语义。
- 风险检查：不启动正式 Mods，不修改正式存档，不调用云端 Provider，不创建提交。
