# NPC 资料条与快速测试启动设计

## 目标

解决本次实机反馈中的三个问题：

1. 明确使用带 Rasmodia、Content Patcher 和 Bridge 的一键启动入口，避免测试 profile 回退到原版男巫头像；
2. 将聊天窗口右侧的竖向头像卡改为紧凑横向资料条，减少空白并改善信息层级；
3. 使用项目已有的 `VisualTestHarness` 和 `scripts/start_visual_test.ps1` 生成真实游戏引擎截图，不依赖浏览器 mock 作为最终判断。

## 根因与范围

- `scripts/start_fast_test.ps1` 只有显式传入 `-IncludeRasmodia` 才会同步 Content Patcher、CMCT 和 Rasmodia；它适合作为底层 profile 同步脚本，不作为日常一键入口。
- `scripts/start_ai_npc_test.ps1` 默认包含 Rasmodia，并在 `-Launch` 时检查或启动 `127.0.0.1:5678` Bridge。本次不重复实现 Bridge 管理，只修正文档/验收入口，必要时为启动参数增加回归测试。
- `ChatInputMenu.DrawProfile` 当前绘制一个贯穿消息区高度的窄竖卡，造成头像、名称和好感度之间留白过大。改动限定在布局几何和资料条绘制，不改消息、输入法或 Bridge 协议。

## UI 方案

资料卡在支持资料区的窗口中改为右侧横向资料条：

- `ProfilePanel` 使用约 280 px 宽、约 112 px 高；仍与左侧 `ConversationArea` 不相交；
- 头像使用运行时 `npc.Portrait` 的 64×64 帧，外加轻量原版风格边框；
- 名称放在头像右侧第一行，好感度放在第二行；
- 好感度条只在有数值时显示，未知时不绘制空进度条；
- 极窄窗口继续隐藏资料条，避免挤压输入框和动作按钮；
- 不新增 PNG、字体或外部 UI 框架，继续使用游戏真实 `SpriteBatch`、字体和贴图。

## 启动与预览验收

日常手动验收只使用：

```powershell
pwsh -NoProfile -File scripts/start_ai_npc_test.ps1 `
  -GamePath 'D:\sbeam\steamapps\common\Stardew Valley' `
  -FastModsPath 'D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest' `
  -Launch
```

视觉回归继续使用 `scripts/start_visual_test.ps1`，输出到新的唯一目录。manifest 必须记录截图来源和 Mod DLL SHA256；源 DLL、FastTest DLL、manifest 三方哈希必须一致。

## 测试策略

实现前先增加失败测试：

1. 桌面布局的资料条宽高满足横向卡约束；
2. 资料条与对话区不相交；
3. 极窄窗口仍隐藏资料条并保持输入框/按钮不重叠；
4. 未知好感度不要求绘制进度条；
5. 启动器源码测试确认默认路径包含 `-IncludeRasmodia`、Bridge 健康检查和 `-Launch` 传递。

绿灯后运行完整 C# / PowerShell / Bridge 测试，再用真实引擎生成 `chat-profile-strip` 截图，人工检查头像、名称、好感度和横向间距。

## 非目标

- 不在本轮接入真实云端 AI 或修改 Provider 路由；
- 不改变 NPC 位置、房屋入口、IME 生命周期和聊天记录逻辑；
- 不把离线 contact sheet 当作最终 UI 证据。
