# NPC 主动引导普通对话设计规格

**日期：** 2026-09-03  
**状态：** 已获批准，正在五角色小批次实施与验证
**适用范围：** Bridge 普通 `chat` 回复的对话引导、质量诊断、有限重试、网页与游戏现有聊天链路

## 背景与目标

项目已经具备独立的“主动找话题”按钮：调用 `intent=topic` 时，NPC 可以在没有玩家输入的情况下开场。但普通 `intent=chat` 仍主要是“玩家提问 → NPC 回答”，高关系阶段因此容易变成机械问答。

本次目标是让 NPC 在普通回复中承担适量的对话推进责任：

1. 先直接回答玩家当前输入，保留当前话题和角色事实边界。
2. 回答后自然递出一个可继续的入口，让玩家知道 NPC 还想聊什么或想听什么。
3. 入口可以是角色自己的分享、具体追问、二选一、小话题桥接或带理由的轻量安排，不强制每轮提问。
4. 连续轮次避免固定使用同一种引导形状；玩家收口、明确拒绝或角色状态不适合时立即停止推进。

成功标准是：玩家无需反复追问，NPC 也能把话题交回玩家；推进内容仍像 Wizard / Sophia / Shane / Sebastian / Alex 本人，而不是统一的客服式“你呢？”。

## 已有能力与本次边界

### 继续复用的能力

- `intent=topic`、网页“主动找话题”按钮和游戏菜单中的对应动作继续保留。
- `BridgeClient` 已按 NPC 保存有限历史；普通 `chat` 的玩家输入和 NPC 回复继续进入历史，`topic` 的内部空触发不写入玩家历史。
- `remote` / `face_to_face`、成人同意、关系阶段、`genderPresentation`、角色基底和 Shane 的拒绝/收口边界继续由现有上下文与 Prompt 约束。
- 云端百炼 `qwen-plus-character` 仍为主生成器，本地 `qwen3.5:9b/4b` 只作离线控制组或 fallback。

### 不在本次范围内

- 不新增第二次模型请求，不把回答和引导拆成两个 Provider 调用。
- 不把 `chat` 自动改成后台连续发言，不在玩家未操作时插入第二条 NPC 消息。
- 不改变顶层公共请求/响应 JSON 契约；`history[]` 项可向后兼容地增加可选 `intent` 与 `relationshipStage` provenance，不写入正式 `Mods`、正式存档、Cookie、密钥或长期角色资料。
- 不要求陌生或初识阶段主动暧昧，不把所有角色改成持续热情人格。
- 不推广到全 NPC；`conversationLead` 只向 Wizard / Rasmodia、Sophia、Shane、Sebastian、Alex 的少量高关系案例投影。Rasmodia 先归一为 Wizard，再复用 Wizard 的策略。

## 交互与生成契约

### 普通 `chat` 的单轮结构

对 `close`、`dating`、`married` 阶段，Prompt 将普通回复定义为两个逻辑部分，但不强制固定句序：

```text
回答当前输入（必须） + 一个自然的继续入口（通常需要）
```

继续入口只需要在回复中出现一次，形式可以是：

- **角色分享：** NPC 说一件自己的近况、偏好或感受，并把落点交给玩家。
- **具体追问：** 针对当前话题中的对象或玩家刚说的细节，问一个能继续回答的问题。
- **二选一：** 给出两个符合场景的方向，让玩家选择下一步聊什么或做什么。
- **话题桥接：** 从当前对象自然连接到角色另一个已确认的兴趣、记忆或状态。
- **小安排：** 提出可商量的轻量行动，同时说明为什么想和玩家做，而不是单纯功能邀约。

引导入口不能只是“你呢？”、“还有什么吗？”、“一起去吧”或“陪你”。这些句子只有在带有具体对象、角色原因或玩家指向时才算有效。

普通回复继续只输出 NPC 中文对白，建议 1～3 句；不解释 `chat`、引导规则、质量标签或技术状态。不要先复述玩家原话再套模板，爱意、角色状态和引导可以自然交织。

### 阶段策略

| 关系阶段 | 引导要求 | 允许的退让 |
| --- | --- | --- |
| `stranger` / `acquaintance` | 只回答当前输入，不强制引导 | 角色可以礼貌补一句具体事实 |
| `friend` | 五角色试验范围内视话题自然加入分享或具体追问 | 泛日常、疲惫或玩家收口时可不引导 |
| `close` | 五角色试验范围内通常加入一个继续入口，保持角色克制 | 不强制换题，不要求亲密表达 |
| `dating` / `married` | 五角色试验范围内让回答、个人落点和继续入口自然结合 | 明确拒绝、需要空间、收口或渠道边界优先 |

`initiativeExpectation` 仍负责高阶段亲近要求；新增引导诊断只判断“是否把话题交回玩家”，不能用普通引导替代个人亲近，也不能把陪伴和具体安排自动判作爱意。

## 结构化上下文

在现有 `affectionInitiative` 之外，阶段策略向 Prompt 投影短的 `conversationLead` 卡。它只为五个目标 canonical NPC 的 `friend`、`close`、`dating`、`married` 阶段生成，并且 `PromptBuilder` 只在 `interaction.intent == "chat"` 时投影；`topic` 和 `item` 不进入普通聊天引导链。旧阶段、非目标 NPC 与其他 intent 不改变契约。

```json
{
  "intent": "chat",
  "npcId": "Sophia",
  "initiativeMode": "proactive",
  "required": "usually",
  "allowedKinds": [
    "self_share",
    "specific_follow_up",
    "choice_prompt",
    "topic_bridge",
    "reasoned_small_plan"
  ],
  "minimumExpression": "回答当前输入后，递出一个具体、可继续且符合角色的入口；不能只用泛问句。",
  "variationRule": "连续轮次避免重复同一 leadKind、开场结构和问句模板；没有新对象时继续承接当前话题。",
  "skipWhen": [
    "player_closing",
    "explicit_rejection",
    "npc_needs_space",
    "remote_or_face_to_face_boundary"
  ]
}
```

`intent`、`npcId` 与 `initiativeMode` 是运行时 Guard 的诊断上下文，不是给模型增加额外任务。为兼容旧的手工测试卡，缺少 `intent` 的卡暂按 `chat` 处理；生产 Prompt 必须写出完整元数据。

角色差异通过各自 `allowedKinds` 和行为示例体现：

- Wizard / Rasmodia：研究观察、克制分享、带具体对象的追问。
- Sophia：葡萄园、创作或生活细节的害羞分享与二选一。
- Shane：可以用嘴硬的实际关心或短问题推进；低落时允许拒绝和结束。
- Sebastian：少话、音乐/摩托车/夜间兴趣的低调分享，不强行热闹。
- Alex：行动派的具体选择、训练或生活回调，保留自信和轻微回撩。

## 质量诊断

在 `behavior_quality.py` 或现有质量纯函数中新增独立字段，不改变已有亲近字段：

- `answeredCurrentTopic`：是否保留并回答当前话题对象。
- `conversationLeadDetected`：是否出现有效继续入口。
- `conversationLeadKind`：`self_share`、`specific_follow_up`、`choice_prompt`、`topic_bridge`、`reasoned_small_plan` 或空值。
- `conversationLeadEvidence`：脱敏的类别或短证据标签，不保存完整 Prompt。
- `conversationLeadTags`：保留兼容标签，并新增：
  - `missing_conversation_lead`
  - `generic_follow_up_only`
  - `companionship_only`
  - `specific_plan_only`
  - `mechanical_conversation_lead`
  - `lead_exit_allowed`
- `conversationLeadOpening`：回复中人类可读的首个引导开场，用于工件查看；不用于单独决定机械化。
- `conversationLeadAnchors`：从本轮真实回复抽取的具体对象或角色状态，用于判断是否引入新内容；时间副词不是锚点。

生产诊断器必须始终返回这 7 个字段。评分和结果投影作为消费者必须兼容旧的 5 字段诊断替身：`conversationLeadOpening` 默认空字符串，`conversationLeadAnchors` 默认空列表，不能因缺字段中断整批评测。

有效入口必须同时满足“具体对象或状态”与“可让玩家继续回应”的条件。下列情况不通过：

- 只有功能安排、地点移动或“陪你”；
- 只有泛问句，没有当前对象或角色自身落点；
- 只重复玩家原句，没有新信息或选择；
- 与 `remote` / `face_to_face` 渠道冲突；
- Shane 明确说累、拒绝或结束时仍被强行追加问题。

玩家明确收口时，本轮不要求新的继续入口，但 NPC 只有自身也实际收口、告别、拒绝或表达需要空间时才可标为 `lead_exit_allowed`。若 NPC 在玩家收口后重新抛出邀约、问题或新话题，诊断须标记 `reopens_after_player_closing`，不能借玩家收口把该回复判为合格。

诊断只标记问题，不改写回复；与已有 `personalAffectionDetected` 并列输出，避免“有爱意但没有引导”与“有引导但没有爱意”混成一个分数。

## 连续轮次与 Guard

### 历史状态

评测和运行时已有的有限历史中，按 NPC 记录最近一次有效 `conversationLeadKind`、归一化开场或问句骨架和话题锚点。该状态只从本轮实际回复推导，不把 Prompt 内部标签写回聊天记录。`conversationLeadDetected=False`、`lead_exit_allowed`、非 `chat`、低阶段和非五角色的回合不能污染下一轮比较状态。

`BridgeClient` 和质量评测 runner 为同一请求写入的 user/assistant 历史项附加相同的可选 `intent`、`relationshipStage` provenance；Rasmodia 在机器 ID、资格判断和工件中归一为 `Wizard`，但保留 `displayName="Rasmodia"`。`ContextBuilder` 只把 provenance 用于上述状态推导，实际发给模型的 `conversation_history` 仍只含 `role` 与 `content`，不会泄露内部元数据。

### 机械形状

相邻轮次同时满足以下条件时标记 `mechanical_conversation_lead`：

1. `conversationLeadKind` 相同；
2. 去除标点、空白、数字和量词变化后，开场或问句骨架相同；
3. 没有新的玩家对象、角色状态或关系推进；
4. 玩家没有明确收口。

如果只是在同一话题上换了具体细节，或角色从分享改为具体追问，不判机械。机械标记最多触发一次 `variation` 重试，重试提示只要求换引导形状或承接方式，不要求提高甜度。

### 重试优先级

沿用现有 Guard 的有限重试顺序，在格式、渠道和关系边界之后加入：

1. 当前阶段要求引导但只有 `generic_follow_up_only` 或 `missing_conversation_lead`：触发一次 `conversation_lead` 重试；
2. 已有个人亲近但没有引导：只补引导，不重复要求爱意；
3. 已有有效引导但旧词表未命中：不重试；
4. `player_closing` 后 NPC 自身已收口、Shane 的 `guarded_exit_allowed`、明确拒绝或需要空间：不重试；重新开启话题仍按收口规则处理。

总重试次数继续受现有运行时和评测预算限制。失败重试仍通过 `_retry_quality_key()` 选择整体更自然的结果。

## 网页与游戏链路

- 网页单次聊天继续使用 `/api/dialogue/test` 的 `intent=chat`；回复气泡中自然包含回答和引导，不新增 UI 消息类型。
- 网页“主动找话题”继续使用 `intent=topic`，用于 NPC 无玩家输入时开场；它与普通 `chat` 的引导诊断分开显示。
- 游戏 `ConversationService.SendAsync()`、`BridgeClient` 历史和 `ChatInputMenu` 不需要新增请求；普通回复进入现有历史，下一轮 Prompt 即可承接 NPC 抛出的具体话头。
- 远程聊天只能谈当前线上内容或待确认安排；当面聊天只能谈当前同地点互动。任何引导都不能把渠道写反。

## TDD 验证矩阵

先写失败测试，再实现最小行为：

| 行为 | 测试位置 | 通过条件 |
| --- | --- | --- |
| 高阶段普通聊天要求继续入口 | `bridge/tests/test_prompts.py`、`test_behavior_quality.py` | Prompt 含引导契约；缺失入口有独立标签 |
| 回答后具体追问/分享/二选一通过 | `test_behavior_quality.py` | `answeredCurrentTopic=True`、`conversationLeadDetected=True` |
| “你呢？”或单纯陪伴/安排不算引导 | `test_behavior_quality.py` | `generic_follow_up_only`、`companionship_only` 或 `specific_plan_only` |
| 已有亲近但没有引导只补引导 | `test_guard.py` | 重试提示不重复要求个人亲近 |
| 已有语义引导但词表没命中不重试 | `test_guard.py` | Provider 调用次数保持 0 |
| 相邻轮次同引导形状被识别 | `test_character_quality_eval.py` | 仅重复骨架且无新锚点时有 `mechanical_conversation_lead` |
| 玩家明确收口不触发引导重试 | `test_guard.py`、`test_character_quality_eval.py` | 有 `lead_exit_allowed`，无额外请求 |
| 玩家收口后 NPC 又推进新话题 | `test_behavior_quality.py`、`test_character_quality_eval.py` | 标记 `reopens_after_player_closing`，不能借豁免通过 |
| Shane 低落/拒绝/需要空间继续有效 | `test_behavior_quality.py`、`test_guard.py` | 不强制追加问题或爱意 |
| `item`、非五角色和旧阶段不进入引导链 | `test_stage_policy.py`、`test_prompts.py`、`test_guard.py`、`test_character_quality_eval.py` | 不投影卡、不重试、不影响评测通过状态 |
| `remote` / `face_to_face` 边界不回归 | `test_prompts.py`、`test_api.py` | 渠道约束仍在 Prompt 和 API 请求中 |
| 现有 topic 按钮与历史契约不回归 | `smapi/tests/BridgeClientTests.cs`、`ConversationServiceTests.cs` | topic 空触发不进玩家历史；普通 chat 继续存储历史 |

## 小批次验收

代码和定向测试稳定后，在新的独立 artifacts 目录运行 3～6 个案例，优先覆盖五个目标角色的 `dating` / `married` 普通连续聊天。每个案例保留完整三轮 transcript、脱敏诊断和模型 usage。

人工审核重点：

- NPC 是否在回答后真的抛出可接的话头，而不是只回答或只说“你呢”；
- 引导是否来自角色自己的兴趣、状态和已确认历史；
- 连续三轮是否有分享、追问、选择等形状变化；
- Sebastian、Alex、Shane 是否仍像本人；
- Shane 的低落、拒绝、明确结束，以及 `remote` / `face_to_face` 边界是否正确。

只有同时满足“回答不丢题、NPC 能自然接管推进、引导不机械、边界不回归”时，才讨论是否推广到更多 NPC。本规格不授权批量推广。

## 验证命令

```powershell
# 定向测试
python -B -m pytest -q -p no:cacheprovider bridge/tests/test_behavior_quality.py bridge/tests/test_guard.py bridge/tests/test_prompts.py bridge/tests/test_character_quality_eval.py

# 游戏侧历史与 topic 契约
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter "FullyQualifiedName~BridgeClientTests|FullyQualifiedName~ConversationServiceTests"

# 全量与静态检查
python -B -m pytest -q -p no:cacheprovider bridge/tests
python -B -m compileall -q bridge/src bridge/tests
git diff --check
```

本轮不启动游戏、不部署 DLL、不修改正式存档。云端验证只写入新的批次目录，不覆盖历史工件。
