# Stardew AI NPC：输入法与引擎视觉预览阶段报告

日期：2026-08-25  
工作树：`story-memory`

## 结论

本轮完成两条基础能力：

1. 聊天输入框的键盘订阅改为可恢复的 lease 生命周期，避免菜单打开时抢占订阅、关闭后不归还，且不再每帧调用原版 `TextBox.Update()` 破坏中文输入焦点。
2. 新增可选的真实游戏视觉测试 harness。它会启动 FastTest profile、加载指定存档、等待渲染资源稳定，并使用 Stardew/MonoGame 自己的 `SpriteBatch`、字体、九宫格对话框、肖像和按钮生成 PNG 与 manifest。

## 输入法诊断与实现

当前版本链路为 Stardew Valley 1.6.15.24356、MonoGame 3.8.0.1641、SMAPI 4.5.2。MonoGame 的 SDL 文本输入会经由 `GameWindow.TextInput` 和 SMAPI `KeyboardDispatcher` 送到 `TextBox`；本项目没有再增加 Windows 专用 IME hook。

代码层面的修复是：

- 在 `SelectMe()` 之前建立 `KeyboardSubscriberLease`，记录并在菜单关闭时恢复原订阅者；
- 移除聊天菜单每帧对 `inputBox.Update()` 的调用，避免鼠标不在输入框时原版控件清空选中状态；
- 用单元测试覆盖 lease 的获取、恢复、重复释放和异常路径。

这证明了焦点/订阅生命周期不再被菜单破坏，但“微软拼音实际输入一段中文”的验收仍需要在游戏窗口中手动做一次；本报告不把自动化回归测试冒充成真实 IME 体验验收。

## 真实引擎预览

入口：`scripts/start_visual_test.ps1`。脚本会：

- 构建 Mod 并同步到 `D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest`；
- 启动 SMAPI，设置 `STARDEW_AI_NPC_VISUAL_*` 环境变量；
- 通过 `VisualTestHarness` 加载 `test_447101921`；
- 等待世界稳定后打开真实 `ChatInputMenu`，但只有在 `SaveLoaded` 已到达后才采集截图；
- 临时替换 `Game1.spriteBatch` 到独立 RenderTarget，重放同一个菜单，再恢复游戏批次；
- 写出 PNG、JSON manifest 和 `visual-test.done`，并验证 profile DLL 哈希一致。

### 最终产物

- [真实引擎聊天菜单截图](../artifacts/visual-tests/chat-empty-final-engine6/chat-empty.png)
- [截图 manifest](../artifacts/visual-tests/chat-empty-final-engine6/chat-empty.json)
- [离线素材快检 contact sheet](../artifacts/visual-tests/rasmodia-assets/contact-sheet.html)
- [离线素材 manifest](../artifacts/visual-tests/rasmodia-assets/manifest.json)

最终 manifest 记录：游戏 1.6.15、SMAPI 4.5.2、中文 locale、1280×720、`uiScale=1`、`zoom=1`，截图来源为 `isolated-game-spritebatch-render-target`。FastTest profile 与构建 DLL 的 SHA-256 均为：

```text
EF7A1E230E9F20F1CCB7BF9378984B4E5AA6C105B66BD9849E99A7F01E0DCD52
```

离线素材快检共发现 57 个资源：56 个 PNG、1 个实际为 lossless WebP 但扩展名为 `.png` 的文件。contact sheet 明确标注“素材快检，不等同于 Stardew Valley 最终渲染”，不能替代真实引擎截图。

## 验证记录

```text
dotnet test ...                         146 passed, 0 failed
VisualTestManifest/Rules focused tests  8 passed, 0 failed
python scripts/test_preview_assets.py   4 passed, 0 failed
test_start_visual_test.ps1              5 passed, 0 failed
真实 FastTest launcher                  VISUAL_TEST_DONE
```

SMAPI 日志确认加载了当前 harness，记录了 `视觉测试截图完成`，并记录测试 NPC 位置为 `tile=7,9`。启动器同时验证了 FastTest profile DLL 与 manifest 中的 `modDllSha256` 相等，因此截图不是旧 DLL 生成的。

## 当前边界

- 离线 contact sheet 只用于检查图片尺寸、格式和透明度；最终 UI 位置、字体、九宫格边框和肖像必须以真实引擎截图为准。
- 本轮不再处理床的交互键路径，也不处理由缺失 SVE 存档引起的红色禁止符号；这两项已按当前测试结论留置。
- 下一次手工验收只需在游戏聊天框中切换微软拼音输入中文，确认输入、退格、回车和再次打开菜单均正常。
