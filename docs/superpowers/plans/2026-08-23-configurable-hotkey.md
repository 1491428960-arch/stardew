# 可配置 AI NPC 快捷键实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将游戏内 AI NPC 对话快捷键从硬编码 `N` 改为可配置，默认使用 `F8`。

**架构：** 在 SMAPI 的 ModConfig 中增加 `DialogueKey` 字段，使用 SMAPI 的 `ReadConfig<T>()` 读取配置；`ModEntry` 将配置映射为 `SButton`，只在按下该键时打开对话菜单。配置文件由 SMAPI 首次启动时自动生成，用户可直接修改键名。

**技术栈：** C#、SMAPI、xUnit、.NET 6/8。

---

### 任务 1：补充快捷键配置与失败测试

**文件：**
- 创建：`smapi/ModConfig.cs`
- 修改：`smapi/ModEntry.cs`
- 测试：`smapi/tests/ModConfigTests.cs`

- [ ] **步骤 1：编写失败的测试**

测试默认值为 `F8`，并验证 `N` 不再是默认触发键；配置文本可被 SMAPI 的 JSON 配置模型读取。

- [ ] **步骤 2：运行测试验证失败**

运行：`dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\\sbeam\\steamapps\\common\\Stardew Valley"`

预期：新增配置类型或默认值断言失败。

- [ ] **步骤 3：编写最少实现代码**

新增：

```csharp
public sealed class ModConfig
{
    public string DialogueKey { get; set; } = "F8";
}
```

在 `ModEntry.Entry` 中调用 `helper.ReadConfig<ModConfig>()`，用 `Enum.TryParse<SButton>` 解析 `DialogueKey`，解析失败时回退到 `SButton.F8`；`OnButtonPressed` 只比较解析后的键。

- [ ] **步骤 4：运行测试验证通过**

运行同上，预期所有测试通过，并保留原有 BridgeClient/GameStateCollector 行为。

- [ ] **步骤 5：Commit**

提交：`feat(SMAPI): 将 AI NPC 快捷键改为可配置 F8`

### 任务 2：构建、部署和回归验证

**文件：**
- 修改：无
- 验证：`smapi/StardewAI.NPC.csproj`、D 盘 Mod 目录

- [ ] **步骤 1：运行完整测试和构建**

运行 Python 测试、C# 测试和构建，预期 Python 52 passed、C# 测试数量不减少、构建 0 警告/0 错误。

- [ ] **步骤 2：部署到游戏 Mod 目录**

运行带 `/p:EnableModDeploy=true` 的构建，仅写入 `D:\sbeam\steamapps\common\Stardew Valley\Mods`。

- [ ] **步骤 3：确认部署产物**

检查部署 DLL 与构建 DLL 的 SHA-256 相同，并确认 `config.json` 的默认快捷键为 `F8`（若 SMAPI 已生成配置）。

- [ ] **步骤 4：Commit/交付**

确认项目主分支工作树干净，并向用户说明按 `F8` 测试。
