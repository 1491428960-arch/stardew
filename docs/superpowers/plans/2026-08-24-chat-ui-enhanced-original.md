# 增强版星露谷聊天界面实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将已确认的“增强版星露谷原版”视觉基线落地到游戏内 `ChatInputMenu`，保留现有聊天、话题、物品和结束逻辑，只改善布局层次、消息气泡、NPC 资料栏和按钮比例。

**架构：** 继续使用 Stardew Valley 原生 `Game1.drawDialogueBox`、原生字体、NPC 肖像和 XNA `SpriteBatch`，不引入新的图片或 UI 框架。`ChatLayoutRules` 负责在不同分辨率下计算面板、对话区、资料栏、输入区和操作按钮的几何关系；`ChatInputMenu` 只负责按照这些矩形绘制，交互命中区域继续复用同一份布局。

**技术栈：** C# / .NET 6、MonoGame/XNA `Rectangle` 与 `SpriteBatch`、xUnit。

---

### 任务 1：锁定精修布局契约

**文件：**
- 修改：`smapi/ChatLayoutRules.cs`
- 测试：`smapi/tests/ChatLayoutRulesTests.cs`

- [x] **步骤 1：编写失败的测试**

增加以下行为断言：布局必须提供不与对话区重叠的 `ProfilePanel`；资料栏宽度在桌面分辨率下保持可读；底部输入框和四个按钮不重叠且输入框不小于 120 像素。

- [x] **步骤 2：运行测试验证失败**

运行：`dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore --filter FullyQualifiedName~ChatLayoutRulesTests`

预期：编译失败，提示 `ChatLayout` 尚未提供 `ProfilePanel`（这是预期红灯）。

- [x] **步骤 3：编写最少实现代码**

在 `ChatLayout` 增加 `ConversationArea` 与 `ProfilePanel`，将 `MessageArea` 保留为两者的总区域；布局计算在消息区右侧预留约 160 像素资料栏，并保持所有按钮的原有顺序和命中矩形。

- [x] **步骤 4：运行测试验证通过**

运行同一条 `dotnet test` 命令，预期 `ChatLayoutRulesTests` 全部通过。

### 任务 2：绘制原版增强视觉层

**文件：**
- 修改：`smapi/ChatInputMenu.cs`

- [x] **步骤 1：使用已通过的布局契约替换绘制分区**

消息区左侧绘制最近 8 条消息的原版风格气泡，NPC 消息使用浅紫灰背景，玩家消息使用浅蓝背景；空记录时显示现有提示文案。右侧资料栏绘制 NPC 肖像、姓名、关系阶段和好感度条，所有边框继续使用原版 `drawTextureBox`。

- [x] **步骤 2：保持现有交互行为**

`SendButton`、`TopicButton`、`InventoryButton`、`CloseButton` 仍使用 `ChatLayout` 的矩形；不修改消息发送、找话题、物品展示和结束回调，只更新按钮的文字布局和颜色。

- [x] **步骤 3：处理小窗口退化**

当消息区不足以容纳资料栏时隐藏资料栏并让对话区回收宽度；输入框至少保留 120 像素，按钮仍保持不重叠。

### 任务 3：验证与交付检查

**文件：**
- 检查：`smapi/ChatLayoutRules.cs`
- 检查：`smapi/ChatInputMenu.cs`
- 检查：`smapi/tests/ChatLayoutRulesTests.cs`

- [x] **步骤 1：运行全部 SMAPI 单元测试**

运行：`dotnet test E:/workspace/hub/.stardew-ai-verify/scratch/StardewAI.NPC.Scratch.Tests.csproj --no-restore`

- [x] **步骤 2：构建 Mod**

运行：`dotnet build E:/workspace/hub/.stardew-ai-verify/scratch/StardewAI.NPC.Scratch.csproj --no-restore`

- [x] **步骤 3：检查变更范围**

运行：`git diff --check` 与 `git status --short`，确认没有生成密钥、运行状态或无关构建产物，并保留工作树中已有的其他改动。
