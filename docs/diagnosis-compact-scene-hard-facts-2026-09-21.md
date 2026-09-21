# 诊断与修复：紧凑路径场景硬事实与跨会话记忆断点（2026-09-21）

> 线上游戏端 `compactPrompt=true` 时，prompt 里**没有**季节 / 日期 / 天气 / 时段 / 地点，
> **也没有**任何跨会话记忆，而同一份 prompt 的 `safety_rules` 却写着
> 「天气、时间和地点是当前场景的硬事实」。
>
> 一句话：**向模型承诺了一个没有给的事实，模型只能按先验自补场景**，
> 表现为「早上说晚上的话」；同时记忆缺失直接对应「没头没尾 / 不记得之前的事」。

本文件记录两轮改动，均已落地：

| 轮次 | 内容 | 状态 |
|---|---|---|
| A | 紧凑路径补精简 `scene` 卡（场景硬事实） | ✅ 已落地 |
| B | 裸整数 → 人类可读时段（公共工具 + 2600 跨日） | ✅ 已落地 |
| D | 补测试（此前完全无覆盖） | ✅ 已落地 |
| §3 | 恢复跨会话记忆（只留记忆行） | ✅ 已落地 |
| §4 | `scene` 卡补 `场合` 结论 | ✅ 已落地 |

## 1. 断点

`bridge/src/stardew_ai_bridge/prompts.py` 的 `if not runtime_compact:`
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

同一门控还砍掉 `interaction`（含 `channelInstruction`）与 `conversation_lead`。
注意 `voice_variation` 是 **`compact`** 管的（`prompts.py:5782`），不是 `runtime_compact`。

## 2. A —— 紧凑路径补精简场景卡

`else` 分支渲染极小卡 `scene`：

```json
{"地点": "Hospital", "场合": "当面", "天气": "晴天", "季节": "春天", "日期": "25", "时段": "清晨（6:00）"}
```

* **只保留场景硬事实 + 渠道结论**；
  `friendship / friendshipHearts / relationship / marriageStatus / childrenCount`
  已有 stage 系卡片覆盖，**不重复渲染**；
* **键名直接用中文**：省掉 `gameState` 包装与英文枚举名开销，
  模型读到的就是结论，不必再翻译一次 `clear` / `spring`；
* **时段字段命名 `时段` 而非 `time`**：完整卡里是裸整数 `time: 600`，
  这里已是可读时段，同名不同义会误导；
* **地点不做枚举映射**：地图标识符是开放集合（mod 地图），认不出就原样透传；
* 完全没有信息时**不产出空卡**；但**只有渠道也会产卡**——
  `interaction` 卡在紧凑路径被跳过，「场合」是这条路径上唯一的渠道信息。

刻意**不**新增任何「必须体现时段」的指令——用户抱怨的是**矛盾**而非「没提早上」，
硬加会诱发「早上好呀」这类机械开场。既有「不要为了显得贴合而硬塞」的约束保持原样。

## 3. B —— 裸整数 → 人类可读时段

新增 `bridge/src/stardew_ai_bridge/scene.py`（公共语义，无项目内依赖），
把原先**只挂在本地演示 provider 上**的时段逻辑提升为公共工具，并细化粒度：

| 原值 | 改动前 | 改动后 | | 原值 | 改动前 | 改动后 |
|---|---|---|---|---|---|---|
| 600 | 早上 | **清晨（6:00）** | | 1830 | 晚上 | **傍晚（18:30）** |
| 830 | 早上 | **上午（8:30）** | | 2100 | 晚上 | **晚上（21:00）** |
| 1200 | 下午 | **中午（12:00）** | | 2300 | 晚上 | **深夜（23:00）** |
| | | | | 2600 | 晚上 | **次日凌晨（2:00）** |

⚠ **跨日边界**：星露谷 `timeOfDay` 域是 **600–2600**，`2400` 表示午夜 0:00、
`2600` 表示**次日 2:00**（游戏强制昏倒线）。不标「次日」的话，
「凌晨（2:00）」会被读成当天下午 2 点。非 10 倍数值（如 `760`）按非法 HHMM 拒绝，
否则会产出 `7:60` 这种不存在的时刻。

`providers.py` 的 `_SEASONS` / `_WEATHER` / `_normalise_context` / `_time_label`
四个私有副本随之删除，改为复用 `scene.py`，避免出现第二份会漂移的映射表。
演示文案取短形式（`include_clock=False`，输出「上午」），不塞括号时刻。

C# 端取值形态已核实（只读解析游戏 DLL IL + `GameStateCollector.cs`）：
`season` 是 `spring/summer/fall/winter` 四值闭集、`weather` **只有 `rain`/`clear`**
（`sunny` 在生产路径永不出现）、`date` 是 `dayOfMonth` 十进制串、
`location` 是英文地图标识符（非闭集、未取 `DisplayName`）、`time` 是 600–2600 整数。

## 4. §3 —— 恢复跨会话记忆

### 4.1 游戏端实际传了什么

`recentFacts` 是**两条通道相加**（`smapi/BridgeClient.cs:338-342`）：

1. **状态差异事实**（11 类，`BridgeClient.cs:989-1011`）：把上一次成功请求的状态与当前比较，
   产出 `时间从“1830”变为“1840”` 等。**仅第 2 次成功请求起才有**。
2. **长期记忆**（`StoryStateStore.cs:102-121`）：存档 `Memories`，**默认取 6 条**，
   形如 `记忆（14）：玩家说：“早上好”；NPC回应：“你来得正好。”`。

条数：单条 240 字符、合并封顶 20（理论上限 11+6=17）。首次对话常见 0 条。

### 4.2 有意还是 bug

**针对 `gameState` 是有意的，`recentFacts` 是被连带牺牲的。**

* 省 token 的决策针对 `gameState`（省掉友谊/心级/关系等已在 stage 卡里的字段），
  契约测试名与配套的「评测路径保留完整卡」测试表明作者清楚两条路径的差异；
* 但 `recentFacts` 与 `gameState` 挤在同一个 `if` 块里，没有任何注释、测试或提交信息
  评估过「记忆是否也该跟着走」。**最强反证**：`select_memory_facts`
  （`prompts.py:641-687`）文档自称**「哪条记忆该进 prompt 的唯一入口」**，
  做长度/去重/排序筛选且在两处被调用——**这套筛选在紧凑路径下全部白做**。
  一个被专门设计来"决定哪条记忆进 prompt"的函数，产出的记忆进不了 prompt，
  这不可能是设计意图。

提交历史不足以定论：全仓仅 1 个提交触及该字面量（`c6baca6`，一次涉及 4 个缺陷 +
5 项一致性的批量修复），未提及 `recentFacts`。

### 4.3 影响面

紧凑路径下原本仅存的记忆通道是：对话历史（裁到 4 条）、`story_state`、
`relationship_world`、`knowledge_facts`（1 条）——**都是本轮窗口内的信息**，
跨会话长期记忆确实一条都没有。用户此前反馈的「没头没尾」「NPC 不记得之前的事」
与此直接相关。

### 4.4 已实施的修复（原推荐方案 1）

紧凑分支单独渲染 `recent_memory` 卡：

```json
{"近期记忆": ["记忆（14）：玩家说：“早上好，今天诊所忙吗？”；NPC回应：“还好，上午只有两位预约。”", …]}
```

* **只留记忆行**，剔掉状态差异行：`scene` 卡已给出当前季节/日期/天气/时段/地点，
  于是 `时间从“1830”变为“1840”` 这类差异行成了纯冗余（当前值就在场景卡里，
  历史值对模型没有增量）；
* 数据源是 `safe_context["recentFacts"]`，**即 `select_memory_facts` 的产物**
  （`prompts.py:4972-4975`），不绕过那套筛选；本条由测试
  `test_compact_memory_card_matches_select_memory_facts_pipeline` 钉住；
* 条数不再二次限制——由 SMAPI 侧控制（默认 6 条、封顶 20）；
* `natural_topic` 时不带记忆，与完整路径门控保持一致（游戏端不传 `qualityContext`，
  该模式恒 false，线上不受影响）。

**识别状态差异行的规则**（`is_state_delta_fact`）：整行匹配
`^(11 个固定 label)从“.+”变为“.+”$`，label 取自 `BridgeClient.cs:999-1009`
与 `AddEventChanges` 的 `剧情事件`。

**误杀安全性**：两个记忆写入源（私聊 `ConversationStateRules.cs:41-43`、
群聊 highlight `StoryStateStore.cs:74/119`）都**强制 `GameDate` 非空**，
所以线上记忆行**恒带 `记忆（…）：` 前缀**，结构上不可能命中以 label 开头的整行匹配。
规则刻意偏保守：若 C# 未来改文案，失效方向是状态差异行重新混进 prompt（多花 token），
**不会丢记忆**。

### 4.5 群聊：为什么不一起补

**群聊路径不在本次范围内，理由三条**：

1. 线上群聊的 `recentFacts` **恒为空**——`smapi/GroupDialogueMenu.cs:349`
   群聊请求第 349 个实参硬编码 `Array.Empty<string>()`；
2. 群聊走 `group_conversation.build_group_messages` **自己的渲染路径**
   （`group_scene` 卡），不经过 `PromptBuilder.build`，
   所以 `recent_memory` / `scene` 两张卡都不适用于群聊；
3. 群聊的 `recentFacts` 来自 `GroupDialogueMenu` 传参，**不是**
   `BridgeClient.BuildRecentFacts` 的产物，因此即使将来 C# 补上填充，
   也不会含 11 类状态差异行。

→ 群聊补记忆是独立议题，需要先改 C# 侧填充（属 `smapi/` 范围，本次不碰）。

## 5. §4 —— `scene` 卡补渠道结论

**问题**：紧凑路径唯一的渠道信息是 `post_history_voice_guard` 里的
`"channel": "face_to_face"`（`prompts.py` 直接抄自 `interaction.get("channel")`）
——**一个没有解释说明的英文 token**。模型知道渠道"叫什么"，但不知道**该怎么表现**。
实测 `channelInstruction` 的三句中文约束
（「这是当面聊天」「玩家和 NPC 当前在同一地点」「不要写成发消息或约定」）
在紧凑路径**全部缺失**，确实可能加重「像在发消息」的体感。

**已实施**：`scene` 卡加一个 `场合` 键，**只给结论**：

| 请求 `channel` | `场合` |
|---|---|
| `face_to_face` | `当面` |
| `remote` | `远程` |
| 缺失 | **不产该键**（不凭空断言「当面」） |

只加这一个键（实测 +6 tokens），**不搬** `channelInstruction` 整段
（那要 +60 tokens/轮，先不花）。短标签 `_CHANNEL_LABELS` 与长文案
`_CHANNEL_INSTRUCTIONS` 放在一起，并有测试钉住两者键集合一致，避免漂移。

## 6. 改动前后 prompt 对照

场景：Harvey，`Hospital`，spring 25 日，`clear`，`face_to_face`，其余字段完全相同。

| 时段 | 改动前 hash | 改动前字符 | 仅 A 后字符 |
|---|---|---|---|
| 早 6:00 | `087fb7d044092eb2` | 4941 | 5013 |
| 中 12:00 | `087fb7d044092eb2` | 4941 | 5014 |
| 晚 21:00 | `087fb7d044092eb2` | 4941 | 5014 |
| 深夜 26:00 | `087fb7d044092eb2` | 4941 | 5015 |

**改动前三时段 hash 逐字节完全相同**（与诊断一致）；**改动后三份不同**。

新增两张卡原文（早 6:00，6 条记忆）：

```
[scene]  84 字符
{"地点": "Hospital", "场合": "当面", "天气": "晴天", "季节": "春天", "日期": "25", "时段": "清晨（6:00）"}

[recent_memory]  298 字符
{"近期记忆": ["记忆（14）：玩家说：“早上好，今天诊所忙吗？”；NPC回应：“还好，上午只有两位预约。”", …]}
```

### 6.1 累计成本（实测）

样本：`face_to_face` + 2 条状态差异行 + 记忆行（SMAPI `RecentMemoryFacts` 默认 6 条）。

| 阶段 | 早 6:00 tokens | Δ | 说明 |
|---|---|---|---|
| 改动前 | 3254 | — | 线上原状 |
| +A | 3286 | **+32** | `scene` 卡（无场合） |
| +§4 | 3292 | **+6** | `场合` 键 |
| +§3（全量） | 3449 / 3528 | **+158 / +236** | `recent_memory` 卡（4 条 / 6 条） |
| **合计** | | **+195 / +273** | **占改动前 5.99% / 8.40%** |

记忆条数会变，成本随之变（SMAPI 默认 6 条即上限）：

| 记忆条数 | Δ§3 | 合计 Δ | 占改动前 | 紧凑 prompt |
|---|---|---|---|---|
| 4 条 | +158 | +195 | **5.99%** | 3254 → 3449 tok |
| 6 条（SMAPI 上限） | +236 | +273 | **8.40%** | 3254 → 3528 tok |

## 7. 测试与验证

```
pwsh -NoProfile -File scripts/verify_project.ps1
[PASS] SMAPI 测试 —— 通过: 791，失败: 0
[PASS] Bridge 测试 —— 3285 passed
[PASS] compileall —— exit=0
[PASS] git diff --check —— 无空白错误
```

* **SMAPI 791 passed** = 与基线**完全一致**（未碰 `smapi/`）；
* **Bridge 3285 passed** = 基线 3260 + 新增 25；
* 只碰 `bridge/`；未碰 `smapi/`、`data/`。

### 新增测试（25 条）

`bridge/tests/test_compact_scene_card.py`（11 条）：

1. `test_compact_prompt_renders_scene_card_with_readable_hard_facts`
2. `test_compact_scene_card_drops_fields_already_covered_by_other_cards`
3. `test_compact_scene_card_renders_nothing_when_every_field_is_missing`
4. `test_compact_scene_card_survives_on_channel_alone`
5. `test_compact_scene_card_translates_raw_time_into_readable_segment`
6. `test_compact_scene_card_marks_next_day_after_midnight` — **2400/2500/2600 跨日**
7. `test_compact_scene_card_omits_segment_for_unusable_time`
8. `test_compact_prompts_differ_across_morning_noon_and_night` — **核心验收**
9. `test_compact_prompt_does_not_leak_relationship_fields_into_scene_card`
10. `test_offline_compact_keeps_full_game_state_and_no_scene_card`
11. `test_compact_scene_card_passes_unknown_location_through`

`bridge/tests/test_compact_memory_and_channel.py`（14 条）：

1. `test_state_delta_detection_covers_all_eleven_labels`
2. `test_state_delta_detection_requires_whole_line_match` — **误杀安全性**
3. `test_state_delta_detection_ignores_ordinary_memory_text`
4. `test_select_compact_memory_facts_keeps_memory_and_order`
5. `test_compact_prompt_restores_cross_session_memory`
6. `test_compact_prompt_drops_redundant_state_delta_facts`
7. `test_compact_memory_card_matches_select_memory_facts_pipeline` — **不绕过筛选**
8. `test_compact_memory_card_keeps_select_memory_facts_deduplication`
9. `test_compact_prompt_omits_memory_card_when_there_is_no_memory`
10. `test_offline_compact_path_has_no_recent_memory_card`
11. `test_compact_scene_card_labels_face_to_face_channel`
12. `test_compact_scene_card_labels_remote_channel` — **证明不恒为「当面」**
13. `test_compact_scene_card_omits_channel_when_request_has_none`
14. `test_channel_labels_stay_in_sync_with_channel_instructions`

另有 2 处既有断言按设计更新：
`test_providers.py:92`（`time=830` 文案"早上"→"上午"）、
`test_game_context_contract.py::test_compact_prompt_omits_structured_game_state_message_for_cloud_relay`
（保留「不发完整 `game_state` 卡」契约，追加精简卡在场断言）。

## 8. 风险

1. **token 成本**：紧凑路径每轮 **+195 ~ +273 tokens（+6.0% ~ +8.4%）**。
   这是**每轮固定**开销，且 `recent_memory` 占绝大部分（+158 ~ +236）。
   若后续要压，最直接的是**改记忆行模板**（见下条）。
2. **记忆行模板冗长**：`玩家说：“…”；NPC回应：“…”` 把一问一答原样带入。
   若改由 bridge 或 C# 压成第三人称摘要（如「玩家早上问诊所忙不忙，
   哈维说上午有两位预约」），同样信息量可再省约一半字符——但这属另一条线，
   且会改变 `StoryStateStore` 的存档内容格式，需单独评估迁移。
3. **`is_state_delta_fact` 依赖 C# 文案**：若 `BridgeClient.cs` 改差异行格式，
   规则失效。**失效方向是安全的**（状态行重新混入，多花 token，不丢记忆），
   但仍建议 C# 侧改动时同步本条正则。
4. **`recent_memory` 与 `story_state` 可能重叠**：长期记忆与剧情进度卡都描述已发生的事，
   二者信息若有重复会白占预算。本次未做交叉去重，未实测重叠率。
5. **地点未本地化**：场景卡给的是 `Hospital` 这类地图标识符（C# 侧未取 `DisplayName`），
   模型能理解含义，但不等于玩家看到的界面名；要显示名属 `smapi/` 侧改动。
6. **渠道只给结论、不给行为约束**：`场合: 当面` 能否达到
   `channelInstruction` 整段的效果，**未经验证**——这是刻意的成本取舍，
   若实测「像发消息」的体感没有改善，再考虑补整段（约 +60 tokens/轮）。
7. **未验证真实上游效果**：全部为离线 prompt 构建验证，**未联网、未启动游戏**。
   「场景卡是否真的消除时间矛盾」「记忆是否真的改善连贯性」需要真机或
   真实上游抽样才能确认。这是本次最大的未验证项。

## 9. 复现与证据

`.tmp/time-repro/`（gitignored，只读诊断脚本，不改生产代码）：

| 脚本 | 用途 |
|---|---|
| `compare_paths.py` | 三路径 × 四时段对照（字符/token/hash/场景卡原文），`--tag` 落盘 |
| `delta.py` | A 的精确增量（同 context 摘掉 `scene` 卡做对照） |
| `delta_s3_s4.py` | **A / §4 / §3 分阶段累计成本**（逐项摘卡隔离） |
| `verify_s3_s4.py` | 记忆行保留/状态差异剔除/场合取值的行为验证 |
| `diag_memory_channel.py` | 记忆与渠道在两条路径下的存留实测 |
| `diag_channel_diff.py` | 逐卡对比 `face_to_face` / `remote` |
| `repro_time.py` / `crosscheck.py` / `realistic.py` | 原始诊断（8 角色 × 4 时段零差异） |

**一个对照陷阱**（已踩）：不能用「删掉 `_runtime_compact`」来模拟改动前——
该标记同时门控 `interaction` 与 `conversation_lead`，删掉会把另外两张卡一起放回来，
实测会虚报 −19% 的"成本"。正确做法是保持同一 context、只摘掉新增的那张卡。
