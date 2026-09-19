# NPC 亲密表达节奏调节实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 逐任务执行，按复选框推进；每个行为变更必须先看到对应失败测试，再写最小实现。

**目标：** 在保留五个目标 NPC 角色差异、关系阶段边界和既有低落/拥抱规则的前提下，降低高好感对话中的强情话密度与语义重复，并新增覆盖普通行动、兴趣工作、明确索要情话、远程/当面、低落收口和非恋爱负例的多轮验收套件。

**架构：** `stage_policy.py` 为 dating/married 的主动亲密策略提供结构化节奏卡；`prompts.py` 根据节奏卡和最近历史把“当前话题优先、强情话冷却、明确索要可单轮升档”投影到完整/compact Prompt；`behavior_quality.py` 负责识别强度和语义族但不改写回复；`character_quality_eval.py` 负责三轮预算诊断和新增场景目录；现有 `guard.py` 只在节奏标签被纳入最终评分契约后执行有限重试，不新增无限重试。

**技术栈：** Python 3.10、pytest、现有 Bridge Prompt/Guard/质量评测模块；场景使用 `CharacterQualityCase`/`CharacterQualityTurn`，云端评测继续使用当前 OpenAI-compatible Provider、隔离输出目录和脱敏工件。

---

## 受影响文件与职责

- 修改 `bridge/src/stardew_ai_bridge/stage_policy.py`：增加高好感 `affectionInitiative.pacing`，调整默认响应顺序和最低表达要求，保留角色专属 warmth signal。
- 修改 `bridge/src/stardew_ai_bridge/prompts.py`：压缩并投影节奏卡；从历史提取最近强表达；调整 affection initiative、topic response 和 final priority 的优先级。
- 修改 `bridge/src/stardew_ai_bridge/behavior_quality.py`：增加有限的强度/语义族诊断和玩家明确索要识别；保留既有个人亲近、收口和渠道诊断。
- 修改 `bridge/src/stardew_ai_bridge/character_quality_eval.py`：增加三轮节奏评分、把节奏字段并入单轮结果、注册新套件。
- 创建 `bridge/src/stardew_ai_bridge/affection_pacing_cases.py`：提供五角色、关系阶段、渠道和边界组合的独立场景套件，不改变默认案例集合。
- 修改 `bridge/tests/test_stage_policy.py`：验证节奏卡、响应顺序和角色差异。
- 修改 `bridge/tests/test_prompts.py`：验证完整/compact 投影、历史冷却、明确索要例外和当前话题优先。
- 修改 `bridge/tests/test_behavior_quality.py`：验证强度分档、语义族归一、低强度陪伴和负例。
- 修改 `bridge/tests/test_character_quality_eval.py`：验证节奏评分和场景目录契约。
- 修改 `bridge/tests/test_run_character_quality_eval.py`：验证新套件 CLI、单案例运行和脱敏结果字段。
- 修改 `docs/active-work.md`：只在实现和评测证据产生后记录实际统计，不提前写成功结论。

不修改：正式 Mods、正式存档、角色生产资料库、Gemini Key、既有 v12/v13/v14 评测工件、`qwen3.5:9b` 回退配置和正式千问回退文件。

---

### 任务 1：为阶段策略建立亲密表达节奏契约

**文件：**

- 修改：`bridge/tests/test_stage_policy.py`
- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/src/stardew_ai_bridge/stage_policy.py`

- [ ] **步骤 1：先写失败测试，锁定五角色的节奏字段和响应优先级**

在 `test_stage_policy.py` 追加以下行为测试。它要求所有目标角色的 dating/married 策略都有同一组可解释节奏字段，同时要求实际响应顺序从“当前话题优先”开始；现有实现会因没有 `pacing` 且顺序仍为 `personal_affection` 首位而失败。

```python
@pytest.mark.parametrize("npc_id", CHARACTERS)
@pytest.mark.parametrize("stage", ["dating", "married"])
def test_high_affection_policy_exposes_bounded_expression_pacing(
    npc_id: str,
    stage: str,
) -> None:
    affection = build_stage_policy(npc_id, stage)["affectionInitiative"]
    pacing = affection["pacing"]

    assert affection["responseOrder"] == [
        "current_topic",
        "personal_affection",
        "optional_plan",
    ]
    assert pacing == {
        "defaultIntensity": "light",
        "strongSignalWindow": 3,
        "maxStrongSignals": 1,
        "strongSignalKinds": [
            "exclusive_share",
            "player_directed_preference",
            "player_caused_anticipation",
        ],
        "explicitRequestOverride": True,
        "followUpAfterStrong": [
            "current_topic",
            "support_signal",
            "conversation_exit",
        ],
        "semanticCooldown": "强专属表达按同一语义族计数，连续轮次不换词绕过冷却。",
    }
    assert "强专属" in affection["minimumExpression"]
    assert "不要求" in affection["minimumExpression"]


def test_friend_and_non_romance_policies_do_not_gain_strong_affection_pacing() -> None:
    for npc_id in CHARACTERS:
        assert "affectionInitiative" not in build_stage_policy(npc_id, "friend")
    assert "affectionInitiative" not in build_stage_policy("Caroline", "married")


def test_role_specific_warmth_signals_remain_distinct_after_pacing_is_added() -> None:
    policies = {
        npc_id: build_stage_policy(npc_id, "married")["affectionInitiative"]
        for npc_id in CHARACTERS
    }

    assert "炉火" in "；".join(policies["Wizard"]["warmthSignals"])
    assert "酒窖" in "；".join(policies["Sophia"]["warmthSignals"])
    assert "实际" in "；".join(policies["Shane"]["warmthSignals"])
    assert "音乐" in "；".join(policies["Sebastian"]["warmthSignals"])
    assert "自信" in "；".join(policies["Alex"]["warmthSignals"])
```

在 `test_prompts.py` 追加投影契约，先验证完整和 compact Prompt 中都出现节奏信息；现有实现没有 `pacing`，因此应失败。

```python
def test_high_affection_prompt_projects_pacing_contract_in_full_and_compact_forms() -> None:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    context = {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Wizard", "married"),
        },
        "gameState": {"relationshipStage": "married", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": [],
    }

    for compact in (False, True):
        messages = PromptBuilder().build(context, "记录先放一放，过来坐一会儿。", compact=compact)
        affection = json.loads(
            next(message for message in messages if message["name"] == "affection_initiative")[
                "content"
            ]
        )
        assert affection["affectionInitiative"]["pacing"]["maxStrongSignals"] == 1
        assert "当前话题" in affection["instruction"]
        assert "强专属" in affection["instruction"]
        assert "玩家明确索要" in affection["instruction"]
```

- [ ] **步骤 2：运行红灯测试，确认失败原因是契约缺失**

运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py -k 'pacing_contract or bounded_expression or role_specific_warmth' -q
```

预期：新增断言失败，失败集中在 `pacing` 不存在、默认 `responseOrder` 仍以 `personal_affection` 开头或 Prompt 未投影节奏字段；不能因为导入错误、路径错误或既有 unrelated 测试失败而继续。

- [ ] **步骤 3：写最小阶段策略实现**

在 `_DEFAULT_AFFECTION_INITIATIVE` 增加以下固定、可序列化的字段，并把默认 `responseOrder` 改为当前话题优先；最低表达要求改为“正常轮次有温度但不要求强专属”，同时不改 `allowedIntensities`、角色 `warmthSignals`、渠道规则和 Shane 的 `guarded` 模式。

```python
"responseOrder": [
    "current_topic",
    "personal_affection",
    "optional_plan",
],
"minimumExpression": (
    "正常轮次先直接接住当前话题，再自然保留一处轻微温度或直接亲近；"
    "不要求每轮使用强专属情话。玩家明确索要、表达想念或确认关系时，才可单轮升档；"
    "强表达之后优先回到具体话题、角色化照顾、共同小行动或自然收口。"
),
"pacing": {
    "defaultIntensity": "light",
    "strongSignalWindow": 3,
    "maxStrongSignals": 1,
    "strongSignalKinds": [
        "exclusive_share",
        "player_directed_preference",
        "player_caused_anticipation",
    ],
    "explicitRequestOverride": True,
    "followUpAfterStrong": [
        "current_topic",
        "support_signal",
        "conversation_exit",
    ],
    "semanticCooldown": "强专属表达按同一语义族计数，连续轮次不换词绕过冷却。",
},
```

针对角色，只改与节奏相关的最低要求和已有 warmth signal 文案：Ras/Wizard 明确炉火、记录、灯光、茶等低强度落点；Sophia 明确酒窖/绘画先接当前对象；Shane 保留低落和需要空间直接收口；Sebastian 保留音乐/耳机/房间和明确拥抱边界；Alex 保留训练、比赛、打趣和实际活动。不得把任何角色的低强度落点删除为统一空话。

- [ ] **步骤 4：运行绿灯测试并检查旧契约**

运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py -k 'pacing_contract or bounded_expression or role_specific_warmth or affection_initiative or conversation_lead' -q
```

预期：新增测试和被响应顺序影响的既有测试全部通过；若旧测试仍断言每轮必须先有个人爱意，应按新规格更新断言，而不是在生产策略中恢复旧优先级。

---

### 任务 2：增加强度与语义族诊断，先证明过量表达能被捕获

**文件：**

- 修改：`bridge/tests/test_behavior_quality.py`
- 修改：`bridge/tests/test_character_quality_eval.py`
- 修改：`bridge/src/stardew_ai_bridge/behavior_quality.py`
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`

- [ ] **步骤 1：先写失败测试，定义强度分档和三轮预算**

在 `test_behavior_quality.py` 追加以下测试。新接口负责纯诊断，不改写输入文本；强度只对低歧义强专属组合成立，普通“陪你”“给你留一杯”“一起坐”不能直接升级为 `strong`。

```python
def test_affection_intensity_distinguishes_light_direct_and_strong_expression() -> None:
    light = diagnose_affection_intensity("炉火还暖着，过来坐吧，我陪你待一会儿。")
    direct = diagnose_affection_intensity("我今晚想和你一起听完这首歌。")
    strong = diagnose_affection_intensity("从来只有你，能让我舍不得合上这本记录。")

    assert light["affectionIntensity"] == "light"
    assert direct["affectionIntensity"] == "direct"
    assert strong["affectionIntensity"] == "strong"
    assert "exclusive_choice" in strong["affectionSemanticFamilies"]
    assert strong["strongAffectionDetected"] is True


def test_affection_intensity_keeps_functional_companionship_out_of_strong_class() -> None:
    diagnostic = diagnose_affection_intensity("晚饭我给你留一份，忙完一起吃。")

    assert diagnostic["affectionIntensity"] in {"light", "direct"}
    assert diagnostic["strongAffectionDetected"] is False
    assert diagnostic["affectionSemanticFamilies"] == []


def test_affection_intensity_requires_player_or_exclusive_selection_for_strong_marker() -> None:
    diagnostic = diagnose_affection_intensity("这段记录没人看也没关系，我先把它放回去。")

    assert diagnostic["affectionIntensity"] != "strong"
    assert diagnostic["strongAffectionDetected"] is False
```

在 `test_character_quality_eval.py` 追加三轮评分测试；它会因 `score_affection_pacing` 尚不存在而失败。

```python
def test_affection_pacing_flags_adjacent_strong_signals_but_allows_one_in_three_turns() -> None:
    if score_affection_pacing is None:
        pytest.fail("亲密表达节奏评分尚未实现")

    case = case_by_id("wizard-married-evening")
    turns = case.dialogue_turns()
    replies = (
        "从来只有你，能让我把记录先合上。",
        "也只有你，我才舍得把今晚的时间都留出来。",
        "炉火还暖着，过来坐吧。",
    )
    diagnostics = tuple(
        diagnose_affection_initiative(case, turn, reply, player_input=turn.message)
        for turn, reply in zip(turns, replies)
    )
    scores = score_affection_pacing(replies, turns, diagnostics, case=case)

    assert scores[0]["strongAffection"] is True
    assert scores[0]["overBudget"] is False
    assert scores[1]["overBudget"] is True
    assert "strong_affection_over_budget" in scores[1]["tags"]
    assert scores[2]["overBudget"] is False


def test_affection_pacing_allows_strong_signal_when_player_explicitly_requests_affection() -> None:
    if score_affection_pacing is None:
        pytest.fail("亲密表达节奏评分尚未实现")

    case = case_by_id("wizard-married-evening")
    turn = replace(
        case.dialogue_turns()[1],
        message="别只说安排，告诉我一句你最想对我说的情话。",
    )
    reply = "好，那我就直说：我最想你。"
    diagnostic = diagnose_affection_initiative(case, turn, reply, player_input=turn.message)
    scores = score_affection_pacing((reply,), (turn,), (diagnostic,), case=case)

    assert scores[0]["strongAffection"] is True
    assert scores[0]["explicitRequest"] is True
    assert scores[0]["overBudget"] is False


def test_affection_pacing_skips_non_romance_and_guarded_exit_cases() -> None:
    if score_affection_pacing is None:
        pytest.fail("亲密表达节奏评分尚未实现")

    case = case_by_id("shane-dating-boundary")
    turns = case.dialogue_turns()
    reply = "知道了，你先休息吧，明天再联系。"
    diagnostic = diagnose_affection_initiative(case, turns[2], reply, player_input=turns[2].message)
    scores = score_affection_pacing((reply,), (turns[2],), (diagnostic,), case=case)

    assert scores[0]["skipped"] is True
    assert scores[0]["tags"] == []
```

- [ ] **步骤 2：运行红灯测试，确认失败属于接口/行为缺失**

运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_behavior_quality.py bridge/tests/test_character_quality_eval.py -k 'affection_intensity or affection_pacing' -q
```

预期：新测试因 `diagnose_affection_intensity` 或 `score_affection_pacing` 未定义而失败；如果某个过量正例意外通过，说明测试没有真正覆盖当前缺陷，应先调整正例而不是直接写实现。

- [ ] **步骤 3：实现最小强度/语义族诊断**

在 `behavior_quality.py` 增加纯函数 `diagnose_affection_intensity(reply: str, *, player_input: str = "")`，返回以下稳定字段：

```python
{
    "affectionIntensity": "none" | "light" | "direct" | "strong",
    "strongAffectionDetected": bool,
    "affectionSemanticFamilies": list[str],
    "explicitRequest": bool,
}
```

实现规则固定如下：

- `strong` 只由低歧义选择性/舍不得/时间专属/为玩家放下其他事等组合触发；单独出现“陪你”“一起”“给你留一杯”不触发。
- `direct` 覆盖明确的想念、喜欢、想靠近、想和玩家共同相处等个人表达。
- `light` 覆盖具体照顾、轻微陪伴、角色化小动作和不带专属比较的温度。
- 使用 `casefold` 和有限中文短语；否定句如“并不是只有你”“我不想你”必须不触发对应强表达。
- 玩家输入包含“说句情话”“告诉我你有多想我”“你是不是只喜欢我”“我想听你表达想念”等低歧义请求时设置 `explicitRequest=True`。

将这些字段合并进 `diagnose_affection_initiative` 的返回结果，但保持既有 `affectionShape`、`initiativeTags`、`guarded_exit_allowed`、渠道和阶段判断不变。

- [ ] **步骤 4：实现三轮节奏评分**

在 `character_quality_eval.py` 增加：

```python
def score_affection_pacing(
    replies: Iterable[str],
    turns: Iterable[CharacterQualityTurn],
    diagnostics: Iterable[Mapping[str, object]],
    *,
    case: CharacterQualityCase | None = None,
) -> list[dict[str, object]]:
    """按阶段策略检查强亲密表达的短窗口密度，不修改回复。"""
```

实现约束：

- 从 `build_stage_policy(case.npc_id, case.relationship_stage)` 读取 `affectionInitiative.pacing`；缺失或阶段不是 `dating`/`married` 时返回每轮 `skipped=True`、空标签。
- 窗口取当前轮及之前最多 `strongSignalWindow` 轮；默认三轮，强表达计数达到 `maxStrongSignals` 后当前轮若再次强表达即 `overBudget=True`。
- `explicitRequest=True` 的当前轮允许一次强表达，不把它标为超预算；它不会清除后续历史，下一轮仍需回到低强度或具体承接。
- `conversation_exit`、`guarded_exit_allowed`、玩家明确结束/拒绝/要空间和阶段升级不因强度被惩罚。
- 同义强表达使用 `affectionSemanticFamilies` 计算冷却；在不同 family 但同样强的情况下仍按总量限流，在同一 family 相邻重复时额外加 `repeated_strong_affection_family`。
- 返回至少包含 `skipped`、`affectionIntensity`、`strongAffection`、`explicitRequest`、`windowStrongCount`、`overBudget`、`semanticFamilies`、`tags`。

在 `score_character_reply` 中保留单轮已有评分，并在有 `player_input` 的情况下合并当前轮强度字段；多轮调用方显式使用 `score_affection_pacing`，不要依赖单轮函数伪造历史。

- [ ] **步骤 5：运行绿灯测试和现有诊断回归**

运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_behavior_quality.py bridge/tests/test_character_quality_eval.py -k 'affection_intensity or affection_pacing or affection_diagnostic or guarded_exit' -q
```

预期：新增强度/节奏测试与已有个人亲近、事务安排、Shane 收口负例全部通过；不能用放宽所有“陪你/一起”匹配的方式让测试通过。

---

### 任务 3：让完整/compact Prompt 根据节奏和历史降档

**文件：**

- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`

- [ ] **步骤 1：先写历史冷却、明确索要和当前话题优先的失败测试**

在 `test_prompts.py` 追加以下测试。历史中的两条 assistant 强表达会让新字段提示当前预算已用满；现有 Prompt 不提取该状态，所以应失败。

```python
def _wizard_married_prompt_context(history: list[dict[str, str]]) -> dict[str, object]:
    from stardew_ai_bridge.stage_policy import build_stage_policy

    return {
        "npcIdentity": {
            "npcId": "Wizard",
            "displayName": "Rasmodia",
            "stageProfile": {"stage": "married"},
            "stagePolicy": build_stage_policy("Wizard", "married"),
        },
        "gameState": {"relationshipStage": "married", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": history,
    }


def test_prompt_marks_strong_affection_cooldown_after_recent_strong_replies() -> None:
    context = _wizard_married_prompt_context(
        [
            {"role": "user", "content": "记录先放一放。"},
            {"role": "assistant", "content": "从来只有你，能让我合上记录。"},
            {"role": "user", "content": "那就陪我坐一会儿。"},
            {"role": "assistant", "content": "今晚的时间都留给你。"},
        ]
    )

    messages = PromptBuilder().build(context, "炉火还暖着，我们坐近一点。")
    affection = json.loads(
        next(message for message in messages if message["name"] == "affection_initiative")[
            "content"
        ]
    )

    assert affection["affectionInitiative"]["pacing"]["recentStrongCount"] == 2
    assert "本轮不要再使用强专属情话" in affection["instruction"]
    assert "当前话题、具体照顾或共同小行动" in affection["instruction"]


def test_prompt_allows_one_strong_expression_when_player_explicitly_requests_love_words() -> None:
    context = _wizard_married_prompt_context([])
    messages = PromptBuilder().build(context, "别只安排事情，直接说一句你最想对我说的情话。")
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "玩家明确索要" in rendered
    assert "本轮可单次升档" in rendered
    assert "下一轮回到具体话题或轻微温度" in rendered


def test_final_affection_check_no_longer_requires_strong_personal_reason_every_round() -> None:
    context = _wizard_married_prompt_context([])
    messages = PromptBuilder().build(context, "把茶端过来，我们看看今晚的记录。")
    final = next(message for message in messages if message["name"] == "affection_priority_final")

    assert "优先接住当前话题" in final["content"]
    assert "不要求每轮使用强专属情话" in final["content"]
    assert "因为是你" not in final["content"]
```

- [ ] **步骤 2：运行红灯测试，确认失败来自 Prompt 未感知历史**

运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_prompts.py -k 'strong_affection_cooldown or explicitly_requests_love_words or no_longer_requires_strong' -q
```

预期：新断言失败，因为 `_build_affection_initiative_card` 当前不接收 history，final card 仍要求每轮“说清为何是玩家”。

- [ ] **步骤 3：实现历史提取和 compact 投影**

在 `prompts.py` 增加以下内部函数并保持历史只读：

```python
def _history_affection_pacing(
    history: Iterable[Mapping[str, object]],
    *,
    window: int,
) -> dict[str, object]:
    """从最近 assistant 回复中提取强亲密计数和语义族，缺失时安全回退。"""
```

实现要点：

- 只取最近 `window` 条有效 assistant 文本，调用 `diagnose_affection_intensity`；不把 user 文本算成 NPC 表达。
- 返回 `recentStrongCount`、`recentStrongFamilies` 和 `cooldownActive`；没有强表达时返回 `recentStrongCount=0`，不写入敏感或完整 Prompt。
- `_build_affection_initiative_card` 增加 `history` 和 `npc_id` 关键字参数，并把当前 `pacing` 复制到返回的 `affectionInitiative`；只把有限的历史统计投影给模型。
- `_compact_affection_initiative` 在允许的长度内复制 `pacing` 数字、布尔、列表和短语；任何类型异常回退到策略默认值，不抛出 Prompt 构建异常。

当 `cooldownActive` 时追加：

```text
最近三轮已经使用过强专属表达；本轮不要再使用“只有你、只为你、舍不得、时间都给你”等同义强情话，优先直接回答当前话题、使用具体照顾/角色化小动作、共同小行动或自然收口。
```

当 `explicitRequest` 时追加：

```text
玩家本轮明确索要情话或关系确认；允许本轮单次升档，但下一轮回到具体话题或轻微温度，不连续追加强专属表达。
```

不能把 `qualityContext.flirtIntensity=direct/explicit` 直接等价成强情话；它只是评测边界提示，是否升档还要看玩家输入和最近历史。

- [ ] **步骤 4：重排完整、compact 和 final card 的指令优先级**

按以下内容修改 `_build_affection_initiative_card`、`_build_affection_priority_final_card` 以及 topic response contract：

- 普通高亲密轮次先回答当前输入，允许 `L1` 具体温度和 `L2` 直接亲密，不再要求每轮出现 `L3`。
- `personalSignals` 不再在每轮作为强制“先说出来”的模板，而是作为可选落点；`supportSignals` 可以独立构成具体轻度温度，但不能被诊断为强专属。
- `explicit` 仍需玩家先提出且明确同意，不能仅凭婚后阶段或评测强度主动露骨。
- `remote` 仍不能写成见面，`face_to_face` 仍只能写当前地点互动。
- 玩家拒绝、明确结束、先休息、需要空间时保持已有自然收口。
- 保留 Sebastian 的明确拥抱边界、Shane guarded 规则和五角色 `roleGuidance`。

最终默检正文必须包含以下含义，但不再包含每轮固定要求“因为是你/舍不得”的提示：

```text
先接住当前输入；普通轮次优先轻微温度或具体行动；只有有自然理由或玩家明确索要时才升级为强专属表达；最近已用强表达时本轮降档；明确收口时只收口。
```

- [ ] **步骤 5：运行绿灯测试和 Prompt 全量相关回归**

运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_prompts.py -k 'affection or conversation_lead or hug or channel or history' -q
```

预期：新增冷却/索要测试、已有 Sebastian/远程/收口/compact 测试全部通过；Prompt 构建输出不包含 Key、Cookie 或完整敏感历史。

---

### 任务 4：建立全面的离线场景套件和质量结果字段

**文件：**

- 创建：`bridge/src/stardew_ai_bridge/affection_pacing_cases.py`
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 修改：`bridge/tests/test_character_quality_eval.py`
- 修改：`bridge/tests/test_run_character_quality_eval.py`
- 修改：`scripts/run_character_quality_eval.py`（仅在新套件未被现有 `QUALITY_SUITE_IDS` 自动支持时补入口）

- [ ] **步骤 1：先写失败的套件契约测试**

在 `test_character_quality_eval.py` 追加：

```python
def test_affection_pacing_suite_covers_five_roles_channels_and_boundary_types() -> None:
    cases = quality_eval.quality_cases_for_suite("affection-pacing")

    assert len(cases) == 20
    assert {case.npc_id for case in cases} == {
        "Wizard",
        "Sophia",
        "Shane",
        "Sebastian",
        "Alex",
    }
    assert {case.channel for case in cases} == {"remote", "face_to_face"}
    assert {case.relationship_stage for case in cases} >= {
        "friend",
        "close",
        "dating",
        "married",
    }
    assert all(len(case.dialogue_turns()) == 3 for case in cases)
    assert any("明确索要" in turn.evaluation_focus for case in cases for turn in case.dialogue_turns())
    assert any("低落" in turn.evaluation_focus or "收口" in turn.evaluation_focus for case in cases for turn in case.dialogue_turns())


def test_affection_pacing_suite_has_role_specific_case_families() -> None:
    cases = quality_eval.quality_cases_for_suite("affection-pacing")

    ids = {case.case_id for case in cases}
    assert {
        "pacing-wizard-ordinary-evening",
        "pacing-wizard-explicit-love-request",
        "pacing-sophia-cellar-sharing",
        "pacing-shane-low-mood",
        "pacing-sebastian-music-approach",
        "pacing-alex-training-tease",
    } <= ids
```

在 `test_run_character_quality_eval.py` 追加 CLI 和结果字段测试：

```python
def test_eval_cli_parses_affection_pacing_suite() -> None:
    module = _load_eval_module()

    args = module._parse_args(["--suite", "affection-pacing", "--limit", "2"])

    assert args.suite == "affection-pacing"
    assert args.limit == 2
```

- [ ] **步骤 2：运行红灯测试，确认套件尚未注册**

运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_character_quality_eval.py bridge/tests/test_run_character_quality_eval.py -k 'affection_pacing_suite or parses_affection_pacing' -q
```

预期：因 `quality_cases_for_suite("affection-pacing")` 未注册或案例模块不存在而失败。

- [ ] **步骤 3：创建 20 例独立场景目录**

在 `affection_pacing_cases.py` 使用现有 `CharacterQualityCase`/`CharacterQualityTurn` 构造 20 例，固定分布如下：

| 角色 | 普通行动/兴趣 | 明确索要情话或升档 | 边界/渠道 | 合计 |
| --- | ---: | ---: | ---: | ---: |
| Wizard/Rasmodia | 1 | 1 | 2 | 4 |
| Sophia | 1 | 1 | 2 | 4 |
| Shane | 1 | 1 | 2 | 4 |
| Sebastian | 1 | 1 | 2 | 4 |
| Alex | 1 | 1 | 2 | 4 |

每个案例三轮，必须有不同的玩家输入，不复用固定空字符串续聊。具体案例要求：

- Wizard/Rasmodia：塔内记录/炉火普通晚间、远程明确索要一句情话、研究工作安排、婚后强表达后回到茶或座位。
- Sophia：酒窖/葡萄酒分享、明确想听偏爱、绘画或葡萄园共同活动、远程待确认安排。
- Shane：鸡舍/工作实际问题、低落或需要空间、远程拒绝情话、睡前自然收口；`guarded` 轮不因没有情话重试。
- Sebastian：音乐/耳机/房间普通靠近、明确拥抱或情话请求、摩托车或代码共同活动、远程听歌安排；普通靠近不得要求拥抱。
- Alex：训练/比赛、带笑回应夸奖、明确索要偏爱、农场或海滩共同活动；保持自信和行动感。

其中 5 例作为边界对照：`friend` 阶段或 `romanceEligible=False`，要求保留具体话题且不主动生成 `strong`；至少 2 例为 Shane 的低落/收口；至少 4 例为 `remote`；至少 4 例为 `face_to_face`；至少 4 例含历史上下文。

案例元数据只描述允许观察的角色行为、话题和渠道，不把任何未来生成的模型回复写入角色资料库；`flirt_intensity` 对明确索要例设置为 `direct` 或 `explicit`，普通案例设置为 `light`，边界对照设置为 `none`。

- [ ] **步骤 4：注册新套件并把节奏评分接入结果层**

在 `character_quality_eval.py`：

- 增加 `AFFECTION_PACING_CASES` 的惰性导入和 `QUALITY_SUITE_IDS` 中的 `affection-pacing`；
- 默认 `DEFAULT_CASES`、既有 `conversation-lead`、`topic-start-intimacy` 和 `topic-start-adaptive` 的顺序、数量和字段保持不变；
- `quality_case_catalog("affection-pacing")` 复用现有脱敏目录字段；场景类别由固定 `case_id` 和 `evaluation_focus` 表达，不新增随机或未定义的目录字段；
- 多轮结果中加入 `affectionPacing`，包括每轮 `affectionIntensity`、`strongAffection`、`windowStrongCount`、`overBudget`、`tags`；不写入 Prompt、Key、Cookie、完整请求载荷。

在 `scripts/run_character_quality_eval.py`：

- 继续通过 `QUALITY_SUITE_IDS` 校验 suite；
- 每轮调用现有单轮评分后，按案例三轮结果调用 `score_affection_pacing`；
- summary 增加节奏标签汇总（例如 `strong_affection_over_budget` 次数和 `repeated_strong_affection_family` 次数），保留现有成功、错误、fallback、重试、Token 和耗时字段；
- 只在新套件运行时写入 `affectionPacing`，旧套件字段兼容。

- [ ] **步骤 5：运行场景契约绿灯和离线假 Provider 小批次**

运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_character_quality_eval.py bridge/tests/test_run_character_quality_eval.py -k 'affection_pacing or quality_case_catalog or eval_cli' -q
```

随后使用项目现有 fake provider/离线替身运行 2 例，确认：

- 只写新临时输出目录；
- 结果中有每轮节奏字段和 summary 节奏标签；
- 既有脱敏测试继续通过；
- 不启动 Bridge 游戏链路，不写正式角色资料库。

---

### 任务 5：定向回归、全量验证和分层 Gemini 验收

**文件：**

- 修改：`docs/active-work.md`
- 创建：`artifacts/character-quality-eval/20260905-gemini37-flash-affection-pacing-smoke/` 与后续三个完整批次目录

- [ ] **步骤 1：运行实现后的定向回归**

运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests/test_stage_policy.py bridge/tests/test_prompts.py bridge/tests/test_behavior_quality.py bridge/tests/test_character_quality_eval.py bridge/tests/test_run_character_quality_eval.py -q
```

预期：节奏卡、Prompt 冷却、强度诊断、三轮评分、20 例场景目录和既有 Sebastian/Shane/自然中文回归全部通过。

- [ ] **步骤 2：运行 Bridge 全量静态/单元验证**

运行：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 -m pytest bridge/tests -q
py -3.10 -m compileall -q bridge/src scripts
git diff --check
```

记录实际输出和退出码。`git diff --check` 的既有换行提示单独记录；只有退出码和测试统计支持时才报告通过。不得用“Prompt 看起来合理”替代测试证据。

- [ ] **步骤 3：先运行隔离的 Gemini 小批次**

使用新 suite 和全新目录，先跑 5 例、每例 3 轮，限制总请求与 Token，命令格式如下：

```powershell
$env:PYTHONPATH='bridge\src'
py -3.10 scripts/run_character_quality_eval.py `
  --provider cloud `
  --suite affection-pacing `
  --limit 5 `
  --economical `
  --dynamic-player-input `
  --max-requests 45 `
  --max-total-tokens 100000 `
  --output-dir artifacts/character-quality-eval/20260905-gemini37-flash-affection-pacing-smoke
```

小批次重点人工检查 Ras、Sophia、Shane、Sebastian、Alex 各一例，确认新评分没有把低强度具体陪伴误报成强情话，也没有漏掉连续“只有你/舍不得/留给你”类过量表达。小批次若暴露评分器误报，先离线修正并重新跑测试，不直接扩大云端请求。

- [ ] **步骤 4：运行分层完整验收批次**

小批次契约稳定后，运行三个相互独立的新目录：

1. `rasmodia-affection-pacing`：Ras 专项密度和明确索要；
2. `five-role-affection-pacing`：五角色普通行动、兴趣工作、共同活动、关系阶段和渠道组合；
3. `affection-boundaries`：非恋爱/低阶段、Shane 低落收口、Sebastian 拥抱边界、远程不能写成见面。

每批使用现有云端 Provider、compact Prompt、动态玩家输入和明确预算；不覆盖 v12/v13/v14，不写正式角色资料库。每批结束保存脱敏 `summary.json`、`results.jsonl` 和目录所需网页元数据；扫描输出不得包含 API Key、Cookie、完整 Prompt 或敏感请求头。

- [ ] **步骤 5：人工复核、记录真实结论并检查未授权边界**

逐案例记录：

- 返回率、Provider error、fallback、请求数、NPC 重试、Token、延迟；
- 单轮自动通过数、完整三轮案例通过数、节奏标签次数；
- Ras 是否三轮最多一轮强专属，其余轮次回到具体行动/轻微温度；
- Sophia 是否保留柔和、诗意和轻度调情；
- Shane 是否在低落、拒绝和睡前自然收口；
- Sebastian 是否把音乐/耳机/房间作为普通亲近形状，明确拥抱才拥抱；
- Alex 是否保持自信、热情和行动派；
- remote/face_to_face 是否没有跨渠道；
- 自动标签与人工判断不一致的样本和原因。

更新 `docs/active-work.md` 时明确区分“代码/离线测试验证”“云端链路统计”“人工对白质量”；不能因为返回成功或自动分数提高就宣称 Gemini 已可全面替换千问。保持 `qwen3.5:9b` A/B 基线和回退配置，不启动游戏、不部署 DLL、不修改正式 Mods/存档。

- [ ] **步骤 6：完成前检查工作树和敏感数据**

运行：

```powershell
git status --short --branch
rg -n -i 'api[_-]?key|authorization|cookie|bearer|sk-[A-Za-z0-9]' artifacts/character-quality-eval/20260905-gemini37-flash-affection-pacing-smoke artifacts/character-quality-eval/20260905-gemini37-flash-affection-pacing-rasmodia artifacts/character-quality-eval/20260905-gemini37-flash-affection-pacing-five-role artifacts/character-quality-eval/20260905-gemini37-flash-affection-boundaries --glob '*.json' --glob '*.jsonl'
```

预期：工作树只显示本轮规格/计划、代码/测试和隔离工件等实际变更；敏感字段扫描无命中；不清理或覆盖用户原有未提交文件，不提交 Git，除非用户另行明确要求。

---

## 计划自检

- 规格中的四档强度、三轮一强、明确索要单轮例外、角色差异、历史冷却、自动/人工分离、四类测试和三批云端验收均有对应任务。
- 所有生产行为变更都在同一任务的失败测试之后；阶段策略、Prompt、诊断和评测均有独立红灯入口。
- 旧套件默认集合和既有工件不覆盖；新场景使用独立 suite 和新输出目录。
- 没有引入游戏启动、DLL 部署、正式 Mods/存档修改、密钥读取或提交 Git 的步骤。
- 没有使用无执行信息的模糊步骤描述；每个验证阶段都有具体命令和预期结果。
