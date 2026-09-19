# NPC 角色覆盖扩展实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 按任务顺序执行；每个任务先完成红灯测试，再写最小实现。保留当前工作树全部既有未提交修改，不创建 Git commit。

**目标：** 在不改变 canonical `npcId` 和基础人格来源的前提下，补齐 Elliott、Harvey、Sam 的女性化男性恋爱角色表达层，并为 `female-bachelors` 增加资格门控，随后按同一资料结构完善其余尚未覆盖的正常角色。

**架构：** 将“女性化”限定为独立的表达 overlay：只有 `Wizard`、`Shane`、`Sebastian`、`Alex`、`Elliott`、`Harvey`、`Sam` 可以应用；`Sophia`、女性角色及非恋爱角色不应用。资格判断集中在 `personas.py`，PersonaStore、ProfileIndex 和 NPC 列表入口共享该判断，避免错误 overlay 替换名字、代词或 vanilla 证据。表达指纹、主动引导、关系讨论和亲密阶段策略仍放在现有 `stage_policy.py`，质量案例继续复用现有套件的数据结构。

**技术栈：** Python 3.10、pytest、JSON persona 数据、现有 Bridge Prompt/ProfileIndex/质量评测管线。

---

### 任务 1：为女性化 overlay 增加集中式资格门控

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/personas.py`
- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`
- 修改：`bridge/src/stardew_ai_bridge/app.py`
- 测试：`bridge/tests/test_persona_layers.py`
- 测试：`bridge/tests/test_profile_index.py`
- 测试：`bridge/tests/test_api.py`

- [x] **步骤 1：编写失败的测试**

  在 persona 测试中导入 `is_female_bachelor_eligible`，断言 `Wizard`、`Shane`、`Sebastian`、`Alex`、`Elliott`、`Harvey`、`Sam` 为真，`Sophia`、`Caroline`、`Marnie`、`Linus` 为假；断言 `PersonaStore.get_persona("Sophia", ["female-bachelors"])` 不改变 Sophia 的正常 `displayName`、代词和 `genderPresentation`。

  增加一个临时 persona 目录：`vanilla.json` 定义 `Caroline`，`female-bachelors.json` 故意给 `Caroline` 写一个伪 overlay。断言 `PersonaStore.get_persona("Caroline", ["female-bachelors"])` 不应用该 overlay；ProfileIndex 的 `Caroline` profile 不因该来源抑制 vanilla 语料；`/api/npcs` 不把 Caroline 解析成 overlay 名字。

- [x] **步骤 2：运行测试验证失败**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider `
    bridge/tests/test_persona_layers.py `
    bridge/tests/test_profile_index.py `
    bridge/tests/test_api.py
  ```

  预期：新增资格函数导入或门控断言失败，证明当前任意 NPC 只要声明 `female-bachelors` 就可能应用 overlay。

- [x] **步骤 3：编写最少实现代码**

  在 `personas.py` 定义不可变资格集合和 `is_female_bachelor_eligible(npc_id)`，通过 `canonical_npc_id()` 处理 `Rasmodia -> Wizard`。在 `merge_persona()` 或 `PersonaStore.get_persona()` 应用 overlay 前跳过不合资格的 `female-bachelors` marker；ProfileIndex 的 `_has_female_bachelors_overlay()` 首先调用同一资格函数；`app.py` 的 NPC 列表解析女性化显示名前同样检查资格。

- [x] **步骤 4：运行测试验证通过**

  运行同一步骤 2 的命令，预期全部通过，并确认现有 Shane/Sebastian/Alex/Wizard overlay 回归不变。

---

### 任务 2：补齐 Elliott、Harvey、Sam 的女性化表达资料

**文件：**
- 修改：`data/personas/female-bachelors.json`
- 测试：`bridge/tests/test_persona_layers.py`
- 测试：`bridge/tests/test_prompts.py`

- [x] **步骤 1：编写失败的测试**

  为三个角色增加参数化断言：应用 overlay 后仍保留 canonical `npcId`，`displayName` 为女性化显示名，代词为 `she/her/her`，`genderPresentation.layer == "expression_only"`、`basePersonaPriority == "higher"`，并且存在角色专属 `voiceStyle`、七阶段 `stageProfiles` 和 `knowledgeRules`。断言三人的 `voiceStyle`、偏好话题和情绪范围互不相同。

- [x] **步骤 2：运行测试验证失败**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider `
    bridge/tests/test_persona_layers.py `
    bridge/tests/test_prompts.py -k 'Elliott or Harvey or Sam or female_bachelors'
  ```

  预期：三个角色缺少表达层而失败。

- [x] **步骤 3：编写最少实现代码**

  在 `female-bachelors.json` 补充：

  - Elliott：保留文学/审美兴趣，但用短句、具体物件和现场感受表达，避免长篇修辞和泛泛抒情；亲密时表达“想把某个具体发现先告诉玩家”，不替玩家安排未来日期。
  - Harvey：温和、谨慎、观察细节，关心优先落在实际照料、状态确认和明确边界，避免医生讲课腔、过度专业化和空泛安慰。
  - Sam：外向、随和、有行动感，保留音乐、滑板和街头活力；用具体动作和轻微玩笑推进，避免每句感叹、幼稚化和只说“太酷了”。

  每人补全 `genderPresentation`、`voiceStyle`、七个 `stageProfiles` 和 `knowledgeRules`，只改变表达/显示名/代词，不改 canonical ID、核心人格、恋爱资格或未确认事实边界。

- [x] **步骤 4：运行测试验证通过**

  运行步骤 2 的定向测试和 persona 全文件结构检查，预期全部通过。

---

### 任务 3：为三名角色增加主动引导、关系讨论与亲密阶段策略

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/stage_policy.py`
- 测试：`bridge/tests/test_stage_policy.py`
- 测试：`bridge/tests/test_prompts.py`

- [x] **步骤 1：编写失败的测试**

  将三人加入角色策略测试集合，断言各自在 friend/close/dating/married 阶段有 `conversationLead`、`relationshipDiscussion`、角色专属 `voiceFingerprint` 和 `affectionInitiative`。分别检查 Elliott 的具体审美落点、Harvey 的实际照料、Sam 的音乐/行动感；同时断言 Sophia 仍使用自己的正常女性策略，Caroline/Marnie/Linus 没有 `conversationLead`。

- [x] **步骤 2：运行测试验证失败**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider `
    bridge/tests/test_stage_policy.py `
    bridge/tests/test_prompts.py
  ```

  预期：三人不在五角色试验集合，缺少角色专属策略而失败。

- [x] **步骤 3：编写最少实现代码**

  将 Elliott、Harvey、Sam 加入主动引导和角色专属策略映射；为三人定义不同的 allowed kinds、role guidance、voice fingerprint、关系讨论指导和 dating/married 的亲密信号。保留现有“一轮最多一个角色化动作”、远程不写成已见面、不得替其他 NPC 发言、不得制造未来日期/预约/排期/日程承诺的共享边界。

- [x] **步骤 4：运行测试验证通过**

  运行步骤 2 的定向测试；随后用无云端 Prompt 构造确认三人的 canonical ID、女性化显示名和 she/her/her 都投影到 identity card，Sophia 仍不出现 female-bachelors overlay。

---

### 任务 4：补充三名角色的可追溯行为样例

**文件：**
- 修改：`data/personas/behavior-examples.json`
- 测试：`bridge/tests/test_generate_behavior_examples.py`
- 测试：`bridge/tests/test_profile_index.py`

- [x] **步骤 1：编写失败的测试**

  断言 Elliott、Harvey、Sam 各至少有一条 `handcrafted_example` 普通聊天样例和一条 dating/married 亲密样例；来源、canonical ID、阶段、频道、initiativeKind 合法，并能在 ProfileIndex 中被检索到。

- [x] **步骤 2：运行测试验证失败**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider `
    bridge/tests/test_generate_behavior_examples.py `
    bridge/tests/test_profile_index.py
  ```

  预期：三个角色当前没有样例而失败。

- [x] **步骤 3：编写最少实现代码**

  为三人各添加两条短、具体、可复用的中文示范：一条普通近况/兴趣，一条亲密阶段的当前动作或情绪表达。样例不得替其他 NPC 说话，不得包含未来日期或确定预约，不得把线上状态写成已见面。

- [x] **步骤 4：运行测试验证通过**

  运行步骤 2 的命令，并检查 ProfileIndex 只把样例作为行为证据，不把 persona overlay 当 dialogue source。

---

### 任务 5：扩展质量评测案例并拆分女性化资格与恋爱资格

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 修改：`bridge/src/stardew_ai_bridge/topic_start_intimacy_cases.py`
- 修改：`bridge/src/stardew_ai_bridge/affection_pacing_cases.py`
- 修改：`bridge/src/stardew_ai_bridge/relationship_world_cases.py`
- 测试：`bridge/tests/test_character_quality_eval.py`

- [x] **步骤 1：编写失败的测试**

  将 `DEFAULT_CHARACTER_PROFILES`、default/conversation-lead/topic-start/affection 套件的覆盖断言扩展到 Elliott、Harvey、Sam；断言 Sophia 可以保留恋爱资格但不被标为女性化男性角色；断言三人的案例使用 `source_mods=("vanilla", "female-bachelors")`、`gender_presentation="female-bachelors"` 和 canonical ID。

- [x] **步骤 2：运行测试验证失败**

  运行：

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py
  ```

  预期：三人不在 profile/case catalog，覆盖断言失败。

- [x] **步骤 3：编写最少实现代码**

  保留 `_ROMANCE_ELIGIBLE_NPCS` 对 Sophia 的包含；另定义/导入仅包含七名男性恋爱角色的女性化集合，不能用一个集合同时表达两种语义。给三人添加最小但完整的 default、主动引导、topic-start 和 affection pacing 案例，覆盖忠诚、玩家与他人交往时的不安/吃醋、不替其他 NPC 发言、无未来排期承诺、代词/显示名/canonical ID、关系修复和线上线下承接边界。

- [x] **步骤 4：运行测试验证通过**

  运行步骤 2 的命令，核对各套例数和角色分布；禁止调用云端或启动 Bridge。

---

### 任务 6：无云端回归和其余正常角色覆盖清单

**文件：**
- 修改：`bridge/tests/test_persona_layers.py`
- 修改：`bridge/tests/test_stage_policy.py`
- 修改：`bridge/tests/test_character_quality_eval.py`
- 修改：`docs/active-work.md`

- [x] **步骤 1：运行定向回归**

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider `
    bridge/tests/test_persona_layers.py `
    bridge/tests/test_prompts.py `
    bridge/tests/test_stage_policy.py `
    bridge/tests/test_profile_context.py `
    bridge/tests/test_profile_index.py `
    bridge/tests/test_character_quality_eval.py
  ```

- [x] **步骤 2：运行完整 Bridge 验证**

  ```powershell
  $env:PYTHONPATH='bridge/src'
  py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests
  py -3.10 -B -m compileall -q bridge/src scripts
  git diff --check
  ```

- [x] **步骤 3：执行无云端 Prompt/索引验收**

  直接调用 PersonaStore、ProfileIndexStore 和 PromptBuilder，确认：

  - 七名女性化男性恋爱角色使用女性化显示名与 `she/her/her`，canonical ID 不变；
  - Sophia 使用自己的 SVE 正常人格，不出现 female-bachelors overlay；
  - Caroline、Marnie、Linus 及其他正常角色不被女性化门控误伤；
  - 三人策略包含角色差异和边界约束；
  - 没有任何云端请求、Bridge 重载、游戏启动或正式 Mods/存档写入。

- [x] **步骤 4：更新活动记录并安排下一批正常角色**

  在 `docs/active-work.md` 顶部记录真实测试证据与未解决阻碍。已按资料完整度处理 `Victor`、`Olivia`、`Andy`、`Lance`、`Claire`、`Morris`；`Caroline`、`Marnie`、`Linus` 的既有资料已纳入验收，全部沿用 Sophia 的“正常性别表达”原则，不套女性化 overlay。

### 计划执行补充（2026-09-09）

- `Victor`、`Olivia`、`Andy`、`Lance`、`Claire`、`Morris` 已补齐 SVE 正常性别表达卡、七阶段资料、知识边界和短行为样例；`Caroline`、`Marnie`、`Linus` 的 vanilla 正常资料已纳入统一验收。
- 这 6 名 SVE 角色没有加入 `female-bachelors`，也没有加入女性化男性恋爱质量目录；后续普通角色评测应沿用正常 `SVE` 来源与各自代词。
- 角色资料相关联合回归为 `382 passed`，Bridge 全量回归为 `1190 passed`；`compileall` 和 `git diff --check` 均通过；无云端 Prompt / ProfileIndex 验收确认 Provider 调用数为 `0`。
