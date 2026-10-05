# 工作线现状总表（2026-10-05）

> **这份文档回答一个问题：现在到底有哪些活在身上，各自做到哪一步了。**
> 起因：`STATE.md` §五 那张「未提交改动清单」从 2026-09-30 之后就没再真正维护过，
> 而工作区里实际躺着 **35 个改动文件 + 19 个新文件**，跨 7 条工作线。
> 本文档是**一次实测快照**，不是长期台账 —— 数字变了要重跑命令，别抄。

---

## 零、三句话结论

1. **代码侧没有欠账**：7 条线的实现、单测、离线验证都齐了，`verify_project.ps1` 全绿。
2. **唯一的共同阻塞是实机验证**：所有 10-04 / 10-05 的工作**没有一个进过游戏**。
3. **文档侧有三处声明与现实不符**（见 §四），其中两处会**误导下一次判断**。

---

## 一、工作线状态总表

图例：✅ 已做 ／ ❌ 未做 ／ ⚠ 部分或不确定

| # | 工作线 | 代码 | 单测 | 离线验证 | **实机** | 最后动作 |
|---|---|---|---|---|---|---|
| 1 | 群聊「每人一份」私有上下文（地基） | ✅ | ✅ 6+3 | ✅ | ❌ | 10-05 |
| 2 | 群聊「打趣」多元关系素材 | ✅ | ✅ 8+2 | ✅ | ❌ | 10-05 |
| 3 | 隐性知识（别的 NPC 说了什么） | ✅ | ✅ 30 C# + 21 Py | ✅ | ❌ | 10-04 |
| 4 | 婚姻的另一端 + 嫉妒闭环 | ✅ | ✅ 8 C# + 3 Py | ✅ | ❌ | 10-04 |
| 5 | 关系世界 / 认识视角 | ✅ | ✅ | ⚠ | ⚠ 修复后未复验 | 10-04 |
| 6 | 亲密尺度角色化 | ✅ | ✅ | ✅ | ❌ | 10-03 |
| 7 | 长度 / 破甲 / 台账 / 评测口径 | ✅ | ✅ | ✅ | N/A | 10-05 |

**「实机」一列全 ❌ 或 ⚠ —— 这就是当前真正的瓶颈。**

补充说明每一条「❌」的含义：

- **线 1 / 2**：DLL 里根本没有这些代码（见 §三），所以不是「验了没过」，是**从没跑过**。
- **线 3**：只有离线端到端（穿透 `payload → ContextBuilder → PromptBuilder`）。
  **触发率天然很低**（要群聊里 NPC 对 NPC 说话），实机要专门构造。
- **线 4**：单测钉住了行为，但**没有任何一次真机观察**；
  ⚠ 且 `SettleDailyJealousy` 挂在 `OnDayStarted`，**得过一天才会跑到**，
  实机验证必须**跨天**，不是开一次游戏就行。
- **线 5**：10-04 那三条问题**本来就是从实机反馈里来的**，但**修复之后没有再回过游戏**。
  ⇒ 「问题是真的」已确认，「修好了」未确认。
- **线 6**：10-03 改的，**从没进过游戏**。

---

## 二、未提交改动归组（梳理前实测：35 改 + 19 新 = 54 项）

命令：`git status --short` / `git diff --stat`（HEAD = `911dd43`）。

> ⚠ 这个数**会因本文档自身的加入而变化**（写完后再跑已显示 55）。
> **引用前请重跑，别抄。** 35 个「改动文件」这一项不受影响。

### 线 1 · 群聊每人一份私有上下文

| 文件 | 规模 |
|---|---|
| `bridge/src/stardew_ai_bridge/group_conversation.py` | +112 |
| `smapi/GroupDialogueMenu.cs` | +110 |
| `smapi/ConversationModels.cs` | +15 |
| `smapi/BridgeClient.cs` | +47（**与线 3 共用**） |
| `bridge/src/stardew_ai_bridge/models.py` | +72（**与线 3 共用**） |
| `bridge/tests/test_group_participant_context.py` | 新 |
| `smapi/tests/GroupDialogueParticipantContextTests.cs` | 新 |

### 线 2 · 群聊打趣

| 文件 | 规模 |
|---|---|
| `smapi/GroupInvitationTemplates.cs` | +69 |
| `smapi/GroupInvitationGenerator.cs` | +39 |
| `smapi/GroupDialogueCoordinator.cs` | +10 |
| `smapi/tests/GroupInvitationTeasingTests.cs` | 新 |
| `smapi/tests/GroupDialogueCoordinatorTests.cs` | +50 |

### 线 3 · 隐性知识

| 文件 | 规模 |
|---|---|
| `smapi/GroupUtteranceRules.cs` | **新建** |
| `smapi/LatentKnowledgeWriter.cs` | **新建** |
| `smapi/StoryStateStore.cs` | +378（**与线 4／5 共用**） |
| `smapi/ConversationService.cs` | +9 |
| `bridge/src/stardew_ai_bridge/app.py` | +6（`_DIALOGUE_FIELDS` 白名单） |
| `bridge/src/stardew_ai_bridge/prompts.py` | +448（**与线 6 共用**） |
| + 8 个新建测试 | 新 |

### 线 4 · 婚姻的另一端 + 嫉妒闭环

| 文件 | 规模 |
|---|---|
| `smapi/StoryStateModels.cs` | +22 |
| `smapi/GameStateCollector.cs` | +69 |
| `smapi/ModEntry.cs` | +80（**多线共用**） |
| `smapi/tests/StoryStateStoreTests.cs` | +263 |
| `bridge/tests/test_marriage_counterpart*.py` | 新 ×2 |

### 线 5 · 关系世界 / 认识视角

| 文件 | 规模 |
|---|---|
| `bridge/src/stardew_ai_bridge/relationship_world.py` | +86 |
| `bridge/src/stardew_ai_bridge/personas.py` | +73 |
| `data/npc-relations.json` | 小改（「小女婴」→「女儿」） |
| `bridge/tests/test_relationship_world.py` | +44 |
| `bridge/tests/test_npc_relations_prompt.py` | +30 |

### 线 6 · 亲密尺度角色化

| 文件 | 规模 |
|---|---|
| `data/personas/vanilla.json` | +221 |
| `data/personas/sve.json` | +134 |
| `data/personas/female-bachelors.json` | +82 |
| `data/personas/rasmodia.json` | +36 |
| `bridge/tests/test_intimacy_policy.py` | 新 |
| `bridge/tests/test_turn_plan_intimacy.py` | 新 |

（四处 persona 改动**同构**：给每个角色加一个 `intimacyPolicy{style, pace, avoidWhen}` 块。）

### 线 7 · 台账 / 评测 / 卡片

| 文件 | 规模 |
|---|---|
| `bridge/src/stardew_ai_bridge/character_quality_eval.py` | +138（含 10-05 补的 6 条 case） |
| `bridge/src/stardew_ai_bridge/stage_policy.py` | +34 |
| `bridge/src/stardew_ai_bridge/guard.py` | +12 |
| `scripts/constraint_scope.py` | +16 |
| `scripts/health_check.py` | +29 |
| `docs/constraint-scope.md` | +20 |
| `bridge/tests/test_prompts.py` | +19 |

### 文档（未提交）

| 文件 | 规模 |
|---|---|
| `docs/STATE.md` | **+975** |
| `docs/active-work.md` | +463 |
| `docs/checklist-group-ingame-2026-10-05.md` | 新 |
| `docs/superpowers/plans/2026-10-05-group-per-participant-context.md` | 新 |

> ⚠ **`STATE.md` 单独 +975 行未提交** —— 也就是说，**这份「唯一事实来源」的绝大部分内容
> 目前只存在于工作区**。它一旦被误删或误还原，损失的是一整段项目的记忆。

---

## 三、部署顺序与依赖（开游戏前必读）

### 硬约束：先 Bridge 后 DLL

`ApiModel` 是 `extra="forbid"` ⇒ **新 DLL + 旧 Bridge = 422**，
而 422 的表现是**群聊直接坏掉**，看起来像功能写错了。顺序反了会浪费一整次实机机会。

### 这一把要带进游戏的改动

从 10-04 下午**最后一次部署**（DLL 833,536 B）到现在，工作区又多了 **10-04 晚 + 10-05** 的工作。
两者的差距是**整个线 1、2、3 以及线 4 的嫉妒闭环** ⇒ 这次换 DLL 的体量**不小**，
建议按 §五 的清单逐项验，不要只试一件事就下结论。

### 各线的部署耦合

- **线 1 + 线 3 绑在一起**：都动了 `ConversationModels.cs` / `BridgeClient.cs` / `models.py` / `prompts.py`，
  没法只部署一个（`_DIALOGUE_FIELDS` 白名单漏一项就是**静默吞字段**）。
- **线 2 独立**，只依赖线 1 已在位（打趣是加在群聊邀约引导上）。
- **线 4 的嫉妒**要 `OnDayStarted` ⇒ **实机需跨天**。
- **线 6 纯数据**（persona json），不涉及协议，可随时单独回滚。

---

## 四、文档侧三处与现实不符（**会误导判断，建议优先修**）

| # | 位置 | 文档说 | 实际 |
|---|---|---|---|
| 1 | `STATE.md` §五 表格 | 「`data/personas/rasmodia.json` **曾改后已回滚，当前无改动**」 | ⚠ **它现在有改动**（+36：`intimacyPolicy`）。那句记的是 09-28 的回滚，10-03 又加了新内容而表没跟 |
| 2 | `STATE.md` §五 表格完整性 | 只登记到 09-28~09-30 那一轮 | 线 5（关系世界）、线 6（亲密角色化）**整条没登记**；`StoryStateStore.cs` +378 也没登记 |
| 3 | `active-work.md` L281–415 | 头部「已完成 / 当前队列 / **下一步操作（真实动态样本）** / 当前停止条件」 | 全是 **2026-08-31~09-01** 的快照。**从文档开头读的人，会先看到四十天前的下一步** |

> ⚠ 第 1 条最危险：下一个人读到「rasmodia 无改动」，可能据此**漏掉一整批 persona 数据**。

---

## 五、下一次实机该验什么（按可验性排序）

1. **F8 私聊八股还在不在**（线 5／6，最便宜，一句话就能判断）
2. **F9 群聊不发 422**（线 1，验 Bridge/DLL 顺序是否正确的最快信号）
3. **群聊里每人一份上下文**（线 1，看 NPC 是否知道只有自己该知道的事）
4. **跨天看嫉妒结算**（线 4，必须过一天）
5. **群聊打趣**（线 2，⚠ 需「同场至少两位已接受多元关系」的角色，是设计而非 bug）
6. **隐性知识**（线 3，触发率低，见 `docs/checklist-group-ingame-2026-10-05.md`）

⚠ 详细步骤与「**别信 pass/fail，要人读台词**」的理由见
`docs/checklist-group-ingame-2026-10-05.md`。

---

## 六、这份快照怎么复现

```powershell
$wt = "E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory"
git -c 'safe.directory=*' -C $wt status --short
git -c 'safe.directory=*' -C $wt diff --stat
git -c 'safe.directory=*' -C $wt log --oneline -5
```

⚠ **不要引用本文档里的数字而不重跑** —— 它是 2026-10-05 一次快照，不是台账。
