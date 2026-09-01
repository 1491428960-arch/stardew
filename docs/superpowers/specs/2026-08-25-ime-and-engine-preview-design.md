# 输入法兼容与真实引擎预览设计

日期：2026-08-25  
状态：待用户审阅  
范围：`smapi` 聊天输入、FastTest 自动截图、离线资源快检

## 1. 背景与目标

用户希望：

1. 在游戏内聊天菜单中稳定使用中文输入法；
2. 不必手动操作游戏，也能判断新增 UI/美术资源在玩家实际画面中的效果。

此前的网页 UI 样稿与游戏实际效果差异很大，因此网页 mock 不再作为视觉正确性的依据。

目标是建立“真实游戏引擎截图为主、离线素材检查为辅”的工作流，同时修复当前输入框的焦点生命周期问题。

非目标：本阶段不改原版床交互、不处理已确认与缺失 SVE 存档有关且不影响游玩的红色禁止符号、不实现独立的完整游戏渲染器。

## 2. 已确认事实

### 2.1 输入链路

- 当前 `ChatInputMenu` 创建 `TextBox` 后先调用 `SelectMe()`，再保存 `Game1.keyboardDispatcher.Subscriber`。本机 Stardew Valley 1.6.15.24356 的 IL 表明 `SelectMe()` 会立即把订阅者设为该 `TextBox`，所以保存下来的“旧订阅者”其实是自己，关闭时无法正确恢复。
- 当前 `update()` 每帧调用 `inputBox.Update()`。本机 IL 表明该方法会按鼠标是否位于输入框改变 `Selected`，鼠标移出输入框时可能取消订阅。原版菜单主要在点击时调用 `TextBox.Update()`，不是每帧调用。
- `KeyboardDispatcher` 通过 MonoGame `GameWindow.TextInput` 分发已提交字符；`TextBox` 只在 `Selected` 时逐字符接收。MonoGame 3.8 没有把 SDL 的 `SDL_TEXTEDITING` 预编辑串绘制到 `TextBox`，因此候选词窗位置仍由 Windows/输入法和游戏窗口处理，Mod 不应自行伪造候选窗。
- 本机实际版本是 Stardew Valley 1.6.15.24356、MonoGame 3.8.0.1641、SMAPI 4.5.2；不能把先前交接文档中的 SMAPI 4.2.2 当作当前运行时证据。

### 2.2 渲染与资源

- 工作树本身没有 PNG/XNB/TMX 等独立美术资源；当前 UI 使用运行时 `LooseSprites\\textBox`、`Game1.smallFont`、`Game1.dialogueFont`、`Game1.drawDialogueBox`、`drawTextureBox` 以及 NPC `Portrait`。
- Content Patcher 会根据 token 和当前上下文修改 `Portraits/Wizard`、`Characters/Wizard` 等资源，直接打开某张原 PNG 不能证明运行时最终素材正确。
- 原生菜单处于 UI mode，官方建议按 `Game1.uiViewport` 和 UI scale/zoom 变换处理坐标；当前代码使用 `Game1.viewport`，需要在实现截图 harness 时覆盖非 100% UI scale 的验证。
- StardewXnbHack 可把 XNB 解包为 PNG/TMX/JSON；Content Patcher 的 `patch export` 可导出当前上下文中补丁应用后的资源。这些适合作为离线快检，但不能替代真实引擎截图。

## 3. 总体方案

采用两层工作流，真实引擎为主：

### A. VisualTestHarness（主路径）

新增一个测试专用 SMAPI mod/入口，在 FastTest profile 中自动完成：

1. 启动 SMAPI 和指定测试存档；
2. 等待游戏进入稳定场景；
3. 由 harness 构造固定地点、NPC、聊天菜单和代表性消息状态；
4. 按场景编号截图到确定的输出目录；
5. 退出游戏并输出截图清单、运行时版本、mod DLL SHA256；
6. 对基准图执行尺寸、像素差或人工审阅门禁。

截图必须使用游戏自己的字体、XNB、Content Patcher 结果、viewport/UI scale 和本地化环境。网页只展示截图结果，不模拟最终 UI。

### B. OfflineAssetPreview（辅路径）

提供一个不启动游戏的快速检查器：

- 读取指定 PNG 或 `StardewXnbHack`/Content Patcher 导出目录；
- 生成接触表，显示实际像素尺寸、透明边界、非透明包围盒、裁切帧和文件哈希；
- 对头像、精灵、图标执行尺寸/透明度/空白边缘 lint；
- 明确标记为“素材快检”，不声称等同于游戏最终画面。

### C. 浏览器视觉伴侣

浏览器页面只负责展示 A 的接触表和 B 的真实引擎截图、标注差异与验收状态。它不再绘制 Stardew 风格的替代 UI，也不作为像素保真依据。

## 4. 输入法实现设计

### 4.1 第一阶段：修复焦点与订阅生命周期

- 在调用 `SelectMe()` 之前保存旧 `Subscriber`；
- 删除每帧 `inputBox.Update()`，改为只在输入框点击/恢复焦点时更新选择状态；
- `Close`、`cleanupBeforeExit`、物品选择器和赠送确认对话框统一走幂等的订阅恢复方法；
- 恢复时只在当前订阅者仍是本菜单输入框时写回旧订阅者，避免覆盖其他菜单的订阅者。

### 4.2 第二阶段：字符提交与 IME 回归

不自行实现 Windows IME 候选窗。沿用游戏的 `KeyboardDispatcher`/MonoGame `TextInput` 链路，补充：

- 中英文、中文标点、退格、光标移动、Enter、Escape 的自动化可测逻辑；
- 游戏内手工回归矩阵：微软拼音/搜狗（若已安装）英文、中文、候选词提交、鼠标移出输入框后继续输入、切换物品选择器后恢复输入；
- 日志只记录输入兼容性诊断，不记录用户实际聊天内容。

如果实测发现某个输入法的预编辑串无法进入游戏，优先提供剪贴板粘贴作为降级路径，并记录具体运行时/输入法版本；只有证据表明需要原生窗口 API 时才另行设计 Windows 专用桥接。

## 5. TDD 验收矩阵

### 输入法

先写失败测试，再实现：

- 构造菜单时旧 `Subscriber` 保存正确，关闭后恢复原对象；
- `update()` 不会因为鼠标离开输入框清除当前订阅；
- Suspend/Resume/Close 重复调用不抛异常、不覆盖外部订阅者；
- 文本提交保留 Unicode BMP 中文字符、中文标点和空格；
- Enter 只触发一次发送，发送期间不重复提交。

真实游戏验收记录：运行时版本、输入法名称、输入序列、截图、SMAPI 日志摘要。

### 真实渲染截图

- harness 能在干净 FastTest profile 中自动启动、等待、截图、退出；
- 输出包含固定命名的场景：空聊天、长中文消息、多轮消息、头像/关系栏、非 100% UI scale；
- 每张截图旁有运行时 manifest：DLL SHA256、游戏版本、语言、分辨率、UI scale、场景 ID；
- 缺少游戏或无法启动时测试明确失败，不退化成 HTML mock 通过；
- 基准图比较先采用尺寸和结构化人工审阅，像素 diff 在基准稳定后启用，避免把字体抗锯齿噪声误判为功能回归。

### 离线资源快检

- 对输入目录生成稳定排序的接触表；
- 透明边界和帧尺寸计算有单元测试；
- 输入目录缺失、文件哈希变化或资源为空时返回非零退出码；
- 报告明确写出“不是游戏最终渲染结果”。

## 6. 分阶段交付

1. 先为 `ChatInputMenu` 的焦点/订阅生命周期补测试，看到 RED 后实现并运行 C# 测试。
2. 在 FastTest profile 中加入真实引擎截图 harness 的最小场景，只覆盖一张可重复截图；确认能自动启动、截图、退出和记录 DLL 哈希。
3. 扩展场景矩阵与 UI scale/locale 覆盖，加入基准图门禁。
4. 最后实现离线素材接触表和 lint，并在浏览器中展示两类结果。

每阶段都必须验证“实际加载的是新 DLL”，不能只报告编译成功。

## 7. 参考资料

- MonoGame `SDLGamePlatform`：<https://github.com/MonoGame/MonoGame/blob/v3.8/MonoGame.Framework/Platform/SDL/SDLGamePlatform.cs>
- MonoGame `GameWindow`：<https://docs.monogame.net/api/Microsoft.Xna.Framework.GameWindow.html>
- SDL 文本输入事件：<https://wiki.libsdl.org/SDL2/SDL_TextInputEvent>
- SDL 预编辑事件：<https://wiki.libsdl.org/SDL2/SDL_TextEditingEvent>
- Stardew UI/viewport 基础：<https://stardewvalleywiki.com/Modding:Modder_Guide/Game_Fundamentals>
- StardewXnbHack：<https://github.com/Pathoschild/StardewXnbHack>
- Content Patcher 导出：<https://github.com/Pathoschild/StardewMods/blob/develop/ContentPatcher/docs/author-guide/troubleshooting.md#export>

## 8. 待审阅问题

请确认这份规格是否同意：

- 真实引擎自动截图是最终视觉验收标准；
- 离线接触表只用于快速筛查；
- IME 第一阶段先修复现有 `TextBox` 焦点/订阅生命周期，不直接引入 Windows 原生 IME 桥接；
- 先做最小一张真实引擎截图，再扩展完整场景矩阵。
