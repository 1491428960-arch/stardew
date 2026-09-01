# Stardew AI NPC

本项目用于探索 Stardew Valley AI NPC 集成方案。Python Bridge 位于
`bridge/`，当前提供可重复安装和测试的独立工程骨架。

当前开发状态、外部 Mod 目录差异和下一步接力顺序见
[`docs/handoff-2026-08-23.md`](docs/handoff-2026-08-23.md)。

当前 `codex/story-memory` 已将原型入口迁移为原生风格聊天流程：面对面互动先由
Stardew Valley 显示原版寒暄，关闭后可选择「继续聊聊」；`F8` 与面对面续聊共用
`ChatInputMenu`。菜单使用原版 `DialogueBox`、`TextBox`、头像和 `InventoryMenu`，
支持中文 Enter 发送、连续对话、NPC 主动找话题，以及背包物品的展示、分享和确认赠送。
Smartphone 不属于当前方案；物品预览不扣背包，确认赠送才调用原版 NPC 收礼入口。

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

默认监听 http://127.0.0.1:5678；测试页为 /test，健康检查为 /health，对话接口为 POST /api/dialogue/test。Provider 按 local → cloud → fallback 回退；Bridge 关闭、超时或两个 Provider 均失败时，SMAPI 客户端保持 offline/fallback，不阻断游戏，界面只显示「暂时联系不上她，可以重试或结束」。

### 外部对话实验室

启动 Bridge 后打开 `http://127.0.0.1:5678/test`，即可在浏览器中使用本地对话实验室：左侧编辑 NPC、来源 Mod、关系阶段、时间地点和好感度，中间进行连续多轮聊天，右侧查看 Provider、延迟、fallback、上下文摘要和脱敏请求。页面支持“主动找话题”、中文 Enter 发送、Shift+Enter 换行、清空会话和导出 JSON。

当前页面和已配置云端的 Bridge 请求默认使用“云端（显式，当前配置）”；“自动”模式需手动选择，使用现有 local → cloud → fallback 路由；云端显式模式只调用配置的云端 Provider，不经过本地模型；“Fake 演示”才显式使用 FakeProvider，并始终标注“非真实 AI”。会话通过同源 Bridge API 保存到本机 JSON 文件，默认路径为 `%TEMP%\StardewAI.NPC\dialogue-lab-session.json`，因此刷新页面或重启 Bridge 后仍可恢复；可用 `BRIDGE_DIALOGUE_SESSION_PATH` 覆盖路径。它不写入浏览器 `localStorage`、游戏存档，也不上传数据。持久化内容仅包括消息、对话历史和脱敏诊断，不包含 API key、Token、完整 prompt 或原始请求 payload。

云端评测和网页显式云端模式会自动读取项目根目录下的 `.env.local`，同时保留“进程环境变量优先”的临时覆盖方式。这个文件已被 `.gitignore` 忽略，只需在本机配置一次，不会写入仓库。内容示例：

```dotenv
BRIDGE_CLOUD_URL=https://api.openai.com/v1/chat/completions
BRIDGE_CLOUD_MODEL=gpt-5.6-terra
BRIDGE_CLOUD_API_KEY=在这里填你新建的key
BRIDGE_CLOUD_ENABLED=false
```

Bridge 每次启动和质量评测脚本每次启动都会自动加载这个文件；修改后重启 Bridge 即可。固定质量评测可显式选择云端：

```powershell
python scripts/run_character_quality_eval.py --provider cloud
```

`BRIDGE_CLOUD_ENABLED=false` 时自动模式不会把云端当作降级候选，但网页选择“云端（显式，当前配置）”仍会直接调用它；如需启用自动降级，再改为 `true`。评测结果会写入 `artifacts/character-quality-eval/`，只保存脱敏结果。

### 本机 Ollama

Bridge 启动脚本默认连接项目已验证的隔离 Ollama（`127.0.0.1:11435`、`qwen3.5:9b`），并优先加载已解析的中文联合资料索引 `data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json`。如需切换地址、模型、接口模式或资料索引，可在启动前覆盖进程环境变量：

```powershell
$env:BRIDGE_LOCAL_URL = "http://127.0.0.1:11435/api/chat"
$env:BRIDGE_LOCAL_MODEL = "qwen3.5:9b"
$env:BRIDGE_LOCAL_API_MODE = "ollama"
$env:BRIDGE_LOCAL_TIMEOUT = "15"
$env:BRIDGE_PROFILE_INDEX = "data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json"
```

原生模式固定发送 `stream=false` 和 `think=false`，避免 Qwen3/DeepSeek 的思考内容泄漏或 OpenAI 兼容接口返回空文本。保留 OpenAI-compatible 模式时不要设置 `BRIDGE_LOCAL_API_MODE=ollama`。

本机测试使用隔离 Ollama 服务（`OLLAMA_HOST=127.0.0.1:11435`、模型目录 `D:\OllamaModels`），已验证 `qwen3.5:4b` 与 `qwen3.5:9b`。游戏内性能诊断仅在 FastTest profile 的 Mod `config.json` 临时设置 `EnablePerformanceDiagnostics=true` 时启用，普通运行默认关闭；日志会每 5 秒输出一条 `[StardewAI.Perf]` 窗口。

模型比较使用项目真实的 Rasmodia 上下文和关系阶段用例：

```powershell
$env:PYTHONPATH = "bridge/src"
python scripts/benchmark_local_models.py --model qwen3.5:4b qwen3.5:9b
```

结果写入 `artifacts/model-benchmark-*.json`，包含每条原文回复、延迟、错误和轻量规则评分；评分不能替代人工角色一致性复核。

对话请求的 `intent` 支持 `chat`、`topic`、`item`；物品互动的 `itemContext` 只允许物品 ID、显示名、类别、品质、动作和原版偏好结果。旧请求省略这些字段时仍按普通聊天处理。

当前 `codex/story-memory` 工作树还包含故事状态基础层：版本化记忆记录、知识范围、关系进度和有效互动门槛。它目前只提供纯 C# 模型、校验和序列化，不会修改原版剧情、NPC 日程或现有 UI；接入游戏事件和存档生命周期前不会影响正式游戏行为。

### 离线资料索引

`scripts/build_profile_index.py` 可把 `data/personas/` 与明确指定的 Mod 资产目录整理为派生索引，分开保存人设覆盖、对白风格证据和剧情候选来源。索引器同时扫描对白文件和 Content Patcher 的 `content.json`，兼容注释、尾逗号及常见单引号字符串；从 `EditData -> Characters/Dialogue/<npcId>` 发现的新 NPC 会生成可追溯来源的资料骨架。对白中的 `{{i18n:...}}` 只保留引用键，不自动把对白当作已确认剧情事实。索引器只读输入 Mod，不修改游戏目录，也不会把用户绝对路径写入索引。

```powershell
$env:PYTHONPATH = (Join-Path (git rev-parse --show-toplevel) 'bridge\src')
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/build_profile_index.py `
  --persona-dir data/personas `
  --mod-root '<已安装 Mod 目录>' `
  --output data/generated/profile-index.json
```

Bridge 启动时按 `BRIDGE_PROFILE_INDEX` 读取资料索引；相对路径相对于项目根目录解析。快速启动脚本在文件存在时默认选择已解析的中文联合索引，未找到时回退到 `data/generated/profile-index.json`。运行时按当前 NPC、来源 Mod、关系阶段和已完成事件只取有限的风格证据与剧情候选；文件缺失或损坏时安全跳过，不影响原有对话。代表角色资料还提供 `voiceStyle`、分阶段 `stageProfiles` 和 `knowledgeRules`：上下文只选择当前心级／婚姻／孩子状态对应的一个阶段，不把全部阶段倾倒给模型。尚未手工细化的 NPC 会获得保守默认层，明确要求不编造剧情，后续可用角色专属资料覆盖。运行时的原版心级、婚姻、孩子和已完成事件标记由 SMAPI 只读采集，并随本 Mod 的故事状态在读档/保存生命周期中安全恢复；仍需在真实存档中核对事件与角色覆盖。

Bridge 返回正式回复后，面对面入口会把一条带日期、参与者、来源和知识范围的短记忆写入故事状态，并在后续对话中只回送当前 NPC 最近几条记忆；fallback、缺少游戏日期和空消息不会写入。记忆按稳定指纹去重并保留最近 200 条，阶段进度仍按原版心级和每天最多一次有效互动计算。

SMAPI 默认按 F8 打开 Rasmodia/Wizard 目标的聊天菜单。安装 Generic Mod Config Menu（GMCM）后，可在游戏内配置 `DialogueKey`、`EnableDialogue`、`BridgeEndpoint` 和 `BridgeTimeoutSeconds`；未安装 GMCM 时配置页会安全跳过。配置仍可直接写入 `config.json`，非法快捷键、非本机回环地址和越界超时会回退到安全默认值。SVE 和娘化 NPC 资料通过 npcId、显示名和来源 mod 兼容，实际是否加载成功需用户在 AI-SVE-测试 profile 内进入游戏确认。回归脚本只读检查 profile、Mods、日志和存档元数据，记录运行前后存档大小/时间戳；默认不启动游戏、不删除或覆盖存档、不修改源 Mods 仓库、不写注册表。实际存档变化、SVE/娘化加载、原版寒暄后的续聊、物品赠送和日志证据必须由用户亲自操作确认。

## 快速测试 profile

修改 C# 代码后，先运行毫秒级自动化测试：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" /p:EnableModDeploy=false /p:EnableModZip=false /p:BundleExtraAssemblies=Game
```

需要验证 F8、GMCM 或基础 NPC 菜单时，使用独立的快速测试目录：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_fast_test.ps1
```

验证法师娘化显示名和 `Wizard` 内部 ID 回退时：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_fast_test.ps1 -IncludeRasmodia
```

脚本默认只把当前构建产物同步到游戏目录下的 `Mods-AI-FastTest`，不启动游戏。需要启动时显式增加 `-Launch`，脚本通过 SMAPI 的 `--mods-path` 加载独立 Mod 目录，不依赖 Stardrop 当前启动 profile。基础模式只复制 `StardewAI.NPC` 和 GMCM；`-IncludeRasmodia` 会同时加入 Rasmodia 内容包及其必需的 Content Patcher、Cross-Mod Compatibility Tokens（CMCT）。脚本不修改正式 `Mods`、Stardrop profile、注册表；启动后的存档选择仍需用户使用独立测试存档，脚本不提供存档目录隔离。

显式启动后，脚本会等待 SMAPI 退出并释放进程句柄。若 Codex 等隔离环境缺少 `windir`，脚本会在本次启动期间从 `SystemRoot` 临时补回，并在退出前恢复原状态，不修改全局环境。

启动快速 profile：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_fast_test.ps1 -Launch
```

只检查同步结果、不启动游戏（默认行为，也可显式写 `-NoLaunch`）：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_fast_test.ps1 -NoLaunch
```

如果自动发现的 Mod 源目录不正确，可显式覆盖：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_fast_test.ps1 -SourceModsPath 'D:\sbeam\steamapps\common\Stardew Valley\Mods'
```

快速测试脚本包含 UTF-8 中文提示，优先使用 PowerShell 7（`pwsh`）运行；Windows PowerShell 5.1 可能按本机代码页误解析脚本。`-ExecutionPolicy Bypass` 只对本次进程生效，不修改系统策略。

首次使用快速 profile 时，请在游戏内选择独立测试存档；完整 SVE、男角色娘化和法师娘化组合仍需在 `AI-SVE-测试` profile 中做最终回归。

### 推荐：一键启动

不想手动打开终端时，直接双击：

```text
scripts\start_ai_npc_test.cmd
```

它会优先复用已经运行的 Bridge；Bridge 未运行时自动后台启动，随后同步并启动包含 Rasmodia 的快速测试 profile。游戏退出后只清理它自己启动的 Bridge，不会停止你原本已经打开的 Bridge。该入口使用 PowerShell 7，并不会修改系统执行策略。
