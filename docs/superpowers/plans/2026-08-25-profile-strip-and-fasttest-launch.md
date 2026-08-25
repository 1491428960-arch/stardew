# NPC 资料条与真实引擎预览实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans（当前会话采用内联执行）逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将聊天窗口右侧的竖向 NPC 资料卡改成紧凑横向资料条，并用正确的 FastTest/Rasmodia 入口生成真实游戏引擎预览截图。

**架构：** `ChatLayoutRules` 负责资料条几何和“是否绘制好感度条”的纯规则；`ChatInputMenu.DrawProfile` 只负责按照该几何绘制运行时 NPC 肖像、名称和好感度。启动器保持现有 Bridge 生命周期，只补充回归测试，真实预览通过 `start_visual_test.ps1` 同步包含 Rasmodia 的 FastTest profile 后启动 SMAPI。

**技术栈：** C#/.NET 8、xUnit、MonoGame `SpriteBatch`、SMAPI、PowerShell 7、VisualTestHarness。

---

### 任务 1：补充资料条布局和数据规则的失败测试

**文件：**
- 修改：`smapi/tests/ChatLayoutRulesTests.cs`
- 修改：`smapi/ChatLayoutRules.cs`

- [ ] **步骤 1：编写失败测试**

在 `ChatLayoutRulesTests` 中增加：

```csharp
[Fact]
public void ProfilePanelUsesCompactHorizontalGeometry()
{
    var layout = ChatLayoutRules.Calculate(1280, 720);

    Assert.Equal(280, layout.ProfilePanel.Width);
    Assert.InRange(layout.ProfilePanel.Height, 96, 128);
    Assert.True(layout.ProfilePanel.Height < layout.MessageArea.Height);
    Assert.False(layout.ConversationArea.Intersects(layout.ProfilePanel));
}

[Theory]
[InlineData(null, false)]
[InlineData(0, true)]
[InlineData(5, true)]
public void FriendshipMeterOnlyDrawsWhenHeartsAreKnown(int? hearts, bool expected)
{
    Assert.Equal(expected, ChatLayoutRules.ShouldDrawFriendshipMeter(hearts));
}
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
$env:OS='Windows_NT'
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter 'FullyQualifiedName~ChatLayoutRulesTests' -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley'
```

预期：新增的资料条尺寸断言失败（当前宽度为 168、面板高度贯穿消息区），`ShouldDrawFriendshipMeter` 尚未定义。

- [ ] **步骤 3：实现最少纯规则代码**

在 `ChatLayoutRules` 中将资料条宽度改为 `280`，资料条高度改为 `Math.Min(112, messageArea.Height)`，并保留 `MinimumConversationWidth + ProfileWidth + ActionGap` 的显示阈值。新增：

```csharp
public static bool ShouldDrawFriendshipMeter(int? hearts) => hearts.HasValue;
```

- [ ] **步骤 4：运行测试确认布局规则通过**

重复步骤 2；预期 `ChatLayoutRulesTests` 全部通过，且 480×320 极窄视口仍返回 `Rectangle.Empty` 资料面板。

- [ ] **步骤 5：提交布局规则**

```powershell
git add smapi/ChatLayoutRules.cs smapi/tests/ChatLayoutRulesTests.cs
git commit -m "test(聊天界面): 约束横向 NPC 资料条布局"
```

### 任务 2：按横向资料条绘制真实运行时肖像

**文件：**
- 修改：`smapi/ChatInputMenu.cs`
- 修改：`smapi/tests/ChatLayoutRulesTests.cs`

- [ ] **步骤 1：先锁定绘制规则的可测试边界**

保留任务 1 的 `ShouldDrawFriendshipMeter` 测试，并增加一个边界断言，确保未知好感度仍可以绘制资料条主体而不需要空进度条：

```csharp
[Fact]
public void KnownFriendshipRuleDoesNotRequirePositiveHeartCount()
{
    Assert.True(ChatLayoutRules.ShouldDrawFriendshipMeter(0));
}
```

- [ ] **步骤 2：运行目标测试确认新增断言通过**

运行同一条 `dotnet test ... --filter 'FullyQualifiedName~ChatLayoutRulesTests'` 命令，预期全部通过。

- [ ] **步骤 3：重写 `DrawProfile` 的最小绘制逻辑**

在 `ChatInputMenu.DrawProfile` 中保持现有 `drawTextureBox` 外框和 `npc.Portrait` 运行时资源，改为：

```csharp
const int portraitSize = 64;
var portraitFrame = new Rectangle(
    panel.X + MessagePadding,
    panel.Y + ((panel.Height - portraitSize) / 2),
    portraitSize,
    portraitSize);
var infoX = portraitFrame.Right + 12;
var infoY = panel.Y + 22;
```

肖像绘制到 `portraitFrame`，名称从 `infoX` 开始绘制，第二行绘制 `好感度 N 心` 或 `好感度未知`。只有 `ChatLayoutRules.ShouldDrawFriendshipMeter(hearts)` 为真时，才在信息区下方绘制 10px 高进度条；未知好感度不绘制灰色空槽。所有文字和进度条都限制在 `panel` 内部。

- [ ] **步骤 4：运行 C# 全量测试**

运行：

```powershell
$env:OS='Windows_NT'
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley'
```

预期：全部测试通过，且测试项目不会触发 ModBuild 部署/压缩目标。

- [ ] **步骤 5：提交资料条绘制**

```powershell
git add smapi/ChatInputMenu.cs smapi/tests/ChatLayoutRulesTests.cs
git commit -m "feat(聊天界面): 改用横向 NPC 资料条"
```

### 任务 3：锁定正确的 FastTest/Rasmodia 启动入口

**文件：**
- 修改：`scripts/test_start_ai_npc_test.ps1`
- 参考：`scripts/start_ai_npc_test.ps1`

- [ ] **步骤 1：增加启动器回归测试**

在已有 PowerShell 测试中增加源码断言：

```powershell
Assert-True ($launcherText -match "\$fastArguments \+= '-IncludeRasmodia'") '默认快速 profile 包含 Rasmodia 资源'
Assert-True ($launcherText -match '\$Launch.*Test-BridgeHealth') '启动游戏前检查 Bridge 健康状态'
```

- [ ] **步骤 2：运行启动器测试确认结果**

运行：

```powershell
pwsh -NoProfile -File scripts/test_start_ai_npc_test.ps1
```

预期：输出 `结果：通过 N，失败 0`；如果源码断言因 PowerShell 正则转义失败，先调整测试字符串而不改变启动器行为。

- [ ] **步骤 3：确认真实预览脚本显式传递 `-IncludeRasmodia`**

运行：

```powershell
rg -n "-IncludeRasmodia|-NoLaunch" scripts/start_visual_test.ps1
```

预期：`Invoke-FastProfileSync` 的参数同时包含 `-IncludeRasmodia` 和 `-NoLaunch`，不修改底层脚本的默认基础模式。

- [ ] **步骤 4：提交启动入口回归测试**

```powershell
git add scripts/test_start_ai_npc_test.ps1
git commit -m "test(启动器): 防止视觉测试遗漏 Rasmodia 资源"
```

### 任务 4：构建、部署并用真实引擎生成资料条截图

**文件：**
- 产物：`artifacts/visual-tests/chat-profile-strip-<唯一后缀>/chat-profile-strip.png`
- 产物：同目录 `chat-profile-strip.json`、`visual-test.done`

- [ ] **步骤 1：运行全量验证**

运行 C# 全量测试和 PowerShell 启动器测试，预期均为零失败。

- [ ] **步骤 2：启动真实视觉预览**

使用新的、此前不存在的输出目录：

```powershell
pwsh -NoProfile -File scripts/start_visual_test.ps1 `
  -GamePath 'D:\sbeam\steamapps\common\Stardew Valley' `
  -FastModsPath 'D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest' `
  -OutputPath 'artifacts\visual-tests\chat-profile-strip-final' `
  -ScenarioId 'chat-profile-strip' `
  -TimeoutSeconds 180
```

预期输出 `VISUAL_TEST_DONE`，同时 manifest 的 `modDllSha256` 与 FastTest profile 中 `StardewAI.NPC.dll` 的 SHA256 相同。

- [ ] **步骤 3：检查实际加载证据**

读取 `chat-profile-strip.json`、源 DLL、FastTest DLL 哈希，并检查 SMAPI 日志包含 `Rasmodia`、`Content Patcher`、`CrossModCompatibilityTokens` 和 `Stardew AI NPC`。预期截图来自真实 `backbuffer`，不使用浏览器 mock。

- [ ] **步骤 4：人工检查截图并提交可追踪产物**

使用 `view_image` 打开 `chat-profile-strip.png`，确认右侧资料条横向排列、头像不变形、名称/好感度不越界、对话区与资料条有间隔。然后运行 `git diff --check`，提交源代码和测试；视觉截图保留为本地验收产物，不提交 DLL、日志或存档。

---

## 交付验收

- C# 全量测试通过；
- PowerShell 启动器回归测试通过；
- 真实引擎视觉测试输出 PNG + manifest + `visual-test.done`；
- 源 DLL、FastTest DLL、manifest SHA256 一致；
- SMAPI 日志确认加载 Rasmodia 相关 5 个 Mod；
- 用户手动启动只使用 `scripts/start_ai_npc_test.ps1 -Launch`，不再直接调用底层 `start_fast_test.ps1`。
