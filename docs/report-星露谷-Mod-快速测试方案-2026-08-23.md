# 星露谷 Mod 快速测试方案

日期：2026-08-23
研究问题：如何减少 StardewAI.NPC 修改后反复启动完整 SVE profile 的等待时间。

## 结论

最快的方案不是继续压缩完整 profile，而是分层测试：

1. 代码和对话服务逻辑：直接运行 C# 测试与 Bridge 测试页，不启动游戏。
2. 快捷键、GMCM、NPC 菜单：使用一个只包含必要 mod 的 SMAPI 快速 profile。
3. SVE NPC、娘化 NPC、真实游戏进程：只在最终回归时启动完整 `AI-SVE-测试` profile。

SMAPI 官方支持用 `--mods-path` 指定独立 mod 目录，专门适合测试和多套 mod 组合；Stardrop 也原生支持多个 profile。因此不需要每次都加载当前完整的 22 个代码 mod 和 8 个内容包。

## 判断依据

### 来源事实

- SMAPI 的 `--mods-path` 可以指定相对或绝对的 mod 目录；官方文档明确将它列为测试/多套 mod 组合的方式。
- Stardrop 支持多个 mod profile，可以按玩法或多人会话切换。
- SMAPI 官方 mod 测试流程仍要求最终在游戏内验证输入事件和菜单行为；这部分不能完全由游戏外测试替代。

### 本地观察

- 当前 Stardrop 并未使用游戏目录下的普通 `Mods`，SMAPI 日志显示实际目录是：
  `C:\Users\Lenovo\AppData\Roaming\Stardrop\Data\SELECT~1`
- 当前完整 profile 启动时加载了 22 个代码 mod 和 8 个内容包；SVE、SpaceCore、多个 Polyamory mod 会显著增加启动和资产重载时间。
- 当前项目的 Bridge 测试页位于 `http://127.0.0.1:5678/test`，不需要启动游戏。
- 当前 C# 回归测试为 23/23，通过配置、Bridge、NPC 名称回退等逻辑；这些测试不需要启动游戏。
- `StardewAI.NPC` 本身没有声明 SVE、Content Patcher 或其他硬依赖，快捷键和菜单烟测可以使用最小 mod 集合。
- 已实现 `scripts/start_fast_test.ps1`，支持独立 `Mods-AI-FastTest`、`-IncludeRasmodia`、默认不启动和显式 `-Launch`；离线安全测试为 37/37 通过。
- 当前构建输出不包含 `manifest.json`，启动器会从 `smapi/manifest.json` 一并复制，避免生成无效 Mod 目录。

## 建议

### P0：每次修改都跑的快速检查

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley"
```

需要验证 AI 回复和上下文时，启动 Bridge 后打开：

`http://127.0.0.1:5678/test`

这能覆盖配置归一化、Bridge 请求、历史记忆、上下文以及 provider 回退，但不能验证游戏按键和菜单。

### P1：使用“AI NPC 快速测试”profile

建议只放入：

- `StardewAI.NPC`
- `GenericModConfigMenu`
- `Console Commands`（可选，便于查看 SMAPI 状态）
- `Content Patcher`、`Cross-Mod Compatibility Tokens`（CMCT）和 `Romanceable Rasmodia`（验证 Rasmodia 时必须同时加入）

用独立的新测试存档，不要直接加载依赖 SVE/SpaceCore 的正式存档。快捷键烟测只需要进入一个普通存档，确认 F8 能打开对话菜单；不需要加载 SVE 全套地图和内容包。

项目已提供脚本；默认只同步、不启动游戏：

```powershell
.\scripts\start_fast_test.ps1
```

验证 Rasmodia 并启动游戏时运行：

```powershell
.\scripts\start_fast_test.ps1 -IncludeRasmodia -Launch
```

只同步不启动游戏时可显式增加 `-NoLaunch`。实际启动后仍需确认日志顶部的 `Mods go here` 指向 `Mods-AI-FastTest`，并选择独立测试存档；SMAPI `--mods-path` 只隔离 Mod 目录，不隔离 Stardew Valley 存档目录。

### P2：完整 profile 只做最终回归

以下情况才启动 `AI-SVE-测试`：

- SVE 新 NPC 是否能被识别；
- 男角色娘化、法师娘化内容是否改变了显示名/内部 ID；
- 游戏日期、季节、地点、友谊和事件上下文是否正确传入；
- 完整 mod 组合下是否存在键位冲突或 GMCM 冲突。

## 来源

- [SMAPI 技术文档：命令行参数与 `--mods-path`](https://github.com/Pathoschild/SMAPI/blob/develop/docs/technical/smapi.md)：支持独立 mod 目录、开发模式和测试用途。
- [SMAPI 官方测试与排错指南](https://stardewvalleywiki.com/Modding%3AModder_Guide/Test_and_Troubleshoot)：说明构建后仍需进行游戏内验证。
- [Stardrop 官方仓库](https://github.com/Floogen/Stardrop)：说明 Stardrop 支持多个 mod profile。
- [项目 README](../README.md)：记录 Bridge 测试页和当前项目测试边界。
- [项目测试用例](test-cases.md)：记录完整 profile 的最终回归范围。

## 证据

- 2026-08-23 本地 SMAPI 日志：当前完整 profile 启动时加载 22 个代码 mod、8 个内容包，并使用 Stardrop 的自定义 `SELECT~1` mod 路径。
- 2026-08-23 本地测试：`dotnet test ...` 通过 23/23。
- 2026-08-23 本地构建：SMAPI mod 构建 0 警告、0 错误。
- 2026-08-23 本地脚本测试：`test_start_fast_test.ps1` 通过 37/37 个离线场景，覆盖默认不启动、显式 Launch、带空格 `--mods-path`、等待退出、缺少 `windir` 的隔离环境及退出前恢复、路径拒绝、额外 Mod 排除、依赖 UniqueID、源 Junction 白名单、同名普通文件和目标 Junction 防护。
- 2026-08-23 本地真实路径检查：`start_fast_test.ps1 -IncludeRasmodia -NoLaunch` 自动发现 `C:\Users\Lenovo\AppData\Roaming\Stardrop\Data\Selected Mods`，生成 `D:\sbeam\steamapps\common\Stardew Valley\Mods-AI-FastTest`；目录包含 5 个项目，DLL SHA-256 为 `1512CAA0FD1D79BA60D35FEEB5B360AFA57B16EE4B27824D10FD2FBC63ED1322`。
- 2026-08-23 本地真实启动：SMAPI 从快速目录成功加载 4 个代码 Mod 和 1 个内容包，`Stardew AI NPC` 进入 ready 状态。正常关闭后日志出现 `ClosedGame`、`Disposing`，启动器释放进程句柄且未新增残留进程。

## 限制

- 已实测最小 profile 能启动到标题界面并正常退出；存档加载耗时仍会受磁盘、SMAPI 缓存和存档规模影响。
- `--mods-path` 是 SMAPI 官方支持的参数，但 Stardrop 仍可能在自己的 profile 管理流程中覆盖启动参数；使用 Stardrop 时应以启动日志顶部的 `Mods go here` 为准。
- 最小 profile 只能验证基础 NPC 和菜单流程，不能替代 SVE/娘化/完整 mod 组合的最终兼容性验证。
- 已实测脚本的离线同步、安全拒绝场景和真实路径同步；尚未在真实游戏进程中替用户完成 F8、GMCM 和独立存档烟测。
- 脚本默认不启动游戏；显式 `-Launch` 时仍需用户自行选择独立存档，不能把 `--mods-path` 误认为存档隔离机制。
