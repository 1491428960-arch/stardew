# 自然个人亲近表达实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现，并在每个验证点保留新鲜输出。

**目标：** 让 Bridge 在 `dating` / `married` 阶段区分个人亲近、普通陪伴和具体安排，识别自然中文的专属亲近，抑制多轮机械形状，并保留 Shane 与渠道边界。

**架构：** `stage_policy.py` 提供结构化个人信号与变化约束；`prompts.py` 将它们压缩到现有亲近 Prompt 卡；`behavior_quality.py` 负责语义组合诊断和多轮信号记录；`guard.py` 只对确实缺少个人亲近或出现机械形状的回复有限重试；`character_quality_eval.py` 与行为示例提供五角色回归契约。

**技术栈：** Python 3、pytest、Pydantic `ProviderResult`、现有 Bridge Prompt/Guard 流程。

---

## 文件职责

- 修改：`bridge/src/stardew_ai_bridge/stage_policy.py`，为恋爱/婚后策略添加 `personalSignals`、`supportSignals`、`variationRule`。
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`，投影新字段并向模型说明陪伴/安排不能单独充作爱意。
- 修改：`bridge/src/stardew_ai_bridge/behavior_quality.py`，实现个人亲近组合、独立陪伴/安排诊断和多轮形状接口。
- 修改：`bridge/src/stardew_ai_bridge/guard.py`，按新诊断决定亲近或变化重试，避免词表漏判导致重试。
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`，在三轮评分中记录并判断机械亲近形状。
- 少量修改：`data/personas/behavior-examples.json`，仅补五角色人工审核示例或负例元数据，不写入未审核云端文本。
- 修改：`bridge/tests/test_behavior_quality.py`，新增语义分类与 Shane 边界失败测试。
- 修改：`bridge/tests/test_guard.py`，新增功能性邀约重试、语义亲近免重试、变化重试失败测试。
- 修改：`bridge/tests/test_stage_policy.py`、`bridge/tests/test_prompts.py`，新增结构化字段投影失败测试。
- 修改：`bridge/tests/test_character_quality_eval.py`，新增多轮机械形状失败测试。

## 任务 1：扩展阶段策略与 Prompt 契约

- [ ] **步骤 1：编写失败测试**：断言五个角色的 `dating` / `married` 策略有 `personalSignals`、`supportSignals`、`variationRule`，朋友阶段没有这些字段；断言 Prompt 中明确“陪伴和安排不能单独充作爱意”。
- [ ] **步骤 2：运行定向测试确认失败**：运行 `python -B -m pytest -q -p no:cacheprovider bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py`，预期新断言失败且旧断言保持通过。
- [ ] **步骤 3：最小实现**：在 `stage_policy.py` 的默认及角色覆盖策略加入字段，在 `prompts.py` 的压缩/亲近卡中保留字段并生成简短约束。
- [ ] **步骤 4：运行定向测试确认通过**：同一命令达到 0 failures。

## 任务 2：实现语义亲近诊断

- [ ] **步骤 1：编写失败测试**：覆盖专属选择、只对玩家分享、玩家触发期待、个人化照顾和脆弱分享；断言纯“陪你/一起去/我在等你/给你看看”分别标记 `companionship_only` 或 `specific_plan_only`；断言组合表达通过；覆盖自然中文不命中旧 marker 的样例。
- [ ] **步骤 2：运行测试确认失败**：运行 `python -B -m pytest -q -p no:cacheprovider bridge/tests/test_behavior_quality.py`，预期新字段不存在或判定错误。
- [ ] **步骤 3：最小实现**：在 `behavior_quality.py` 增加个人信号类别、玩家指向/个人原因组合判断，保留旧 `initiativeTags` 和关系/渠道边界；返回 `personalAffectionDetected`、`companionshipDetected`、`specificPlanDetected`、`affectionEvidence`、`affectionShape`。
- [ ] **步骤 4：运行测试确认通过**：同一命令达到 0 failures，并检查旧机械复述测试仍通过。

## 任务 3：实现多轮机械形状评分

- [ ] **步骤 1：编写失败测试**：构造三轮相同开场、相同 `initiativeKind` 和相同亲近类别但无新对象的回复，断言标记 `mechanical_affection_shape`；构造亲近原因变化或新话题对象，断言不标记；构造明确收口，断言不要求新亲近。
- [ ] **步骤 2：运行测试确认失败**：运行 `python -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py`，预期新诊断字段或标签缺失。
- [ ] **步骤 3：最小实现**：在 `character_quality_eval.py` 增加基于上一轮诊断结果的形状比较函数，将结果并入三轮评分和现有 `initiativeTags`，不改写回复文本。
- [ ] **步骤 4：运行测试确认通过**：同一命令达到 0 failures。

## 任务 4：调整 Guard 重试门控

- [ ] **步骤 1：编写失败测试**：断言纯功能性邀约触发一次 `affection_retry`；断言自然专属表达即使不命中旧词表也不重试；断言机械形状触发一次 `variation_retry` 并提示换形状；断言 Shane 状态差/拒绝/需要空间不重试；保留 remote / face_to_face 边界。
- [ ] **步骤 2：运行测试确认失败**：运行 `python -B -m pytest -q -p no:cacheprovider bridge/tests/test_guard.py`，预期新门控断言失败。
- [ ] **步骤 3：最小实现**：让 Guard 复用语义诊断结果；仅在 `companionship_only` / `specific_plan_only` 缺个人亲近时触发爱意重试；新增有限 `variation_retry`；保持 `_retry_quality_key`、预算异常和现有边界。
- [ ] **步骤 4：运行测试确认通过**：同一命令达到 0 failures。

## 任务 5：行为示例与质量结果契约

- [ ] **步骤 1：编写失败测试**：断言五角色各至少有一条人工审核的个人亲近示例或对应元数据，断言质量结果保留新增诊断字段且脱敏层不写入 Prompt/Token；断言默认案例契约和旧字段兼容。
- [ ] **步骤 2：运行测试确认失败**：运行 `python -B -m pytest -q -p no:cacheprovider bridge/tests/test_quality_pipeline.py bridge/tests/test_quality_results.py bridge/tests/test_character_quality_eval.py`。
- [ ] **步骤 3：最小实现**：只补少量明确审核的 JSON 示例/负例；在 `score_character_reply()` 和结果汇总处写入新字段，保持 API 兼容。
- [ ] **步骤 4：运行测试确认通过**：同一命令达到 0 failures。

## 任务 6：完整验证与云端小批次

- [ ] **步骤 1：运行定向套件**：执行五个目标测试文件，确认全部通过。
- [ ] **步骤 2：运行 Bridge 全量测试**：执行 `python -B -m pytest -q -p no:cacheprovider bridge/tests`，记录完整通过数和警告。
- [ ] **步骤 3：运行静态检查**：执行 `python -B -m compileall -q bridge/src bridge/tests` 与 `git diff --check`。
- [ ] **步骤 4：运行隔离云端批次**：使用当前 `qwen-plus-character` 运行 3～6 个五角色高阶段案例，输出到新的 `artifacts/character-quality-eval/20260903-natural-personal-affection-cloud`，保留完整三轮 transcript、脱敏摘要、诊断和 usage，不覆盖历史批次。
- [ ] **步骤 5：人工复核**：逐例检查亲近是否明确且自然、陪伴是否冒充爱意、三轮是否变换形状、Sebastian/Alex/Shane 是否保持角色、渠道/同意/收口是否正确；未达标则只修复当前五角色，不推广全 NPC。
