# Stardew AI NPC

本项目用于探索 Stardew Valley AI NPC 集成方案。Python Bridge 位于
`bridge/`，当前提供可重复安装和测试的独立工程骨架。

当前开发状态、下一步与交接入口见
[`docs/active-work.md`](docs/active-work.md)（**最新条目在文件末尾**）、
[`docs/handoff-group-dialogue-2026-09-20.md`](docs/handoff-group-dialogue-2026-09-20.md) 与
[`docs/overnight-report-2026-09-20.md`](docs/overnight-report-2026-09-20.md)。

当前 `codex/story-memory` 已将原型入口迁移为原生风格聊天流程：面对面互动先由
Stardew Valley 显示原版寒暄，关闭后可选择「继续聊聊」；`F8` 与面对面续聊共用
`ChatInputMenu`。菜单使用原版 `DialogueBox`、`TextBox`、头像和 `InventoryMenu`，
支持中文 Enter 发送、连续对话、NPC 主动找话题，以及背包物品的展示、分享和确认赠送。
Smartphone 不属于当前方案；物品预览不扣背包，确认赠送才调用原版 NPC 收礼入口。

## 开发环境

- Python **3.10+**（本机为 3.10.8，装在 `%LOCALAPPDATA%\Programs\Python\Python310\`）。注意：**本机的 3.10 没有注册到 `py` launcher，所以 `py -3.10` 在任何会话都会报 `No Installed Pythons Found!`**（早先写的“只在 SYSTEM 会话不可用”不准确）；请直接用绝对路径 `"$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"`，详见 `.dsh/memory/commands.md` 开头那条
  `C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe`
- Bridge 依赖：FastAPI、httpx、uvicorn、pytest、pytest-asyncio

**不要求虚拟环境**：`scripts/start_bridge.ps1` 会按 `bridge\.venv` → 本机 Python 3.10 → `PATH` 的顺序自动探测解释器。

跑测试（推荐一键验证，它把 SMAPI 测试、Bridge 测试、语法编译、工作树检查都串好了）：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_project.ps1
```

只跑 Bridge 时：

```powershell
$env:PYTHONPATH='bridge/src;scripts'
$py = "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"    # 本机 & $py 不可用，见上文 Python 那条
& $py -B -m pytest bridge/tests -q -p no:cacheprovider
```

项目不提交密钥、用户数据、虚拟环境或构建产物。

## Task 8 运行与安全边界

启动 Bridge：

~~~powershell
.\scripts\start_bridge.ps1
~~~

默认监听 http://127.0.0.1:5678；测试页为 /test，健康检查为 /health，对话接口为 POST /api/dialogue/test。云端 provider 当前是 **DeepSeek 官方 API**（`/health` 会报 `provider=cloud`）；云端关闭、超时、429 或其他失败时只进入安全 fallback，**不静默切回本地模型**。本地 Qwen 保留为显式 `provider=local` 的手动 A/B 与回滚入口。Bridge 关闭或上游失败时，SMAPI 客户端保持 offline/fallback，不阻断游戏，界面只显示「暂时联系不上她，可以重试或结束」。（历史：早期曾以 Gemini 官方 API 为目标，受区域限制阻塞，相关调研见 `docs/report-gemini-*.md`，已不适用。）

### 外部对话实验室

启动 Bridge 后打开 `http://127.0.0.1:5678/test`，即可在浏览器中使用本地对话实验室：左侧编辑 NPC、来源 Mod、关系阶段、时间地点和好感度，中间进行连续多轮聊天，右侧查看 Provider、延迟、fallback、上下文摘要和脱敏请求。页面支持“主动找话题”、中文 Enter 发送、Shift+Enter 换行、清空会话和导出 JSON。

网页测试页（`/test`）与群聊实验台（`/test/group`）的 Provider 选项文案**目前都仍写作“Gemini 云端（正式运行，默认）”——那是历史文案，没有随 provider 更换而更新**；实际后端走的是 **DeepSeek 官方 API**（见上文说明）。“自动”模式同样只走云端，失败时安全兜底、**不静默切回 Qwen**；“Qwen 本地（手动 A/B / 回滚）”才会显式调用本机模型；“Fake 演示”才显式使用 FakeProvider，并始终标注“非真实 AI”。会话通过同源 Bridge API 保存到本机 JSON 文件，默认路径为 `%TEMP%\StardewAI.NPC\dialogue-lab-session.json`，因此刷新页面或重启 Bridge 后仍可恢复；可用 `BRIDGE_DIALOGUE_SESSION_PATH` 覆盖路径。它不写入浏览器 `localStorage`、游戏存档，也不上传数据。持久化内容仅包括消息、对话历史和脱敏诊断，不包含 API key、Token、完整 prompt 或原始请求 payload。

云端评测和网页显式云端模式会自动读取项目根目录下的 `.env.local`，同时保留“进程环境变量优先”的临时覆盖方式。这个文件已被 `.gitignore` 忽略，只需在本机配置一次，不会写入仓库。

字段如下（值按你实际使用的服务填写；**当前部署使用的是 DeepSeek 官方 API**，此前为 Gemini 的配置已不适用）：

```dotenv
BRIDGE_CLOUD_URL=<你的服务商的 chat/completions 端点>
BRIDGE_CLOUD_MODEL=<模型名>
BRIDGE_CLOUD_API_KEY=<在这里填你的 key>
BRIDGE_CLOUD_ENABLED=true
BRIDGE_CLOUD_ONLY=true
BRIDGE_CLOUD_TIMEOUT=45
```

Bridge 每次启动和质量评测脚本每次启动都会自动加载这个文件；修改后**重启 Bridge** 即可（运行中的进程不会热加载）。固定质量评测可显式选择云端：

```powershell
& $py scripts/run_character_quality_eval.py --provider cloud
```

`BRIDGE_CLOUD_ONLY=true` 时，未指定 Provider 与 `auto` 都只调用云端；云端失败后只使用安全 fallback，**不静默切回本地模型**。网页显式选择“Qwen 本地（手动 A/B / 回滚）”或请求传入 `provider=local` 才会调用本地 Qwen。评测结果会写入 `artifacts/character-quality-eval/`，只保存脱敏结果。

#### Vertex AI 认证模式（Google Cloud 路线，**当前未启用**）

> 说明（2026-09-20 补）：这是为「账号不能直接使用 AI Studio API Key」准备的**备选路线**；当前云端走 DeepSeek 官方 API，本节保留作备选方案参考，示例中的模型名随 Vertex 上的可用模型而定。

当账号不能直接使用 AI Studio API Key 时，可以把云端 Provider 切到 Vertex AI 的 OpenAI-compatible 端点。Bridge 不要求把 service account JSON、access token 或任何凭据写进项目：它只读取本机 ADC 文件，并在进程内按需刷新短期 token（不写日志、不进异常消息、不落评测工件）。

```dotenv
BRIDGE_CLOUD_API_MODE=vertex
BRIDGE_CLOUD_VERTEX_PROJECT=你的-project-id
BRIDGE_CLOUD_VERTEX_LOCATION=global
BRIDGE_CLOUD_MODEL=gemini-3.7-flash
BRIDGE_CLOUD_ENABLED=true
BRIDGE_CLOUD_ONLY=true
BRIDGE_CLOUD_TIMEOUT=45
```

前置条件：Cloud project 已启用 Vertex AI API 并已关联 billing，本机已执行 `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/cloud-platform`。ADC 路径按 `BRIDGE_CLOUD_VERTEX_CREDENTIALS` → `GOOGLE_APPLICATION_CREDENTIALS` → `%APPDATA%\gcloud\application_default_credentials.json` 顺序解析，可用 `BRIDGE_CLOUD_VERTEX_CREDENTIALS` 指向自定义位置。省略 `BRIDGE_CLOUD_VERTEX_LOCATION` 时默认 `global`；显式设置 `BRIDGE_CLOUD_URL` 仍会覆盖自动拼接的端点。凭据缺失、刷新失败、凭据类型不受支持或端点不是 https，都只产生不含 token 的 `ProviderError` 并进入安全 fallback，不会静默切回 Qwen。

`/health=200`、ADC 能取到 token 都不能单独证明对话成功；真实验收仍要求一次最小请求同时满足云端 Provider、`fallback=false`、回复非空且带 usage。

### 本机 Ollama

Bridge 启动脚本默认连接项目已验证的隔离 Ollama（`127.0.0.1:11435`、`qwen3.5:9b`），并优先加载已解析的中文联合资料索引 `data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json`（含 vanilla／SVE／Rasmodia 的事件对白素材，2026-09-18 起为默认）。如需切换地址、模型、接口模式或资料索引，可在启动前覆盖进程环境变量：

```powershell
$env:BRIDGE_LOCAL_URL = "http://127.0.0.1:11435/api/chat"
$env:BRIDGE_LOCAL_MODEL = "qwen3.5:9b"
$env:BRIDGE_LOCAL_API_MODE = "ollama"
$env:BRIDGE_LOCAL_TIMEOUT = "15"
$env:BRIDGE_PROFILE_INDEX = "data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
```

原生模式固定发送 `stream=false` 和 `think=false`，避免 Qwen3/DeepSeek 的思考内容泄漏或 OpenAI 兼容接口返回空文本。保留 OpenAI-compatible 模式时不要设置 `BRIDGE_LOCAL_API_MODE=ollama`。

本机测试使用隔离 Ollama 服务（`OLLAMA_HOST=127.0.0.1:11435`、模型目录 `D:\OllamaModels`），已验证 `qwen3.5:4b` 与 `qwen3.5:9b`。游戏内性能诊断仅在 FastTest profile 的 Mod `config.json` 临时设置 `EnablePerformanceDiagnostics=true` 时启用，普通运行默认关闭；日志会每 5 秒输出一条 `[StardewAI.Perf]` 窗口。

模型比较使用项目真实的 Rasmodia 上下文和关系阶段用例：

```powershell
$env:PYTHONPATH = "bridge/src"
& $py scripts/benchmark_local_models.py --model qwen3.5:4b qwen3.5:9b
```

结果写入 `artifacts/model-benchmark-*.json`，包含每条原文回复、延迟、错误和轻量规则评分；评分不能替代人工角色一致性复核。

对话请求的 `intent` 支持 `chat`、`topic`、`item`；物品互动的 `itemContext` 只允许物品 ID、显示名、类别、品质、动作和原版偏好结果。旧请求省略这些字段时仍按普通聊天处理。

当前 `codex/story-memory` 工作树还包含故事状态层：版本化记忆记录、知识范围、关系进度和有效互动门槛。它由纯 C# 模型、校验与序列化组成，并**已接入存档生命周期**——读档时恢复、保存时写回，群聊与单聊的长期记忆都会进存档（不修改原版剧情、NPC 日程或原版 UI）。

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

## 线上群聊（F9）

按 `F9` 打开**多人对话中心**：既可以接受一张邀约卡（接受后直接进入群聊），也可以在已认识的 NPC 里自由发起并选 2～3 人。群聊固定走远程频道（`channel=remote`），不要求 NPC 在场、不传送他们、不改变日程，也不会被写成线下见面。

- **策略**：默认 `multi_turn`（自然接话流）——一次请求里名单内多个人可以依次发言、插话或由同一个人补一句；配置项 `GroupDialogueStrategy` 可在 Generic Mod Config Menu 里切回 `turn_based`（固定一人一轮）。
- **回合预算**：调用方未显式指定时按在场人数给额度（2 人 → 2、3 人 → 3，上限 4），避免三人场必然有人整场不开口。
- **两层记忆**：内存层每位 NPC 保留 6 条、一次群聊只占 1 条合并记录（“群里玩家说…；我回应…”）；存档层只写 Bridge 挑出的重要事实或约定（`memoryHighlights`，闲聊不写），且在场每个 NPC 各记一条。群里说过的事之后会在私聊的 `recentFacts` 里被想起来。
- **关系边界**：群聊不修改好感度、关系阶段或库存；回应名单内的人用“你”，对玩家说话时 `addressedTo` 留空。
- **验证方式**：游戏内视觉场景（`group-hub` / `group-message` / `group-send` / `group-accept` / `group-free`）与云端批次运行器，用法与产物见 `docs/handoff-group-dialogue-2026-09-20.md`。

## 房屋访问

单人游戏里默认允许提前进入**已确认属于 NPC 住宅**的外门（`EnableHouseAccess`，个人测试档默认开启）；住宅与商店共用的复合建筑另由 `AllowMixedBuildingAccess` 控制，默认同样开启。**节日、事件与多人游戏一律保持原版门禁**，不打断原版流程；放行与回退的原因都会写进日志。该功能只放宽**开门条件**，不改地图、不改 NPC 日程、也不写 `eventsSeen`／邮件／任务／好感度。

## 快速测试 profile

修改 C# 代码后，先运行毫秒级自动化测试：

```powershell
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" /p:EnableModDeploy=false /p:EnableModZip=false /p:BundleExtraAssemblies=Game
```

想一次跑完日常检查（SMAPI 测试 + Bridge 测试与 collect 探测 + Python 语法编译 + 工作树空白检查），用：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_project.ps1
```

它会先探测 Bridge 测试能否收集：若失败原因是**并行工作线**造成的 ImportError，会标成 `ENV`（需人工确认）而不是本线回归失败，避免误判；退出码 `0` 全绿、`1` 有失败、`2` 有环境问题。只验一侧时可用 `-SkipBridge` / `-SkipSmapi`。

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

首次使用快速 profile 时，请在游戏内选择独立测试存档。注意 **`Mods-AI-FastTest` 只装 `StardewAI.NPC`、GMCM、Content Patcher、CMCT 与 `[CP] Romanceable Rasmodia`——不含 SVE**；因此 SVE 相关内容（如 SVE 角色的 gameState、SVE 事件素材）在该 profile 里取不到，需要覆盖时请另配一个含 SVE 的 Mod 目录再回归。

### 推荐：一键启动

不想手动打开终端时，直接双击：

```text
scripts\start_ai_npc_test.cmd
```

它会优先复用已经运行的 Bridge；Bridge 未运行时自动后台启动，随后同步并启动包含 Rasmodia 的快速测试 profile。游戏退出后只清理它自己启动的 Bridge，不会停止你原本已经打开的 Bridge。该入口使用 PowerShell 7，并不会修改系统执行策略。
