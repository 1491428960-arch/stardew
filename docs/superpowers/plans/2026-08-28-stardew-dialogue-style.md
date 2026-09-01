# Stardew 对话角色风格与阶段检索实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 在当前工作树逐任务实现，并用 `update_plan` 跟踪整体状态；保留文档中的复选框。

**目标：** 让 Bridge 从正确的 Stardew 原文分支和当前关系阶段中取证，并以紧凑、成对的 few-shot 对话约束本地模型，使五个角色的回复更像游戏原有语言风格且能承接连续对话。

**架构：** 在语料提取层保留控制脚本原文，同时拆出可检索的干净对白变体；在索引层解析 `Mon6` 等好感阈值并过滤不适用阶段；在 Prompt 层把人工示例投影为相邻的 `user → assistant` 消息，限制证据和历史总量，保留角色卡与当前话题约束。Wizard/Rasmodia 继续使用 canonical `Wizard`，只由 Romanceable Rasmodius 提供显示名与语气覆盖。

**技术栈：** Python 3.10+、pytest、FastAPI Bridge、JSON 离线索引、Ollama `qwen3.5:9b`。

---

### 任务 1：为原文控制分支和关系阶段建立红灯测试

**文件：**
- 修改：`bridge/tests/test_corpus.py`
- 修改：`bridge/tests/test_profile_index.py`

- [ ] **步骤 1：编写失败的测试**

在 `test_corpus.py` 增加一个包含 `^`、`||`、`#$b#`、`$q/$r` 的 `EditData` 条目，断言提取结果保留 `text` 原文，并产生多个 `dialogueVariants`；每个变体去除控制标记、保留可读中文，不把分支连接符喂给最终语气样本。

在 `test_profile_index.py` 增加 `Mon`、`Mon6`、`Mon8`、`Mon10` 四条同一 NPC 原版样本，使用 `relationship_stage="friend"` 检索，断言不返回初识 `Mon`，而返回 `Mon6` 或更高阶段中的一条；使用 `relationship_stage="stranger"` 检索时断言只返回初识条目。

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_corpus.py bridge/tests/test_profile_index.py
```

预期：新增控制分支字段与 `Mon6` 阶段选择断言失败，现有测试保持可定位的失败输出。

### 任务 2：实现语料变体和原版好感阈值解析

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/corpus.py`
- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`

- [ ] **步骤 1：实现最小语料解析**

新增纯函数把 Stardew 控制脚本拆成稳定的文本变体：去除 `#$b#`、`#$e#`、`$q/$r`、表情/动作标记和 `^`/`||` 分支连接；原始 `text` 仍完整保留，清洁结果写入 `dialogueVariants`，有清洁结果时 `resolvedText`/检索文本使用清洁变体而不是控制脚本。

- [ ] **步骤 2：实现最小阶段解析**

从 `sourceKey` 匹配 `Mon6`、`Tue8`、`Wed10` 等键，把数字解释为好感心数，写入 `conditions.relationshipStage`；`Mon` 等普通日常键标记为 `stranger`，并让阶段匹配支持“当前阶段可以使用不高于当前心级的关系对白”，但不能让朋友阶段回退到初识对白。保留婚后/室友现有 `married` 条件。

- [ ] **步骤 3：运行定向测试验证通过**

运行同任务 1 的 pytest 命令，预期语料与阶段测试全部通过。

### 任务 3：把人工行为示例投影为真实 few-shot 消息

**文件：**
- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 必要时修改：`bridge/src/stardew_ai_bridge/profile_index.py`

- [ ] **步骤 1：编写失败的测试**

增加断言：`PromptBuilder.build()` 对一个行为示例生成相邻的 `user` 和 `assistant` 消息，示例中的 NPC 回复不再只出现在 JSON 资料块中；历史仍出现在当前输入前，且相邻示例不会被当作当前会话历史。

增加长度回归：带完整角色卡、6 条 speech evidence、8 条 style samples、4 条行为示例和 12 条历史消息的 Prompt 序列化长度低于 `16000` 字符，并且角色身份、当前玩家输入和最近历史仍存在。

增加历史窗口回归：`ContextBuilder` 从 16 条输入中保留最后 12 条，而不是最后 6 条。

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_prompts.py
```

预期：成对消息、16000 字符预算和 12 条历史断言在当前实现上失败。

- [ ] **步骤 3：实现最小 Prompt 修改**

把行为示例按筛选后的 `playerInput`/`npcReply` 逐条追加为 `user`、`assistant` 消息，保留示例元数据在一个短的 system 说明中；把证据投影字段缩短为模型需要的来源、键和文本；统一限制证据数量和字符数；把 ContextBuilder 历史截取窗口设为 12，并在 Prompt 末尾再次强调当前角色 voiceStyle、当前话题和当前输入。

- [ ] **步骤 4：运行定向测试验证通过**

运行同任务 3 的 pytest 命令，预期新增和已有 Prompt 测试全部通过。

### 任务 4：重建索引并做完整回归

**文件：**
- 生成：`data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json`
- 修改：仅在测试暴露契约变化时修改 `bridge/tests/test_api.py`

- [ ] **步骤 1：重建中文联合索引**

使用项目现有 `scripts/build_profile_index.py` 参数重建 `vanilla + SVE + Romanceable Rasmodius` 中文索引，输出到上述生成文件；不修改 Token、Cookie、个人数据和正式游戏存档。

- [ ] **步骤 2：运行完整 Bridge 测试**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests
```

记录实际通过数、失败数和警告，不沿用旧结果。

- [ ] **步骤 3：重启并检查 Bridge HTTP 边界**

确认包装 PowerShell 与真正绑定 `5678` 的 Python 子进程来自当前工作树；检查 `/health` 返回 `status=ok`、`provider=local`，并用 `/api/context/preview` 核对 Shane 朋友阶段不再首选初识拒答，Wizard/Rasmodia 仍只有 canonical `Wizard`。

### 任务 5：用干净会话做五角色小样本运行时复核

**文件：**
- 运行时临时会话：仅使用 `BRIDGE_DIALOGUE_SESSION_PATH` 指向临时目录，不覆盖既有用户会话
- 复核：`http://127.0.0.1:5678/test`

- [ ] **步骤 1：清理本轮临时会话**

只删除本轮明确创建的临时评测会话文件；保留用户原有网页记录、正式存档和任何密钥配置。

- [ ] **步骤 2：每个角色发送三轮连续对话**

使用 `Wizard/Rasmodia`、`Sophia`、`Shane`、`Sebastian`、`Alex` 五个按钮，各发送三轮围绕同一话题的短消息，检查第二、三轮是否承接前文并保持各自语气，不把所有角色写成书面总结。

- [ ] **步骤 3：浏览器视觉与接口双重核对**

在浏览器中确认角色按钮切换后记录与当前角色隔离、当前页面无需额外翻页即可看到对话；同时核对接口记录只有消息和脱敏诊断，不含 Token、API key、完整 prompt。保存必要截图并人工检查文字与布局。

