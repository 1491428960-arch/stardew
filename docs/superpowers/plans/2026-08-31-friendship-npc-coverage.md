# 好感度 NPC 全覆盖实现计划

> 本计划在现有 `codex/story-memory` 工作树上内联执行；保留所有已有修改，不执行 reset、checkout 或清理。

## 目标

让所有有友谊/好感度记录的 NPC 都能通过 Bridge 和游戏内 F8 使用 AI 对话，并把高好感、背景、已知 NPC、剧情门槛加入可测试上下文。

## 任务 1：先补 Bridge 红灯测试

**文件：**

- 修改：`bridge/tests/test_profile_index.py`
- 修改：`bridge/tests/test_profile_context.py`
- 修改：`bridge/tests/test_api.py`
- 修改：`bridge/tests/test_external_dialogue_lab.py`

- [x] 增加 `ProfileIndexStore.npc_catalog()` 的目录测试：从 profile、对白证据合并普通 NPC，canonical Wizard/Rasmodia 只出现一次。
- [x] 增加结构化 `knownCharacters`/`storyEvents` 的加载、来源过滤和 `requiredEventId` 门槛测试。
- [x] 增加 `/api/npcs` 返回普通友谊 NPC、来源和对白证据字段的测试。
- [x] 增加页面使用完整目录、重点按钮只是快捷入口的契约测试。
- [x] 运行定向测试，确认新增断言失败且失败原因是缺少实现，而不是测试环境错误。

## 任务 2：实现索引目录与结构化知识

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 修改：`bridge/src/stardew_ai_bridge/app.py`
- 修改：`data/personas/vanilla.json`
- 修改：`data/personas/sve.json`
- 修改：`data/personas/rasmodia.json`

- [x] 在索引 schema 2 中加入 `knownCharacters`，加载并按来源/范围/完成事件过滤。
- [x] 将 `biography` 兼容转换为有来源的 `knowledgeFacts`，同一 `factId` 去重，保留 `requiredEventId`。
- [x] 从 persona 资料加载显式 `storyEvents`，不从普通对白文本猜剧情事件。
- [x] 在 `ContextBuilder` 投影 `knownCharacters`，在 `PromptBuilder` 以独立消息加入“角色知道的其他人物/背景”；为空时保持当前兼容形状。
- [x] `/api/npcs` 合并 PersonaStore 和 ProfileIndexStore 的目录；对外只暴露 NPC ID、显示名、来源和是否有对白证据。
- [x] 为至少 Wizard、Shane、Sophia、Sebastian、Alex 以及 3 名普通友谊 NPC 添加少量来源明确的事实/关系样本，避免无边界人工编造资料。

## 任务 3：让网页工作台真正可选全部目录角色

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
- 修改：`bridge/tests/test_external_dialogue_lab.py`

- [x] `loadNpcs()` 保存目录条目并按当前条目默认显示名/来源；手工重点评测 profile 仍覆盖其特殊 Mod 配置。
- [x] 普通 NPC 通过下拉框可直接进入聊天，不被 `EVALUATION_NPC_IDS` 排除。
- [x] 重点五人按钮文案改成快捷评测，不暗示只有五人可聊；切换时按 canonical ID 清理当前案例状态并恢复该角色记录。
- [x] 页面提示和测试例筛选显示“重点案例”与“全部资料目录”的区别。

## 任务 4：游戏端实时友谊 NPC 目标

**文件：**

- 修改：`smapi/NpcTargetResolver.cs`
- 修改：`smapi/ModEntry.cs`
- 修改：`smapi/tests/NpcTargetResolverTests.cs`

- [x] 增加 `NpcTargetCandidate` 与纯排序方法，覆盖命中、距离、无友谊记录和空候选。
- [x] `ModEntry` 构造当前地点 NPC 候选，从 `Game1.player.friendshipData` 判断资格，优先当前鼠标交互目标，再选最近 NPC。
- [x] F8 无合适友谊 NPC 时给出明确日志并安全退出；视觉测试保留 Wizard/Rasmodia 模板回退。
- [x] 更新启动日志/GMCM 描述，避免继续声称 F8 只与 Rasmodia 对话。

## 任务 5：扩充质量案例与验证

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 修改：`bridge/tests/test_character_quality_eval.py`
- 修改：`docs/active-work.md`

- [x] 增加高好感 `close`/`married` 案例、背景事实案例、已知 NPC 案例和未完成剧情门槛案例，至少覆盖一个普通友谊 NPC。
- [x] 案例定义保持多轮对话结构，不把模型生成结果写回 canonical 资料。
- [x] 运行 Bridge 全套测试、C# 测试和索引重建；核对输出统计与 SHA-256。
- [x] 重启 5678，核对包装器与实际监听子进程、`/health`、`/api/npcs` 和 `/api/context/preview`。
- [x] 只在服务实际指向当前 worktree 且验证了接口后，再在浏览器查看；不启动游戏或部署 DLL，除非后续证据显示需要。
