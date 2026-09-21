# 诊断与修复：紧凑路径场景硬事实断点（2026-09-21）

> 线上游戏端 `compactPrompt=true` 时，prompt 里**没有**季节 / 日期 / 天气 / 时段 / 地点，
> 而同一份 prompt 的 `safety_rules` 却写着「天气、时间和地点是当前场景的硬事实」。
>
> 一句话：**向模型承诺了一个没有给的事实，模型只能按先验自补场景**，
> 表现为「早上说晚上的话」。

## 1. 断点

`bridge/src/stardew_ai_bridge/prompts.py:5268`（改动前行号）的 `if not runtime_compact:`
——`game_state` 卡只在**非**紧凑时渲染，而该卡同时承载 `gameState` 与 `recentFacts`。

* 游戏端：`smapi/BridgeClient.cs:26-27` `CompactPrompt = true`（且 `SendAsync`
  从不显式赋值、无配置开关）→ **每次请求都走紧凑路径**；
* 评测端：`compactPrompt` 默认 false（`models.py:592`，与 C# 刻意不同）
  → 完整卡组，所以**评测看不到这个坑**。

`runtime_compact` 的真正条件（`prompts.py:4824`）是
`compact and context["_runtime_compact"] is True`，而 `_runtime_compact` 只由请求的
`compactPrompt` 置位（`app.py:394-402`）。因此：

| 路径 | `compact` | `_runtime_compact` | 受影响 |
|---|---|---|---|
| 游戏端线上 | True | True | **是** |
| 离线评测（`EvaluationBudget.compact_prompt=True`） | True | 未设置 | 否 |
| 离线/脚本默认 | False | 未设置 | 否 |

## 2. 改动（只碰 `bridge/`）

### A. 紧凑路径补一张精简场景卡

`prompts.py` 原 `if not runtime_compact:` 增加 `else` 分支，渲染极小卡 `scene`：

```json
{"地点": "Hospital", "天气": "晴天", "季节": "春天", "日期": "25", "时段": "清晨（6:00）"}
```

* **只保留场景硬事实**：`season / date / weather / timeOfDay / location`；
  `friendship / friendshipHearts / relationship / marriageStatus / childrenCount`
  已有 stage 系卡片覆盖，**不重复渲染**（`test_compact_scene_card_drops_fields_...` 钉住）；
* **键名直接用中文**（季节/日期/天气/时段/地点）：省掉 `gameState` 包装与英文枚举名开销，
  模型读到的就是结论，不必再翻译一次 `clear` / `spring`；
* **时段字段命名 `时段` 而非 `time`**：完整卡里是裸整数 `time: 600`，
  这里已是可读时段，同名不同义会误导；
* `gameState` 为空时**不产出空卡**；
* **地点不做枚举映射**：地图标识符是开放集合（mod 地图），认不出就原样透传
  （给 `Hospital` 也强于让模型不知道身在何处）。

刻意**不**新增任何「必须体现时段」的指令——用户抱怨的是**矛盾**而非「没提早上」，
硬加会诱发「早上好呀」这类机械开场。既有「不要为了显得贴合而硬塞」的约束保持原样。

### B. 裸整数 → 人类可读时段

新增 `bridge/src/stardew_ai_bridge/scene.py`（公共语义，无项目内依赖），
把原先**只挂在本地演示 provider 上**的时段逻辑提升为公共工具，并细化粒度：

| 原值 | 改动前（`FakeProvider._time_label`） | 改动后 |
|---|---|---|
| 600 | 早上 | **清晨（6:00）** |
| 830 | 早上 | **上午（8:30）** |
| 1200 | 下午 | **中午（12:00）** |
| 1830 | 晚上 | **傍晚（18:30）** |
| 2100 | 晚上 | **晚上（21:00）** |
| 2300 | 晚上 | **深夜（23:00）** |
| 2600 | 晚上 | **次日凌晨（2:00）** |

⚠ **跨日边界**：星露谷 `timeOfDay` 域是 **600–2600**，`2400` 表示午夜 0:00、
`2600` 表示**次日 2:00**。不标「次日」的话，「凌晨（2:00）」会被读成当天下午 2 点。

`providers.py` 的 `_SEASONS` / `_WEATHER` / `_normalise_context` / `_time_label`
四个私有副本随之删除，改为复用 `scene.py`，避免出现第二份会漂移的映射表。
演示文案取短形式（`include_clock=False`，输出「上午」），不塞括号时刻。

C# 端取值形态已核实（只读解析游戏 DLL IL + `GameStateCollector.cs`）：
`season` 是 `spring/summer/fall/winter` 四值闭集、`weather` **只有 `rain`/`clear`**
（`sunny` 在生产路径永不出现）、`date` 是 `dayOfMonth` 十进制串、
`location` 是英文地图标识符（非闭集、未取 `DisplayName`）、`time` 是 600–2600 整数。
`scene.py` 的映射表按此口径编写。

### D. 补测试

新增 `bridge/tests/test_compact_scene_card.py`（10 条），
并更新 `test_game_context_contract.py::test_compact_prompt_omits_structured_game_state_message_for_cloud_relay`
（保留「不发完整 `game_state` 卡」的原契约，同时断言精简卡在场）。

## 3. 改动前后 prompt 对照

场景：Harvey，`Hospital`，spring 25 日，`clear`，其余字段完全相同。

| 时段 | 改动前 hash | 改动后 hash | 改动前字符 | 改动后字符 | Δ | 新增 scene 卡 |
|---|---|---|---|---|---|---|
| 早 6:00 | `087fb7d044092eb2` | `986e1349cf20ceb4` | 4941 | 5013 | +72 | `{"地点": "Hospital", "天气": "晴天", "季节": "春天", "日期": "25", "时段": "清晨（6:00）"}` |
| 中 12:00 | `087fb7d044092eb2` | `a03349b067d19222` | 4941 | 5014 | +73 | …`"时段": "中午（12:00）"` |
| 晚 21:00 | `087fb7d044092eb2` | `3dea3cc3658d4c11` | 4941 | 5014 | +73 | …`"时段": "晚上（21:00）"` |
| 深夜 26:00 | `087fb7d044092eb2` | `9ccf515a52d09d7e` | 4941 | 5015 | +74 | …`"时段": "次日凌晨（2:00）"` |

* **改动前三时段 hash 完全相同**（逐字节一致，与诊断一致）；
  **改动后是三份不同 prompt**。
* token 成本（内容级估算）：**+32 tokens / +0.98%**；场景卡本身 72 字符。
* 卡组：12 张 → 13 张，只多一张卡，其余 12 张逐字节未变。

## 4. `recentFacts`（记忆）丢失 —— 诊断

**结论：传了，但从未进过 prompt；是有意省 token 的决策造成的无意副作用。**
建议修复（未实施）。

### 4.1 游戏端实际传了什么

`recentFacts` 是**两条通道相加**（`smapi/BridgeClient.cs:338-342`）：

1. **状态差异事实**（11 类，`BridgeClient.cs:989-1011`）：把上一次成功请求的状态与当前比较，
   产出 `时间从“1830”变为“1840”`、`地点从“SeedShop”变为“Town”` 等。
   **仅第 2 次成功请求起才有**（首次 `previous is null` → 空）。
2. **长期记忆**（`StoryStateStore.cs:102-121`）：存档 `Memories`，**默认取 6 条**，
   形如 `记忆（14）：玩家说：“早上好”；NPC回应：“你来得正好。”`
   （`ConversationStateRules.cs:41-43` + `StoryStateStore.cs:116-119`）。

条数：单条 240 字符、合并封顶 20 条（理论上限 11+6=17）。首次对话常见 0 条，
之后常见 7–10 条。群聊路径**恒为空**（`GroupDialogueMenu.cs:349` 硬编码 `Array.Empty`）。

### 4.2 有意还是 bug

**都不是纯粹的二者之一**：

* **针对 `gameState` 是有意的**——省掉友谊/心级/关系等已在 stage 卡里的字段，
  契约测试名 `test_compact_prompt_omits_structured_game_state_message_for_cloud_relay`
  与配套测试 `test_regular_compact_prompt_keeps_game_state_for_quality_evaluation`
  表明作者清楚两条路径的差异，并刻意保护评测路径；
* **`recentFacts` 是被连带牺牲的**——它与 `gameState` 挤在同一个 `if` 块里
  （`prompts.py:5268-5295`），没有任何注释、测试或提交信息评估过「记忆是否也该跟着走」。
  更关键的反证：`select_memory_facts`（`prompts.py:641-687`）的文档明确写着
  **「哪条记忆该进 prompt 的唯一入口」**，并在 `_build_context_core` 与 `_safe_context`
  两处被调用做长度/去重/排序筛选——**这套精心设计的筛选，在紧凑路径下全部白做**。
  一个被专门设计来"决定哪条记忆进 prompt"的函数，产出的记忆进不了 prompt，
  这不可能是设计意图。

提交历史不足以定论：全仓仅 1 个提交触及该字面量（`c6baca6`，一次涉及 4 个缺陷 + 5 项
一致性的批量修复），未提及 `recentFacts`。

### 4.3 影响面（为什么这条最要紧）

若游戏内记忆从未进过 prompt，则用户此前反馈的「没头没尾」「NPC 不记得之前的事」
与此**直接相关**。注意紧凑路径下仍有的记忆通道只有：
对话历史（裁到 4 条）、`story_state`、`relationship_world`、`knowledge_facts`（1 条）
——都是**本轮窗口内**的信息，跨会话的长期记忆确实一条都没有。

### 4.4 修复方案与成本

| 方案 | 内容 | 新增字符 | 新增 token | 相对现状 |
|---|---|---|---|---|
| **1（推荐）** | 只恢复**记忆行**，丢掉状态差异行 | ~201 | ~158 | +4.4% |
| 2 | 恢复完整 `recentFacts` | ~254 | ~175 | +4.9% |

**推荐方案 1**，理由：本次 A 的场景卡已经给出了**当前**季节/日期/天气/时段/地点，
于是 `时间从“1830”变为“1840”` 这类状态差异行变成纯冗余
（当前值已在场景卡里，历史值对模型无增量）。真正有价值的是记忆行。

实现要点：把 `prompt_recent_facts` 从 `game_state` 卡里拆出来，
在紧凑分支单独渲染一张 `{"近期记忆": [...]}` 卡（条数建议沿用 SMAPI 的 6 条上限，
与 `select_memory_facts` 的筛选口径一致）。**群聊路径不必处理**（本就恒空）。

> 可选优化：记忆行模板 `玩家说：“…”；NPC回应：“…”` 较冗长，
> 若改由 C# 侧或 bridge 侧压成一条第三人称摘要（如「玩家早上问诊所忙不忙，哈维说上午有两位预约」），
> 同样的信息量能再省一半字符。这属于另一条线的改动范围，本次仅记录。

## 5. `interaction` 卡（含 `channelInstruction`）—— 判断与方案

**判断：渠道信息是「半丢失」，不是全丢，但丢失的那一半恰好是有用的那一半。**

实测紧凑路径 vs 完整路径（`face_to_face` 对比 `remote`）：

| | 完整路径 | 紧凑路径 |
|---|---|---|
| `interaction` 卡（含中文渠道指令） | 在场 | **被跳过** |
| `post_history_voice_guard.channel` | 在场 | 在场 |
| 「这是当面聊天…可以描述当面反应和动作」 | 命中 | **缺失** |
| 「不要写成发消息或线上约定」 | 命中 | **缺失** |
| 「玩家和 NPC 当前在同一地点」 | 命中 | **缺失** |
| 两份 prompt 是否不同 | 是（3 张卡不同） | 是（1 张卡不同） |

紧凑路径的**唯一**渠道信息是 `post_history_voice_guard` 里的
`"channel": "face_to_face"`（`prompts.py:5792-5796`，直接抄自
`interaction.get("channel")`）——**一个没有解释说明的英文 token**。
模型知道渠道"叫什么"，但不知道**该怎么表现**。

这确实可能加重「像在发消息」的体感：完整路径下模型被明确告知
「可以描述当面反应和动作」「不要写成发消息」，紧凑路径下这个方向性约束消失了。

**方案（未实施，建议与 §4.4 一并做）**：`channelInstruction` 只有 2 个取值、
各约 60 字符，恢复成本极低。两个选项：

* **方案 a（推荐，最省）**：在 `scene` 卡里加一个 `"场合": "当面"` / `"远程"` 字段
  （约 8–10 字符），只给渠道**结论**；
* **方案 b（最稳）**：紧凑分支补渲染一张极小的渠道卡，带完整
  `channelInstruction`（约 70 字符，+~60 tokens）。

若用户反馈的核心是「像在发消息」，选 b；若只想在几乎零成本下补上方向性，选 a。

## 6. 测试与验证

```
pwsh -NoProfile -File scripts/verify_project.ps1
[PASS] SMAPI 测试 —— 通过: 791，失败: 0
[PASS] Bridge 测试 —— 3270 passed in 67.33s
[PASS] compileall —— exit=0
[PASS] git diff --check —— 无空白错误
```

* **SMAPI 791 passed** = 与基线**完全一致**（未碰 `smapi/`）；
* **Bridge 3270 passed** = 基线 3260 + 新增 10；
* 改动文件：`prompts.py`、`providers.py`、新增 `scene.py`；
  测试 `test_compact_scene_card.py`（新增）、`test_game_context_contract.py`、
  `test_providers.py`（各改 1 处断言/追加断言）。

新增测试清单（`bridge/tests/test_compact_scene_card.py`）：

1. `test_compact_prompt_renders_scene_card_with_readable_hard_facts` — 场景卡内容完整
2. `test_compact_scene_card_drops_fields_already_covered_by_other_cards` — 不重复关系字段
3. `test_compact_scene_card_renders_nothing_when_every_field_is_missing` — 空状态不产出空卡
4. `test_compact_scene_card_translates_raw_time_into_readable_segment` — 六档时段可读化
5. `test_compact_scene_card_marks_next_day_after_midnight` — **2400/2500/2600 跨日边界**
6. `test_compact_scene_card_omits_segment_for_unusable_time` — 越界/非法值不编造时段
7. `test_compact_prompts_differ_across_morning_noon_and_night` — **早/中/晚三份不同**（核心验收）
8. `test_compact_prompt_does_not_leak_relationship_fields_into_scene_card` — 仍不发完整卡
9. `test_offline_compact_keeps_full_game_state_and_no_scene_card` — 评测路径不受影响
10. `test_compact_scene_card_passes_unknown_location_through` — 未知地点透传

另有 1 处既有断言按设计更新：`test_providers.py:92` 原断言演示文案含「早上」，
`time=830` 实为 8:30，时段细化后正确落在「上午」。

## 7. 风险

1. **token 成本**：紧凑路径每轮 +32 tokens（+0.98%）。这是**每轮固定**开销，
   即便 `gameState` 为空也有判断成本，但空卡不渲染，实际不会白花。
2. **若一并做 §4.4 + §5，成本会翻几倍**：方案 1 约 +158 tokens（+4.4%）、
   渠道卡约 +60 tokens。三者合计约 +250 tokens（**约 +7%**），
   在紧凑路径上是不可忽略的涨幅——建议**分两次上线**，先验证 A 的效果再决定后两项。
3. **场景卡与 `recentFacts` 的信息重叠**：本次 A 落地后，
   `recentFacts` 里的状态差异行（11 类）变成冗余；这既是 §4.4 推荐方案 1 的依据，
   也意味着**若先做了 §4.4 方案 2 再做 A，会重复付一遍 token**。
4. **中文键名的兼容性**：`scene` 卡用中文键是刻意的，但若将来有脚本按英文键名解析
   `scene` 卡，需要同步。目前无此消费者（卡片名 `scene` 为新增）。
5. **地点未本地化**：场景卡给的是 `Hospital` 这类地图标识符（C# 侧未取 `DisplayName`）。
   模型能理解其含义，但不等于玩家看到的界面名；若要显示名，属 `smapi/` 侧改动。
6. **未验证真实上游效果**：本次全部为离线 prompt 构建验证，**未联网、未启动游戏**。
   「场景卡是否真的消除时间矛盾」需要一次真机或真实上游抽样才能确认。

## 8. 复现与证据

`.tmp/time-repro/`（gitignored，只读诊断脚本，不改生产代码）：

| 脚本 | 用途 |
|---|---|
| `compare_paths.py` | 三路径 × 四时段对照（字符/token/hash/场景卡原文），`--tag` 落盘 |
| `delta.py` | 改动前后精确增量（同 context 摘掉 `scene` 卡做对照） |
| `diag_memory_channel.py` | 记忆与渠道在两条路径下的存留实测 |
| `diag_channel_diff.py` | 逐卡对比 `face_to_face` / `remote` |
| `cost_fix_options.py` | §4.4 两个方案的 token 成本估算 |
| `repro_time.py` / `crosscheck.py` / `realistic.py` | 原始诊断（8 角色 × 4 时段零差异） |

**一个对照陷阱**（已踩）：不能用「删掉 `_runtime_compact`」来模拟改动前——
该标记同时门控 `interaction` 与 `conversation_lead`，删掉会把另外两张卡一起放回来，
实测会虚报 −19% 的"成本"。正确做法是保持同一 context、只摘掉新增的那张卡。
