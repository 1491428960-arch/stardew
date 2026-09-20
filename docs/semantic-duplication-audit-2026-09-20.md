# 语义层「同概念多实现」审计（2026-09-20）

> 起因：本日反复遇到「同一件事被两处独立实现」（单轮 vs 多轮的 invitation、生成 vs 写入的校验、
> 模板表 vs 白名单、SMAPI vs Bridge 的空消息规则……）。用户要求做一轮**系统性排查**。
>
> 先做过一轮**表层扫描**（重复常量、重复函数），604 处候选里只有 2 处是真问题。
> 本文件是**第二轮：语义层**——读代码找「同一个概念在两处各有一套判定/计算」。

## 怎么做的

六个并行子代理，各负责一条主线，**通读代码而不是 grep**：

| 线 | 范围 | 候选 | 确认漂移 |
|---|---|---|---|
| A | 关系阶段与好感度 | 8 | 4 |
| B | 记忆、历史与证据 | 5 | 5 |
| C | 护栏与质量评估 | 10 | 9 |
| D | 话题、场景与生成路径 | 14 | 11 |
| E | SMAPI 侧规则类与目标解析 | 14 | 11 |
| F | SMAPI ↔ Bridge 契约 | 13 | 8 |
| **合计** | | **64** | **48** |

**判据**（用来排除误报）：
- 两处只是「调用同一个函数」→ 不是。
- 一处是纯数据表、另一处是判定逻辑 → 通常不是。
- **只有当两处都在「做判断/计算」，且它们应该给出一致结果时**，才算。

---

## P0 — 玩家可感知的功能缺失

### ✅ 已修

| # | 症状 | 位置 |
|---|---|---|
| 1 | **群聊「挑重要的记」整条链从未生效**——`ValidateGroupResponse` 重建响应时漏复制 `MemoryHighlights`。视觉验证用 `QueueResponseForVisualTest` 直塞响应、绕过了这层，所以一直没暴露 | `BridgeClient.ValidateGroupResponse` |
| 2 | **矮人与 Abigail 的矿石对话是坏的**——`specialInteraction.ToString().ToLowerInvariant()` 发出 `"mineraltasting"`，Bridge 只认 `"mineral_tasting"` → 422 → 兜底回复 | `ConversationModels.SpecialInteractionValue` |
| 3 | **心数 2 时阶段判错**——`providers` 用 `>=3`、其它三处用 `>=2`，走 stranger 的短答与不主动策略。夹具只喂 3／4 心，所以没照到 | `providers._relationship_stage` 等四处 |
| 4 | **`providers` 忽略显式 `relationshipStage`**，自己重新推导一遍 | `providers._relationship_stage` |
| 5 | **「朋友及以上」阶段集合的第四份字面量**（上一轮我误称「三处已统一」） | `stage_policy` 里对 `relationship_gating.CONVERSATION_LEAD_STAGES` 的引用 |
| 13 | **群聊完全没有回复质量门**——舞台动作／Markdown／提示词泄露会原样进对白、甚至进长期记忆 | `group_conversation.guard_group_turns` 逐条过 `ResponseGuard.check`，丢弃不合格那条（**不把整场拖进 fallback**） |
| 14 | **群聊开场对 `guard` 完全不可见**——只有私聊的 topic 契约算开场 | `guard.is_opening_prompt` 统一开场信号（私聊 topic 契约／群聊卡 + 没有玩家消息），`_missing_topic_grounding` → `missing_opening_grounding` |
| 6 · 7 | **`recentFacts`／`relationshipWorld` 进不了群聊多轮 prompt**（SMAPI 一直在发） | 第 194 项：`build_group_messages` 注入场景卡 |
| 8 | **群聊 `warnings` 超 20 条 → pydantic 校验失败 → 端点 500** | 第 194 项：`group_conversation.limit_warnings` 两边共用 |
| 9 | **`build_group_voice_cards` 读错 key**（`identity` vs `npcIdentity`）→ 声线卡三项永远为空 | 第 194 项：改 key 名（`prompts.build_group_voice_cards`） |
| 11 | **`usage` 合并两套口径**（群聊保守、私聊累加） | 第 194 项：统一到保守口径 |
| 12 | **记忆去重用 `string.GetHashCode()`**（.NET 跨进程随机化 → 重启后去重失效） | 第 194 项：改用稳定 SHA256 |
| 15 | **`objectiveRelationships` 形状不匹配**（C# 有向边 vs Python 单对象 + `extra="forbid"` → 422） | 第 194 项：在同一 normalizer 里折叠 from/to |

### ⬜ 待修（都确认是 bug，修法明确）

| # | 症状 | 修法 |
|---|---|---|
| 10 | **同一请求里参与者上下文被构建两次**，而其中一份的产物在主路径被丢弃（纯浪费） | 主路径跳过 voice card 构建 |

---

## P1 — 静默不一致（两处都跑，结论不同）

> **✅ 全部 16 条已修（2026-09-20）**，分两个 commit 落地：收口判定线 `eadb974`（#16–#24）、
> 阶段条件与事件匹配线 `8027ba2`（#10／#25–#29／#31）。修法统一为**提取单一来源、两处共用**，
> 新增 `dialogue_boundaries.py` 与 `dialogue_stage.py` 两个只放表与纯判定的模块，
> 而不是让一边照抄另一边。逐条结论见 `docs/p1-16-24-unification-report-2026-09-20.md`
> 与 `active-work.md` 第 199 项。下表保留当时的「分歧」记录，便于回溯判断依据。

| # | 概念 | 分歧 |
|---|---|---|
| 16 | **玩家是否在「收口／要空间」** | 五处各一张标记表：guard 无条件认 23 条，`behavior_quality` 的正则不认 `不用陪`／`别过来`／`心情很差`，pacing 内联 8 条不含 `先休息`／`改天再聊` |
| 17 | **NPC 是否在「自然收口」** | 反向差集 9 条（`好好休息`／`去吧`／`路上小心`／`注意安全`…）只在 bq 有；正向 7 条只在 guard 有。同一句「你先休息吧。」guard 放过、bq 判 `missing_proactive_affection` |
| 18 | **收口后有没有「重新拉开」** | guard 只在 conversation lead 启用时才采信共享诊断，否则跑自己的正则 → 运行时放过、离线评测判失败 |
| 19 | **「爱意有没有落地」** | 同名 tag `missing_proactive_affection`，两处 mode 来源不同（guard 还看 turn_plan） |
| 20 | **「有没有给出具体安排」** | **三套判定 + 一个同名 tag**；实测同一份诊断里同时出现 `specific_plan` 与 `companionship_only`（自相矛盾） |
| 21 | **渠道越界**（线上写成已见面） | 同名 tag `wrong_channel`，两处标记表不同；bq 没有 face_to_face 方向的反向检查 |
| 22 | **阶段锁 vs 事件锁** | 「当前不该出现的亲密」两套判定 + 两套信号表。stage=dating 但 eventGate=friend 时：guard 拦、bq 判合规 |
| 23 | **开场／口头颗粒重复** | guard 与 `dialogue_style_quality` 各自从 history 重算；同一事实两个名字（`repeated_opening` vs `repeated_speech_particle`）；颗粒表一个硬编码 8 个、一个用 persona 的 `speechParticleHints` |
| 24 | **相邻轮次机械复用同一亲密形状** | 同名 tag；guard 只看 shape，cqe 还看 kind + 新锚点豁免 → 运行时重写、评测判不机械 |
| 25 | **对白样本「阶段条件是否适用」** | 三套：`profile_index` 按 rank 宽放、`speech` 严格相等、`_stage_matches` 已断线却仍有 10 条测试钉住 |
| 26 | **对白证据长度窗口** | 生成侧 6–80 字、私聊截断到 100、群聊 >60 直接丢弃 → 60–80 字之间合格的锚点在群聊侧被静默丢弃 |
| 27 | **记忆「该不该进 prompt」** | 两条通道：`knowledge_facts` 按 scope + confidence + 事件门控筛；`RecentMemoryFacts` 只按时间取 6 条，**完全不看 Confidence／Importance／KnownBy**（这些字段写了但没有任何选择逻辑读） |
| 28 | **游戏事件「是否已完成」** | **四套匹配规则**；`requiredEventId="56"` + `completed=["flashshifter.SVE:56"]` 时 3:1 分裂（当前内容侧无人触发，属潜伏） |
| 29 | **群聊回合上限** | 四处：`turn_budget` 带 clamp、`_group_scene_instruction` 自己算不 clamp、`build_group_prompt` 用未过滤的人数、models 两处默认值语义不同 |
| 30 | **回应质量门** | ✅ **已随 #13 一起解决**：群聊现在逐条过 `ResponseGuard.check`，不再是「只有一句提示词」 |
| 31 | **`addressedTo` 约束** | 三处各判一遍（当前等价，纯维护成本） |

---

## P2 — 需要产品口径（我不该替你决定）

### ⚠️ `parent` 算不算「既成亲密阶段」

**现状是分裂的**：

- `prompts.py` 一旦 `childrenCount > 0` 就判 `parent`，**优先于 marriageStatus**
- `stage_policy` 里 `affectionInitiative` 的发放处只认 `{dating, married}` → **「已婚 + 有孩子」的 NPC 拿不到任何亲密契约**
- 而 `relationship_gating` 与 `character_quality_eval._case_romance_eligible` 又把它当亲密阶段
- `behavior_quality` 的 `romance_boundary_violation` 判定更是把 parent 的任何浪漫表达直接判违规

**后果**：已婚有孩子的 NPC 在运行时收不到亲密引导，在评测里又被判「越界」。

**两个选项**（原始记录，保留以见决策过程）：
1. **`parent` 继承 `married` 的亲密契约**（修 `stage_policy` 的集合）
2. **保持现状**，只在代码里把这条口径注释清楚

**✅ 已解决（2026-09-20 用户拍板，见 `active-work.md` 第 194 项）——走的是「比选项 1 更准」的第三条路。**

用户的原话是：「parent 这个要不要我们做两种状态，普通 npc 就沿用之前的，可婚 npc 和玩家有孩子变成新状态，
**这两种混一起感觉很麻烦啊**」——判断准确：`childrenCount > 0` 此前把两件事混成一件：
① **这个 NPC 自己有孩子**（如 Jodi 的两个孩子，属**背景信息**）；② **我和他有了孩子**（**关系状态**，是 married 的子状态）。

改法：只有「**配偶 + 有孩子**」才判 `parent`，非配偶的 `childrenCount` 不再影响阶段；新增
`INTIMATE_STAGES = {dating, married, parent}` 作为「既成亲密关系」的唯一定义，`stage_policy` 与
`behavior_quality` 的四处字面量改为引用它——**parent 因此恢复拿到 `affectionInitiative`**，
运行时与评测不再打架。

---

## P3 — 结构风险（当前无可见影响，但会腐化）

> **✅ 除 4 条需真机或产品决策的以外已全部处理（2026-09-20）**：C# 侧 #33／#34／#36–#38／
> #40／#42–#44 落于 `4eb9af9`（新增 5 个权威模块、按**等价重构**处理，并用 2^7／2^11
> 全组合枚举断言与改前一致）；Python 侧 #45（映射去重）、#46（默认值刻意的不同 → 注释 +
> 护栏测试）、#47／#48（跨语言常量 + 一致性测试）落于后续两个 commit。
> **未做并附理由**：#32 视口（会改渲染与点击坐标，需真机）、#35 F8 与交互键能聊到的集合
> 是否一致（产品决策，见待办 B26）、#39 是否统一大小写口径（任一方向都会改行为，
> 已用测试钉住差异）、#41 生产路径 `Context.IsWorldReady`（需真机）。
> 详见 `docs/semantic-duplication-p3-fixes-2026-09-20.md`。

| # | 概念 | 状态 |
|---|---|---|
| 32 | **聊天菜单按哪个视口算** | `ChatInputMenu`／`InventoryItemPicker` 用 `Game1.viewport`，两个群聊菜单用 `MenuViewportRules.PreferUiViewport`。**有文档证据**：设计文档写明「官方建议按 uiViewport……当前代码使用 viewport」，计划里写了待验证后再改——**这是一次没做完的统一** |
| 33 | **亲吻的双重门槛** | `KissInteractionRules` 与 `NpcKissAnimationController` 各判一遍；A 有 sameDay／npcNearby，B 没有。当前被 A 掩盖 |
| 34 | **「跟上次记住的 NPC 续聊」的前置条件** | 同一批值在两个方法体里各拼一次（7 个 vs 11 个实参）。表达式目前逐字一致，但无共享点 |
| 35 | **「当前该跟哪个 NPC 对话」** | F8 与交互键两套解析：距离门槛只在续聊侧、命中在一处只影响排序在另一处是硬条件 → **能按 F8 聊到的与能续聊的 NPC 集合不同**（与待办 B26 直接相关） |
| 36 | **消息区显示哪些消息** | 三套；`ChatLayoutRules.VisibleMessages` **生产零调用**（死规则，容易被误当权威） |
| 37 | **邀约卡按钮矩形算三遍** | draw 用局部字面量、点击用类常量 → 同一按钮两个矩形（视觉测试恰好点在交集内才没失败） |
| 38 | **面板矩形怎么放** | 四个菜单同构四份、边距两处常量两处字面量（当前等价） |
| 39 | **`relationType` 等白名单** | 三份，成员一致但**比较口径不同**（`Ordinal` vs `OrdinalIgnoreCase`）→ `"Dating"` 校验拒绝、亲吻接受 |
| 40 | **`HasFriendshipRecord`** | 两份同名同义实现（反射策略要改三处） |
| 41 | **「世界是否就绪」** | `Context.IsWorldReady` vs harness 的 `IsGameReady`，填进同一形参位 |
| 42 | **住宅门放行参数** | `minFriendship` 一处 `-1`、一处 `"0"`；`npcName` 一处 `null`、一处空串 |
| 43 | **「重大阶段」白名单** | `StoryStateModels` 里有死条目「订婚/结婚」（阶段名域里不存在） |
| 44 | **记忆写入规则** | 两份字段模板 + 去重 + 上限 + 截断，常量靠注释人工同步 |
| 45 | **`turn_plan.mode → 主动亲密要求`** | 两处各一份映射（当前一一对应） |
| 46 | **`provider`／`compactPrompt` 默认值** | 两边语义相反（当前都被显式发送掩盖） |
| 47 | **安全兜底文案** | 跨语言 4 份拷贝（当前逐字一致） |
| 48 | **topic 回声过滤正则** | 两语言各一份（当前逐字相同） |

---

## 没被采纳的（记录以免重复排查）

- **长度／条数上限**：C# 一律更严或相等（240<2000、6<40、20<50），方向安全，不会触发 422。
- **空消息判定**：核实为语义一致——`Topic` 意图走 `RequestTopicAsync`，`ConversationService` 只处理 `Chat`／`Item`。
- **`evidence.py`**：`is_model_evidence_record` 等被三方统一调用，无并行实现。
- **`_GUARDED_WARMTH_MARKERS`**：全仓只有定义、无引用——是**死表**而非重复实现。
- **`app.py` 的 15 个「无人调用」函数**：都是 FastAPI 路由，靠装饰器注册。
- **`DrawButton` 四份**：第一轮已修（抽到 `MenuButtonDrawing`）。
- **关系阶段集合与序号**：第一轮已统一下沉到 `relationship_gating`。

---

## 方法论（值得记住的）

1. **候选 ≠ 问题。** 表层扫了 604 处、语义层 64 个，真正有行为影响的是一部分。**核实语义是不可省的一步**——否则会改出一堆无意义的「重构」。
2. **最值钱的线索是「同名 tag 给出不同结论」**。P1 里大半是这么找出来的：两处都跑、都写同一个诊断字段，却因为规则表不同而结论相反。**这类分歧用户看不见，但会同时影响运行时行为与离线评测**，使评测结论与实际体验脱节。
3. **「两条路径各自演化」是本项目第一大技术债来源**：单轮 vs 多轮、私聊 vs 群聊、运行时 guard vs 离线评测、C# vs Python、事件投影 vs 案例声明。**修一条时一定要问：另一条路径呢？**
4. **改代码不要用正则做结构性删除。** 本次我用正则删 `DrawButton` 删过头（连带删掉相邻方法），改用行级配对又因签名跨行而删少——最终用精确字符串匹配才对。
5. **变异验证之后必须重新构建。** `dotnet test` 会把当时的源码构建进 `bin/`；恢复源码不会自动重建，于是「改坏的版本」可能被部署出去（本次实际发生过）。
