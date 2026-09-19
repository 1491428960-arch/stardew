# DeepSeek 角色表达契约实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans`（内联执行）逐任务实现。按任务顺序完成测试红灯、最小实现和验证检查点；不创建 Git 提交。

**目标：** 在不改变 Provider、fallback、关系状态或游戏边界的前提下，减少 DeepSeek 质量评测中的语义重试，并让五个核心角色在回答当前话题时保持可辨识的个人表达。

**架构：** 统一高亲密阶段的生成优先级为“直接回答当前话题 → 一个角色化细节/态度 → 可选的具体继续入口”，由最终生成卡再次明确角色指纹。阶段策略中的固定爱意顺序和未来排期措辞与该契约保持一致；重试只补缺失目标，不覆盖已有角色细节。所有修改仍位于 Bridge Prompt/策略/Guard 层，云端路由和游戏端不变。

**技术栈：** Python 3.10、pytest、现有 `PromptBuilder`、`stage_policy`、`retry_for_format_noise` 和 `character_quality_eval`。

---

### 任务 1：为策略冲突和最终角色卡建立失败回归测试

**文件：**
- 修改：`bridge/tests/test_stage_policy.py`
- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/tests/test_guard.py`

- [ ] **步骤 1：编写失败测试**

在现有策略测试中增加以下行为断言：

```python
@pytest.mark.parametrize("npc_id", ("Wizard", "Sophia", "Shane", "Sebastian", "Alex"))
@pytest.mark.parametrize("stage", ("dating", "married"))
def test_high_stage_policy_does_not_request_future_schedule_commitments(
    npc_id: str,
    stage: str,
) -> None:
    rendered = json.dumps(build_stage_policy(npc_id, stage), ensure_ascii=False)
    assert "日期" not in rendered
    assert "排期" not in rendered
    assert "预约" not in rendered
    assert "自动履约" not in rendered
```

在 Prompt 测试中增加最终卡契约：

```python
def test_prompt_adds_final_role_voice_contract_before_player_input() -> None:
    policy = build_stage_policy("Alex", "married")
    context = {
        "npcIdentity": {
            "npcId": "Alex",
            "displayName": "Alex",
            "stageProfile": {"stage": "married"},
            "stagePolicy": policy,
            "voiceStyle": {
                "tone": "直接、热情",
                "sentencePattern": ["短句"],
                "responseRules": ["落到具体行动"],
                "avoid": ["教练式说教"],
            },
        },
        "gameState": {"relationshipStage": "married", "friendshipHearts": 10},
        "interaction": {"intent": "chat", "channel": "face_to_face"},
        "history": [],
    }
    messages = PromptBuilder().build(context, "今天训练累不累？")
    names = [message["name"] for message in messages]
    contract = next(message for message in messages if message["name"] == "final_role_voice_contract")

    assert names.index("final_role_voice_contract") < names.index("player_input")
    assert "当前话题" in contract["content"]
    assert "Alex" in contract["content"]
    assert "教练式说教" in contract["content"]
```

在 Guard 测试中增加重试保留角色指纹的断言：

```python
def test_conversation_lead_retry_preserves_role_specific_guidance() -> None:
    prompt = [
        {"role": "system", "name": "conversation_lead", "content": json.dumps({
            "conversationLead": {
                "required": "usually",
                "roleGuidance": "短、具体、带一点自信或轻微炫耀，不要变成教练式说教",
            }
        }, ensure_ascii=False)},
        {"role": "user", "name": "player_input", "content": "今天训练累不累？"},
    ]
    result = ProviderResult(reply="还行。", provider="cloud", fallback=False)
    calls: list[list[dict[str, str]]] = []

    retry_for_format_noise(
        result,
        prompt,
        lambda messages: calls.append(messages) or result.model_copy(
            update={"reply": "肩膀有点酸，但今天的发球还不错。你想听哪一段？"}
        ),
        max_retries=1,
    )

    assert calls
    assert "角色" in calls[0][-1]["content"]
    assert "不要变成统一模板" in calls[0][-1]["content"]
```

- [ ] **步骤 2：运行定向测试确认红灯**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider `
  bridge/tests/test_stage_policy.py `
  bridge/tests/test_prompts.py `
  bridge/tests/test_guard.py
```

预期：新断言因现有 Alex 的“日期”策略、缺少 `final_role_voice_contract` 或重试文本没有角色保护而失败；不得修改生产代码来绕过红灯。

---

### 任务 2：统一高阶段策略并修正 Alex 未来排期措辞

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/stage_policy.py`

- [ ] **步骤 1：调整共享高阶段策略**

将 dating/married 的 `responseShape`、`initiative`、`followUp` 改为与当前话题优先契约一致：先回答当前输入，再选择一个角色化细节或情绪，最后只允许可商量的当前入口；不得要求固定的“爱意 → 话题 → 安排”顺序。

统一文本必须表达以下含义：

```python
"先直接回应当前话题，再用一个角色化细节、态度或轻微亲近表达个人特色；"
"需要继续时最多递出一个当前可商量的入口，不把安排写成既定事实。"
```

- [ ] **步骤 2：修正角色覆盖**

保留每个角色的不同表达重点，但移除任何“日期、排期、预约、自动履约”措辞。Alex 婚后策略改为当前可商量的吃饭、散步或分工动作，保留短、直接、自信、轻微炫耀和行动派；不加入教练式解释。

- [ ] **步骤 3：运行策略测试确认通过**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_stage_policy.py
```

预期：策略测试全部通过，且没有修改恋爱资格、关系阶段计算或关系世界观规则。

---

### 任务 3：添加最终角色表达卡并压缩重复优先级

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 修改：`bridge/tests/test_prompts.py`

- [ ] **步骤 1：生成最终角色卡**

从 `npcIdentity.stagePolicy.voiceFingerprint`、`conversationLead.roleGuidance` 和 `voiceStyle.avoid` 中读取脱敏后的短文本，新增 `final_role_voice_contract`。卡片只放在最终玩家输入之前，并包含：

```python
{
    "instruction": (
        "最后按当前角色指纹生成对白：先直接回答当前话题，"
        "最多加入一个角色化细节或态度，再决定是否给一个具体且可商量的继续入口。"
        "不要把多个角色特征拼接成说明书，不要复述规则，不要使用未来日期、排期或预约。"
    ),
    "npcId": ..., 
    "relationshipStage": ..., 
    "voiceFingerprint": ..., 
    "roleGuidance": ..., 
    "avoid": ...,
}
```

所有值继续使用现有 `_text` / `_remove_secret_labels` 限制长度，不把凭据、完整 Prompt 或内部诊断字段送入上游。

- [ ] **步骤 2：让重试提示保留角色特色**

在 `CONVERSATION_LEAD_RETRY_CONTENT` 和 `AFFECTION_RETRY_CONTENT` 中增加同一条短约束：保留当前具体对象和当前角色指纹，只补缺失的一个动作；不得改写成跨角色通用情话、教练式说教或事务清单。保持现有重试次数和 fallback 行为不变。

- [ ] **步骤 3：运行 Prompt/Guard 定向测试**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider `
  bridge/tests/test_prompts.py `
  bridge/tests/test_guard.py
```

预期：新增契约与现有格式、渠道、历史、关系边界测试全部通过。

---

### 任务 4：Bridge 回归和运行时重载

**文件：**
- 不新增业务文件；只验证任务 2–3 的修改。

- [ ] **步骤 1：运行 Bridge 全量回归**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests
```

预期：退出码 `0`，无失败测试；不得把测试结果当成云端质量结果。

- [ ] **步骤 2：重载并核对 Bridge 进程**

仅在代码测试通过后，使用项目已有 `scripts/start_bridge.ps1` 重载。若执行策略阻止，只对子进程使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start_bridge.ps1
```

检查 5678 监听 PID 的命令行是否指向当前 `story-memory` 工作树，并调用 `/health` 与 `/api/quality/cases`。`/health` 只证明服务存活，不证明新的 DeepSeek 请求成功。

---

### 任务 5：新的 5 案例/15 轮云端冒烟

**文件：**
- 创建：唯一的 `artifacts/character-quality-eval/<timestamp>-deepseek-chat-voice-contract-smoke/`
- 不覆盖任何历史工件。

- [ ] **步骤 1：显式运行云端冒烟**

使用现有评测入口，显式 `--provider cloud`，选择 Wizard、Sophia、Shane、Sebastian、Alex 各 3 轮，设置保守请求/Token 上限；不调用 local 或 fake。

- [ ] **步骤 2：验证硬门槛**

逐项记录案例数、轮数、ProviderError、fallback、重试、Token、延迟和预算停止原因。若出现 `401/403/429`、超时、格式不兼容或 fallback，立即停止，不继续烧额度。

- [ ] **步骤 3：验证质量目标**

抽取脱敏结果确认：当前话题先被回答、五个角色有各自的表达指纹、关系阶段没有越界、没有未来排期承诺、没有替其他 NPC 发言；自动评分只作为证据之一，不把通过数直接等同于人工角色质量通过。

在新冒烟达到门槛前，不运行剩余四套完整评测。

---

## 计划自检

- 规格覆盖度：当前话题优先、角色个性、Alex 特殊问题、重试保留特色、阶段边界、TDD、Bridge 回归和 5×3 云端验证均有对应任务。
- 敏感边界：计划没有读取、打印或写入 Key；没有修改 Provider 配置；没有启动游戏、SMAPI 或部署 DLL；没有创建提交。
- 工件隔离：新冒烟使用新的唯一目录，不覆盖已有结果。
- 失败处理：任何账号授权失败、429、超时、fallback 或预算停止都只记录并停止后续云端调用。
