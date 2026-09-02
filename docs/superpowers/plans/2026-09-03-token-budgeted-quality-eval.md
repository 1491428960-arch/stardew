# 质量评测 Token 预算与最小上下文实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现；用 `update_plan` 跟踪整体状态，保留验证证据。

**目标：** 在不更换模型、不改变普通对话行为的前提下，降低质量评测的请求次数和每次输入量，并让超出预算的批次可预测地停止。

**架构：** 评测脚本增加可选的经济配置：默认少量 smoke case、NPC 每轮最多一次格式重试、动态玩家输入默认开启且失败不重试、总请求/Token 预算硬上限。3 个自适应案例按 9 次 NPC 请求、6 次玩家模拟和最多 9 次 NPC 重试配置为 24 次请求上限。PromptBuilder 增加最小上下文模式，只保留当前角色、阶段、话题和有限历史/证据；生产聊天继续使用完整上下文。结果摘要与每轮记录保存请求、重试和 usage 统计，不记录完整 Prompt。

**技术栈：** Python 3.12、pytest、现有 `ProviderUsage`、`CharacterQualityCase`、`PromptBuilder` 和脱敏 JSON 结果管线。

---

### 任务 1：锁定经济配置和预算行为

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/quality_eval_budget.py`
- 修改：`scripts/run_character_quality_eval.py`
- 测试：`bridge/tests/test_run_character_quality_eval.py`

- [x] **步骤 1：编写失败测试**

增加 `EvaluationBudget` 的默认值、经济模式值和预算判定测试；增加 `run_evaluation()` 在达到 `max_requests` 或 `max_total_tokens` 时停止后续轮次且摘要记录 `budgetStopReason` 的测试；增加动态玩家输入失败不重试、NPC 格式噪声最多重试一次的测试。

- [x] **步骤 2：运行测试验证失败**

运行：`python -m pytest bridge/tests/test_run_character_quality_eval.py -k "budget or economical or retry" -q`

预期：因配置类型、预算停止字段和单次重试限制尚不存在而失败；不得是导入路径错误。

- [x] **步骤 3：实现最少预算逻辑**

新增不可变配置 `EvaluationBudget`，至少包含 `max_requests`、`max_total_tokens`、`max_npc_retries`、`max_player_retries`、`compact_prompt` 和 `follow_up_mode`。CLI 增加 `--economical`、`--max-requests`、`--max-total-tokens`、`--dynamic-player-input`，经济模式显式覆盖为 3 个案例上限、24 次请求上限、每次 NPC 最多 1 次重试、玩家 0 次重试且默认开启动态玩家输入，并在发起请求前检查预算。

- [x] **步骤 4：运行测试确认通过**

运行同一条定向命令，预期新增测试通过且既有 Fake Provider 测试保持通过。

### 任务 2：压缩评测 Prompt 的重复上下文

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 修改：`scripts/run_character_quality_eval.py`
- 测试：`bridge/tests/test_prompts.py`
- 测试：`bridge/tests/test_run_character_quality_eval.py`

- [x] **步骤 1：编写失败测试**

增加 compact 模式测试：`styleSamples`、`speechEvidence`、`behaviorExamples` 各不超过 1 条；历史只保留最近 4 条；不出现 `responseOrder`；相同规则只在一个执行卡中出现；当前 `player_input` 和 `topic_response_contract` 仍保留。

- [x] **步骤 2：运行测试验证失败**

运行：`python -m pytest bridge/tests/test_prompts.py -k "compact or response_order or prompt_budget" -q`

预期：旧 Prompt 会携带多条证据/历史或固定顺序字段，测试应失败在断言内容上。

- [x] **步骤 3：实现最小上下文投影**

给 `PromptBuilder.build()` 增加 `compact: bool = False`，仅在评测经济模式传入 `True`。compact 模式按当前 NPC 与关系阶段保留一条最相关语气证据、一条行为示例、一条 style sample 和最近四条消息；合并重复的阶段/亲密/回复规则，过滤 `responseOrder`；完整模式保持旧消息契约。

- [x] **步骤 4：运行测试确认通过**

运行：`python -m pytest bridge/tests/test_prompts.py bridge/tests/test_run_character_quality_eval.py -q`，预期全部通过。

### 任务 3：成本统计、结果脱敏与小批次验证

**文件：**

- 修改：`scripts/run_character_quality_eval.py`
- 修改：`bridge/tests/test_run_character_quality_eval.py`
- 修改：`docs/active-work.md`

- [x] **步骤 1：编写失败测试**

断言每个 turn 记录 `requestCount`、`retryCount`、`inputTokens`、`outputTokens` 字段或等价脱敏统计；摘要记录 `requestCount`、`npcRetryCount`、`playerInputRetryCount`、`budget` 和 `budgetStopReason`，且序列化结果不含完整 Prompt、API key 或 token 字符串。

- [x] **步骤 2：运行测试验证失败**

运行：`python -m pytest bridge/tests/test_run_character_quality_eval.py -k "usage or retry_count or budget" -q`

预期：统计字段缺失导致断言失败。

- [x] **步骤 3：实现统计与 smoke 入口**

汇总真实 Provider 返回的 `ProviderUsage`，将每次尝试和重试计数写入脱敏结果；经济模式默认选取一个 dating、一个 married、一个 acquaintance/friend 对照案例，输出独立目录，不覆盖历史批次。

- [x] **步骤 4：运行离线验证**

运行：`python -m pytest bridge/tests -q`、`python -m compileall -q bridge/src bridge/tests scripts/run_character_quality_eval.py`、`git diff --check`；再用 Fake Provider 运行 3 例，确认 3 例、首轮 topic 语义、后续历史和预算字段正确。

### 任务 4：受控云端 smoke 与记录

**文件：**

- 创建：`artifacts/character-quality-eval/<timestamp>-token-economical-smoke/summary.json`
- 创建：`artifacts/character-quality-eval/<timestamp>-token-economical-smoke/results.jsonl`
- 修改：`docs/active-work.md`

- [ ] **步骤 1：运行 3 例经济模式云端 smoke**

只在离线回归全绿后运行 `python scripts/run_character_quality_eval.py --provider cloud --suite topic-start-intimacy --economical --limit 3 --output-dir <独立目录>`；不运行完整 32 例，不覆盖旧工件。

- [ ] **步骤 2：核对成本与结果**

核对案例数、请求数、重试数、输入/输出/总 Token、预算停止原因和敏感字段扫描；对比上一批次的单例平均输入量和请求次数，只报告实际测得的变化。

- [ ] **步骤 3：更新活动记录**

写入绝对/相对工件路径、统计和验证命令，明确未更换模型、未启动游戏、未部署 DLL、未修改正式存档；保留既有工作树改动，不提交密钥、运行状态或完整 Prompt。

---

## 计划自检

- 目标覆盖：请求数、输入量、重试上限、Token 上限、统计和 3 例 smoke 均有对应任务。
- 范围边界：未安排模型迁移、角色文案重写、游戏部署或正式存档操作。
- 脱敏边界：只记录 usage 数字、计数和停止原因，不记录完整 Prompt、API key、Cookie 或 Token 文本。
- 兼容性：`compact=False` 为默认，普通聊天与已有完整 Prompt 测试不改变。
