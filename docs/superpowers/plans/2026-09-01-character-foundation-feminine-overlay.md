# 五人角色基底与娘化表达层实现计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 按任务顺序执行；每个任务完成后运行对应验证，并保留本计划中的复选框。

**目标：** 建立五个主要 NPC 的独立角色基底、娘化表达层和心事件后状态，让 Shane 在高好感阶段不再错误地沿用初识冷淡，并让后续高阶段评测真正覆盖这些差异。

**架构：** `PersonaStore` 继续负责原版人格与 Mod 覆盖合并；新增纯函数 `story_state` 根据关系阶段、已完成事件和索引事件生成可解释状态；`ContextBuilder` 将 `genderPresentation` 和 `storyState` 放入 NPC 身份；`PromptBuilder` 把两层作为独立系统卡传给模型。派生索引使用当前已解析 corpus 重建到新工件路径，不覆盖旧工件。

**技术栈：** Python 3.10、pytest、JSON 资料、FastAPI Bridge；当前默认云端百炼 Qwen 保持不变，本地 `qwen3.5:9b` 保持 fallback。

---

## 文件清单

### 创建

- `bridge/src/stardew_ai_bridge/story_state.py`：把关系阶段和已完成事件转换为可解释的信任与开放状态。
- `bridge/tests/test_story_state.py`：覆盖 Shane 的阶段跃迁、事件状态和暂时收口边界。
- `bridge/tests/test_persona_layers.py`：覆盖原版基底与娘化表达层的合并结果。
- `docs/superpowers/plans/2026-09-01-character-foundation-feminine-overlay.md`：本实现计划。
- `data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-character-foundation.json`：重建后的独立索引工件。

### 修改

- `data/personas/female-bachelors.json`：为 Shane、Sebastian、Alex 增加独立 `genderPresentation`。
- `data/personas/vanilla.json`：补充五人稳定基底中的阶段/事件行为说明，保留现有原版事实。
- `bridge/src/stardew_ai_bridge/stage_policy.py`：补充高阶段信任语气、Shane 的状态边界和五人角色化主动性。
- `bridge/src/stardew_ai_bridge/prompts.py`：传递并压缩 `genderPresentation`、`storyState`，增加优先级和心事件约束。
- `bridge/src/stardew_ai_bridge/profile_index.py`：在构建与加载时对已解析文本和明显控制残渣保持严格分层，并为角色层字段保留可追溯信息。
- `data/personas/behavior-examples.json`：增加五人 dating/married 与娘化表达的人工审核样例。
- `data/personas/behavior-quality-scenarios.json`：增加高好感、心事件后、女性化表达和主动亲密的多轮场景元数据。
- `bridge/tests/test_stage_policy.py`：覆盖五人高阶段差异和 Shane 的 post-heart-event 规则。
- `bridge/tests/test_profile_context.py`：覆盖 ContextBuilder 输出的新状态层。
- `bridge/tests/test_profile_index.py`：覆盖角色层字段及重建索引中的解析文本筛选。
- `bridge/tests/test_prompts.py`：覆盖身份层、女性化层、故事状态卡的顺序和边界。
- `bridge/tests/test_character_quality_eval.py`：覆盖高好感与心事件案例的元数据校验。
- `bridge/tests/test_generate_behavior_examples.py`：覆盖新增样例字段和阶段覆盖。
- `docs/active-work.md`：记录本轮验证数字、索引哈希和未完成的游戏实机边界。

## 任务 1：先写角色层与故事状态的失败测试

**文件：**

- 创建：`bridge/tests/test_story_state.py`
- 创建：`bridge/tests/test_persona_layers.py`
- 修改：`bridge/tests/test_stage_policy.py`
- 修改：`bridge/tests/test_profile_context.py`

- [ ] **步骤 1：编写失败测试**

新增以下可执行断言：

```python
def test_shane_close_stage_is_trusted_not_stranger_cold() -> None:
    state = build_story_state("Shane", "close", [])
    assert state["trustState"] == "established"
    assert "初识" not in state["behaviorInstruction"]


def test_completed_story_event_enables_shane_recovery_disclosure() -> None:
    state = build_story_state(
        "Shane",
        "close",
        ["vanilla:shane-heart-6"],
    )
    assert "recovery" in state["completedStoryStates"]
    assert "current_struggle" in state["allowedDisclosure"]


def test_temporary_bad_mood_does_not_erase_established_trust() -> None:
    state = build_story_state(
        "Shane",
        "married",
        ["vanilla:shane-heart-6"],
        current_mood="low",
    )
    assert state["trustState"] == "established"
    assert state["temporaryBoundary"] == "可以简短拒绝或结束，但不得退回初识式冷淡。"


def test_female_bachelors_adds_expression_layer_without_replacing_base_persona() -> None:
    store = PersonaStore(Path(__file__).parents[2] / "data" / "personas")
    persona = store.get_persona("Shane", ["female-bachelors"])
    assert "直白" in persona["voiceStyle"]["tone"]
    assert persona["genderPresentation"]["layer"] == "expression_only"
    assert persona["genderPresentation"]["basePersonaPriority"] == "higher"
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q bridge/tests/test_story_state.py bridge/tests/test_persona_layers.py bridge/tests/test_stage_policy.py bridge/tests/test_profile_context.py -p no:cacheprovider
```

预期：新测试因 `story_state` 和 `genderPresentation` 尚未实现而失败，既有阶段测试保持可定位的既有结果。

## 任务 2：实现角色层与故事状态

**文件：**

- 创建：`bridge/src/stardew_ai_bridge/story_state.py`
- 修改：`data/personas/female-bachelors.json`
- 修改：`data/personas/vanilla.json`
- 修改：`bridge/src/stardew_ai_bridge/stage_policy.py`

- [ ] **步骤 1：实现最小状态函数**

实现固定签名：

```python
def build_story_state(
    npc_id: object,
    relationship_stage: object,
    completed_event_ids: Iterable[object] = (),
    *,
    story_events: Iterable[Mapping[str, Any]] = (),
    current_mood: object = "",
) -> dict[str, Any]:
    ...
```

规则：`close`、`dating`、`married`、`parent` 的默认 `trustState` 为 `established`；只有配置中明确匹配的事件才加入 `completedStoryStates`；当前低落只设置 `temporaryBoundary`，不改变信任状态。Shane 的事件标签使用 `story_events` 的 `eventId` / `requiredEventId`，并兼容 `vanilla:shane-heart-6`、`shane-heart-6` 和 `Shane6` 形式。

- [ ] **步骤 2：补充三个娘化表达层**

`female-bachelors.json` 中三个角色均增加：

```json
"genderPresentation": {
  "layer": "expression_only",
  "basePersonaPriority": "higher",
  "toneAdjustments": [],
  "affectionExpression": [],
  "avoid": ["女性化刻板模板", "重复语气词"]
}
```

每个角色的 `toneAdjustments` 和 `affectionExpression` 使用不同内容，并明确不改变原版核心人格、话题和已确认事实。

- [ ] **步骤 3：让高阶段策略表达信任变化**

调整 `stage_policy.py` 中 Shane 的 `close`、`dating`、`married`：去掉会把他长期固定为冷淡的描述，增加「默认信任已建立、状态差时才收口、亲密通过具体行动表达」；同时为 Sophia、Sebastian、Alex 的高阶段保留各自不同的主动方式。

- [ ] **步骤 4：运行最小测试**

运行任务 1 的 pytest 命令，预期新测试和既有 `test_stage_policy.py`、`test_profile_context.py` 全部通过。

## 任务 3：把两层接入 ContextBuilder 和 PromptBuilder

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/tests/test_profile_context.py`

- [ ] **步骤 1：编写失败测试**

新增断言：

```python
def test_context_exposes_story_state_and_gender_presentation() -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        "Shane",
        source_mods=["female-bachelors"],
        friendshipHearts=10,
        marriageStatus="married",
        completedEventIds=["vanilla:shane-heart-6"],
    )
    identity = context["npcIdentity"]
    assert identity["storyState"]["trustState"] == "established"
    assert identity["genderPresentation"]["layer"] == "expression_only"


def test_prompt_places_base_persona_before_gender_and_story_layers() -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        "Shane",
        source_mods=["female-bachelors"],
        friendshipHearts=10,
        marriageStatus="married",
        completedEventIds=["vanilla:shane-heart-6"],
    )
    messages = PromptBuilder().build(context, "今天还好吗？")
    names = [item.get("name") for item in messages]
    assert names.index("persona_core") < names.index("gender_presentation")
    assert names.index("gender_presentation") < names.index("story_state")
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q bridge/tests/test_prompts.py::test_context_exposes_story_state_and_gender_presentation bridge/tests/test_prompts.py::test_prompt_places_base_persona_before_gender_and_story_layers -p no:cacheprovider
```

预期：因身份字段和消息卡尚未存在而失败。

- [ ] **步骤 3：实现最小接线**

在 `ContextBuilder` 中加入 `storyState`，在 `_IDENTITY_FIELDS` 和 `_compact_identity` 中加入 `genderPresentation`、`storyState`，并在 `PromptBuilder` 中按 `persona_core → gender_presentation → story_state → stage_execution_card` 的顺序注入。两张新卡都声明「不是台词、不得复述规则」，且明确基底人格优先。

- [ ] **步骤 4：运行定向回归**

运行：

```powershell
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q bridge/tests/test_prompts.py bridge/tests/test_profile_context.py -p no:cacheprovider
```

预期：相关 Prompt 与上下文测试全部通过。

## 任务 4：补齐高阶段行为样例与评测场景

**文件：**

- 修改：`data/personas/behavior-examples.json`
- 修改：`data/personas/behavior-quality-scenarios.json`
- 修改：`bridge/tests/test_generate_behavior_examples.py`
- 修改：`bridge/tests/test_character_quality_eval.py`

- [ ] **步骤 1：编写覆盖失败测试**

测试必须检查每个主要角色至少拥有 `dating` 和 `married` 样例，且娘化角色样例含 `sourceMods` 中的 `female-bachelors`；场景文件必须出现高阶段和 `completedEventIds` 字段。

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q bridge/tests/test_generate_behavior_examples.py bridge/tests/test_character_quality_eval.py -p no:cacheprovider
```

预期：覆盖断言因现有样例主要集中在 `friend/close` 而失败。

- [ ] **步骤 3：增加人工审核样例**

为五个角色各增加 dating 与 married 样例，至少覆盖主动关心、具体邀约、笨拙调情和自然收口；后三位另增加女性化表达样例。样例只写角色化回应动作和已确认事实，不把模型生成文本直接写回原文语料。

- [ ] **步骤 4：增加多轮场景**

为每个主要角色添加至少一组高好感 3 轮场景，元数据包含 `relationshipStage`、`friendshipHearts`、`completedEventIds`、`channel`、`topic`、`flirtIntensity` 和 `genderPresentation`；Shane 额外保留一组低落收口场景。

- [ ] **步骤 5：运行定向回归**

运行任务 4 的 pytest 命令，预期样例 schema、阶段覆盖和质量案例校验全部通过。

## 任务 5：重建解析索引并验证来源隔离

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`
- 修改：`bridge/tests/test_profile_index.py`
- 创建：`data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-character-foundation.json`

- [ ] **步骤 1：编写失败测试**

新增一个使用真实 `sve-dialogue-corpus.json` 的小型抽样测试，断言 `resolvedText` 进入派生样本，`{{i18n:...}}` 不进入模型样本；同时验证 `genderPresentation` 只来自 persona overlay，不把女性化文本伪装成 vanilla。

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q bridge/tests/test_profile_index.py -p no:cacheprovider
```

预期：真实当前索引快照中的未解析文本统计测试失败，新增源分层断言失败。

- [ ] **步骤 3：实现最小修复**

保留已有同 `sampleId` 的解析文本替换逻辑；在索引加载和构建审计中增加 unresolved 计数与来源警告，检索层继续拒绝未解析模板。对女性化层使用 persona 字段而不是修改原版 `voiceCard` 的来源归属。

- [ ] **步骤 4：生成独立索引**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B scripts/build_profile_index.py --persona-dir data/personas --corpus data/generated/sve-dialogue-corpus.json --corpus data/generated/rasmodia-with-vanilla-wizard-corpus.json --vanilla-root artifacts/corpus/vanilla --vanilla-locale zh-CN --output data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.next-character-foundation.json
```

实际参数以当前存在的 vanilla 解包目录核对后执行；输出必须落到 `.next-character-foundation.json`，不能覆盖现有索引。

- [ ] **步骤 5：运行定向回归**

验证输出中的五人样本：可解析文本无 `{{i18n:`，Shane 有 close/married 样本，Sophia 的 SVE 样本使用中文 `resolvedText`，并记录 SHA-256。

## 任务 6：完整回归、Bridge 重启与运行时确认

**文件：**

- 修改：`docs/active-work.md`
- 检查：`bridge/src/stardew_ai_bridge/app.py`、`scripts/start_bridge.ps1`、`scripts/start_ai_npc_test.ps1`

- [ ] **步骤 1：运行完整 Bridge 测试**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests
```

必须记录真实通过数、失败数和 warning 数；若失败，先修复回归，不启动云端批量生成。

- [ ] **步骤 2：重启并核对当前 Bridge**

按监听 PID 精确确认旧 5678 子进程和包装器，再重启当前 worktree 服务；检查 `/health`、`/test`、`/api/context/preview`。只在两个进程命令行均指向当前 worktree 时记录运行时接线有效。

- [ ] **步骤 3：生成独立小批次并记录用量**

使用当前默认百炼 Qwen 配置运行高阶段五人多轮评测，输出到新批次目录；记录案例数、轮数、Provider、请求数、输入/输出/总 Token 和费用字段。旧批次不覆盖，未审核回复不写回资料库。

- [ ] **步骤 4：浏览器人工检查**

在当前 `http://127.0.0.1:5678/test` 查看新批次的完整多轮案例，至少检查 Shane 的 close/married、Sebastian 的克制亲密、Alex 的非训练话题、Sophia 的非机械葡萄园话题和 Wizard/Rasmodia 的普通日常。页面截图/显示只作为网页证据，不能替代游戏 DLL 加载证据。

- [ ] **步骤 5：更新活动记录**

在 `docs/active-work.md` 记录实际测试数字、索引哈希、Bridge 运行 Provider、浏览器检查范围和未完成的游戏实机边界；不声称游戏已经加载新 DLL，除非实际构建、部署哈希和 SMAPI 日志路径均已核对。

## 执行顺序与检查点

按任务 1 → 2 → 3 → 4 → 5 → 6 执行。任务 2、3、4 每完成后检查一次既有测试是否仍然通过；任务 5 完成后才允许使用新索引做评测；任务 6 的 Bridge 全量回归失败时停止批量生成并回到失败测试对应任务。

不执行 Git commit、push、reset、checkout 或清理现有工作树修改。
