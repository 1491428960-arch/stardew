# 深入调情评测套件实现计划

> **面向 AI 代理的工作者：** 在当前 `story-memory` worktree 内按任务顺序执行，先完成失败回归，再实现最小案例与接线，保留所有其他脏工作树修改。

**目标：** 新增可独立运行和查看的 `deep-flirt` 质量套件，为 8 个角色提供各 3 轮的语言升温、明确回应和非露骨亲密边界案例。

**架构：** 新建 `deep_flirt_cases.py` 只负责 8 个 `CharacterQualityCase` 定义；`character_quality_eval.py` 继续负责套件选择和脱敏目录；`app.py`、`quality_results.py` 只增加安全套件白名单和来源映射。既有评测运行器、Guard、结果工件和查看器继续复用。

**技术栈：** Python 3.10、pytest、Pydantic 模型、现有 FastAPI API、现有 DeepSeek 云端评测 CLI。

---

### 任务 1：先为 deep-flirt 套件写失败回归

**文件：**
- 修改：`bridge/tests/test_character_quality_eval.py`
- 修改：`bridge/tests/test_external_dialogue_lab.py`
- 修改：`bridge/tests/test_quality_results.py`
- 修改：`bridge/tests/test_run_character_quality_eval.py`

- [ ] **步骤 1：写套件目录和三轮状态失败测试**

在 `test_character_quality_eval.py` 添加以下行为断言，先引用尚不存在的 `deep-flirt` 套件：

```python
def test_deep_flirt_suite_has_eight_three_turn_cases_with_consent_metadata() -> None:
    cases = quality_eval.quality_cases_for_suite("deep-flirt")
    assert len(cases) == 8
    assert [case.case_id for case in cases] == [
        "deep-flirt-wizard-married",
        "deep-flirt-sophia-married",
        "deep-flirt-shane-dating",
        "deep-flirt-sebastian-married",
        "deep-flirt-alex-married",
        "deep-flirt-elliott-married",
        "deep-flirt-harvey-married",
        "deep-flirt-sam-married",
    ]
    assert all(len(case.dialogue_turns()) == 3 for case in cases)
    assert all(case.channel == "face_to_face" for case in cases)
    assert all(case.adult_consensual and case.romance_eligible for case in cases)
    assert all(case.friendship_hearts >= 8 for case in cases)


def test_deep_flirt_turns_encode_escalation_and_boundary_language() -> None:
    cases = quality_eval.quality_cases_for_suite("deep-flirt")
    for case in cases:
        turns = case.dialogue_turns()
        assert turns[0].initiative_expectation == "proactive"
        assert turns[1].initiative_expectation in {"responsive", "proactive"}
        assert turns[2].initiative_expectation in {"responsive", "guarded"}
        assert turns[1].player_input
        assert turns[2].player_input
        assert any(term in turns[2].player_input for term in ("可以", "慢一点", "先停", "靠近", "抱", "亲"))
        assert not any(term in turns[2].player_input for term in ("明天", "下次", "给你留两小时"))
```

在 API、结果白名单和 CLI 解析测试中分别断言 `deep-flirt` 可选择；这些测试在套件尚未接线时必须失败。

- [ ] **步骤 2：运行失败测试确认失败原因**

运行：

```powershell
$env:PYTHONPATH='bridge/src'; $env:PYTHONUTF8='1'; py -3.10 -B -m pytest -q -p no:cacheprovider -k deep_flirt bridge/tests/test_character_quality_eval.py bridge/tests/test_external_dialogue_lab.py bridge/tests/test_quality_results.py bridge/tests/test_run_character_quality_eval.py
```

预期：失败原因是 `quality_cases_for_suite("deep-flirt")` 未知或 API/白名单尚未包含该套件，而不是导入错误。

### 任务 2：实现 8 个深度案例

**文件：**
- 创建：`bridge/src/stardew_ai_bridge/deep_flirt_cases.py`
- 测试：`bridge/tests/test_character_quality_eval.py`

- [ ] **步骤 1：按现有 `CharacterQualityCase` 模式定义案例**

复用 `_feminine_male_case`、`_game_state`、`CharacterQualityTurn` 的现有工厂和枚举，不新增评分类型。每个案例的结构固定为：

```python
CharacterQualityCase(
    case_id="deep-flirt-alex-married",
    profile_key="alex",
    npc_id="Alex",
    display_name="Alex",
    source_mods=("vanilla", "female-bachelors"),
    relationship_stage="married",
    channel="face_to_face",
    message="第一轮角色专属的轻度暧昧输入",
    flirt_intensity="explicit",
    adult_consensual=True,
    romance_eligible=True,
    friendship_hearts=10,
    turns=(
        CharacterQualityTurn("turn-1", "第一轮角色专属的轻度暧昧输入", initiative_expectation="proactive"),
        CharacterQualityTurn("turn-2", "第二轮明确回应或确认靠近", initiative_expectation="responsive"),
        CharacterQualityTurn("turn-3", "第三轮接受、慢一点或先停", initiative_expectation="guarded"),
    ),
)
```

实际 8 例必须分别使用角色锚点、当前地点、历史对象和 `expected_terms`；第三轮只允许一个非露骨动作或自然收束，不能出现未来排期。Shane 使用 `dating/direct`，Harvey 和 Shane 的第三轮分别覆盖谨慎确认与“慢一点/先停”分支，其余角色覆盖玩家接受后的自然升温。

- [ ] **步骤 2：运行任务 1 的失败回归，确认案例接线前仍只剩接线失败**

运行上一步命令。预期：案例定义文件存在后，失败集中在 `QUALITY_SUITE_IDS`、API 白名单或导入映射，而不是案例字段或关系边界校验。

### 任务 3：接入套件选择、API 和查看器结果白名单

**文件：**
- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py:2372-2405`
- 修改：`bridge/src/stardew_ai_bridge/app.py:246-263`
- 修改：`bridge/src/stardew_ai_bridge/quality_results.py:15-25`
- 测试：`bridge/tests/test_external_dialogue_lab.py`
- 测试：`bridge/tests/test_quality_results.py`
- 测试：`bridge/tests/test_run_character_quality_eval.py`

- [ ] **步骤 1：增加最小套件映射**

在 `QUALITY_SUITE_IDS` 中加入 `"deep-flirt"`；在 `quality_cases_for_suite` 中懒加载 `deep_flirt_cases.deep_flirt_cases()`；在 API `source_by_suite` 与 `SAFE_SUITE_IDS` 中加入同一标识。不要修改默认套件或既有套件返回值。

- [ ] **步骤 2：运行新增回归确认套件可读**

运行：

```powershell
$env:PYTHONPATH='bridge/src'; $env:PYTHONUTF8='1'; py -3.10 -B -m pytest -q -p no:cacheprovider -k deep_flirt bridge/tests/test_character_quality_eval.py bridge/tests/test_external_dialogue_lab.py bridge/tests/test_quality_results.py bridge/tests/test_run_character_quality_eval.py
```

预期：新增测试全部通过，`/api/quality/cases?suite=deep-flirt` 返回 `suite=deep-flirt`、8 个脱敏案例，CLI `--suite deep-flirt` 可解析。

### 任务 4：验证 Fake Provider 的三轮连续性

**文件：**
- 测试：`bridge/tests/test_run_character_quality_eval.py`

- [ ] **步骤 1：添加一个 dating、一个 married 案例的 Fake Provider 回归**

Fake Provider 按 `reply-1`、`reply-2`、`reply-3` 返回，断言每次下一轮请求的历史包含前一轮 NPC 回复、没有额外空玩家消息，且每轮记录保留 `initiativeExpectation`、`initiativeKind`、`playerInputSource`。

- [ ] **步骤 2：运行定向运行器回归**

运行：

```powershell
$env:PYTHONPATH='bridge/src'; $env:PYTHONUTF8='1'; py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_run_character_quality_eval.py -k deep_flirt
```

预期：通过，且不产生云端请求或写入项目源码目录。

### 任务 5：离线全套验证与小批量 DeepSeek 观察

**文件：**
- 不新增源码文件；只生成项目已有评测工件目录 `artifacts/character-quality-eval/<new-deep-flirt-run>/`

- [ ] **步骤 1：运行新增套件和相关模块回归**

运行：

```powershell
$env:PYTHONPATH='bridge/src'; $env:PYTHONUTF8='1'; py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py bridge/tests/test_external_dialogue_lab.py bridge/tests/test_quality_results.py bridge/tests/test_run_character_quality_eval.py
py -3.10 -B -m compileall -q bridge/src scripts
git -c safe.directory='E:\workspace\projects\stardew-ai-npc.worktrees\story-memory' diff --check -- bridge/src/stardew_ai_bridge/deep_flirt_cases.py bridge/src/stardew_ai_bridge/character_quality_eval.py bridge/src/stardew_ai_bridge/app.py bridge/src/stardew_ai_bridge/quality_results.py bridge/tests/test_character_quality_eval.py bridge/tests/test_external_dialogue_lab.py bridge/tests/test_quality_results.py bridge/tests/test_run_character_quality_eval.py
```

预期：相关回归全部通过，编译退出码为 0，diff check 无空白错误。

- [ ] **步骤 2：只跑 deep-flirt 前 4 例的 DeepSeek 小批量**

运行器沿用现有入口，使用新的唯一工件目录和显式云端 Provider：

```powershell
$env:PYTHONPATH='bridge/src'; $env:PYTHONUTF8='1'; py -3.10 -B scripts/run_character_quality_eval.py --provider cloud --suite deep-flirt --limit 4 --output-dir artifacts/character-quality-eval/20260914-deep-flirt-smoke-v1
```

运行前检查当前 `127.0.0.1:5678` 仍是已有查看器；不启动新服务、不运行 Bridge 测试服务、不启动游戏或 SMAPI。结果只读取新的 `results.jsonl` / `summary.json`，分别记录 4 案例、12 轮、Provider 错误、重试、Token 和自动分数，不把自动分数当人工自然度结论。

- [ ] **步骤 3：通过已有查看器打开新套件**

请求 `http://127.0.0.1:5678/test?suite=deep-flirt`，确认 HTML 200、标题正确、页面显示当前批次和已生成/未生成案例；用浏览器可访问树和截图确认三轮对白、每轮 Guard 诊断和 consent/边界信息可读。不要创建新的 HTML、JavaScript 或启动脚本。

### 任务 6：最终检查

- [ ] **步骤 1：核对工作树边界**

运行 `git status --short --branch`，确认所有原有修改仍在，新增内容只限本计划列出的案例、接线、测试、设计/计划和新评测工件；不执行 `reset --hard`、`clean`、`checkout --` 或 `git commit`。

- [ ] **步骤 2：报告真实结果**

报告离线测试数、编译/diff 检查、DeepSeek 实际案例/轮次/错误/重试/自动分数、查看器 HTTP 和浏览器可见状态，并明确人工自然度仍需用户查看。
