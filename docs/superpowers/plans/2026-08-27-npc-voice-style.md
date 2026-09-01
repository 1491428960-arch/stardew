# 五个评测角色口语风格修复实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现。用 `update_plan` 跟踪整体状态，并保留文档中的复选框。

**目标：** 让 Dialogue Lab 的五个评测角色具有可区分、可测试的口语风格，并把 Wizard/Rasmodia 统一为同一个 canonical NPC 与关系历史。

**架构：** 在资料层提供明确的 `voiceStyle` 口语卡，在 `PersonaStore` 与 `ProfileIndexStore` 统一 Wizard/Rasmodia 的 canonical ID；Prompt 只注入当前角色的约束和经过来源过滤的语气证据。Dialogue Lab 使用固定评测配置，为每个按钮提供独立来源 Mod 和 canonical 历史筛选。

**技术栈：** Python 3.12、FastAPI、pytest、JSON persona/profile index、内嵌 HTML/JavaScript Dialogue Lab。

---

### 任务 1：建立 canonical NPC 与资料层口语卡的失败测试

**文件：**
- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/tests/test_profile_context.py`
- 修改：`bridge/tests/test_profile_index.py`

- [ ] **步骤 1：编写失败测试**

  增加测试，明确 `Rasmodia` 请求在 Romanceable Rasmodius 来源下返回 `npcId == "Wizard"`、能检索 Wizard 证据；无该来源时不出现 Rasmodia 覆盖；Wizard/Rasmodia 共享 voice card 和历史检索；五个评测角色均有 `tone`、`sentencePattern`、`responseRules`、`preferredTopics`、`openers`、`closers`、`avoid`、`emotionRange`，且 tone 不完全相同。

- [ ] **步骤 2：运行测试验证失败**

  运行：`$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'; $env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_prompts.py bridge/tests/test_profile_context.py bridge/tests/test_profile_index.py`

  预期：新增的 canonical/voice-card 断言失败，证明现有实现仍将 Rasmodia 当作独立 ID 或缺少完整口语字段。

- [ ] **步骤 3：编写最少实现代码**

  在 `personas.py` 提供单一 canonical 化函数；让 `PersonaStore` 以 `Wizard` 查找基础资料，并仅在来源包含 Romanceable Rasmodius 时应用 Rasmodia overlay。让 `profile_index.py` 的检索和 `voice_card` 入口先 canonical 化请求 ID，并把旧索引中的 Rasmodia 记录归入 Wizard 结果而不创建第二条历史链。补充五个角色的显式口语卡字段。

- [ ] **步骤 4：运行测试验证通过**

  运行同上定向 pytest 命令，预期所有相关测试通过。

### 任务 2：移除统一书面化 Prompt，接入角色专属约束

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 修改：`bridge/tests/test_prompts.py`

- [ ] **步骤 1：编写失败测试**

  对 Wizard、Sophia、Shane、Sebastian、Alex 构造 Prompt，断言每个 Prompt 包含其专属 `voiceStyle` 规则和示例；断言所有 Prompt 不包含统一的「还算顺利」示例；断言日常输入仍直接回答，但不强制所有角色使用同一句式；断言 Wizard/Rasmodia canonical 身份一致。

- [ ] **步骤 2：运行测试验证失败**

  运行：`$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'; $env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_prompts.py`

  预期：至少在统一示例和角色专属约束断言处失败。

- [ ] **步骤 3：编写最少实现代码**

  调整 `PromptBuilder` 的消息构造顺序和内容：安全规则、canonical 身份、当前 voiceStyle、少量来源过滤后的 speech/style evidence、事实与历史、玩家输入。删除跨角色的具体开场示例，保留 1–3 句和日常直接回答等格式规则；不加入字符串后处理。

- [ ] **步骤 4：运行测试验证通过**

  运行上述 Prompt 定向测试，预期全部通过。

### 任务 3：固定 Dialogue Lab 五个评测按钮及来源隔离

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
- 修改：`bridge/tests/test_external_dialogue_lab.py`

- [ ] **步骤 1：编写失败测试**

  断言页面包含固定顺序 `Wizard`、`Sophia`、`Shane`、`Sebastian`、`Alex` 的评测配置；Rasmodia/Wizard 按钮显示为同一评测配置；每个配置携带独立来源 Mod；请求使用 canonical ID 和当前配置的来源，不再向所有角色发送全量来源。

- [ ] **步骤 2：运行测试验证失败**

  运行：`$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'; $env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_external_dialogue_lab.py`

  预期：固定配置或来源隔离断言失败。

- [ ] **步骤 3：编写最少实现代码**

  在页面脚本中维护固定评测配置；Wizard/Rasmodia 使用 `Wizard` 作为历史和请求 ID，只有显示名/来源覆盖随配置切换。发送、找话题、切换和恢复会话均按 canonical ID 筛选，并保持已有持久化会话兼容。

- [ ] **步骤 4：运行测试验证通过**

  运行上述页面定向测试，预期全部通过。

### 任务 4：重建派生索引并做全量自动验证

**文件：**
- 生成：`data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json`
- 修改：仅在需要时更新 `docs/active-work.md` 的本轮状态记录

- [ ] **步骤 1：重建索引**

  使用项目现有 `scripts/build_profile_index.py` 命令重建中文联合索引，保留生成文件为派生工件，不把运行状态、密钥、Token 或用户会话写入 Git。

- [ ] **步骤 2：验证索引内容**

  读取生成索引，核对 Wizard 为唯一 canonical 语料键、五个角色存在独立 profile/voiceCard，统计值和警告数记录实际输出。

- [ ] **步骤 3：运行完整 Bridge 测试**

  运行：`$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'; $env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests`

  预期：完整 Bridge 测试 0 失败；警告数量如有变化则如实记录。

### 任务 5：本地 Bridge 与浏览器小样本复核

**文件：**
- 不新增运行状态文件到仓库

- [ ] **步骤 1：核对运行服务**

  确认 `GET http://127.0.0.1:5678/health` 返回当前 `provider=local`，`GET /test` 返回更新后的页面；重启时同时核对包装 PowerShell 和实际绑定 5678 的子进程。

- [ ] **步骤 2：在浏览器生成小样本**

  在 `http://127.0.0.1:5678/test` 对每个固定角色发送 3–5 条相同或相近输入，覆盖问近况、表达关心、找话题和追问；切换 Wizard/Rasmodia 检查显示名变化但历史连续。

- [ ] **步骤 3：视觉与文本复核**

  通过浏览器截图和页面文本确认五个角色均有记录、句式不再共享「还算顺利」、日常问题不普遍强行魔法化，并记录仍然不自然的本地模型输出，不以小样本人工观察替代自动化测试。

- [ ] **步骤 4：更新活动记录并汇报边界**

  在 `docs/active-work.md` 写入实际测试数字和浏览器证据；明确本轮只验证网页/Bridge 角色风格，未验证游戏内新 DLL 或游戏端跨重启历史。

