# NPC 主动引导普通聊天实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现，并在每个任务完成后运行文档中列出的验证命令。

**目标：** 在 Wizard / Rasmodia、Sophia、Shane、Sebastian、Alex 的 `friend`、`close`、`dating`、`married` 普通 `intent=chat` 中，让 NPC 在回答玩家当前输入后自然递出一个具体、可继续且符合角色的入口，同时保持个人亲近诊断独立、连续轮次不机械、Shane 与渠道边界不回归。

**架构：** `stage_policy.py` 仅为五个目标 canonical NPC 的四个阶段提供角色化 `conversationLead` 卡；`prompts.py` 只将该卡投影到 `intent=chat`，不增加 Provider 请求。`behavior_quality.py` 使用纯函数分别判断当前话题回答、引导类型、实际收口和开场/问句骨架；`guard.py` 使用卡内的 NPC、intent 与主动模式上下文，在格式、渠道、关系边界之后最多重试一次缺失或机械引导；`character_quality_eval.py` 只对适用回合记录脱敏诊断与连续轮次状态，并兼容旧诊断字段。

**技术栈：** Python 3.10+、pytest、现有 Bridge Prompt/Guard/质量评测；C# 侧仅运行既有历史与 topic 契约回归。

**执行状态（2026-09-04）：** 任务 1～4 的失败测试、最小实现与定向回归已完成；runner 已补齐 Rasmodia/Wizard canonical ID 和 `history[]` provenance，Prompt 会跳过不参与普通 chat 引导的历史对并保留最近有效引导。任务 5 的 Bridge 全量、`compileall`、SMAPI 定向回归、独立云端五角色批次和人工 transcript 审阅仍待执行，完成前不得推广。

---

### 任务 1：补齐引导诊断与 Prompt 的失败测试

**文件：**
- 修改：`bridge/tests/test_behavior_quality.py`
- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/tests/test_guard.py`
- 修改：`bridge/tests/test_character_quality_eval.py`

- [ ] **步骤 1：编写失败的测试**

新增以下可执行断言：

```python
def test_conversation_lead_separates_answer_from_specific_follow_up():
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {"initiative_expectation": "proactive"},
        "你说的葡萄酒已经稳定了。酒窖里还有两种香气，你想先听哪一种？",
        player_input="葡萄酒稳定了吗？",
    )
    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "choice_prompt"

def test_conversation_lead_rejects_generic_question_companionship_and_plain_plan():
    for reply, tag in (("还行。你呢？", "generic_follow_up_only"),
                       ("我陪你聊一会儿。", "companionship_only"),
                       ("今晚一起去鸡舍。", "specific_plan_only")):
        result = diagnose_conversation_lead(_high_affection_case(), {}, reply,
                                            player_input="今天怎么样？")
        assert result["conversationLeadDetected"] is False
        assert tag in result["conversationLeadTags"]

def test_conversation_lead_accepts_natural_private_share_and_player_caused_expectation():
    result = diagnose_conversation_lead(
        _high_affection_case(), {},
        "这件事我没和别人说过，想先告诉你。明晚你有空听我讲完吗？",
        player_input="最近还好吗？",
    )
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] in {"self_share", "specific_follow_up"}

def test_conversation_lead_allows_player_closing_and_shane_needs_space():
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {"initiative_expectation": "guarded"},
        "我今天累得不行，先让我一个人待会儿。",
        player_input="那我先走了。",
    )
    assert result["conversationLeadDetected"] is True
    assert "lead_exit_allowed" in result["conversationLeadTags"]
```

同时断言高阶段普通 chat Prompt 含 `conversationLead`、初识阶段不含该卡，topic 仍保留 `topic_response_contract`；Guard 缺引导只发一次 `conversation_lead_retry`，有个人亲近但缺引导时不追加 `affection`；语义引导未命中旧词表时 Provider 调用数为 0；相邻相同引导形状带 `mechanical_conversation_lead`；评测结果包含 `answeredCurrentTopic`、`conversationLeadDetected` 和 `conversationLeadKind`。

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -B -m pytest -q -p no:cacheprovider bridge/tests/test_behavior_quality.py bridge/tests/test_prompts.py bridge/tests/test_guard.py bridge/tests/test_character_quality_eval.py
```

预期：FAIL，报错集中在 `diagnose_conversation_lead`、`conversationLead` 字段或新重试类型尚未实现，而不是导入或测试语法错误。

---

### 任务 2：实现阶段策略与普通 chat Prompt 契约

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/stage_policy.py`
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 测试：`bridge/tests/test_prompts.py`

- [ ] **步骤 1：写失败测试并确认高/低阶段差异**

使用 `PromptBuilder().build(...)` 断言 `friend`、`close`、`dating`、`married` 的 JSON system message 含 `conversationLead` 与 `allowedKinds`，`stranger`、`acquaintance` 不含；`intent=topic` 仍生成空 `topic_trigger`。

- [ ] **步骤 2：运行红灯命令**

```powershell
python -B -m pytest -q -p no:cacheprovider bridge/tests/test_prompts.py -k "conversation_lead or topic"
```

- [ ] **步骤 3：编写最少实现**

在 `_SHARED_POLICIES` 为 `friend`、`close`、`dating`、`married` 增加结构化 `conversationLead`，字段固定为 `required`、`allowedKinds`、`minimumExpression`、`variationRule`、`skipWhen`；在 `_ROLE_OVERRIDES` 仅为五个目标角色补角色化允许类型。`_compact_stage_policy` 透传该卡；`PromptBuilder.build()` 的普通 chat 分支在 `player_input` 之前追加 `conversation_lead` system 卡，要求“先回答当前输入，再给具体入口”，禁止裸 `你呢`、单纯陪伴和无理由事务安排，并保留渠道/同意/收口规则。不要给 topic 分支追加普通 chat 卡。

- [ ] **步骤 4：运行绿灯命令**

```powershell
python -B -m pytest -q -p no:cacheprovider bridge/tests/test_prompts.py
```

预期：现有 Prompt 测试与新测试全部通过。

---

### 任务 3：实现独立引导诊断、Guard 重试与机械形状

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/behavior_quality.py`
- 修改：`bridge/src/stardew_ai_bridge/guard.py`
- 测试：`bridge/tests/test_behavior_quality.py`
- 测试：`bridge/tests/test_guard.py`

- [ ] **步骤 1：先运行任务 1 红灯测试**

确认失败原因为缺少行为，而非 Guard fixture 或 ProviderResult 构造错误。

- [ ] **步骤 2：编写最少实现**

在 `behavior_quality.py` 新增 `diagnose_conversation_lead(case, turn, reply, *, player_input="", previous_diagnostic=None)`，返回 `answeredCurrentTopic`、`conversationLeadDetected`、`conversationLeadKind`、`conversationLeadEvidence`、`conversationLeadTags`。引导必须同时包含当前对象/角色状态与可回应结构；自然中文覆盖专属分享、只对玩家说、因玩家产生期待、具体细节追问、二选一和角色化桥接；“你呢？”、裸陪伴、裸计划单独打标签但不通过。玩家收口、明确拒绝、Shane 低落/需要空间返回 `lead_exit_allowed`。个人亲近信号继续由 `diagnose_personal_affection` 单独负责。

在 `guard.py` 增加 `conversation_lead` 解析、最近一轮引导形状/话题锚点读取和 `_missing_conversation_lead()`；在格式、topic echo、渠道、亲近边界检查之后，普通高阶段缺失或泛问句触发一次 `CONVERSATION_LEAD_RETRY_CONTENT`，已有个人亲近时重试内容只要求补具体入口；有语义引导但词表未命中不重试；玩家收口与 Shane `guarded_exit_allowed` 不重试；同形状无新锚点最多触发一次 `VARIATION_RETRY_CONTENT`。

- [ ] **步骤 3：运行定向绿灯**

```powershell
python -B -m pytest -q -p no:cacheprovider bridge/tests/test_behavior_quality.py bridge/tests/test_guard.py
```

预期：新诊断、重试次数、Shane 豁免和既有个人亲近测试全部通过。

---

### 任务 4：接入质量评测与游戏契约回归

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 修改：`bridge/tests/test_character_quality_eval.py`
- 检查：`smapi/tests/BridgeClientTests.cs`
- 检查：`smapi/tests/ConversationServiceTests.cs`

- [ ] **步骤 1：编写并运行失败测试**

让 `score_character_reply()` 带 `player_input` 时写入引导字段；让 `score_conversation_lead_variation()` 对相同 kind、相同开场骨架且无新锚点标记机械，对换 kind 或具体对象不标记；加入 Shane 收口豁免测试。

- [ ] **步骤 2：编写最少实现**

调用 `diagnose_conversation_lead()` 并把字段加入评分结果；新增纯函数保存前一轮引导 kind、归一化开场和实际命中的对象，只对相邻同形状无新锚点标 `mechanical_conversation_lead`，收口始终豁免；质量目录/脱敏层只保留类别、标签和计数，不保留完整 Prompt。保持 SMAPI 端现有普通历史写入与 topic 空触发不写入玩家历史。

- [ ] **步骤 3：运行 Bridge 与 SMAPI 定向回归**

```powershell
python -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py
dotnet test smapi/tests/StardewAI.NPC.Tests.csproj --no-restore /p:OS=Windows_NT /p:GamePath="D:\sbeam\steamapps\common\Stardew Valley" --filter "FullyQualifiedName~BridgeClientTests|FullyQualifiedName~ConversationServiceTests"
```

---

### 任务 5：全量验证与五角色云端小批次

**文件：**
- 生成：`artifacts/character-quality-eval/20260903-conversation-lead-cloud-v1/`
- 检查：`docs/active-work.md`

- [ ] **步骤 1：运行完整静态与测试验证**

```powershell
python -B -m pytest -q -p no:cacheprovider bridge/tests
python -B -m compileall -q bridge/src bridge/tests
git diff --check
```

预期：Bridge 全量通过，`compileall` 和 `git diff --check` 返回码为 `0`；不把 `.tmp-pytest/` 加入 Git。

- [ ] **步骤 2：生成独立云端批次**

使用当前 `qwen-plus-character`、当前工作树 Bridge 和现有预算接口，只选 Wizard/Rasmodia、Sophia、Shane、Sebastian、Alex 的 3～6 个 `dating`/`married` 普通连续 `chat` 案例，输出完整三轮 transcript、脱敏诊断和 usage 到 `20260903-conversation-lead-cloud-v1`，不覆盖历史目录。

- [ ] **步骤 3：人工核对并记录结论**

逐案例阅读三轮 transcript，核对“回答当前输入 + 具体继续入口”、入口形状变化、角色基底、Sebastian/Alex/Shane 角色感、`remote`/`face_to_face`、Shane 收口与成人同意。若仍出现陪伴冒充爱意、泛问句或重复模板，只记录失败并停止推广，不修改正式 `Mods`、存档、密钥或长期资料。
