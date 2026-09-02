# “找话题”高亲密主动调情实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 按任务顺序执行；每完成一个任务更新工作计划并保留验证证据。

**目标：** 新增一个独立的 `topic-start-intimacy` 质量评测套件，32 个案例全部从空 topic 入口开始，检验 dating/married 阶段 NPC 是否主动、热情且保持角色边界。

**架构：** 复用现有 `CharacterQualityCase`、PromptBuilder 和脱敏结果管线，新增独立案例模块与套件选择入口，不改变默认固定案例。评测请求显式携带 `intent=topic` 与空 `message`，三轮真实回复继续写入当前评测内存历史；结果使用独立批次目录供 Bridge 读取。

**技术栈：** Python 3.12、pytest、Pydantic、FastAPI、现有 OpenAI-compatible Bridge。

---

## 文件清单

- 创建：`bridge/src/stardew_ai_bridge/topic_start_intimacy_cases.py`，保存 32 个结构化案例和套件元数据。
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`，让案例保留 `intent`、topic 入口为空，并支持选择套件后的稳定编号。
- 修改：`scripts/run_character_quality_eval.py`，增加 `--suite topic-start-intimacy`，默认仍运行既有案例。
- 修改：`bridge/src/stardew_ai_bridge/app.py`，让 `/api/quality/cases?suite=topic-start-intimacy` 返回新套件目录。
- 修改：`bridge/tests/test_character_quality_eval.py`，覆盖新套件元数据、空入口和三轮定义。
- 修改：`bridge/tests/test_run_character_quality_eval.py`，覆盖 topic 请求构造、选套件和结果编号。
- 修改：`bridge/tests/test_quality_results.py`，覆盖独立批次中 suite 字段的安全保留（若结果过滤器需要变更）。
- 创建：`artifacts/character-quality-eval/20260902-topic-start-intimacy-cloud/summary.json` 与 `results.jsonl`，仅保存脱敏质量结果。
- 修改：`docs/active-work.md`，记录本批次统计、验证命令和哈希，不写入密钥或完整 Prompt。

### 任务 1：添加可选择的 topic-start 案例套件

**文件：**

- 创建：`bridge/src/stardew_ai_bridge/topic_start_intimacy_cases.py`
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 测试：`bridge/tests/test_character_quality_eval.py`

- [ ] **步骤 1：编写失败测试**

  增加测试，要求 `topic_start_intimacy_cases()` 返回 32 个唯一案例；每个案例 `intent="topic"`、第一轮消息为空、共三轮；目标案例属于 dating/married 且 `adultConsensual=True`，对照案例属于 acquaintance/friend 且 `flirtIntensity="none"`。

- [ ] **步骤 2：运行测试确认失败**

  运行：`python -m pytest bridge/tests/test_character_quality_eval.py -k topic_start_intimacy -q`

  预期：因套件导出和 `intent` 字段尚不存在而失败，不能是导入路径错误。

- [ ] **步骤 3：实现最少数据与兼容字段**

  在 `CharacterQualityCase` 增加默认值为 `"chat"` 的 `intent` 字段，验证值只允许 `chat`、`topic`、`item`；新模块定义五个主要角色的 24 个高亲密目标案例和 8 个低亲密对照案例。目标案例使用 `message=""`，续聊轮使用笨拙或日常短句；不写露骨性行为过程，只写强烈成人暧昧、拥抱/亲吻/靠近和双方同意的亲密安排。

- [ ] **步骤 4：运行测试确认通过**

  运行：`python -m pytest bridge/tests/test_character_quality_eval.py -k topic_start_intimacy -q`

  预期：新套件元数据测试全部通过，既有默认案例校验保持通过。

### 任务 2：让评测器真实发送空 topic 请求并维持三轮历史

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 修改：`scripts/run_character_quality_eval.py`
- 测试：`bridge/tests/test_run_character_quality_eval.py`

- [ ] **步骤 1：编写失败测试**

  使用真实 `run_evaluation()` 和捕获 Provider，断言新套件第一轮请求的 `message == ""`、`intent == "topic"`；Prompt 包含 `topic_response_contract` 与空 `topic_trigger`，而当前历史不包含空玩家消息。断言第二、三轮包含前一轮真实 NPC 回复。

- [ ] **步骤 2：运行测试确认失败**

  运行：`python -m pytest bridge/tests/test_run_character_quality_eval.py -k topic -q`

  预期：当前评测器会把空消息回退成 `case.message`，或不带 `intent`，因此测试失败。

- [ ] **步骤 3：实现最少请求构造与套件选择**

  修改请求构造逻辑：当案例 `intent == "topic"` 时保留空消息并传入 `intent`；普通 chat 案例保持旧行为。让结果案例编号按本次 `selected_cases` 从 1 开始，避免新套件出现空编号。CLI 增加 `--suite`，只接受 `default` 和 `topic-start-intimacy`，默认值为 `default`；新增套件时不改变默认案例数量和默认输出语义。

- [ ] **步骤 4：运行测试确认通过**

  运行：`python -m pytest bridge/tests/test_run_character_quality_eval.py -k topic -q`

  预期：topic 请求字段、Prompt 契约、三轮历史和结果编号全部通过。

### 任务 3：暴露新套件目录并做 Fake Provider 小批次验证

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/app.py`
- 修改：`bridge/tests/test_character_quality_eval.py`
- 修改：`bridge/tests/test_quality_results.py`

- [ ] **步骤 1：编写失败测试**

  增加 API 测试：`GET /api/quality/cases?suite=topic-start-intimacy` 返回 `schemaVersion=1`、32 个连续案例，且默认 `/api/quality/cases` 仍返回原固定套件。结果过滤测试确认 `suite` 只保留短标识，不泄露 Prompt、Token 或凭据。

- [ ] **步骤 2：运行测试确认失败**

  运行：`python -m pytest bridge/tests/test_character_quality_eval.py bridge/tests/test_quality_results.py -k "topic_start_intimacy or suite" -q`

  预期：新查询参数和套件目录尚不存在而失败。

- [ ] **步骤 3：实现最少 API 选择逻辑并跑小批次**

  让目录函数按套件返回脱敏案例；未知 suite 返回明确的 400。用 Fake Provider 运行 3 个案例：至少一个 dating、一个 married、一个低亲密对照，确认 `provider=fake`、`fallback=false`、请求成功，且不创建或修改正式存档。

- [ ] **步骤 4：运行测试确认通过**

  运行：`python -m pytest bridge/tests/test_character_quality_eval.py bridge/tests/test_quality_results.py -q`

  预期：定向测试全部通过，Fake 小批次生成 9 轮且历史契约正确。

### 任务 4：运行独立云端质量批次并记录证据

**文件：**

- 修改：`scripts/run_character_quality_eval.py`（仅使用已实现的 CLI）
- 创建：`artifacts/character-quality-eval/20260902-topic-start-intimacy-cloud/summary.json`
- 创建：`artifacts/character-quality-eval/20260902-topic-start-intimacy-cloud/results.jsonl`
- 修改：`docs/active-work.md`

- [ ] **步骤 1：运行完整 Bridge 回归后再请求云端**

  运行：`python -m pytest bridge/tests -q`

  预期：退出码为 0，输出包含全部通过和最多既有 warning；失败时停止，不发送云端批次。

- [ ] **步骤 2：使用当前索引和当前云端 Provider 运行 32 例**

  运行：`python scripts/run_character_quality_eval.py --suite topic-start-intimacy --profile-index data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-proactive-affection.json --provider cloud --model qwen-plus-character --output-dir artifacts/character-quality-eval/20260902-topic-start-intimacy-cloud`

  预期：生成 32 个结果、96 轮计划；记录实际成功数、错误数、fallback 数、主动性标签、Token 和耗时。不得覆盖旧批次。

- [ ] **步骤 3：验证工件和 API**

  运行：`Get-FileHash artifacts/character-quality-eval/20260902-topic-start-intimacy-cloud/results.jsonl,artifacts/character-quality-eval/20260902-topic-start-intimacy-cloud/summary.json -Algorithm SHA256`；调用 `GET http://127.0.0.1:5678/api/quality/results`，确认返回 `batchId=20260902-topic-start-intimacy-cloud`、`caseCount=32`，并搜索结果目录确认不含 `apiKey`、`token`、`prompt` 字段。

- [ ] **步骤 4：人工复核范围**

  在浏览器查看五个主要角色各至少一个目标案例、一个对照案例，以及 remote/face_to_face 各一例。记录角色热情是否真实、是否像本人、是否出现“礼貌但不情愿”，不把自动通过率单独作为结论。

### 任务 5：完成前回归与工作记录

**文件：**

- 修改：`docs/active-work.md`

- [ ] **步骤 1：运行最终验证**

  运行：`python -m pytest bridge/tests -q`、`python -m compileall -q bridge/src bridge/tests scripts/run_character_quality_eval.py`、`git diff --check`（在不改变其他已有改动的前提下）。

- [ ] **步骤 2：更新活动记录**

  写入新批次统计、工件绝对路径/相对入口、哈希和真实验证边界；明确未启动游戏、未部署 DLL、未修改正式存档。

- [ ] **步骤 3：提交前状态核对**

  使用 `git status --short` 确认只报告本任务文件的新增/修改，绝不加入现有用户改动、密钥、Cookie、运行日志和构建产物。
