# P1 #16～#24「静默不一致」修复报告（2026-09-20）

## 先说人话（不看代码也能懂）

这九条说的是**同一件麻烦事**：

> 一句 AI 对白该不该算「玩家想结束对话」、该不该算「NPC 在收口」、
> 有没有给出具体安排、有没有渠道说错（线上聊天却写成已经见面）……
> **这些判断在程序里有两份实现：一份管游戏里真正跑的那条路（运行时），
> 一份管离线跑分的那条路（评测）。两份都在跑，规则却不一样。**

后果：**同一句对白，运行时觉得没问题、评测判不合格**（或反过来）。
玩家看不见这件事，但它会带来更坏的结果——**评测说好、玩家体验却是另一回事**，
那么拿评测结论去调角色就没有意义了。

**这次的修法不是「把 A 抄给 B」，而是把这个判断收成一份、两处都用它。**
好比两个部门各有一份客户名单还互相对不上——正确做法不是让一边照抄另一边，
而是**只留一份名单，两边都去查它**。项目里 `relationship_gating`（关系阶段表）
早就是这个路子，这次照办。

九条各自改了什么、证据是什么、对评测结论有什么影响，见下面正文；
任务版上有一份同口径的简版：`docs/next-steps-2026-09-20.md` 的 **B30**。

---

> 范围：`docs/semantic-duplication-audit-2026-09-20.md` 的 P1 一节中「两处都跑、结论不同」
> 的第 16～24 条。改动只落在 `guard.py`、`behavior_quality.py`、
> `character_quality_eval.py`（外加同源的 `dialogue_style_quality.py` 与测试）。
>
> 统一原则：**提取单一实现、两处共用**，不把 A 抄给 B；合并标记表默认取**并集**。

---

## 0. 新增的单一来源模块

`bridge/src/stardew_ai_bridge/dialogue_boundaries.py`——只放**表与纯判定**，
不 import 任何 bridge 模块，避免与 `behavior_quality → guard → character_quality_eval`
的既有依赖方向成环。需要「个人亲近信号」这类上层诊断时由调用方传回调
（`violates_event_gate(..., detect_personal_affection=...)`）。

内容：玩家收口表与判定、NPC 收口表与判定、边界表、照顾表、重新拉开动作表、
渠道方向标记与判定、具体安排表与判定、事件锁判定、回合契约映射、
口头颗粒与开场判定、相邻轮次机械形状判定。

---

## 1. 逐条结论

### #16 玩家是否在「收口／要空间」

- **统一到哪边**：并集。`dialogue_boundaries.PLAYER_CLOSE_MARKERS`（23 条，来自 guard 字面表，
  多出离线正则漏掉的 `不用陪`／`别过来`／`心情很差` 等）∪
  `_CONVERSATION_LEAD_PLAYER_CLOSING_PATTERN`（guard 与离线正则的公共部分）。
- **改了谁**：guard 三处判定改走 `contains_marker` / 共享表；
  `behavior_quality.diagnose_conversation_lead` 的 `player_closing` 改为 `is_player_closing(...)`；
  bq 的 `_GUARDED_CLOSE_INPUT_MARKERS` 删除，改引用共享表。
- **为什么这样统一**：运行时放过的，离线评测也该放过。**并集扩大最容易吞正向词**，
  因此专门补了负向语义：`下次再聊的时候，你愿意告诉我那件事吗？` 是**开场铺垫**不是收口，
  `is_player_closing` 对这两个时间标记带 `的时候` 时不计入（测试 `test_ordinary_player_input_is_not_a_close`
  还用「你不用抢我的耳机」钉住「不用」不必然是否定）。

### #17 NPC 是否在「自然收口」

- **统一到哪边**：并集，共 26 条（guard 20 条 ∪ 离线 9 条）。
- **改了谁**：guard 的 `_CLOSE_REPLY_MARKERS` 与 bq 的 `_GUARDED_CLOSE_REPLY_MARKERS`
  都指向 `NPC_CLOSE_REPLY_MARKERS`；bq 的 `close_reply` 也由「只看自己的正则」改成
  `is_npc_close_reply(text) or 正则`——实测该正则漏认 8 条（`早点睡`／`先睡了`／
  `先休息`／`早点钻被窝`／`休息吧`／`明天再联系`／`不打扰你`／`不想聊`）。
- **为什么这样统一**：同一句「你先休息吧。」以前 guard 放过、离线评测判 `missing_proactive_affection`，
  同一条真实对白在两条链上得到相反结论。
- **顺带**：`别跟我较劲` 在 guard 的**边界表**里、不在收口表里，bq 的收口表把它当收口——
  已按边界语义归属；bq 的 `_INITIATIVE_SIGNAL_MARKERS["guarded_care"]` 补上它
  （并集口径：顶回去也是「按玩家边界收住」，而不是没完成主动行为）。

### #18 收口后有没有「重新拉开」

- **统一到哪边**：共享判定。`guard._reopens_after_player_close` 的玩家侧收口信号改用
  `is_player_closing`（此前是另一张 23 条表），「重新拉开」动作表改用
  `dialogue_boundaries.reopens_after_close`，且**不再以「有 conversation lead 契约」为前提**——
  lead 诊断只是**额外**证据来源。
- **为什么这样统一**：没有 lead 契约的回合，guard 回落到自己的正则、离线诊断用另一套，
  于是「运行时放过、离线评测判失败」。
- **判据边界（重要）**：并集里只有**实质追问**（把选择交回玩家，如「你想先听哪一种？」）
  才算重新拉开。收口里的关心式反问（「你现在还好吗？」「你别跟我较劲行不行？」）
  与带否定的未来动作（「不用过来帮我」）都不算——这两条都是实测出来的必要边界，
  否则自然的关心式收口会被拖进重试链。

### #19 「爱意有没有落地」同名 tag

- **结论**：**不需要再改代码**。tag 的 mode 来源（guard 的 `_affection_requirement` 与
  cqe 的 `_turn_for_plan_scoring`）当前是**一一对应**的：
  `answer_plus_warmth`／`explicit_intimacy` → `proactive`；
  其余四个模式 → 不要求。两者的差异只是**表达位置**（guard 在 prompt 侧读，
  cqe 在回合对象侧写），不是两套映射。
- **已加的护栏**：这份映射表统一到
  `dialogue_boundaries.affection_requirement_from_turn_plan`，将来谁改模式集合，
  两处会同时改（否则会出现「guard 要求爱意、评测判合规」这种反向分歧）。

### #20 「有没有给出具体安排」（三套判定 + 一个同名 tag）

- **统一到哪边**：`dialogue_boundaries.is_specific_arrangement`。
- **改了谁**：
  1. bq 的 `specificPlanDetected` 由 `_SPECIFIC_PLAN_PATTERNS` 改为该判定；
  2. bq 的 lead `has_plan` 不再用自己那份 `_CONVERSATION_LEAD_PLAN_PATTERN`，
     改为同一判定——**这才是矛盾的真正位置**：
     `明天我陪你坐一会儿。` 在同一份 tags 里同时得到 `specific_plan_only`（内容判定）
     与 `companionship_only`（陪伴词）；
  3. cqe 的 `_SPECIFIC_PLAN_PATTERNS` 删除，改引用共享表。
- **归因按内容定**：`specific_plan_only` 与 `companionship_only` 互斥；
  **纯陪伴说法**（「陪你坐一会儿」「陪你待一会儿」）不是安排——没有时间点、没有可执行的事。
- **顺带修掉一处真漏判**：旧表的 `帮(?:个)?忙` **永远匹配不到**「帮你收拾」，
  已补 `帮你`；`明天我过来帮你收拾。` 以前不算安排，现在算。
- **保留分工**：`_INITIATIVE_SIGNAL_MARKERS["specific_plan"]`（`今晚`／`一起` 等单字标记）
  仍是**粗粒度信号**，只决定主动类型，不冒充「安排已发生」；这是两种粒度，不是两套实现。

### #21 渠道越界（同名 tag `wrong_channel`）

- **统一到哪边**：并集 + 双向。
  `REMOTE_ONLY_MARKERS`（bq 5 条 ∪ cqe 3 条）与 `FACE_TO_FACE_MARKERS`（cqe 3 条，
  原本只有 cqe 有）上移到共享模块；bq 与 cqe 都改走
  `dialogue_boundaries.channel_direction_tag(channel, reply)`。
- **为什么这样统一**：bq 只有 `remote` 一个方向，`face_to_face` 回合缺反向检查；
  而两个方向的语义是同一件事（回复里的时空定位与当前渠道矛盾）。

### #22 阶段锁 vs 事件锁

- **统一到哪边**：事件锁判定的唯一实现
  `dialogue_boundaries.violates_event_gate(event_gate, reply, detect_personal_affection=...)`，
  事件锁有效上限集合 `EVENT_GATE_BLOCKED_STAGES = {stranger, acquaintance, friend}` 同源。
- **改了谁**：guard 的 `_violates_event_gate` 改为调用它（判定与回调分开，避免
  `dialogue_boundaries` 反向依赖 `behavior_quality`）；
  `character_quality_eval.score_character_reply` 新增同一入口的调用，
  命中记 `event_gate_intimacy`——**离线评测此前完全不看事件锁**，
  于是 `stage=dating` + `eventGate=friend` 时一处拦、一处判合规。
- **不误报的前提**：评测侧的事件锁由
  `resolve_relationship_gate(case.npc_id, relationship_stage=…, friendship_hearts=…,
  completed_event_ids=case.completed_event_ids)` 得到；案例没有 `completedEventIds` 时
  该函数**不启用**事件锁，因此不会把「没提供事件状态」误判成「事件全部未完成」。
- **行为变更**：带事件声明且事件未完成的案例，若回复里落下主动亲密，
  现在会被标记 `event_gate_intimacy`（运行时 guard 本来就会重试这种回复）。

### #23 开场／口头颗粒重复

- **统一到哪边**：`reply_avoids_speech_particle(reply, particles)` 与
  `reply_opens_with_marker(reply, markers)` 成为唯一实现；
  guard 的 `_repeats_history_speech_particle`／`_has_repeated_opening` 与
  `dialogue_style_quality` 都改为调用它们。
- **刻意保留的不同输入**（不是分歧）：
  - guard 的颗粒来自 prompt 的 `voice_execution_card.avoidSpeechParticles`
    （「历史里已经用过」的清单）；
  - `dialogue_style_quality` 既看「同一条回复内同一颗粒 ≥2 次」，也看「开场颗粒与历史开场相同」，
    两处 **谓词同源**、输入不同。这两件事在语义上确实是两件事，故未强行合并。
- `dialogue_style_quality` 的 `repeated_opening` 仍用本模块的**短签名**口径
  （`今天还行` 与 `今天挺忙` 共享 `今天`），只把「是否以历史开场起句」这一步收敛到共享判定。

### #24 相邻轮次机械复用同一亲密形状

- **统一到哪边**：`repeats_affection_shape(shape, previous_shape, *, allowed_close=)`，
  判据 = **形状相同 + 没有新锚点 + 不是明确收口**。
- **改了谁**：guard 的 `_repeats_personal_affection_shape` 与
  cqe 的 `score_affection_variation` 都走它。
- **判定依据（关键）**：cqe 原先额外要求 `kind` 也相同，这正是报告的「guard 只看 shape、
  cqe 还看 kind + 新锚点豁免」；既有用例
  `test_affection_variation_flags_same_personal_shape_even_when_kind_changes`
  钉住的恰是「kind 变了也算机械复用」，因此统一为**不看 kind**。
  新锚点豁免由调用方判定后传入（guard 的历史里没有评测话题锚点，这一维度只在评测侧存在）。

---

## 2. 顺带完成/发现

| 项 | 处置 |
|---|---|
| `_GUARDED_WARMTH_MARKERS` 死表（审计「没被采纳的」一节） | 已删；连带删掉只服务于它的 `_WARMTH_SIGNAL_MARKERS`（AST 核实全仓无读取点） |
| `character_quality_eval` 缺 `diagnose_personal_affection` import | 补上。这是本次迁移引入的**调用期** NameError（pytest 收集期不报），曾造成全量 64 条连锁失败 |
| 测试固化旧分歧 | `test_an_ordinary_reply_after_a_closing_input_is_retried` 原断言把「好的，那你早点休息。」当敷衍（正是并集修掉的分歧），已改写为新语义，并**补一条负向用例**（换话题、既没收口也没照顾 → 仍须重试） |

---

## 3. 文件改动列表

| 路径 | 说明 |
|---|---|
| `bridge/src/stardew_ai_bridge/dialogue_boundaries.py` | **新增**：收口／重新拉开／渠道／事件锁／具体安排／口头颗粒／机械形状的唯一定义与判定 |
| `bridge/src/stardew_ai_bridge/guard.py` | 收口与重新拉开改走共享判定；事件锁判定外提；颗粒与开场判定改走共享谓词；机械形状改走共享函数；删两张死表 |
| `bridge/src/stardew_ai_bridge/behavior_quality.py` | 收口两表改引用共享表；`player_closing`／`close_reply`／`has_plan`／`specificPlanDetected`／渠道判定改走共享入口；两个「只有……」标签互斥；`guarded_care` 补边界标记 |
| `bridge/src/stardew_ai_bridge/character_quality_eval.py` | 渠道判定改走共享入口；新增事件锁判定与 `event_gate_intimacy`；机械形状改走共享函数（不再看 kind） |
| `bridge/src/stardew_ai_bridge/dialogue_style_quality.py` | 口头颗粒与开场起句判定改走共享谓词 |
| `bridge/tests/test_dialogue_boundary_semantics.py` | **新增**：P1 #16～#24 的收口测试（32 条） |
| `bridge/tests/test_boundary_and_snapshot_edges.py` | 把固化旧窄表的断言改写为新语义，并补一条负向用例 |

---

## 4. 行为变更（会影响离线评测结论）

1. **#16/#17 并集**：运行时与评测都会把更多收口说法**当成已收口** → 亲密重试变少；
   离线评测里 `missing_proactive_affection` 的触发面收窄（这是刻意的：运行时放过的评测也放过）。
2. **#20 纯陪伴不算安排**：「陪你坐一会儿」类回复的 `specificPlanDetected`
   由 True 变 False，标签从 `specific_plan_only` 变为 `companionship_only`；
   同时「帮你收拾」类**新算**安排。lead 的 `has_plan` 同源变化。
3. **#21 face_to_face 方向**：当面回合写「发消息给我／线上再聊／下次视频」现在会带
   `wrong_channel`（cqe 侧是新出现的标签；该标签当前不影响 `passed`，只进诊断）。
4. **#22 事件锁**：带 `completedEventIds` 且事件未完成的案例，回复里落下主动亲密会新增
   `event_gate_intimacy` 标签（`passed` 判定暂未把它计入失败，属可讨论的口径）。
5. **#24 机械形状**：cqe 不再因 `kind` 不同而放过机械复用 → `mechanical_affection_shape`
   的触发面**变宽**（与 guard 一致）。
6. **#23**：`dialogue_style_quality` 的颗粒判定改走共享谓词后，判定口径统一为
   「标点或行首 + 完整颗粒」（原先「同一回复内重复」那一路是计数制，只认标点后位置）。
   现有用例（`嗯，今天还行。嗯，没别的事。`）在新口径下仍判重复，行为未变。

---

## 5. 未修与留给主线的判断

1. **`bridge/tests/test_behavior_quality.py` 的
   `test_guarded_refusal_with_shane_irritation_is_allowed_without_forcing_affection`**：
   `别跟我较劲` 属边界表而非收口表，`guarded_exit_allowed` 在该夹具下不可满足。
   已由主线自行决断并落地（删掉第 2 条断言、换成
   `assert "missing_proactive_affection" not in initiativeTags`），本线不再改。
2. **`_CONVERSATION_LEAD_PLAN_PATTERN`（bq）在改动后已无引用**：本次只把
   `has_plan` 换成共享判定，未删该常量（删它属同文件内的收尾清理，留待主线统一处理，
   避免与并行线冲突）。
3. **不在本线范围但影响两处一致性的观察**：`character_quality_eval` 与
   `behavior_quality` 都从 `prompts.py` 间接取 `turn_plan`，而
   `prompts._TURN_PLAN_MODES` 有自己的字面量副本（P3 #46 一类）。三次核对当前一致，
   本次未动 `prompts.py`（不在本线文件范围）。
4. **并行线的同类新模块** `bridge/src/stardew_ai_bridge/dialogue_stage.py`
   （对白样本阶段条件，P1 #25）与本次的 `dialogue_boundaries.py` 在概念上不重叠
   （前者管「阶段条件是否适用」，后者管「对白边界」），但命名相近，提交时请确认两者都在。

---

## 6. 验证与实测数字

命令（`bridge/tests` 下逐文件或全量）：

```powershell
$env:PYTHONPATH='bridge/src;scripts'; $env:PYTHONIOENCODING='utf-8'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest bridge/tests -q -p no:cacheprovider
```

| 范围 | 结果 |
|---|---|
| 全量 `bridge/tests` | **3167 passed / 0 failed**（90.71s） |
| 本线定向（新增 32 条 + guard/bq/cqe/run_cqe/dialogue_style/boundary_edges/group_guard） | **787 passed / 0 failed**（14.86s） |
| 修改前基线（同一 worktree，含并行线中间状态） | 2 failed / 2986 passed；两条均为 `test_relationship_gating_edges.py` 的「固化两处事件匹配器分歧」用例 |

- `git diff --check` 干净（exit 0）。
- 改动规模：`guard.py −284/+…`（净减）、`behavior_quality.py`、`character_quality_eval.py`、
  `dialogue_style_quality.py`、`test_boundary_and_snapshot_edges.py` 共 5 个文件修改、
  1 个源文件与 1 个测试文件新增。
- 未 `git add` / `git commit`（按约定留给主线统一提交）。
