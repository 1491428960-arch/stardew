# Sophia 原文声线重构实现计划

> **面向 AI 代理的工作者：** 使用 `subagent-driven-development`（独立任务）或 `executing-plans`（内联执行）逐任务实现。用 `update_plan` 跟踪整体状态，并保留文档中的复选框。

**目标：** 让 Sophia 在自然找话题和普通续聊中同时保留原文的谨慎、敏感、活泼外放和亲密阶段的情绪起伏，避免再次退化成只有安静感官细节的角色。

**架构：** 在现有角色卡、语气索引和自然 Prompt 结构上做 Sophia 专属扩展。原文证据按关系阶段和表达能量重新选择，Prompt 只携带少量可解释的语气锚点与阶段能量提示；`answer_only` 仍限制 NPC 不额外追问或安排，但不再隐式限制情绪强度。其他角色沿用当前路径。

**技术栈：** Python 3.10、pytest、现有 JSON persona/profile index、Bridge `PromptBuilder`。

---

### 任务 1：锁定 Sophia 原文能量识别与阶段锚点选择

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/speech.py`
- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`
- 测试：`bridge/tests/test_speech.py`
- 测试：`bridge/tests/test_profile_index.py`

- [ ] **步骤 1：编写失败的测试**

在 `test_speech.py` 增加真实行为断言：

```python
def test_sophia_voice_energy_selects_stage_fit_calm_and_expressive_anchors() -> None:
    samples = [
        {"sampleId": "stranger", "sourceMod": "SVE", "sourceKey": "Mon",
         "conditions": {"relationshipStage": "stranger"}, "text": "嗯……你好。"},
        {"sampleId": "married-calm", "sourceMod": "SVE", "sourceKey": "Rain",
         "conditions": {"relationshipStage": "married"}, "text": "今天酒窖里很安静。"},
        {"sampleId": "married-hot", "sourceMod": "SVE", "sourceKey": "Good_0",
         "conditions": {"relationshipStage": "married"},
         "text": "嘿，小傻瓜！再靠近一点……！！！爱你哟！"},
    ]

    selected = select_stage_voice_anchors(
        samples, npc_id="Sophia", relationship_stage="married", max_count=2
    )

    assert [item["sampleId"] for item in selected] == [
        "married-calm",
        "married-hot",
    ]
    assert selected[1]["voiceEnergy"] == "high"
```

在 `test_profile_index.py` 增加阶段调用断言：

```python
def test_sophia_voice_card_reselects_stage_energy_anchors(tmp_path: Path) -> None:
    # 写入 Sophia 的静态 voiceCard 与三条 speechEvidence，调用带阶段的 voice_card。
    card = ProfileIndexStore(index_path).voice_card(
        "Sophia", ["SVE"], relationship_stage="married"
    )
    assert [item["sourceKey"] for item in card["voiceAnchors"][:2]] == [
        "Rain", "Good_0"
    ]
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_speech.py bridge/tests/test_profile_index.py -k 'sophia_voice_energy or sophia_voice_card_reselects'
```

预期：FAIL，当前没有 `select_stage_voice_anchors`，且 `voice_card` 不接受 `relationship_stage`。

- [ ] **步骤 3：编写最少实现代码**

在 `speech.py` 增加确定性的能量信号统计和 `select_stage_voice_anchors`。只对调用方指定的角色启用阶段能量选择；默认 `derive_speech_profile` 的旧排序和其他角色保持不变。`profile_index.py` 的 `voice_card` 增加可选关键字 `relationship_stage`，仅当 canonical NPC 为 Sophia 时，从当前阶段的 `speechEvidence` 过滤稳定记录并调用新选择器；静态 card、来源过滤和返回副本行为保持不变。`PromptContextBuilder` 调用该关键字，测试替身增加默认参数。

- [ ] **步骤 4：运行测试验证通过**

运行同一条定向 pytest，预期新增测试和原有 speech/profile index 测试全部 PASS。

### 任务 2：把原文画像写入 Sophia 角色资料

**文件：**
- 修改：`data/personas/sve.json`
- 测试：`bridge/tests/test_persona_layers.py`
- 测试：`bridge/tests/test_prompts.py`

- [ ] **步骤 1：编写失败的测试**

新增断言：

```python
def test_sophia_persona_exposes_stage_energy_and_excited_particles() -> None:
    voice = load_persona("SVE", "Sophia")["voiceStyle"]
    assert voice["speechParticleHints"][:3] == ["嘿", "哇", "哦哦哦"]
    assert voice["energyProfile"]["married"]
    assert "兴奋" in voice["energyProfile"]["married"]
    assert any("先反应" in item for item in voice["emotionTexture"])
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_persona_layers.py bridge/tests/test_prompts.py -k 'sophia_persona_exposes_stage_energy'
```

预期：FAIL，当前 persona 没有 `speechParticleHints` 和 `energyProfile`。

- [ ] **步骤 3：编写最少实现代码**

在 Sophia 的 `voiceStyle` 中补入基于原文统计的阶段画像：陌生阶段保持低声、停顿和先道歉；熟悉/亲近阶段允许惊呼、连续补半句和喜欢的事立刻分享；婚后允许热情先冒出来再害羞收住。加入 `speechParticleHints` 作为可选颗粒，不把它们写成固定句首。更新已有 `emotionTexture`，把“热情后压住”改为“热情先冒出、说多后自我收回”的顺序。

- [ ] **步骤 4：运行测试验证通过**

运行同一条定向 pytest，预期 persona 加载、Prompt 压缩和既有角色层测试全部 PASS。

### 任务 3：让自然 Prompt 携带阶段能量与少量原文锚点

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 测试：`bridge/tests/test_prompts.py`
- 测试：`bridge/tests/test_profile_context.py`

- [ ] **步骤 1：编写失败的测试**

新增自然 adaptive Prompt 结构测试：

```python
def test_natural_sophia_prompt_keeps_stage_energy_and_two_voice_anchors() -> None:
    messages = PromptBuilder().build(sophia_natural_context_with_married_history(), "", compact=False)
    role = next(item for item in messages if item.get("name") == "natural_role_texture")
    payload = json.loads(role["content"])
    assert "energyMode" in payload
    assert "兴奋" in payload["energyMode"]
    assert [item["sourceKey"] for item in payload["voiceAnchors"]] == ["Rain", "Good_0"]
    assert "嘿" in payload["speechParticleHints"]
    assert "不是固定句式" in payload["instruction"]
```

同时增加非 Sophia 回归：同样的自然上下文不得自动携带 Sophia 的能量字段或 `Good_0` 锚点。

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_prompts.py bridge/tests/test_profile_context.py -k 'natural_sophia_prompt_keeps_stage_energy or natural_non_sophia_does_not_inherit_sophia'
```

预期：FAIL，当前自然角色卡没有 `energyMode`、`voiceAnchors` 和 `speechParticleHints`。

- [ ] **步骤 3：编写最少实现代码**

扩展 `_build_natural_role_texture_card`：从 `stageProfile.stage` 选择 `voiceStyle.energyProfile` 的一项，生成 `energyMode`；从已经按阶段重选的 `voiceCard.voiceAnchors` 中最多保留一条普通日常和一条高能量锚点；传入 `speechParticleHints` 作为低优先级可选颗粒。自然契约明确“能量不是每轮必须表现、锚点只模仿节奏、不照抄事实”。`answer_only` 只继续禁止追问、邀约和安排，不添加低能量限制。其他角色不带 Sophia 专属字段。

- [ ] **步骤 4：运行测试验证通过**

运行 Prompt/profile-context 定向测试，预期全部 PASS，并确认已有 Elliott 的自然模式条件不受影响。

### 任务 4：补齐 Sophia 自然案例的触发面并做离线验收

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/topic_start_adaptive_cases.py`
- 测试：`bridge/tests/test_character_quality_eval.py`
- 测试：`bridge/tests/test_run_character_quality_eval.py`

- [ ] **步骤 1：编写失败的测试**

为 Sophia adaptive 案例增加覆盖断言：至少包含普通日常、兴奋分享、被夸后改口、婚后家庭/亲密四类触发；三轮仍为自然响应，不把 `answer_only` 改成主动邀约。

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py bridge/tests/test_run_character_quality_eval.py -k 'sophia_adaptive'
```

预期：FAIL，当前 Sophia 案例只有酒窖/画架等低能量入口，缺少阶段化触发标记。

- [ ] **步骤 3：编写最少实现代码**

只调整 Sophia 的案例定义和玩家动态输入提示：保留具体小事、被逗笑/被夸、看到对方卡住想帮忙、说快后改口等自然触发；不在玩家台词里写“请表现兴奋”等评测术语，不添加新云端调用。

- [ ] **步骤 4：运行测试验证通过**

运行案例、Prompt、profile index、speech、persona 层定向回归。

- [ ] **步骤 5：离线结构验收**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_speech.py bridge/tests/test_profile_index.py bridge/tests/test_profile_context.py bridge/tests/test_prompts.py bridge/tests/test_persona_layers.py bridge/tests/test_character_quality_eval.py bridge/tests/test_run_character_quality_eval.py
py -3.10 -B -m compileall -q bridge/src scripts
git diff --check
```

验收内容：阶段锚点中同时存在普通和高能量 Sophia 原文，最终自然 Prompt 出现阶段能量和少量锚点，其他角色没有继承 Sophia 字段，案例没有新增云端请求或游戏依赖。离线验证通过后，再由用户决定是否生成新的 DeepSeek 小批量。

