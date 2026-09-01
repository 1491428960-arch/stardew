# 一键测试启动器设计

## 目标

让用户不需要手动输入 PowerShell 命令即可启动快速测试 profile。双击入口应自动复用已运行的 Bridge，必要时在后台启动 Bridge，再启动 `start_fast_test.ps1 -IncludeRasmodia -Launch`。

## 方案

- `scripts/start_ai_npc_test.cmd`：用户入口，只负责定位 PowerShell 7 并调用编排脚本。
- `scripts/start_ai_npc_test.ps1`：编排 Bridge 与快速 profile 生命周期。
- Bridge 只监听 `127.0.0.1:5678`；健康检查成功时复用现有进程，不重复启动。
- 若由编排脚本启动 Bridge，则游戏退出后在 `finally` 中停止该进程；原本已存在的 Bridge 不处理。
- Bridge 启动失败时不启动游戏，并输出可读错误；快速 profile 脚本的路径、依赖和存档安全边界保持不变。

## 错误处理与兼容性

- 优先使用 `bridge/.venv/Scripts/python.exe`，其次使用 PATH 中的 Python，最后探测 Codex bundled Python。
- 优先调用 PowerShell 7（`pwsh`），避免 Windows PowerShell 5.1 对 UTF-8 中文脚本的误解析。
- `.cmd` 不修改执行策略；仅通过 `-ExecutionPolicy Bypass` 作用于本次 PowerShell 进程。
- 启动器不删除存档、不修改正式 `Mods` 或 Stardrop profile。

## 验证

- 静态测试确认 `.cmd` 使用 PowerShell 7、编排脚本包含健康检查和子进程清理。
- 使用 PowerShell 7 解析两个脚本，验证 UTF-8 中文脚本可被正确解析。
- 完整 Bridge 测试与既有快速 profile 测试继续运行。
