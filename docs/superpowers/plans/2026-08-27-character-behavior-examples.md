# 角色行为示例与上下文执行卡实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现。用 `update_plan` 跟踪整体状态，并保留文档中的复选框。

**目标：** 让 Bridge 使用少量人工审核的 `playerInput → npcReply` 行为示例，并按角色、来源、关系阶段、渠道和话题选择示例，从而改善 NPC 的个性化口语风格。

**架构：** 新增独立的 `behavior-examples.json` 源文件，索引器把它编译到 `behaviorExamples`，`ProfileIndexStore` 使用显式 `topicKeywords` 做确定性相关性排序。`PromptBuilder` 在原有人设和原文证据之外注入成对示例，并在聊天历史之后加入短的 `post_history_voice_guard`；原版语料仍作为事实/风格证据，不伪装成成对示例。

**技术栈：** Python 3.12、pytest、JSON 资料索引、Bridge chat messages、现有 Qwen/Ollama Provider。

---

### 任务 1：行为示例索引契约与检索

**文件：**
- 创建：`data/personas/behavior-examples.json`
- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`
- 修改：`bridge/tests/test_profile_index.py`

- [x] **步骤 1：编写失败测试**

  已加入 `test_profile_index_selects_behavior_examples_by_topic_stage_and_source`，要求索引读取示例，并在 `npcId`、`sourceMods`、`relationshipStages`、`channels` 和 `topicKeywords` 不匹配时排除候选。

- [x] **步骤 2：运行测试验证失败**

  已运行：

  ```powershell
  $env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
  $env:PYTHONDONTWRITEBYTECODE='1'
  & 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_profile_index.py::test_profile_index_selects_behavior_examples_by_topic_stage_and_source
  ```

  当前结果为预期红灯：`AttributeError: ProfileIndexStore has no attribute behavior_examples`。

- [ ] **步骤 3：实现最少检索能力**

  在 `ProfileIndexBuilder.build()` 增加 `behaviorExamples`，从 `behavior-examples.json` 读取并校验允许字段；在 `ProfileIndexStore` 增加：

  ```python
  behavior_examples(
      npc_id,
      source_mods,
      *,
      relationship_stage="",
      channel="",
      player_input="",
      limit=4,
  ) -> list[dict[str, Any]]
  ```

  先硬过滤角色、来源、阶段和渠道，再按 `topicKeywords` 在玩家输入中的命中数排序；无命中时使用稳定的原始顺序，不调用网络或向量数据库。返回值只保留 Prompt 需要的字段。

- [ ] **步骤 4：运行定向测试验证通过**

  运行同一条定向 pytest，预期 `1 passed`。

### 任务 2：五个评测角色的人工审核行为示例

**文件：**
- 创建：`data/personas/behavior-examples.json`
- 测试：`bridge/tests/test_profile_index.py`

- [ ] **步骤 1：编写最小资料集**

  为 `Wizard`、`Sophia`、`Shane`、`Sebastian`、`Alex` 各提供 8 条成对示例，覆盖日常寒暄、工作/兴趣、被关心、被质疑、感谢/拒绝、邀约或连续追问。每条示例必须带 `sourceType=handcrafted_example`，并标明 `topicKeywords`、`speechFunction`、`emotion`、关系阶段和渠道；Wizard/Rasmodia 只使用 canonical `Wizard`。

- [ ] **步骤 2：添加资料完整性测试**

  测试五个角色都有示例、每条有玩家输入和 NPC 回复、没有空字符串、没有未授权的 `apiKey`/`token` 字段，且不同角色的示例回复不完全相同。

- [ ] **步骤 3：运行资料测试**

  运行 `bridge/tests/test_profile_index.py`，预期新增断言先失败，再由资料文件补齐并通过。

### 任务 3：Prompt 注入和历史后执行卡

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 修改：`bridge/src/stardew_ai_bridge/models.py`
- 修改：`bridge/src/stardew_ai_bridge/app.py`
- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/tests/test_api.py`

- [x] **步骤 1：编写失败测试**

  已加入 `test_prompt_renders_behavior_examples_and_reinforces_voice_after_history`，并更新固定消息顺序测试，要求 `behavior_examples` 位于历史之前、`post_history_voice_guard` 位于历史之后且玩家输入仍是最后一条。

- [x] **步骤 2：运行测试验证失败**

  已确认三项红灯：缺少 `behavior_examples` 检索、Prompt 未渲染行为示例、缺少历史后执行卡。

- [ ] **步骤 3：实现 Prompt 数据清洗和消息顺序**

  将行为示例加入 ContextBuilder 和安全 Prompt 数据；注入一条独立 `behavior_examples` system message。扩展可选 `channel` 请求字段，支持 `remote` 与 `face_to_face`，缺省时保持旧调用行为。把 `post_history_voice_guard` 放在历史之后、`player_input` 之前，只重复本轮渠道、关系阶段、当前话题和 2～3 条行为规则，不复制完整 persona。

- [ ] **步骤 4：运行 Prompt/API 定向测试**

  运行：

  ```powershell
  $env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
  $env:PYTHONDONTWRITEBYTECODE='1'
  & 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_prompts.py bridge/tests/test_api.py
  ```

  预期全部通过。

### 任务 4：编译索引、完整回归和本地 Bridge 复核

**文件：**
- 生成：`data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json`
- 修改：仅在完成后更新 `docs/active-work.md`

- [ ] **步骤 1：重建派生索引**

  使用现有 `scripts/build_profile_index.py` 入口重建中文联合索引，核对 `behaviorExamples` 的数量和 canonical NPC 分布；生成文件不写入密钥、Token、Cookie 或聊天运行状态。

- [ ] **步骤 2：运行完整 Bridge 测试**

  运行项目交接文档规定的 `bridge/tests` 全量 pytest，记录实际通过数和警告数。

- [ ] **步骤 3：检查本地服务和上下文预览**

  检查 `GET http://127.0.0.1:5678/health`、`GET /test`，并用 `/api/context/preview` 验证五个角色请求返回对应的行为示例，不把示例正文之外的敏感字段带入 Prompt。

- [ ] **步骤 4：小样本人工复核**

  对五个角色各发送 3 条相同类型输入，再检查不同角色是否呈现不同回应动作；记录“更贴切”“仍书面化”与“事实越界”三类结果，不把一次成功回复表述成整体角色问题已解决。
