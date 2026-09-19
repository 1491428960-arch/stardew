# Stardew AI NPC 工作协议

## 主动推进协议

本项目采用“阶段确认 + 持续执行”模式。阶段性向用户确认只用于同步进度、验收当前阶段和暴露风险，不代表停止工作。

每次开始工作时：

1. 先读取 `docs/active-work.md`、相关 handoff 和当前 `git status`；
2. 从待办队列中选择当前最高优先级、风险可控的一项；
3. 先写测试或可验证的失败样例，再实现；
4. 完成一个子任务后，立即更新活动记录并继续下一项，不等待用户再次询问“接下来干什么”。

每次阶段汇报必须包含：

- 已完成什么；
- 用什么证据确认有效；
- 当前真实阻碍；
- 接下来正在做什么。

只有以下情况才允许暂停并等待用户：总目标已经完成、缺少无法自行取得的账号/Token、需要破坏性或外部发布操作，或存在会明显改变结果且无法自行判断的重大方案分歧。

不得把“构建成功”“单个测试通过”或“一个子任务完成”表述成整个目标完成，也不得在未达到停止条件时用“你现在不用做任何事”结束工作。


## 开发现场说明

- **本目录就是开发现场**：`story-memory` worktree（分支 `codex/story-memory`），一切实现改动只做在这里。主库 `E:\workspace\projects\stardew-ai-npc\` 的 `main` 分支落后且只含文档提交，不要在那边动实现。
- 每次开始工作前：先读 `docs/active-work.md`（权威工作日志，**最新条目在文件末尾**；历史条目顺序混杂，别只看开头）与 `git status --short --branch`（仓库被 `CodexSandboxOffline` 用户拥有，git 命令需加 `-c safe.directory=<本目录>`，严禁 `git config --global`）。
- **一键验证**：`pwsh -NoProfile -File scripts/verify_project.ps1`（SMAPI 测试 + Bridge 测试与 collect 探测 + `compileall` + `git diff --check`；会把并行工作线造成的 ImportError 报成 `ENV` 而不是本线 `FAIL`）。
- 当前状态与交接入口：**`.dsh/memory/current-state.md`（“当前值”的唯一权威源**——测试数、覆盖率等只维护在这一处，带取数时间戳）、`docs/overnight-report-2026-09-20.md`（当日工作与「醒来后的复核清单」）、`docs/handoff-group-dialogue-2026-09-20.md`（群聊线现状、五个视觉场景与十条坑）、`docs/next-steps-2026-09-20.md`（按 A/B/C 分档的可点单待办）。
- 本地服务端口记忆：Bridge 常驻 `127.0.0.1:5678`——**改完 Bridge 的 Python 代码必须重载该进程**，否则游戏与探针都在连旧代码（2026-09-19 因此白验过一次）；评测产物在 `artifacts/`；另一条工作线（气泡元素／回放页）可能同时在改 `bridge/` 下的页面文件，动它们之前先确认。

## 红线（一切操作的前提，违反即停止）

1. 不启动游戏（Stardew/SMAPI）——**游戏内验证需用户逐次授权**（走受控 `Mods-AI-FastTest` profile 与测试存档，见 `docs/handoff-group-dialogue-2026-09-20.md` 的视觉场景清单）；不部署 DLL 到正式 `Mods`、不修改正式存档或角色资料库。
2. 不读写、不输出任何 API Key / 凭据（含订阅认证字段、Token）；云端生成请求（Gemini／DeepSeek 等）需先经用户确认，并写到新的独立工件目录、不覆盖历史批次。
3. 不创建 Git commit——除非用户明确要求。
4. 不修改全局设置：`git config --global`、注册表、系统级环境变量一律不动。
5. 评测结论必须以真实运行输出为证据（`pytest` 退出码 / 工件计数），不得把「构建成功」或「单个测试通过」当作目标完成。
