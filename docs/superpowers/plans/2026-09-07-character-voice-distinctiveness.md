# 角色表达辨识度校准实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 在当前工作树中按任务顺序执行；保留所有已有未提交修改，不创建 Git commit。

**目标：** 在不改变五个角色的身份、关系边界和性格底线的前提下，减少 Prompt 对“完整回复”的过度编排，让 Wizard/Rasmodia、Sophia、Shane、Sebastian 和 Alex 都保留可辨认的口头动作；Alex 作为最突出对象优先校准。

**架构：** 在 `stage_policy.py` 增加短小的角色表达指纹，作为阶段策略的一部分传入 Prompt；在阶段执行卡和普通聊天引导卡中加入“一轮只做一个额外表达动作”的预算，避免同时解释、抒情、追问和安排。行为样例只增加少量经过人工筛选的口语化成对示例，由现有 ProfileIndex 读取，不改变 canonical persona、Provider、关系安全或游戏端逻辑。

**技术栈：** Python 3.10、pytest、现有 `PromptBuilder`、`ProfileIndexStore`、JSON persona corpus。

---

### 任务 1：为五个角色锁定表达指纹和 Prompt 减负行为

**文件：**
- 修改：`bridge/tests/test_stage_policy.py`
- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/src/stardew_ai_bridge/stage_policy.py`
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`

- [ ] **步骤 1：先写失败的策略测试**

  在 `test_stage_policy.py` 增加测试，要求五个评测角色均有 `voiceFingerprint`，五个值互不相同，并分别包含 Alex 的“短答/具体细节/得意或挑战”、Wizard 的“判断/观察对象”、Sophia 的“轻柔接住/创作或酿造细节”、Shane 的“短答/实际照顾或自嘲”、Sebastian 的“具体对象/冷幽默或短句”这些可执行特征；同时断言指纹不要求统一主题。

- [ ] **步骤 2：运行策略测试确认红灯**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_stage_policy.py
  ```

  预期：新增断言因当前策略没有 `voiceFingerprint` 而失败，已有测试收集和 fixture 正常。

- [ ] **步骤 3：先写失败的 Prompt 行为测试**

  在 `test_prompts.py` 增加两类断言：

  1. `stage_execution_card` 对每个角色都包含“直接回答后最多追加一个角色化动作”，并明确不要求同时解释、表达、追问和安排；
  2. `conversation_lead` 的普通 chat 指令同样包含单动作预算，且仍保留当前输入优先、具体对象和角色指纹。

- [ ] **步骤 4：运行 Prompt 测试确认红灯**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py
  ```

  预期：新增 Prompt 断言因当前输出没有单动作预算和指纹投影而失败，不因导入或测试数据错误失败。

- [ ] **步骤 5：写最小策略实现**

  在 `stage_policy.py` 增加五个 canonical 角色的短指纹，并在 `build_stage_policy()` 的结果中返回 `voiceFingerprint`；Rasmodia 继续通过 `canonical_npc_id()` 复用 Wizard。不要改写 canonical persona 和关系策略。

- [ ] **步骤 6：写最小 Prompt 实现**

  在 `_compact_stage_policy()` 保留 `voiceFingerprint`，在 `_stage_execution_instruction()` 把它作为执行提示加入；把 `_build_conversation_lead_card()` 的“回答后继续推进”改为“直接回答后最多追加一个角色化动作”，明确不要强行同时解释、抒情、追问和安排。保留当前的 lead 类型、skip 条件、渠道限制和质量评测契约。

- [ ] **步骤 7：运行定向测试确认绿灯**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py
  ```

  预期：定向策略与 Prompt 测试全部通过。

---

### 任务 2：补少量五角色口语化行为样例并验证索引投影

**文件：**
- 修改：`data/personas/behavior-examples.json`
- 修改：`bridge/tests/test_profile_context.py`
- 修改：`bridge/tests/test_generate_behavior_examples.py`

- [ ] **步骤 1：先写样例覆盖测试**

  增加测试，要求五个角色各至少有一条新增的 `voice-distinctiveness` 样例，样例必须是 `handcrafted_example` 或 `human_approved`，包含 `playerInput`、`npcReply`、`topicKeywords` 和当前角色的具体表达动作；测试还要确认这些样例可被 `ProfileIndexStore.behavior_examples()` 选出，而不是只存在于原始 JSON。

- [ ] **步骤 2：运行测试确认红灯**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_profile_context.py bridge/tests/test_generate_behavior_examples.py
  ```

  预期：新增样例 ID 尚不存在，测试失败；现有行为样例校验保持可收集。

- [ ] **步骤 3：增加最小样例集**

  为 Wizard/Rasmodia、Sophia、Shane、Sebastian、Alex 各增加 1–2 条短成对样例：只展示说话方式和一个具体对象，不写动作旁白、不制造未来排期、不替其他 NPC 发言、不改变关系边界。Alex 样例重点使用短答、身体/球/海滩细节和轻微挑战；其他角色分别保留判断、创作细节、实际照顾、自嘲/冷幽默。

- [ ] **步骤 4：运行样例和索引测试确认绿灯**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_profile_context.py bridge/tests/test_generate_behavior_examples.py
  ```

  预期：新增样例均能通过现有索引和 Prompt 上下文筛选。

---

### 任务 3：Bridge 级回归与脱敏的本地 Prompt 预览

**文件：**
- 修改：`docs/active-work.md`
- 读取：`bridge/src/stardew_ai_bridge/config.py`、项目现有 `.env.local`（只做字段和非空检查，不输出值）

- [ ] **步骤 1：运行 Bridge 定向回归、语法检查和差异检查**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py bridge/tests/test_profile_context.py bridge/tests/test_generate_behavior_examples.py
  py -3.10 -B -m compileall -q bridge/src scripts
  git diff --check
  ```

  预期：定向测试通过，编译检查退出码为 `0`，差异检查无新增错误。

- [ ] **步骤 2：运行 Bridge 全量回归**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests
  ```

  预期：全量通过；若失败，先按 systematic debugging 定位，不把失败归咎于 Gemini Key。

- [ ] **步骤 3：构造不调用 Provider 的五角色 Prompt 预览**

  使用现有 `PromptBuilder` 和新建的唯一临时/预览工件路径，检查五个角色的 `stage_execution_card`、`conversation_lead`、`voice_execution_card` 是否都存在且含各自指纹；只输出角色名、卡片字段、消息数和脱敏短摘要，不输出环境文件、Authorization、Key 或完整敏感请求。

- [ ] **步骤 4：更新活动记录**

  在 `docs/active-work.md` 顶部追加本轮真实测试结果、工作树保留情况、未启动游戏/Bridge 的事实，以及 Gemini 真实请求仍需账号条件满足后按既定顺序进行的说明；不覆盖历史记录，不创建提交。

---

### 任务 4：云端验证门控

**文件：**
- 读取：项目现有 `.env.local`
- 运行：现有 `scripts/start_bridge.ps1` 和项目既有质量评测脚本

- [ ] **步骤 1：只做脱敏配置核验**

  确认官方 Gemini URL、`gemini-3.7-flash`、`BRIDGE_CLOUD_ENABLED=true`、`BRIDGE_CLOUD_ONLY=true`、`BRIDGE_CLOUD_TIMEOUT=45`，只报告 Key 非空和长度，不输出实际值或完整 env。

- [ ] **步骤 2：按项目顺序重载并证明 Bridge 来源**

  确认 5678 监听 PID/命令行指向本工作树并检查 `/health`；另用关系案例接口确认不是旧 Bridge。`/health=200` 只能作为服务证据，不能作为 Gemini 成功证据。

- [ ] **步骤 3：最小官方 Gemini 冒烟后再决定评测**

  真实请求必须核验 HTTP、返回结构、`provider`、`fallback`、延迟和 usage；遇到 401/403/429/超时/格式不兼容/fallback 就停止，不执行批量评测。只有最小请求成功时，才按既定流程创建新的 5 案例/15 轮和五套独立完整评测目录。

---
