# deep-flirt 玩家表达卡实现计划

> **面向 AI 代理的工作者：** 使用 `subagent-driven-development`（独立任务）或 `executing-plans`（内联执行）逐任务实现。用 `update_plan` 跟踪整体状态，并保留文档中的复选框。

**目标：** 为 `deep-flirt` 的固定三轮玩家输入加入“渴望被爱但略有不配得感、助人冲动强且偶尔莽撞后自我修正”的玩家表达卡，让测试例像真人，同时保留原有调情递进与同意边界覆盖。

**架构：** `CharacterQualityCase` 持有可选的不可变 `PlayerExpressionCard`；八个 `deep-flirt` 案例各自声明一张卡，固定三轮台词按卡重写。案例目录输出安全的卡片摘要，既有 Dialogue Lab 在固定案例详情中显示“玩家表达倾向”，但不显示禁用项和评分锚点。NPC Prompt、默认套件和 adaptive 玩家模拟器不接收这张卡。

**技术栈：** Python 3.10、dataclasses、pytest、现有 Dialogue Lab 内嵌 JavaScript。

---

## 文件职责

- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
  - 定义 `PlayerExpressionCard`；为 `CharacterQualityCase` 保存可选卡片；向案例目录输出受控摘要。
- 修改：`bridge/src/stardew_ai_bridge/deep_flirt_cases.py`
  - 为 8 个案例填写卡片并重写 24 条固定玩家台词；保留原 `expected_terms`、轮次目标和边界元数据。
- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py`
  - 让既有案例详情在固定 `deep-flirt` 结果中显示玩家表达倾向；不创建新的 HTML 或页面入口。
- 修改：`bridge/tests/test_character_quality_eval.py`
  - 覆盖卡片完整性、目录序列化、自然输入和边界语义。
- 修改：`bridge/tests/test_quality_results.py`
  - 确认质量结果清洗仍只暴露有限长度的玩家表达摘要，不泄露禁用项或评分字段。
- 修改：`docs/active-work.md`
  - 在离线验证和真实小批量评测完成后记录结果。
- 创建：`docs/superpowers/specs/2026-09-14-player-expression-card-design.md`
  - 已记录并获用户批准的设计规格。

### 任务 1：先写失败回归，锁定玩家卡和自然台词边界

**文件：**

- 修改：`bridge/tests/test_character_quality_eval.py`

- [ ] **步骤 1：编写失败测试**

新增以下可运行测试，测试真实的 `quality_cases_for_suite` 和 `quality_case_catalog`：

```python
def test_deep_flirt_cases_have_player_expression_cards() -> None:
    cases = quality_cases_for_suite("deep-flirt")
    assert len(cases) == 8
    for case in cases:
        card = case.player_expression_card
        assert card is not None
        assert card.relationship_stance
        assert card.language_texture
        assert card.helping_impulse
        assert card.distance_pattern
        assert card.flirt_progression
        assert card.boundary_style
        assert card.self_correction
        assert card.forbidden_tendencies


def test_deep_flirt_fixed_inputs_are_not_stage_directions_or_eval_checklists() -> None:
    forbidden = (
        "我挪近了", "我坐近了", "我坐你旁边了", "你问一声就行",
        "测试例", "评测", "关键词", "NPC 回复",
    )
    for case in quality_cases_for_suite("deep-flirt"):
        for turn in case.dialogue_turns():
            assert not any(marker in turn.message for marker in forbidden)


def test_deep_flirt_catalog_exposes_only_player_expression_summary() -> None:
    item = next(
        item for item in quality_case_catalog("deep-flirt")
        if item["caseId"] == "deep-flirt-sebastian-married"
    )
    card = item["playerExpressionCard"]
    assert card["relationshipStance"]
    assert "forbiddenTendencies" not in card
    assert item["playerSimulationStyle"]
```

- [ ] **步骤 2：运行测试确认红灯**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py -k 'player_expression or deep_flirt_fixed_inputs_are_not_stage'
```

预期：因 `CharacterQualityCase` 尚无 `player_expression_card`，测试失败；不得把失败改成跳过。

### 任务 2：加入不可变玩家表达卡和安全目录字段

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/character_quality_eval.py:221-270`
- 测试：`bridge/tests/test_character_quality_eval.py`

- [ ] **步骤 1：定义最小类型**

在 `CharacterQualityTurn` 后加入：

```python
@dataclass(frozen=True)
class PlayerExpressionCard:
    relationship_stance: str
    language_texture: str
    helping_impulse: str
    distance_pattern: str
    flirt_progression: str
    boundary_style: str
    self_correction: str
    forbidden_tendencies: tuple[str, ...]

    def summary(self) -> str:
        return f"{self.relationship_stance}；{self.language_texture}；{self.flirt_progression}"
```

给 `CharacterQualityCase` 增加：

```python
player_expression_card: PlayerExpressionCard | None = None
```

- [ ] **步骤 2：向案例目录输出受控字段**

在 `quality_case_catalog` 的每个条目中加入：

```python
"playerSimulationStyle": (
    case.player_expression_card.summary()
    if case.player_expression_card is not None
    else case.player_simulation_style
),
"playerExpressionCard": (
    {
        "relationshipStance": card.relationship_stance,
        "languageTexture": card.language_texture,
        "helpingImpulse": card.helping_impulse,
        "distancePattern": card.distance_pattern,
        "flirtProgression": card.flirt_progression,
        "boundaryStyle": card.boundary_style,
        "selfCorrection": card.self_correction,
    }
    if (card := case.player_expression_card) is not None
    else None
),
```

目录只公开表达倾向，不公开 `forbidden_tendencies`、`expected_terms` 或内部评分锚点；默认套件保持 `None` 和原有 `player_simulation_style` 行为。

- [ ] **步骤 3：运行任务 1 回归确认通过**

运行同一条 `pytest` 命令，预期新增测试通过，其他已存在的 `character_quality_eval` 测试不受影响。

### 任务 3：为 8 个案例填写卡片并重写固定玩家台词

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/deep_flirt_cases.py`
- 测试：`bridge/tests/test_character_quality_eval.py`

- [ ] **步骤 1：为每个角色声明一张卡**

每张卡都保留共同核心，但通过角色语境改变表面表达：Wizard 偏观察和低声，Sophia 偏害羞改口，Shane 偏生活化照顾，Sebastian 借音乐靠近，Alex 用挑战和玩笑，Elliott 限制文学密度，Harvey 把关心和自我需要放在一起，Sam 用行动和音乐承载亲近。

- [ ] **步骤 2：重写 24 条固定台词**

每个案例保持三轮的隐藏目标：第一轮从场景切入并露出靠近意愿，第二轮暴露一点“想被接受”或多走半步，第三轮接受、放慢或暂停并在需要时自我修正。台词只使用自然口语，不出现旁白式“我……了”、评测术语或关键词堆叠。

- [ ] **步骤 3：运行输入与目录回归**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py -k 'deep_flirt or player_expression'
```

预期：deep-flirt 案例结构、三轮边界、卡片完整性和自然台词测试全部通过。

### 任务 4：让现有查看器显示固定案例的玩家表达倾向

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/dialogue_lab_page.py:1184-1208`
- 修改：`bridge/tests/test_quality_results.py`

- [ ] **步骤 1：扩展既有渲染函数**

把 `renderAdaptiveInputSummary` 的条件从“仅 adaptive”改为“adaptive 或存在 `playerExpressionCard`”，固定案例显示“玩家表达倾向”和一条摘要；自适应案例继续显示原来的生成方式和模拟风格。

- [ ] **步骤 2：保留安全清洗边界**

检查 `/api/quality/cases?suite=deep-flirt` 只返回卡片的七个公开字段，不返回 `forbiddenTendencies`；`/api/quality/results` 继续限制 `playerSimulationStyle` 长度。

- [ ] **步骤 3：运行接口/结果层回归**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_quality_results.py bridge/tests/test_api.py -k 'quality or player'
```

### 任务 5：相关离线验证和新批次人工复核

**文件：**

- 修改：`docs/active-work.md`
- 创建：`artifacts/character-quality-eval/20260914-deep-flirt-player-card-v1/`（运行产物，不覆盖历史工件）

- [ ] **步骤 1：运行定向回归**

运行：

```powershell
$env:PYTHONPATH='bridge/src'
py -3.10 -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py bridge/tests/test_quality_results.py bridge/tests/test_api.py
py -3.10 -B -m compileall -q bridge/src scripts
git diff --check
```

- [ ] **步骤 2：运行新 DeepSeek 小批量**

使用已授权的云端小批量入口，写入新目录：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH='bridge/src'
py -3.10 -B scripts/run_character_quality_eval.py `
  --provider cloud `
  --suite deep-flirt `
  --limit 4 `
  --max-requests 120 `
  --max-total-tokens 400000 `
  --output-dir artifacts/character-quality-eval/20260914-deep-flirt-player-card-v1
```

不启动游戏、SMAPI、Bridge 测试服务，不读取或输出密钥，不覆盖 v3。

- [ ] **步骤 3：按人工对白和自动指标分别验收**

读取新工件摘要和三轮对白，比较 v3 的：玩家输入自然度、NPC 是否机械复述、`missing_proactive_affection`、`missing_current_topic_answer`、`missing_continuity_evidence`、重试数和 Token。自动评分与人工可读性分开报告。

- [ ] **步骤 4：刷新已有查看器并确认页面**

确认 `127.0.0.1:5678` 的 `/health`、`/api/quality/results?suite=deep-flirt` 和现有 deep-flirt 页面仍为可访问状态；浏览器刷新后应能看到新批次、玩家表达倾向和 4 个案例的完整三轮对白。

- [ ] **步骤 5：更新活动记录**

在 `docs/active-work.md` 顶部记录离线计数、云端工件、人工对白结论、查看器状态、未启动的服务和未创建提交的事实。

## 计划自检

- 规格中的“只作用于 deep-flirt”由任务 3 的案例填写和任务 2 的默认套件回归覆盖。
- 规格中的“固定三轮、保留边界目标”由任务 3 的结构回归和任务 5 的实际工件覆盖。
- 规格中的“查看器显示表达倾向但不泄露评分内部字段”由任务 4 的接口和结果层回归覆盖。
- 规格中的“不开启自适应、不改 NPC Prompt、不创建提交”在任务 2、任务 4 和任务 5 的边界检查中明确。
- 计划没有使用 `TODO`、`待定` 或未定义的函数名；所有命令都指定目标工作树作为工具工作目录。
