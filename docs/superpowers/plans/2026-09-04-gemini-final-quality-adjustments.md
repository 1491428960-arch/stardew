# Gemini 最终质量校准实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 逐任务实现，按复选框推进并在每个质量边界保留红灯、绿灯证据。

**目标：** 在不改变千问基线、正式配置、Mods 或存档的前提下，修正 Gemini `conversation-lead` v13 暴露的三个窄问题：Sebastian 不再因普通靠近/听歌动作重复拥抱，Shane 在低落/拒绝/准备休息时可以直接回应并收口，质量诊断器识别稳定的自然中文个人亲近和酒窖动作承接。

**架构：** 继续沿用现有分层：`stage_policy.py` 提供角色行为约束，`prompts.py` 投影约束，`behavior_quality.py` 负责不改写回复的语义诊断，`guard.py` 只根据诊断决定是否有限重试，`character_quality_eval.py` 只负责评测证据与脱敏结果。修正保持五角色试验范围，不把自然语言词表扩散成全局宽松匹配。

**技术栈：** Python 3.10、pytest、现有 Bridge Prompt/Guard/质量评测模块；验证使用项目自带 Python、Bridge 全量回归、`compileall` 和 `git diff --check`。

---

### 任务 1：收窄 Sebastian 的拥抱动作规则

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/stage_policy.py` 的 `_CONVERSATION_LEAD_ROLE_GUIDANCE["Sebastian"]`
- 修改：`bridge/src/stardew_ai_bridge/prompts.py` 的亲密行为卡紧凑投影（仅在需要时投影角色变化约束）
- 测试：`bridge/tests/test_stage_policy.py`、`bridge/tests/test_prompts.py`

- [x] **步骤 1：编写失败测试**

  在阶段策略测试中断言 Sebastian 的角色引导明确区分“玩家明确提出拥抱”和“玩家只要求靠近/听歌/回房间”，并在 Prompt 测试中断言 compact 卡保留该约束。测试还要确认 `拥抱` 仍出现在明确拥抱的允许路径中。

- [x] **步骤 2：运行测试验证失败**

  运行：`$env:PYTHONPATH='bridge\src'; py -3.10 -m pytest bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py -k 'sebastian and (hug or embrace or affection or conversation_lead)' -q`

  预期：新增断言失败，因为当前角色引导对“拥抱、靠近、听完音乐后一起走”统一要求出现“抱”。

- [x] **步骤 3：编写最少实现代码**

  将 Sebastian 的角色引导改为：只有玩家明确提出拥抱/想抱时才直接回应拥抱；玩家只说靠近、分耳机、听歌或听完回房间时，优先回应音乐、耳机、肩并肩、房间或安静的具体对象；若最近一轮已经使用拥抱，本轮改用其他亲近形状。把角色变化规则投影到 compact 亲密卡，避免云端经济 Prompt 看不到这条限制；不改其他 NPC 的亲密约束。

- [x] **步骤 4：运行测试验证通过**

  运行：`$env:PYTHONPATH='bridge\src'; py -3.10 -m pytest bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py -k 'sebastian and (hug or embrace or affection or conversation_lead)' -q`

  预期：新增断言与既有 Sebastian Prompt/阶段策略测试全部通过。

---

### 任务 2：允许 Shane 在低落、拒绝和准备休息时直接收口

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/behavior_quality.py` 的 Shane guarded 退出识别
- 修改：`bridge/src/stardew_ai_bridge/guard.py` 的缺少主动性/缺少 conversation lead 判断
- 测试：`bridge/tests/test_behavior_quality.py`、`bridge/tests/test_guard.py`、`bridge/tests/test_character_quality_eval.py`

- [x] **步骤 1：编写失败测试**

  新增 Shane `npc_id=Shane`、`initiative_expectation=guarded`、包含 `npc_needs_space`/`explicit_rejection` 的回归，覆盖“心情不好，早点钻被窝里休息”“知道了，今天先不聊了”“先睡吧，明天再联系”等“直接回应状态 + 简短收口”。断言 `conversationLeadKind=lead_exit_allowed` 或等价的 guarded 退出标记，且不产生 `missing_personal_affection`、`missing_proactive_affection`、`missing_conversation_lead` 或 retry。新增一个非 Shane 对照，确认同样含糊的低落句仍遵守其原有策略，不被 Shane 例外放宽。

- [x] **步骤 2：运行测试验证失败**

  运行：`$env:PYTHONPATH='bridge\src'; py -3.10 -m pytest bridge/tests/test_behavior_quality.py bridge/tests/test_guard.py bridge/tests/test_character_quality_eval.py -k 'shane and (close or exit or mood or space or sleep)' -q`

  预期：至少有一条新 Shane 低落短收口测试失败，原因是现有退出词表未覆盖自然的“钻被窝/休息吧/状态不好”表达，或 Guard 仍进入主动话题重试。

- [x] **步骤 3：编写最少实现代码**

  增加仅作用于 Shane `guarded` 模式的低落/拒绝/休息表达识别，并要求回复确实包含状态承认、拒绝或低压力休息/联系中的一项；将其映射为 `lead_exit_allowed`/`guarded_exit_allowed`，使 `_missing_proactive_affection`、`_missing_conversation_lead` 和重试链路跳过强制爱意或新话题。保留玩家收口后的重开检测、明确“别走/继续聊”的反例和非 Shane 的 `npc_needs_space` 既有路径。

- [x] **步骤 4：运行测试验证通过**

  运行：`$env:PYTHONPATH='bridge\src'; py -3.10 -m pytest bridge/tests/test_behavior_quality.py bridge/tests/test_guard.py bridge/tests/test_character_quality_eval.py -k 'shane and (close or exit or mood or space or sleep)' -q`

  预期：新增 Shane 正例、非 Shane 对照和既有收口/重开测试全部通过。

---

### 任务 3：补齐自然中文个人亲近和酒窖动作语义

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/behavior_quality.py` 的个人亲近正则与 conversation-lead 语义等价表
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py` 的自然中文 expected-term 语义映射（如测试需要）
- 测试：`bridge/tests/test_behavior_quality.py`、`bridge/tests/test_character_quality_eval.py`

- [x] **步骤 1：编写失败测试**

  新增低歧义回归：`“今晚的时间本就该留给你”` 识别为 `player_directed_preference`；`“我就想靠你这么近”` 识别为个人指向；玩家在酒窖已经建立上下文后提出 `“再喝一口，然后陪我去里面坐会儿，好吗？”`，回复 `“好，去里面坐吧”` 或 `“带上酒进去坐”` 能判定回答当前动作。保留负例：只有“陪你/一起去/有空来”的功能性安排，以及与酒窖无关的“去里面坐”不能被自动当作亲近或无条件的当前话题回答。

- [x] **步骤 2：运行测试验证失败**

  运行：`$env:PYTHONPATH='bridge\src'; py -3.10 -m pytest bridge/tests/test_behavior_quality.py bridge/tests/test_character_quality_eval.py -k 'natural or semantic or cellar or wine or time or closeness or inside' -q`

  预期：新增的三类自然表达至少各有一条失败，证明测试没有被现有词表意外满足。

- [x] **步骤 3：编写最少实现代码**

  只增加低歧义的个人指向和动作同义映射：把“本就该留给你”纳入时间专属选择，把“靠你这么近”纳入玩家亲近表达；把“去里面坐”及“进去坐/带上酒进去坐”纳入当前动作等价，并限制在玩家当前输入已包含该动作或现有酒窖对象上下文能证明承接时。保持否定表达、纯功能性事务、陪伴冒充爱意和既有 exact/semantic evidence 分栏不变。

- [x] **步骤 4：运行测试验证通过**

  运行：`$env:PYTHONPATH='bridge\src'; py -3.10 -m pytest bridge/tests/test_behavior_quality.py bridge/tests/test_character_quality_eval.py -k 'natural or semantic or cellar or wine or time or closeness or inside' -q`

  预期：新增语义测试和既有负例全部通过，`exactExpectedHits`、`semanticExpectedHits` 与脱敏字段契约不回归。

---

### 任务 4：定向回归、全量验证和最终 Gemini 小批次

**文件：**
- 修改：`docs/active-work.md`，记录本轮修正、测试证据和最终独立批次统计
- 创建：`artifacts/character-quality-eval/20260904-gemini37-flash-conversation-lead-v14-final/`，仅写入脱敏评测工件

- [x] **步骤 1：运行定向回归**

  运行行为质量、Guard、Prompt、阶段策略、质量评测相关测试，确认三项修正组合工作；预期全部通过。

- [x] **步骤 2：运行项目验证**

  在 worktree 使用 Python 3.10 运行 Bridge 全量 pytest；随后运行 `compileall` 和 `git diff --check`。预期 pytest 全绿、compileall 返回 0，diff check 返回 0；既有换行提示单独记录，不把它误报为代码错误。

- [x] **步骤 3：运行独立 Gemini 最终批次**

  使用当前已配置的云端 Provider、同一 `conversation-lead` 五角色套件、compact Prompt、动态玩家输入、最多 45 次请求、300000 Token 上限、每轮最多一次 NPC 重试，输出到全新 `v14-final` 目录，不覆盖 v12/v13，不写入角色资料库。保存完整三轮脱敏 transcript、诊断和 usage。

- [x] **步骤 4：人工复核并更新活动记录**

  逐案例检查 Sebastian 是否只在明确拥抱请求时使用拥抱、Shane 是否能低落/拒绝/睡前自然收口、Wizard/Sophia 的自然个人指向和酒窖动作是否不再误判；同时报告返回率、错误/fallback、重试、Token、单轮通过和完整案例通过。若仍有角色性真实缺口，只记录证据，不把未经确认的对白写回资料库。
