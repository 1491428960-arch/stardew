# 真实游戏引擎视觉预览实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:executing-plans` 逐任务实现此计划；每个步骤完成后更新复选框并保留实际测试输出。

**目标：** 让 FastTest 自动加载指定存档、打开真实聊天菜单、从游戏 backbuffer 抓取 PNG 和 manifest；同时提供不启动游戏的 PNG/XNB 导出资源接触表作为快速筛查。

**架构：** `VisualTestHarness` 只在显式环境变量开启时运行，使用 Stardew/MonoGame 实际 draw call 后的 backbuffer 截图，脚本负责构造隔离 profile、自动选择存档、等待完成标记并停止进程。`preview_assets.py` 使用 Python 标准库解析 PNG 头并生成带 data URI 的 HTML 接触表，明确标注其不是游戏最终画面。

**技术栈：** C# / .NET 6、SMAPI 4.5.2、MonoGame 3.8 `GraphicsDevice.GetBackBufferData` / `Texture2D.SaveAsPng`、PowerShell 7、Python 3.12 标准库。

---

### 任务 1：定义可重复的截图 manifest 并先写失败测试

**文件：**
- 创建：`smapi/VisualTestManifest.cs`
- 创建：`smapi/tests/VisualTestManifestTests.cs`

- [ ] **步骤 1：编写 manifest 失败测试**

```csharp
[Fact]
public void SerializeUsesStableFieldOrderAndIncludesRuntimeIdentity()
{
    var manifest = new VisualTestManifest(
        SchemaVersion: 1,
        ScenarioId: "chat-empty",
        GameVersion: "1.6.15.24356",
        SmapiVersion: "4.5.2",
        ModDllSha256: "ABC",
        Locale: "zh-CN",
        BackBufferWidth: 1920,
        BackBufferHeight: 1080,
        UiViewportWidth: 1920,
        UiViewportHeight: 1080,
        UiScale: 1f,
        Zoom: 1f,
        ScreenshotFile: "chat-empty.png");

    var json = manifest.ToJson();

    Assert.StartsWith("{\"schemaVersion\":1,\"scenarioId\":\"chat-empty\"", json);
    Assert.Contains("\"modDllSha256\":\"ABC\"", json);
    Assert.Contains("\"screenshotFile\":\"chat-empty.png\"", json);
}

[Fact]
public void RejectsUnsafeScenarioAndScreenshotNames()
{
    Assert.Throws<ArgumentException>(() => VisualTestManifest.ValidateFileName("..\\old.png"));
    Assert.Throws<ArgumentException>(() => VisualTestManifest.ValidateFileName("nested/old.png"));
    Assert.Throws<ArgumentException>(() => VisualTestManifest.ValidateFileName(""));
}
```

- [ ] **步骤 2：运行测试确认类型尚未实现**

```powershell
$env:OS='Windows_NT'
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~VisualTestManifestTests -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：因 `VisualTestManifest` 未定义而编译失败。

- [ ] **步骤 3：实现最小 manifest 类型**

在 `VisualTestManifest.cs` 使用不可变 `record`，按测试中的字段顺序用 `System.Text.Json` 序列化；`ValidateFileName` 只允许单层文件名，拒绝空值、目录分隔符、`.`、`..` 和非法文件名字符。

- [ ] **步骤 4：运行测试确认通过**

重复步骤 2 命令，预期该测试类 PASS。

- [ ] **步骤 5：提交 manifest**

```powershell
git add smapi/VisualTestManifest.cs smapi/tests/VisualTestManifestTests.cs
git commit -m "feat(视觉测试): 添加稳定截图 manifest"
```

### 任务 2：实现真实引擎截图 harness

**文件：**
- 创建：`smapi/VisualTestHarness.cs`
- 修改：`smapi/ModEntry.cs`
- 创建：`smapi/tests/VisualTestHarnessRulesTests.cs`

- [ ] **步骤 1：先写运行规则失败测试**

测试 `VisualTestHarnessRules` 的纯逻辑，不加载游戏程序集状态：

```csharp
[Fact]
public void DisabledEnvironmentDoesNotStartHarness()
{
    Assert.False(VisualTestHarnessRules.IsEnabled(null));
    Assert.False(VisualTestHarnessRules.IsEnabled("0"));
}

[Fact]
public void EnabledEnvironmentRequiresSafeSaveNameAndOutputDirectory()
{
    var options = VisualTestHarnessRules.Parse(
        new Dictionary<string, string?>
        {
            ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
            ["STARDEW_AI_NPC_VISUAL_SAVE_NAME"] = "test_447101921",
            ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
        });

    Assert.True(options.Enabled);
    Assert.Equal("test_447101921", options.SaveName);
    Assert.Equal("chat-empty", options.ScenarioId);
}

[Fact]
public void UnsafeSaveNameFailsClosed()
{
    Assert.Throws<ArgumentException>(() => VisualTestHarnessRules.Parse(
        new Dictionary<string, string?>
        {
            ["STARDEW_AI_NPC_VISUAL_TEST"] = "1",
            ["STARDEW_AI_NPC_VISUAL_SAVE_NAME"] = "..\\other-save",
            ["STARDEW_AI_NPC_VISUAL_OUTPUT"] = "artifacts/visual-tests/run",
        }));
}
```

- [ ] **步骤 2：运行筛选测试确认失败**

预期：`VisualTestHarnessRules` 未定义导致编译失败；任务 1 的 manifest 测试保持通过。

- [ ] **步骤 3：实现规则解析和最小 harness**

实现要点：

1. 仅当 `STARDEW_AI_NPC_VISUAL_TEST=1` 或 `true` 时启用；默认完全不改变正常 Mod 行为。
2. `STARDEW_AI_NPC_VISUAL_SAVE_NAME` 默认 `test_447101921`，只允许单层保存名；`STARDEW_AI_NPC_VISUAL_OUTPUT` 必须是显式输出目录。
3. 在 `GameLaunched` 后安排一次 `SaveGame.Load(saveName)`；已经 `Context.IsWorldReady` 时不重复加载。
4. `SaveLoaded` 后等待固定 tick，取得 `NpcTargetResolver` 解析出的 NPC 和现有 `conversationService`，将 `ChatInputMenu` 设为 `Game1.activeClickableMenu`。
5. 订阅 `Display.Rendered`，连续 3 帧确认菜单仍为当前菜单后调用 `GraphicsDevice.GetBackBufferData<Color>`，创建 `Texture2D`、`SetData`、`SaveAsPng`。
6. manifest 写入游戏版本、SMAPI 版本、Mod DLL SHA256、backbuffer、`Game1.uiViewport`、UI scale、zoom、locale、场景 ID 和 PNG 文件名；写入完成标记 `visual-test.done` 后不再截图。
7. 不调用系统级截图、不模拟 Stardew UI、不记录聊天文本；脚本看到完成标记后负责停止进程。
8. 游戏缺少存档、NPC、Bridge/菜单或 backbuffer 时写入 `visual-test.failed` 和明确日志，并停止后返回失败。

- [ ] **步骤 4：把 harness 接入 ModEntry 的事件生命周期**

在 `ModEntry.Entry` 创建 harness 并注册 `GameLaunched`、`SaveLoaded`、`Display.Rendered`、`ReturnedToTitle`；在正常环境变量缺失时不订阅运行逻辑。`OnReturnedToTitle` 清理 harness 状态，避免测试模式泄漏到下一存档。

- [ ] **步骤 5：运行纯测试确认通过**

```powershell
$env:OS='Windows_NT'
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~VisualTest -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：manifest 与规则测试全部 PASS。

- [ ] **步骤 6：提交 harness 代码**

```powershell
git add smapi/VisualTestHarness.cs smapi/ModEntry.cs smapi/tests/VisualTestHarnessRulesTests.cs
git commit -m "feat(视觉测试): 接入真实游戏引擎截图 harness"
```

### 任务 3：实现自动启动、选档、抓图和哈希门禁脚本

**文件：**
- 创建：`scripts/start_visual_test.ps1`
- 创建：`scripts/test_start_visual_test.ps1`
- 修改：`.gitignore`

- [ ] **步骤 1：编写脚本失败测试**

`test_start_visual_test.ps1` 使用临时目录和假的 SMAPI 可执行脚本，验证以下行为：

1. 脚本先调用 `start_fast_test.ps1 -NoLaunch` 同步隔离 profile；
2. 以 `--mods-path <fast profile>` 启动 SMAPI，参数路径作为单个参数传递；
3. 子进程继承 `STARDEW_AI_NPC_VISUAL_TEST=1`、存档名和输出目录；
4. 看到 `visual-test.done` 后停止自己启动的进程树并返回 0；
5. 超时、`visual-test.failed`、DLL 缺失或 profile 路径不安全时返回非零；
6. 不删除正式游戏目录、正式 Mods 或用户存档。

- [ ] **步骤 2：运行脚本测试确认新入口不存在**

```powershell
pwsh -NoProfile -File scripts/test_start_visual_test.ps1
```

预期：因 `start_visual_test.ps1` 尚未存在而失败。

- [ ] **步骤 3：实现隔离启动器**

`start_visual_test.ps1` 具体参数：`-GamePath`、`-FastModsPath`、`-ProjectRoot`、`-SaveName`、`-OutputPath`、`-ScenarioId`、`-TimeoutSeconds`。实现：

1. 复用 `start_fast_test.ps1 -IncludeRasmodia -NoLaunch` 完成 profile 同步；
2. 检查 FastTest DLL 存在，记录其 SHA256；
3. 用 `Start-Process -PassThru -WindowStyle Hidden` 启动 SMAPI，并设置上述环境变量；
4. 每 250ms 检查完成/失败标记，超时按进程树结束 SMAPI 和其子进程；
5. 完成后验证 manifest 中的 `modDllSha256` 等于 profile DLL SHA256，验证 PNG 与 manifest 同时存在；
6. 输出 `VISUAL_TEST_DONE`、截图路径、manifest 路径、DLL SHA256；异常输出 `VISUAL_TEST_FAILED` 并返回 1；
7. `finally` 恢复当前 PowerShell 进程原有环境变量，不清理用户存档。

把 `artifacts/visual-tests/` 加入 `.gitignore`，不把截图、临时日志和基准图提交到 Git。

- [ ] **步骤 4：运行脚本单元测试确认通过**

```powershell
pwsh -NoProfile -File scripts/test_start_visual_test.ps1
```

预期：全部脚本断言 PASS，输出明确报告通过/失败数量。

- [ ] **步骤 5：执行一次真实最小截图**

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/start_visual_test.ps1 `
  -GamePath 'D:\sbeam\steamapps\common\Stardew Valley' `
  -FastModsPath 'D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest' `
  -SaveName 'test_447101921' `
  -OutputPath 'artifacts/visual-tests/chat-empty' `
  -ScenarioId 'chat-empty' `
  -TimeoutSeconds 120
```

预期：无需人工点击游戏，输出 `chat-empty.png`、`chat-empty.json` 和 `visual-test.done`；SMAPI 日志显示加载 FastTest profile 下的新 DLL。

- [ ] **步骤 6：核对真实加载而非仅构建成功**

```powershell
$manifest = Get-Content artifacts/visual-tests/chat-empty/chat-empty.json -Raw | ConvertFrom-Json
$dll = 'D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest\StardewAI.NPC\StardewAI.NPC.dll'
Get-FileHash $dll -Algorithm SHA256
Select-String -Path "$env:APPDATA\StardewValley\ErrorLogs\SMAPI-latest.txt" -Pattern 'Stardew AI NPC.*Mods-AI-FastTest|AI NPC 原型已加载'
```

预期：manifest 哈希、profile DLL 哈希和 SMAPI 日志对应同一构建；缺任一证据都不能标记截图测试通过。

- [ ] **步骤 7：提交启动器**

```powershell
git add scripts/start_visual_test.ps1 scripts/test_start_visual_test.ps1 .gitignore
git commit -m "feat(视觉测试): 自动启动 FastTest 并验证截图产物"
```

### 任务 4：补充真实场景与 UI scale 回归

**文件：**
- 修改：`smapi/VisualTestHarness.cs`
- 修改：`scripts/start_visual_test.ps1`
- 创建：`docs/report-visual-preview-and-ime-2026-08-25.md`

- [ ] **步骤 1：先扩展场景规则测试**

增加 `VisualTestScenarioTests`，对固定清单逐项断言：`chat-empty`、`chat-long-zh`、`chat-multi-message`、`chat-profile`；每个场景都有稳定文件名和 manifest 场景 ID，未知场景直接抛 `ArgumentException`。

- [ ] **步骤 2：运行测试确认场景清单先失败**

```powershell
$env:OS='Windows_NT'
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~VisualTestScenarioTests -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：新场景尚未注册时失败。

- [ ] **步骤 3：实现场景和运行时 manifest**

场景数据固定为：

- `chat-empty`：无消息、头像和关系栏；
- `chat-long-zh`：一条 120 字中文消息，覆盖换行；
- `chat-multi-message`：玩家/NPC 交替 8 条消息；
- `chat-profile`：头像、好感度和发送中按钮状态。

每张图记录 `viewport` 与 `uiViewport`，并在 harness 中优先以 `Game1.uiViewport` 作为菜单坐标验证依据；真实截图中若发现当前 `Game1.viewport` 导致 UI scale 非 100% 时偏移，再先写回归测试后修改 `ChatInputMenu`/`ChatLayoutRules`。

- [ ] **步骤 4：运行三组真实引擎配置**

依次运行 100%/100%、UI 75% + zoom 200%、UI 150% + zoom 75%，另跑 `zh-CN` 与英文 locale；每组输出独立目录和 manifest，不能复用旧 baseline。

- [ ] **步骤 5：生成研究报告**

创建 `docs/report-visual-preview-and-ime-2026-08-25.md`，记录：输入链路事实、MonoGame 3.8 预编辑限制、三层预览取舍、实际运行版本、场景截图清单、DLL/SMAPI 证据、已知限制和官方来源链接。报告不嵌入个人聊天文本或密钥。

- [ ] **步骤 6：提交场景与报告**

```powershell
git add smapi/VisualTestHarness.cs scripts/start_visual_test.ps1 docs/report-visual-preview-and-ime-2026-08-25.md
git commit -m "docs(视觉测试): 记录真实引擎预览验收矩阵"
```

### 任务 5：实现离线素材接触表（辅路径）

**文件：**
- 创建：`scripts/preview_assets.py`
- 创建：`scripts/test_preview_assets.py`

- [ ] **步骤 1：编写 PNG 解析失败测试**

测试用标准库构造一个 2×3 RGBA PNG 头，断言 `read_png_metadata` 返回宽度、高度、色彩类型和 SHA256；空文件、非 PNG、缺少 IHDR 必须抛出 `ValueError`。另测 HTML 输出包含 `素材快检`、相对文件名和 data URI，不包含“游戏最终画面”等误导性字样。

- [ ] **步骤 2：运行测试确认函数尚未实现**

```powershell
python scripts/test_preview_assets.py -v
```

预期：因 `preview_assets.py` 不存在而失败。

- [ ] **步骤 3：实现标准库接触表**

递归扫描输入目录中的 `.png`，按相对路径排序，读取 PNG signature/IHDR、计算 SHA256、生成 base64 data URI；输出：

1. `manifest.json`：相对路径、字节数、宽高、色彩类型、SHA256；
2. `contact-sheet.html`：每张图片、尺寸、哈希前 12 位、透明度提示，并在页眉写明“素材快检，不等同于 Stardew 最终渲染”。

输入目录为空或没有合法 PNG 时返回非零；不覆盖既有输出目录中的文件，使用带时间戳的新输出目录。

- [ ] **步骤 4：运行测试确认通过**

```powershell
python scripts/test_preview_assets.py -v
```

预期：全部 PASS。

- [ ] **步骤 5：用真实资源生成一次接触表**

```powershell
python scripts/preview_assets.py `
  --input 'D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest\[CP] Romanceable Rasmodia\assets' `
  --output 'artifacts/visual-tests/assets'
```

预期：生成接触表和 manifest；该结果只用于快速筛查，最终 UI 仍以任务 3/4 的游戏截图为准。

- [ ] **步骤 6：提交离线快检器**

```powershell
git add scripts/preview_assets.py scripts/test_preview_assets.py
git commit -m "feat(视觉预览): 添加离线素材接触表"
```

## 完成门禁

- 最小真实引擎截图能在无人手动点击情况下完成；
- PNG、manifest、FastTest DLL SHA256、SMAPI 日志四项证据一致；
- UI scale/zoom 与中英文场景均有独立 manifest；
- 离线接触表可用但明确标注非最终渲染；
- 所有新增 C#、PowerShell、Python 测试先 RED 后 GREEN；
- 截图和临时输出不进入 Git；
- 研究报告包含本地版本证据、已知限制和官方来源。
