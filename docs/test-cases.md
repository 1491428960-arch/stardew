# AI NPC 第一版固定回归清单

本页是 Task 8 的固定回归入口。它记录可自动验证的静态/接口证据，以及必须由用户在游戏内完成的 SMAPI 证据。回归脚本默认只读；除非用户显式传入 `-LaunchSmapi`，脚本不会启动游戏。

## 脚本静态验证目标

对 `scripts/run_smapi_regression.ps1` 运行 PowerShell AST 检查，必须同时满足：

1. 存在可覆盖的真实路径参数：游戏目录、SMAPI 启动入口、`AI-SVE-测试.json` profile 文件、Stardrop `Selected Mods` 目录、存档目录、SMAPI 日志和 Bridge 地址；默认值为 `C:\Users\Lenovo\AppData\Roaming\Stardrop\Data\Profiles\AI-SVE-测试.json`、`C:\Users\Lenovo\AppData\Roaming\Stardrop\Data\Selected Mods`，游戏入口为 `D:\sbeam\steamapps\common\Stardew Valley\StardewModdingAPI.exe`。这些是显式参数，不通过注册表或环境变量推导，并允许覆盖。
2. profile 文件使用 `Leaf` 检查，Selected Mods 和 Mods 根使用 `Container` 检查；它们、存档和日志只通过 `Test-Path`、`Get-Item`、`Get-ChildItem`、`Get-Content` 读取。脚本不得出现删除、覆盖、复制、移动、写文件或注册表调用。
3. 存档快照只记录相对文件名、大小、`LastWriteTimeUtc`；启动前和 SMAPI 结束后各记录一次，不读取存档内容。
4. 只有 `-LaunchSmapi` 明确传入时才调用 SMAPI 启动入口；只有 `-InspectLog` 明确传入时才读取日志，且启动前后快照仍然执行。
5. Bridge 关闭时必须输出可辨识的 `Bridge closed` 记录，并继续输出只读环境检查结果，不把 Bridge 关闭误判为游戏崩溃。
6. Bridge 在线且 local/cloud 两个 Provider 都失败时，必须记录 `local provider failed`、`cloud provider failed` 和 `fallback` 证据；缺少其中任一项时输出未观测，而不是伪造通过。
7. 默认路径检查失败时只告警并返回非零状态；不得为了让回归继续而创建 profile、存档目录或修改源 Mods 仓库。

## 固定回归用例

| 编号 | 场景 | 操作 | 通过证据 |
| --- | --- | --- | --- |
| R0 | 静态安全边界 | AST 检查脚本；运行 Bridge pytest、SMAPI `dotnet test`、显式 Windows `dotnet build` | 命令退出码为 0；AST 无禁用写入/注册表调用 |
| R1 | Bridge 与测试页 | 启动 `scripts/start_bridge.ps1`，打开 `http://127.0.0.1:5678/test`，选择 Rasmodia，发送固定问句 | `/health` 为 `ok`；测试页返回 `provider=fake` 且有回复 |
| R2 | API 契约 | 调用 `POST /api/dialogue/test`，分别使用 `provider=fake` 和不传 provider；调用 `GET /api/context/preview` | 返回结构包含 `reply`、`provider`、`fallback`、`latencyMs`、`warnings`；上下文含 SVE/娘化来源摘要 |
| R3 | Bridge 关闭回退 | 停止 Bridge 后启动游戏并按 `N` | SMAPI 原型不崩溃；C# 客户端记录 `offline`/`fallback`，游戏仍可继续操作 |
| R4 | Provider 双失败 | Bridge 配置 local/cloud 均启用但指向不可用地址，发送不指定 provider 的请求 | 回复来自 `fallback`；`warnings` 同时含两个 Provider 失败记录；不泄露 URL 中的凭据 |
| R5 | SMAPI 原型 | 确认 `AI-SVE-测试` profile 已由 Stardrop 选中，启动脚本并进入存档；按 `N` 与 Rasmodia 对话 | SMAPI 日志显示 mod 加载；出现 Rasmodia 对话菜单；Bridge 在线时显示 AI/fallback 回复 |
| R6 | SVE 与娘化兼容 | 在同一 profile 中保持 SVE 和娘化 NPC 内容包启用；分别打开 SVE NPC 与 Rasmodia 的资料预览/对话 | `sourceMods`/身份资料保留来源；NPC 不因显示名变化而丢失；上下文保护规则生效 |
| R7 | 存档安全 | 脚本运行前后对同一 `-SaveRoot` 生成快照；完成 R5/R6 后退出游戏并再次运行快照 | 控制台列出每个文件的大小和 UTC 时间戳变化；脚本不删除、不覆盖、不回滚存档，实际变化由用户判断 |
| R8 | 日志证据 | 用户明确传入 `-InspectLog -SmapiLogPath <实际日志>`，完成一次 R5 后退出游戏 | 只读输出 SMAPI 日志尾部及匹配的加载/Bridge/异常行；未传 `-InspectLog` 时不得自动读日志 |

## 推荐运行顺序

先执行 R0，再执行 R1～R4 的游戏外/Bridge 回归，最后由用户执行 R5～R8。示例：

```powershell
Set-Location E:\workspace\projects\stardew-ai-npc\.worktrees\ai-npc-bridge
pwsh -NoProfile -File .\scripts\run_smapi_regression.ps1
pwsh -NoProfile -File .\scripts\run_smapi_regression.ps1 -LaunchSmapi -InspectLog -SmapiLogPath <实际 SMAPI-latest.txt>
```

第二条命令会等待用户退出 SMAPI；运行前应确认游戏没有打开重要存档，并保留用户自己的备份。脚本不自动改存档，R5/R6 的“出现对话、兼容性和视觉结果”不能由 pytest 或静态脚本替代。
