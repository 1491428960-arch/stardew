# 好感度 NPC 全覆盖与剧情上下文设计

## 目标

让“能否使用 AI 对话”由 NPC 是否存在原版友谊记录决定，而不是由是否可恋爱决定；同时让测试工作台和模型上下文能够覆盖普通友谊 NPC，并为高好感、背景故事、已知人物和已完成剧情提供可追溯输入。

## 范围与边界

- Bridge 的 NPC 目录来自当前 profile index 的有效角色 profile 与对白证据，合并 `PersonaStore` 中的手工资料；不再只遍历 4 个可恋爱角色和 Wizard。
- 生成索引中的对白角色不等于游戏内一定可建立友谊。浏览器显示的是“当前索引可测试角色”；游戏内的最终资格由 `player.friendshipData` 实时判断。
- Wizard 与 Rasmodia 保持 canonical `Wizard`，显示名仍由当前内容包覆盖决定。
- 只把 `canon_confirmed`、`runtime_confirmed`、`player_provided` 且满足事件门槛的知识事实交给模型；未完成事件和未确认传闻不进入上下文。
- 本轮覆盖 Vanilla、当前索引已有的 SVE 与 Romanceable Rasmodius 资料；Ridgeside/East Scarp 仅在它们被重新建索引后自动进入目录，不虚构资料覆盖。
- 不把模型生成回复写回角色资料库，不把测试结果当作 canonical 事实。

## 方案

### 1. 资料与目录

在 `ProfileIndexStore` 增加只读目录方法，按 canonical NPC ID 合并 `profiles`、`speechEvidence`、`styleSamples` 和 `voiceCards` 中出现的角色，输出 `npcId`、`displayName`、`sourceMods`、`hasDialogueEvidence`。过滤明显不是 NPC 的对白资源键（例如 `MarriageDialogue*`、`rainy`），但不按恋爱资格过滤。

`/api/npcs` 合并 PersonaStore 与 ProfileIndexStore 目录，并返回来源信息。网页下拉框使用整个目录，五个重点角色按钮仅作为快捷入口，不再作为可用角色边界。

### 2. 结构化角色知识

扩展索引的知识字段：

- `knowledgeFacts`：角色自己知道或可安全谈论的事实；每项有 `factId`、`npcId`、`sourceMod`、`summary`、`knowledgeScope`、`confidence`、`sourceRefs`，可选 `requiredEventId`。
- `knownCharacters`：角色与其他 NPC 的已确认关系或认知；每项有 `subjectNpcId`、`knownNpcId`、`relation`、`summary`、`knowledgeScope`、`sourceRefs`，可选 `requiredEventId`。
- `storyEvents`：角色参与的剧情候选；每项有 `eventId`、`sourceMod`、`sourceKey`、`participants`、`summary`、`canonical`，运行时完成 ID 命中后标记 `completed`。

为了让没有手工 profile 的普通 NPC 也能工作，索引器从 `data/personas/vanilla.json` 的结构化资料加载这些字段；没有资料时保留原文语气证据和保守默认人设，不编造背景。

### 3. 游戏内目标选择

新增纯规则目标排序：指针/交互 tile 命中的友谊 NPC优先，其次是当前地点距离玩家最近的友谊 NPC；候选必须有非空 ID、可用对象、`friendshipData` 记录，且不在事件/节日保护状态下。保留旧的 `ResolveTargetName(Func<string,bool>)` 兼容测试和床边视觉测试的 Wizard/Rasmodia 回退，但正常 F8 入口改走实时友谊候选。

## 验收标准

- `/api/npcs` 包含至少一名不可恋爱但有原版对白/友谊的 NPC（例如 `Caroline`、`Marnie` 或 `Willy`），且不会只返回重点五人。
- 普通 NPC 的上下文包含其有限语气证据；高好感阶段使用 `close`/`married` 等阶段 profile，不会把未完成事件事实送入 prompt。
- 角色提到已知人物时，只有 `knownCharacters` 中有来源且满足门槛的条目进入上下文。
- F8 目标规则测试证明：普通友谊 NPC 可以被选中；无友谊记录的 NPC 不会被选中；命中目标优先于距离排序。
- Bridge 与 C# 测试通过；实际 Bridge 重启后确认 `/health`、`/api/npcs` 和 `/api/context/preview` 来自当前 worktree。未构建/部署 DLL 前不宣称游戏已加载新版本。
