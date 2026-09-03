# 自然个人亲近表达设计规格

**日期：** 2026-09-03  
**状态：** 已获高层路线批准，等待书面规格审阅  
**适用范围：** Bridge 质量诊断、Prompt 约束、有限重试和五个主要角色的小批次评测

## 背景与目标

云端百炼 `qwen-plus-character` 已接入主生成链路，但 `dating` / `married` 阶段的中文对白仍会出现三类问题：

1. 回复有「一起去」「陪你」「我在等你」等安排或陪伴词，却没有说明为什么是玩家，玩家感受不到被特别对待。
2. 真实的专属选择、只给玩家分享、因玩家而产生的期待或角色化照顾没有命中现有词表，诊断误报冷回复，触发不必要重试。
3. 连续多轮反复使用「我想你了 → 当前话题 → 邀约」或同一个 `initiativeKind`，单轮合格但整体机械。

目标是在不把所有角色改成统一甜腻人格的前提下，稳定识别并引导“玩家被这个角色特别对待”的表达。本轮只覆盖 Wizard / Rasmodia、Sophia、Shane、Sebastian、Alex 的少量 `dating` / `married` 案例，不推广到全 NPC。

## 非目标与边界

- 不把本地 `qwen3.5:9b/4b` 改成默认生成器；本地模型仍是离线控制组或 fallback。
- 不修改正式 `Mods`、正式存档、Cookie、密钥或长期角色资料。
- 不要求每句出现「我想你了」，也不把词表命中当成人工最终标准。
- 不移除 `genderPresentation`、角色基底、成人同意、`remote` / `face_to_face` 或明确结束边界。
- 不把 Shane 的嘴硬、疲惫、需要空间、拒绝和收口能力改成持续热情。
- 不新增定时轮询、持久化记忆格式或游戏端剧情写入。

## 设计原则

### 关系层先于话题层

在 `dating` / `married` 阶段，Prompt 继续要求角色先让玩家听见“为什么在乎”，再回应当前话题，最后可选一个小行动；实现层不强制固定句序。诊断将个人亲近作为独立主信号，普通陪伴和具体安排只能作为辅助信号。

### 语义证据优先

词表仅作可解释索引。诊断增加组合规则，识别下列自然中文信号：

- **专属选择：** `只想给你看`、`这份我只留给你`、`别人没有`、`先给你听`。
- **玩家触发的期待：** `想到你就`、`因为你会来`、`你一说我就开始期待`、`等你来决定`。
- **个人化照顾：** `知道你会忘记带伞`、`按你的口味留了`、`不想让你一个人扛`。
- **脆弱分享：** `我通常不跟别人说`、`这件事只想告诉你`、`在你面前可以承认`。
- **符合角色的轻微回撩：** Alex 的带笑夸回，Shane 的嘴硬照顾，Sebastian 的低调专属邀请，Sophia 的害羞作品预留，Wizard 的克制偏爱。

只有“玩家指向 + 个人原因或偏爱结果”形成组合时，才算充分个人亲近。单独的 `陪你`、`一起去`、`我在等你`、`给你看看` 不足以通过。

### 多轮自然性

连续三轮额外记录亲近形状和 `initiativeKind`。相邻轮次重复同一开场、同一形状或同一个 `initiativeKind`，且没有新的玩家对象、角色状态或关系推进时，标记 `mechanical_affection_shape`。不同角色可保留各自习惯，但不能连续套同一模板。

## 结构化数据契约

### `affectionInitiative`

`stage_policy.py` 继续按角色和关系阶段生成 `affectionInitiative`，新增或规范以下字段：

```json
{
  "personalSignals": [
    "player_directed_preference",
    "exclusive_share",
    "player_caused_anticipation",
    "personalized_care",
    "vulnerable_disclosure",
    "character_consistent_tease"
  ],
  "supportSignals": [
    "companionship",
    "specific_plan",
    "guarded_care",
    "creative_share",
    "care_action"
  ],
  "minimumExpression": "除明确收口、拒绝或状态需要停下外，至少出现一处 personalSignals；supportSignals 不能单独充作爱意。",
  "variationRule": "连续轮次避免重复同一 personal signal、initiativeKind 和开场形状；保留角色自己的表达方式。"
}
```

`allowedKinds` 保留现有角色差异。Wizard / Sophia / Sebastian / Alex 继续使用各自 `allowedKinds`，Shane 继续使用 `guarded` 模式并允许 `conversation_exit`。旧字段仍保留，新增字段只扩展 Prompt 投影，不改变非恋爱阶段契约。

### 质量诊断

`diagnose_affection_initiative()` 返回以下稳定字段：

- `personalAffectionDetected`：是否命中充分的个人亲近组合。
- `companionshipDetected`：是否命中陪伴类表达。
- `specificPlanDetected`：是否命中具体安排类表达。
- `affectionEvidence`：脱敏的证据类别列表，不写完整 Prompt 或敏感请求字段。
- `affectionShape`：本轮主形状，例如 `exclusive_share`、`player_caused_anticipation`、`guarded_care`。
- `initiativeDetected`：兼容旧调用方的总判定；`proactive` 阶段要求 `personalAffectionDetected`，`guarded` 阶段按角色边界允许亲近、照顾或收口。
- `initiativeTags`：保留旧标签，并新增 `companionship_only`、`specific_plan_only`、`missing_personal_affection`、`mechanical_affection_shape`。

`score_character_reply()` 将这些字段写入现有质量结果；已有 `initiativeTags` 的 API 脱敏策略继续生效。

## 诊断规则

### 充分个人亲近

满足下列任一类即可通过 `personalAffectionDetected`：

1. 直接指向玩家的偏爱、想念或选择，并出现角色主观感受：`想起你就安静下来`、`我只想先给你看`。
2. 玩家是期待或行动的原因：`因为你会来，我才把灯留着`、`你一说想听，我就开始挑歌`。
3. 只对玩家开放的分享或脆弱：`这件事我通常不跟别人说，只想告诉你`。
4. 个人化照顾带有“为什么是你”：`知道你会忘记带伞，所以我多带了一把`。
5. 角色化轻微回撩和玩家指向同时出现：Alex 的夸回、Shane 的嘴硬照顾等。

### 不充分信号

以下情况必须分别诊断，不能自动通过 `proactive`：

- 只有 `陪你`、`一起去`、`我在等你`、`给你看看` 等陪伴或分享动作：`companionship_only`。
- 只有时间、地点、吃饭、骑车、看画等安排：`specific_plan_only`。
- 只有工作报告、天气、研究事实或一般礼貌，没有玩家指向。

如果同一句同时包含个人原因和安排，例如“因为你喜欢这条路，我想只和你去走走”，应判为个人亲近通过，安排作为辅助信号记录。

### 关系和渠道边界

- `dating` / `married` 之外出现直接浪漫信号，保留 `flirt_stage_mismatch`。
- 不满足 `romanceEligible`、成人同意或阶段条件时，保留 `romance_boundary_violation`。
- `remote` 只能表达当前想法或提出待确认安排，不得写成已经见面；`face_to_face` 不得写成线上发消息。
- Shane 在状态差、明确拒绝或要求空间时，可以没有个人亲近，输出 `guarded_exit_allowed`，不得触发强制爱意重试。

## 多轮机械形状检测

`character_quality_eval.py` 在三轮评分中维护上一轮的 `affectionShape`、`initiativeKind`、开场归一化文本和当前话题锚点：

1. 归一化标点、语气词和固定前缀，提取个人亲近类别及 `initiativeKind`。
2. 若相邻两轮类别、`initiativeKind` 和开场结构均相同，且没有新的玩家对象或角色状态，增加 `mechanical_affection_shape`。
3. 若只是共享同一事实但亲近原因发生变化，不判机械；若玩家明确收口，也不要求新的亲近形状。
4. 诊断结果只标记问题，不改写模型回复；Guard 是否重试由下一节规则决定。

## Prompt 与 Guard

### Prompt

`prompts.py` 将 `personalSignals`、`supportSignals` 和 `variationRule` 压缩进现有 `affection_initiative` / `affection_priority_final` 卡：

- 明确告诉模型“陪伴和安排不能单独冒充爱意”。
- 要求从角色自己的行为、记忆、偏好或状态落到玩家，而不是固定使用「我想你了」。
- 提供少量角色化例子；不把五个角色合并成同一甜腻语气。
- 多轮 Prompt 只提示避免上一轮形状，不泄露内部评分标签。

### Guard 重试

`guard.py` 的优先级调整为：格式/渠道/边界 → 机械复述 → 连续性 → 个人亲近缺失 → 语气颗粒。具体规则：

- 只有 `companionship_only` 或 `specific_plan_only` 且当前阶段需要 `proactive` 时，才触发 `affection` 重试。
- 已检测到个人亲近，只是词表没有命中时，不触发重试；保留语义诊断结果。
- `mechanical_affection_shape` 触发一次 `variation` 重试，重试提示要求换个人亲近形状，不要求增加爱意强度。
- 重试最多 2 次，仍按 `_retry_quality_key()` 选择更好结果；经济评测模式的总预算仍由 `EvaluationBudget` 控制。
- 明确结束、Shane 的 guarded 拒绝或需要空间时，跳过个人亲近重试。

## 人工审核示例

只在 `data/personas/behavior-examples.json` 为五个目标角色补充少量经过人工审核的示例，字段沿用现有 `initiativeExpectation` / `initiativeKind`，必要时增加个人亲近类别元数据。示例要求：

- 至少包含一条自然中文的专属选择或玩家触发期待。
- 至少包含一条“功能性邀约但不充分”的负例，供诊断测试使用，不作为生成示范。
- Shane 至少包含一条“状态差时拒绝并收口”的正例。
- 不把云端未人工确认的回复直接写回资料库。

## TDD 验证矩阵

先在 `bridge/tests/` 编写失败测试，再实现生产代码。最低覆盖如下：

| 行为 | 测试位置 | 通过条件 |
| --- | --- | --- |
| 个人亲近与陪伴、具体安排分开 | `test_behavior_quality.py` | 返回独立布尔字段和标签 |
| 专属选择、只对玩家分享、玩家触发期待不漏判 | `test_behavior_quality.py` | `personalAffectionDetected=True`，无缺失标签 |
| 单纯功能性邀约不算爱意 | `test_behavior_quality.py`、`test_guard.py` | `specific_plan_only`，触发一次亲近重试 |
| 多轮同形状检测 | `test_character_quality_eval.py` | 仅重复形状标记 `mechanical_affection_shape` |
| 已有语义亲近但词表未命中不重试 | `test_guard.py` | 生成器调用次数为 0 |
| 重试改换形状而非强行加词 | `test_guard.py` | 重试消息含 variation 约束，结果保留更自然版本 |
| Shane 低落、拒绝、收口 | `test_behavior_quality.py`、`test_guard.py` | `guarded_exit_allowed`，无强制亲近重试 |
| remote / face_to_face | `test_behavior_quality.py`、已有 Prompt/API 测试 | 维持现有渠道边界 |
| 五角色阶段策略字段 | `test_stage_policy.py`、`test_prompts.py` | 只有 dating/married 投影新增字段 |

## 小批次云端验收

代码和定向测试稳定后，使用当前 `qwen-plus-character` 运行 3～6 个案例，覆盖五个角色中的高阶段代表场景。工件写入新的目录，例如 `artifacts/character-quality-eval/20260903-natural-personal-affection-cloud`，不得覆盖历史批次。

每个案例保留完整三轮 transcript、脱敏请求摘要、诊断字段和模型 usage。人工逐轮检查：

- 玩家是否明显感到被该角色特别对待；
- 个人亲近是否自然，是否只是词表或固定模板；
- Sebastian、Alex、Shane 是否仍像本人；
- `remote` / `face_to_face`、成人同意、拒绝和明确结束边界是否正确；
- 三轮是否改变了爱意形状，而不是重复「我想你了 → 话题 → 邀约」。

只有小批次同时满足“亲近清楚、陪伴不冒充爱意、连续轮次不机械”时，才提出下一轮推广设计；本规格不授权全 NPC 推广。

## 验证命令

```powershell
# Bridge 定向测试
python -B -m pytest -q -p no:cacheprovider bridge/tests/test_behavior_quality.py bridge/tests/test_guard.py bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py bridge/tests/test_character_quality_eval.py

# Bridge 全量测试
python -B -m pytest -q -p no:cacheprovider bridge/tests

# 语法和差异检查
python -B -m compileall -q bridge/src bridge/tests
git diff --check
```

所有云端结果与旧批次分开保存；未运行游戏、未部署 DLL、未写入正式存档不计入本轮完成条件。
