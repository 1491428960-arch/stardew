# Stardew AI NPC

本项目用于探索 Stardew Valley AI NPC 集成方案。Python Bridge 位于
`bridge/`，当前提供可重复安装和测试的独立工程骨架。

当前开发状态、外部 Mod 目录差异和下一步接力顺序见
[`docs/handoff-2026-08-23.md`](docs/handoff-2026-08-23.md)。

## 开发环境

- Python 3.12
- FastAPI
- httpx
- uvicorn
- pytest
- pytest-asyncio

在项目根目录执行以下命令创建虚拟环境并安装开发依赖：

```powershell
Set-Location bridge
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

项目不提交密钥、用户数据、虚拟环境或构建产物。

## Task 8 运行与安全边界

启动 Bridge：

~~~powershell
.\scripts\start_bridge.ps1
~~~

默认监听 http://127.0.0.1:5678；测试页为 /test，健康检查为 /health，对话接口为 POST /api/dialogue/test。Provider 按 local → cloud → fallback 回退；Bridge 关闭、超时或两个 Provider 均失败时，SMAPI 客户端保持 offline/fallback，不阻断游戏。

SMAPI 原型默认按 F8 触发 Rasmodia 对话。安装 Generic Mod Config Menu（GMCM）后，可在游戏内配置 `DialogueKey`、`EnableDialogue`、`BridgeEndpoint` 和 `BridgeTimeoutSeconds`；未安装 GMCM 时配置页会安全跳过。配置仍可直接写入 `config.json`，非法快捷键、非本机回环地址和越界超时会回退到安全默认值。SVE 和娘化 NPC 资料通过 npcId、显示名和来源 mod 兼容，实际是否加载成功需用户在 AI-SVE-测试 profile 内进入游戏确认。回归脚本只读检查 profile、Mods、日志和存档元数据，记录运行前后存档大小/时间戳；默认不启动游戏、不删除或覆盖存档、不修改源 Mods 仓库、不写注册表。实际存档变化、SVE/娘化加载、游戏内对话和日志证据必须由用户亲自操作确认。

## 快速测试 profile

修改 C# 代码后，先运行毫秒级自动化测试：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley"
```

需要验证 F8、GMCM 或基础 NPC 菜单时，使用独立的快速测试目录：

```powershell
.\scripts\start_fast_test.ps1
```

验证法师娘化显示名和 `Wizard` 内部 ID 回退时：

```powershell
.\scripts\start_fast_test.ps1 -IncludeRasmodia
```

脚本默认只把当前构建产物同步到游戏目录下的 `Mods-AI-FastTest`，不启动游戏。需要启动时显式增加 `-Launch`，脚本通过 SMAPI 的 `--mods-path` 加载独立 Mod 目录，不依赖 Stardrop 当前启动 profile。它只复制 `StardewAI.NPC`、GMCM 和按需加入的 Rasmodia 内容包，不修改正式 `Mods`、Stardrop profile、注册表；启动后的存档选择仍需用户使用独立测试存档，脚本不提供存档目录隔离。

启动快速 profile：

```powershell
.\scripts\start_fast_test.ps1 -Launch
```

只检查同步结果、不启动游戏（默认行为，也可显式写 `-NoLaunch`）：

```powershell
.\scripts\start_fast_test.ps1 -NoLaunch
```

如果自动发现的 Mod 源目录不正确，可显式覆盖：

```powershell
.\scripts\start_fast_test.ps1 -SourceModsPath 'D:\sbeam\steamapps\common\Stardew Valley\Mods'
```

首次使用快速 profile 时，请在游戏内选择独立测试存档；完整 SVE、男角色娘化和法师娘化组合仍需在 `AI-SVE-测试` profile 中做最终回归。
