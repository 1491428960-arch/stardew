# 聊天菜单标题可读性实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:executing-plans 逐任务实现此计划。

**目标：** 移除容易与背景混淆的左上角聊天标题和状态行，保留右侧 NPC 资料卡作为身份展示。

**架构：** 不改布局模型，只调整 `ChatInputMenu.DrawHeader` 的绘制内容。NPC 名称、肖像和好感度继续由 `DrawProfile` 使用游戏原版资源绘制。

**技术栈：** C#、SMAPI、MonoGame `SpriteBatch`、xUnit。

---

### 任务 1：锁定标题绘制行为

**文件：**
- 修改：`smapi/ChatInputMenu.cs:442-462`
- 测试：`smapi/tests/ChatLayoutRulesTests.cs`

- [x] **步骤 1：确认现有测试基线**

运行：

```powershell
$env:OS='Windows_NT'
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：当前全部测试通过，证明本次只需增加 header 文本职责的回归断言。

- [x] **步骤 2：添加可测试的标题规则**

在 `ChatLayoutRules` 中增加纯函数：

```csharp
public static bool ShouldDrawHeaderTitle() => false;
public static bool ShouldDrawHeaderStatus() => false;
```

在 `ChatLayoutRulesTests` 中断言两条规则均为 `false`。不让测试依赖 MonoGame 图形对象或截图像素。

- [x] **步骤 3：运行新增测试确认失败**

运行：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~ChatLayoutRulesTests -p:GamePath='D:\sbeam\steamapps\common\Stardew Valley' -p:EnableModDeploy=false -p:EnableModZip=false
```

预期：在规则尚未添加前编译失败，提示 `ShouldDrawHeaderTitle` 不存在。

### 任务 2：移除左上角标题和状态行

**文件：**
- 修改：`smapi/ChatLayoutRules.cs`
- 修改：`smapi/ChatInputMenu.cs`
- 测试：`smapi/tests/ChatLayoutRulesTests.cs`

- [x] **步骤 1：实现最小规则与绘制分支**

在 `ChatLayoutRules` 中添加返回 `false` 的纯规则，并将 `DrawHeader` 中标题和状态行绘制分别包在规则判断内；好感度仍由右侧 `DrawProfile` 绘制：

```csharp
if (ChatLayoutRules.ShouldDrawHeaderTitle())
{
    b.DrawString(
        Game1.dialogueFont,
        title,
        new Vector2(layout.Header.X + MessagePadding, layout.Header.Y + 8),
        Color.Black);
}
```

由于规则固定为 `false`，最终运行时不绘制左上角文字；保留分支使后续布局策略可单独测试，不移动 header 坐标。

- [x] **步骤 2：运行聚焦测试确认通过**

运行同任务 1 的聚焦命令，预期 `ChatLayoutRulesTests` 全部通过。

- [x] **步骤 3：运行完整 C# 回归**

运行完整 `dotnet test`，预期 0 失败。

### 任务 3：真实引擎截图验证

**文件：**
- 生成：`artifacts/visual-tests/chat-header-clean-final2/`
- 验证：`scripts/start_visual_test.ps1`

- [x] **步骤 1：构建并同步 FastTest**

运行启动器生成唯一输出目录：

```powershell
pwsh -NoProfile -File scripts/start_visual_test.ps1 `
  -ProjectRoot (Get-Location).Path `
  -FastModsPath 'D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest' `
  -OutputPath 'artifacts\visual-tests\chat-header-clean-final2' `
  -ScenarioId 'chat-empty' -TimeoutSeconds 180
```

预期：输出 `VISUAL_TEST_DONE`，并验证 manifest DLL 哈希等于 FastTest profile。

- [x] **步骤 2：人工检查截图**

确认左上角不再有标题或状态文字；右侧资料卡仍显示肖像、NPC 名称和好感度。

- [x] **步骤 3：检查工作树边界**

运行 `git status --short`，确认只出现本计划预期的源文件/测试/文档以及既有未提交改动，不覆盖或清理其他修改。

### 审查补充：极窄窗口输入区域

代码审查发现 `480×320` 下输入框与“发送”按钮会重叠。已先补充失败回归测试，再将极窄 footer 的按钮宽度与间距收紧；聚焦布局测试 10/10、完整 C# 回归 149/149 通过，避免该问题影响输入法点击命中。
