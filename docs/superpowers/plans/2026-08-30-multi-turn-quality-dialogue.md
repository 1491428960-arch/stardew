# 多轮角色质量评测实现计划

> **面向 AI 代理的工作者：** 使用 `subagent-driven-development`（独立任务）或 `executing-plans`（内联执行）逐任务实现。用 `update_plan` 跟踪整体状态，并保留文档中的复选框。

**目标：** 为固定角色质量评测增加三轮真实连续对话、每轮/案例级 token 统计和测试例浏览器 transcript 展示。

**架构：** `CharacterQualityTurn` 描述每轮输入与评分要求，评测器在同一案例内顺序构建 prompt 并把成功生成的消息追加到下一轮。Provider 将上游 usage 标准化为 `ProviderUsage`；质量工件只保存脱敏轮次记录，页面通过现有结果 API 展示完整 transcript，并兼容旧单轮工件。

**技术栈：** Python 3.10+、Pydantic、httpx、FastAPI、pytest、内嵌 HTML/CSS/JavaScript。

---

## 文件结构

- 修改 `bridge/src/stardew_ai_bridge/models.py`：增加标准化 usage 模型并挂载到 Provider/Dialogue 响应。
- 修改 `bridge/src/stardew_ai_bridge/providers.py`：解析 OpenAI-compatible 和 Ollama 返回的 usage。
- 修改 `bridge/src/stardew_ai_bridge/character_quality_eval.py`：增加轮次类型、15 个三轮案例和脱敏案例目录字段。
- 修改 `scripts/run_character_quality_eval.py`：按案例顺序执行三轮、追加真实上下文、累计请求/usage/费用并写 schema v2 工件。
- 修改 `bridge/src/stardew_ai_bridge/quality_results.py`：脱敏并读取 schema v2，同时包装旧单轮结果。
- 修改 `bridge/src/stardew_ai_bridge/dialogue_lab_page.py`：列表、详情和右侧概览展示多轮 transcript 与 token/费用。
- 修改 `bridge/tests/test_providers.py`：Provider usage 解析回归。
- 修改 `bridge/tests/test_character_quality_eval.py`：三轮案例目录契约。
- 修改 `bridge/tests/test_run_character_quality_eval.py`：顺序调用、上下文承接、轮次汇总和脱敏。
- 修改 `bridge/tests/test_external_dialogue_lab.py`：多轮页面展示与安全契约。

### 任务 1：增加 usage 模型和 Provider 解析

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/models.py`
- 修改：`bridge/src/stardew_ai_bridge/providers.py`
- 测试：`bridge/tests/test_providers.py`

- [ ] **步骤 1：编写失败测试**

在 `test_providers.py` 增加两个真实 HTTP mock 行为测试：OpenAI-compatible 响应中的 `usage.prompt_tokens/completion_tokens/total_tokens` 应进入 `result.usage`；Ollama 响应中的 `prompt_eval_count/eval_count` 应被标准化。断言同时确认未把 API key 写进 result。

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest -q bridge/tests/test_providers.py -p no:cacheprovider`

预期：新增断言因 `ProviderResult` 没有 usage 或 Provider 未解析 usage 而失败。

- [ ] **步骤 3：编写最少实现代码**

新增 `ProviderUsage`，字段为 `inputTokens`、`outputTokens`、`totalTokens`，全部允许缺失但拒绝负数；给 `ProviderResult` 和 `DialogueResponse` 增加 `usage`。在两个 Provider 中只从响应 JSON 的 usage/明确计数项创建 `ProviderUsage`，没有数据就返回 `None`。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest -q bridge/tests/test_providers.py bridge/tests/test_api.py -p no:cacheprovider`

预期：新增 usage 测试和既有 Provider/API 测试全部通过；若 API 响应模型集合断言变化，只增加明确的 `usage` 字段断言。

### 任务 2：把固定案例定义为三轮并保留旧接口

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 测试：`bridge/tests/test_character_quality_eval.py`

- [ ] **步骤 1：编写失败测试**

增加测试断言所有默认案例的 `dialogue_turns()` 长度为 3、每轮有非空输入和唯一 `turnId`，且 `quality_case_catalog()` 返回 `turns`、每轮包含 `playerInput` 和评分字段；原有 `case.message` 和 `case.history` 仍可用。

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest -q bridge/tests/test_character_quality_eval.py -p no:cacheprovider`

预期：当前 `CharacterQualityCase` 没有三轮方法和目录 `turns` 字段，测试失败。

- [ ] **步骤 3：编写最少实现代码**

新增 `CharacterQualityTurn` 与 `dialogue_turns()`。为现有 15 个案例补充贴合场景的第二、三轮输入、期望证据和复核重点；第一轮继续映射现有字段。目录增加 `turnCount` 和 `turns`，不删除兼容字段。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest -q bridge/tests/test_character_quality_eval.py -p no:cacheprovider`

预期：三轮结构测试及原有评分/场景矩阵测试全部通过。

### 任务 3：实现顺序评测、上下文承接和工件汇总

**文件：**
- 修改：`scripts/run_character_quality_eval.py`
- 修改：`bridge/src/stardew_ai_bridge/quality_results.py`
- 修改：`bridge/src/stardew_ai_bridge/behavior_quality.py`（仅在现有脱敏入口需要允许新字段时）
- 测试：`bridge/tests/test_run_character_quality_eval.py`

- [ ] **步骤 1：编写失败测试**

使用捕获 Provider 运行单个三轮案例，断言调用顺序为 3 次；第二次 messages 包含第一轮实际回复，第三次包含前两轮实际回复；结果只含 `turns` 中的回复而不含 `prompt`/`payload`/API key；summary 汇总成功轮数、请求数和三类 token。

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest -q bridge/tests/test_run_character_quality_eval.py -p no:cacheprovider`

预期：当前评测器只调用一次并只写单条 `reply`，新增断言失败。

- [ ] **步骤 3：编写最少实现代码**

在每个案例内维护 `conversation_history`：初始为案例 history；每轮以该历史构建 context/prompt，调用 Provider，评分并记录；只有成功回复才向下一轮追加 user/assistant。将 ProviderResult.usage 转为脱敏 `usage`，汇总 `requestCount`、`successfulTurns`、`failedTurns`、`inputTokens`、`outputTokens`、`totalTokens`、`usageReturnedTurns`，费用仅使用显式输入/输出单价计算。结果写入 schema version 2，并保留单轮字段供旧读取器使用。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest -q bridge/tests/test_run_character_quality_eval.py bridge/tests/test_quality_results.py -p no:cacheprovider`

预期：评测器与结果读取器测试通过，旧单轮结果仍能被读取为单轮展示结构。

### 任务 4：升级测试例浏览器为完整 transcript

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
- 修改：`bridge/src/stardew_ai_bridge/quality_results.py`（若任务 3 未完成字段过滤）
- 测试：`bridge/tests/test_external_dialogue_lab.py`

- [ ] **步骤 1：编写失败测试**

增加页面契约断言：页面含 `turns`、`renderCaseTranscript`、每轮 `playerInput`/`reply`/`usage` 的渲染路径，含案例级 `totalTokens`/费用显示，并且页面源码不含敏感请求字段。增加结果 API fixture，确认多轮结果会进入页面可用数据。

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest -q bridge/tests/test_external_dialogue_lab.py -p no:cacheprovider`

预期：当前页面只有 `renderCaseResult` 单条回复路径，新增契约失败。

- [ ] **步骤 3：编写最少实现代码**

在案例详情中按预置 history、每轮用户输入和 NPC 回复构造 transcript；每轮显示状态、Provider、延迟、usage（缺失时显示“用量未返回”）及评分；批次和右侧概览显示请求数、总 token、已返回 usage 的轮数和已配置/未配置费用。保持 DOM 使用 `textContent`，不把任何 prompt 或凭据写入页面。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest -q bridge/tests/test_external_dialogue_lab.py -p no:cacheprovider`

预期：页面契约测试通过，原有统一工作区、NPC 切换、原文参照和会话持久化测试不回归。

### 任务 5：完整回归、百炼批次和浏览器验证

**文件：**
- 修改：`docs/active-work.md`（记录实际验证结果）
- 创建：`artifacts/character-quality-eval/<timestamp>-api-qwen-multiturn/`（新工件，不覆盖旧批次）

- [ ] **步骤 1：运行定向和完整测试**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests
```

预期：输出 0 failures；记录实际通过数和耗时。

- [ ] **步骤 2：运行百炼 Qwen 三轮批次**

使用当前 `.env.local` 中的云端配置和 `--provider cloud`，指定一个新的时间戳输出目录；不打印环境变量、不读取或写出 API key。核对结果应有 15 个案例、45 个轮次，并统计 cloud/fallback/error、usage 返回率和 token 汇总。

- [ ] **步骤 3：核对接口和运行服务**

检查 `GET http://127.0.0.1:5678/health`、`GET /api/quality/results` 和 `GET /test`。若重启 Bridge，需同时核对包装 PowerShell 与绑定 5678 的实际子进程；不要把旧服务响应当成当前代码证据。

- [ ] **步骤 4：浏览器视觉验证**

在当前 `http://127.0.0.1:5678/test` 查看一个有结果的案例，确认三轮 transcript、每轮 token、案例总 token和费用状态可见，截图后用视觉检查对照预期。再查看一个失败/缺 usage 状态（若批次存在），确认页面不崩溃。

- [ ] **步骤 5：更新活动记录并汇报边界**

将实际测试数字、批次目录、provider/fallback、token 和费用配置状态写入 `docs/active-work.md`。明确网页评测批次已验证、游戏内历史和 DLL 未在本轮验证；不把人工角色质量判断写成自动通过。
