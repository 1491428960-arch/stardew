# 角色质量流水线实现计划

> **面向 AI 代理的工作者：** 使用 `subagent-driven-development`（独立任务）或 `executing-plans`（内联执行）逐任务实现。用 `update_plan` 跟踪整体状态，并保留文档中的复选框。

**目标：** 将朋友提出的多轮生成、审查、修订和 few-shot 路线落地为可审核的离线角色样本流水线，并让现有在线 Prompt 只使用少量、条件匹配的高质量样本。

**架构：** 新增纯 Python 质量契约和离线流水线，分别负责样本校验、Draft、Review、单次 Revise、人工确认和脱敏工件保存；运行时继续使用现有 `ProfileIndexStore`、`ContextBuilder` 和 `PromptBuilder`，不把三个模型串入游戏实时请求。首批只覆盖五个评测按钮，其中 Rasmodia／Wizard 共用 canonical `Wizard`；`openLoop` 和游戏存档持久化另行设计。

**技术栈：** Python 3.10+、pytest、现有 `Provider` 协议、JSON／JSONL、Ollama `qwen3.5:9b`、FastAPI Dialogue Lab。

---

## 范围与执行边界

本计划实现以下闭环：

```text
质量场景
→ Draft 候选
→ Review 结构化评分
→ 最多一次 Revise
→ 人工确认的 approved 样本
→ 条件检索与在线 Prompt
→ 固定场景评测和 Dialogue Lab 复核
```

本计划不实现跨渠道 `openLoop` 数据写入、`StoryStateSerializer`／`StoryStateStore` 存档接入或游戏端跨重启历史。这些部分需要独立的状态设计和 save/load 测试；本计划只保留 `channel` 与样本条件接口，不将它们伪装成已完成。

## 文件清单与职责

### 创建

- `bridge/src/stardew_ai_bridge/behavior_quality.py`：行为样本字段、评分维度、候选校验、通过门槛和脱敏逻辑。
- `bridge/src/stardew_ai_bridge/quality_pipeline.py`：Draft／Review／Revise 的离线编排，以及模型生成器协议。
- `bridge/src/stardew_ai_bridge/character_quality_eval.py`：五个评测按钮的固定场景、通用回复评分和评测结果结构。
- `scripts/generate_behavior_examples.py`：从场景 JSON 调用本地 Provider，保存候选、审查、修订和人工确认结果。
- `scripts/run_character_quality_eval.py`：使用固定场景调用现有 Prompt 和本地模型，输出脱敏评测工件。
- `data/personas/behavior-quality-scenarios.json`：首批评测场景和生成元数据，不保存密钥、Cookie 或用户会话。
- `bridge/tests/test_behavior_quality.py`：样本契约和评分门槛测试。
- `bridge/tests/test_quality_pipeline.py`：离线流水线编排测试，使用确定性假生成器，不联网。
- `bridge/tests/test_character_quality_eval.py`：五个配置、连续性、渠道和硬错误评分测试。
- `bridge/tests/test_generate_behavior_examples.py`：CLI 参数、输出脱敏和人工确认边界测试。
- `bridge/tests/test_run_character_quality_eval.py`：评测 CLI 使用实际 Prompt、临时工件和 Provider 的测试。

### 修改

- `bridge/src/stardew_ai_bridge/profile_index.py`：统一使用行为样本校验结果，保留合法旧样本兼容性，补充质量字段的脱敏检索投影和证据不足诊断。
- `bridge/src/stardew_ai_bridge/prompts.py`：把条件元数据以紧凑方式交给模型，明确渠道／阶段／回应动作，保持成对 few-shot、历史顺序和字符预算。
- `bridge/tests/test_profile_index.py`：增加质量字段、人工确认样本、缺失样本降级和五个配置隔离测试。
- `bridge/tests/test_prompts.py`：增加渠道差异、角色样本元数据、历史连续性和不混用其他角色样本测试。
- `bridge/tests/test_api.py`：仅在评测诊断需要通过 `/api/context/preview` 暴露新字段时增加接口契约测试。
- `data/personas/behavior-examples.json`：只在候选经过确认后更新首批金样本；不直接用未审查模型输出覆盖现有数据。
- `docs/active-work.md`：实现和验证结束后记录实际测试数字、Bridge 状态和未完成的游戏端边界。

## 任务 1：建立行为样本质量契约

**文件：**

- 创建：`bridge/src/stardew_ai_bridge/behavior_quality.py`
- 创建：`bridge/tests/test_behavior_quality.py`
- 修改：无

- [ ] **步骤 1：编写失败测试**

测试固定必填字段、枚举字段、来源标记、评分范围和硬错误：

```python
def test_validate_example_requires_context_and_pair() -> None:
    normalized, errors = validate_behavior_example(
        {"exampleId": "shane-1", "npcId": "Shane"},
        require_review=True,
    )

    assert normalized is None
    assert {"missing:playerInput", "missing:npcReply"} <= set(errors)


def test_review_pass_requires_no_hard_error_and_minimum_style_scores() -> None:
    review = {
        "stardewVoice": 2,
        "characterDistinctiveness": 2,
        "relationshipFit": 2,
        "channelFit": 2,
        "topicResponse": 2,
        "contextContinuity": 1,
        "naturalChinese": 2,
        "boundarySafety": 2,
        "hardErrors": [],
        "tags": [],
    }

    assert review_passes(review) is True
    assert review_passes({**review, "hardErrors": ["invented_lore"]}) is False
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_behavior_quality.py
```

预期：因 `behavior_quality` 模块和校验函数尚不存在而失败。

- [ ] **步骤 3：实现最小契约**

定义以下稳定接口，后续任务只依赖这些接口：

```python
REVIEW_DIMENSIONS = (
    "stardewVoice",
    "characterDistinctiveness",
    "relationshipFit",
    "channelFit",
    "topicResponse",
    "contextContinuity",
    "naturalChinese",
    "boundarySafety",
)


def validate_behavior_example(
    raw: Mapping[str, object],
    *,
    require_review: bool = False,
) -> tuple[dict[str, object] | None, list[str]]:
    normalized = dict(raw)
    errors: list[str] = []
    for field in ("exampleId", "npcId", "playerInput", "npcReply"):
        if not isinstance(normalized.get(field), str) or not normalized[field].strip():
            errors.append(f"missing:{field}")
    if isinstance(normalized.get("npcId"), str):
        normalized["npcId"] = canonical_npc_id(normalized["npcId"])
    if require_review:
        review = normalized.get("review")
        if not isinstance(review, Mapping):
            errors.append("missing:review")
        else:
            errors.extend(validate_review(review))
    return (None, errors) if errors else (normalized, [])


def validate_review(review: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    for dimension in REVIEW_DIMENSIONS:
        score = review.get(dimension)
        if not isinstance(score, int) or isinstance(score, bool) or score not in {0, 1, 2}:
            errors.append(f"invalid-score:{dimension}")
    return errors


def review_passes(review: Mapping[str, object]) -> bool:
    if review.get("hardErrors"):
        return False
    scores = [review.get(name) for name in REVIEW_DIMENSIONS]
    return all(isinstance(score, int) and not isinstance(score, bool) and score >= 1 for score in scores)


SENSITIVE_KEYS = {
    "apikey",
    "token",
    "cookie",
    "authorization",
    "prompt",
    "request",
}


def sanitize_quality_artifact(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_quality_artifact(item)
            for key, item in value.items()
            if str(key).casefold() not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [sanitize_quality_artifact(item) for item in value]
    return value
```

校验器必须：

- 要求 `exampleId`、`npcId`、`playerInput`、`npcReply`；
- 规范化 `npcId`，使 `Rasmodia` 归入 canonical `Wizard`；
- 检查 `channels`、`relationshipStages` 为非空字符串数组；
- 检查 Review 分数只能是 0、1、2；
- 将安全错误、未授权剧情、错误渠道和明显病句列为硬错误；
- 清除 API key、Token、Cookie、Authorization、完整 Prompt 和完整请求字段；
- 返回结构化错误，不抛出会中断整批任务的未处理异常。

- [ ] **步骤 4：运行测试确认通过**

运行同一步骤 2 的命令，预期全部通过，并补充测试：合法 Shane 样本、Wizard／Rasmodia canonical 合并、缺失 review 的旧手工样本兼容和敏感字段脱敏。

## 任务 2：实现 Draft／Review／Revise 离线流水线

**文件：**

- 创建：`bridge/src/stardew_ai_bridge/quality_pipeline.py`
- 创建：`bridge/tests/test_quality_pipeline.py`
- 修改：无

- [ ] **步骤 1：编写失败测试**

使用确定性生成器证明流水线严格执行“生成候选 → 审查 → 最多一次修订”，且未经显式确认不进入 `approved`：

```python
def test_pipeline_revises_once_and_only_explicit_ids_are_approved() -> None:
    generator = ScriptedGenerator(
        [
            draft_json("候选一", "draft-1"),
            review_json("too_formal"),
            revised_json("修订一", "draft-1"),
            review_json(),
        ]
    )
    run = CharacterQualityPipeline(generator).run(
        scenario=SCENARIO,
        candidate_count=1,
        approved_ids=("draft-1",),
    )

    assert run.revision_count == 1
    assert run.review_count == 2
    assert [item["npcReply"] for item in run.approved] == ["修订一"]


def test_pipeline_rejects_invalid_review_without_retry_loop() -> None:
    generator = ScriptedGenerator([draft_json("候选", "draft-1"), "不是 JSON"])

    run = CharacterQualityPipeline(generator).run(
        scenario=SCENARIO,
        candidate_count=1,
    )

    assert run.approved == []
    assert run.revision_count == 0
    assert "invalid_review" in run.rejections[0]["reasons"]
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_quality_pipeline.py
```

预期：因流水线模块和确定性测试生成器尚不存在而失败。

- [ ] **步骤 3：实现最小流水线**

定义生成器和结果对象，不修改现有实时 Provider 协议：

```python
class MessageGenerator(Protocol):
    def generate(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class QualityRun:
    candidates: list[dict[str, object]]
    reviews: list[dict[str, object]]
    revised: list[dict[str, object]]
    approved: list[dict[str, object]]
    rejections: list[dict[str, object]]
    revision_count: int
    review_count: int


class CharacterQualityPipeline:
    def run(
        self,
        scenario: Mapping[str, object],
        *,
        candidate_count: int = 2,
        approved_ids: Iterable[str] = (),
    ) -> QualityRun:
        candidates = self._draft_candidates(scenario, candidate_count)
        reviews: list[dict[str, object]] = []
        revised: list[dict[str, object]] = []
        approved: list[dict[str, object]] = []
        rejections: list[dict[str, object]] = []
        approved_id_set = set(approved_ids)
        for candidate in candidates:
            first_review = self._review(candidate, scenario)
            reviews.append(first_review)
            selected = candidate
            if not review_passes(first_review):
                selected = self._revise_once(candidate, first_review, scenario)
                if selected is None:
                    rejections.append({"exampleId": candidate["exampleId"], "reasons": ["revision_failed"]})
                    continue
                revised.append(selected)
                second_review = self._review(selected, scenario)
                reviews.append(second_review)
                if not review_passes(second_review):
                    rejections.append({"exampleId": selected["exampleId"], "reasons": ["review_failed"]})
                    continue
            if str(selected.get("exampleId")) in approved_id_set:
                approved.append(selected)
        return QualityRun(
            candidates=candidates,
            reviews=reviews,
            revised=revised,
            approved=approved,
            rejections=rejections,
            revision_count=len(revised),
            review_count=len(reviews),
        )
```

实现规则：

- Draft 默认生成 2 个候选，最多接受调用方指定的 3 个；
- Review 必须解析为 JSON，解析失败直接拒绝，不把自由文本当评分；
- Review 有硬错误或低于最低分时才进入 Revise；
- Revise 每个候选最多执行一次；
- 修订后必须再次 Review，第二次失败即淘汰；
- 只有 `approved_ids` 中且第二次 Review 通过的候选进入 `approved`；
- 结果工件只保存脱敏内容和评分，不保存生成器配置中的密钥或完整请求；
- 生成器异常只影响当前候选，并记录安全错误，不中断整批任务。

- [ ] **步骤 4：运行测试确认通过**

运行同一步骤 2 的命令，预期流水线编排、一次修订、坏 JSON、硬错误和人工确认测试全部通过。

## 任务 3：增加场景目录和离线 CLI

**文件：**

- 创建：`data/personas/behavior-quality-scenarios.json`
- 创建：`scripts/generate_behavior_examples.py`
- 创建：`bridge/tests/test_generate_behavior_examples.py`
- 修改：无

- [ ] **步骤 1：编写失败测试**

测试 CLI 默认只生成候选工件，不修改正式角色样本；只有显式的本地确认 ID 才生成 `approved.json`：

```python
def test_cli_does_not_write_approved_samples_without_explicit_ids(tmp_path: Path) -> None:
    result = run_cli(
        scenario_path=SCENARIOS,
        output_dir=tmp_path,
        generator=DeterministicGenerator(),
    )

    assert result.approved == []
    assert (tmp_path / "candidates.jsonl").is_file()
    assert (tmp_path / "reviews.jsonl").is_file()
    assert not (tmp_path / "approved.json").exists()


def test_cli_artifacts_never_contain_secret_labels(tmp_path: Path) -> None:
    run_cli(
        scenario_path=SCENARIOS,
        output_dir=tmp_path,
        generator=DeterministicGenerator("apiKey=secret-token"),
    )

    rendered = "".join(path.read_text(encoding="utf-8") for path in tmp_path.iterdir())
    assert "secret-token" not in rendered
    assert "apiKey" not in rendered
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_generate_behavior_examples.py
```

预期：因场景目录和 CLI 尚不存在而失败。

- [ ] **步骤 3：实现固定场景和 CLI**

场景目录至少包含以下五个评测按钮及统一的场景分类；Rasmodia／Wizard 只出现一个 `npcId=Wizard` 配置：

```json
{
  "schemaVersion": 1,
  "scenarios": [
    {
      "scenarioId": "wizard-acquaintance-remote-invitation",
      "npcId": "Wizard",
      "displayName": "Rasmodia",
      "sourceMods": ["Romanceable Rasmodius"],
      "relationshipStage": "acquaintance",
      "channel": "remote",
      "topic": "invitation",
      "playerInput": "改天一起核对一下记录？"
    }
  ]
}
```

CLI 接口固定为：

```text
python scripts/generate_behavior_examples.py \
  --scenarios data/personas/behavior-quality-scenarios.json \
  --output-dir artifacts/character-quality/<run-id> \
  --provider local \
  --model qwen3.5:9b \
  --approve draft-001,draft-004
```

实现要求：

- 默认输出 `candidates.jsonl`、`reviews.jsonl`、`revisions.jsonl` 和 `run-summary.json`；
- 未传 `--approve` 时不输出 `approved.json`；
- `--approve` 只接受本次运行中 Review 通过的 ID；
- Ollama 配置从现有环境变量读取，不把 Token 或 URL 中的敏感信息写入工件；
- 输出路径默认位于已被忽略的 `artifacts/`，不自动改写 `data/personas/behavior-examples.json`；
- 采用批量上限，首轮最多处理 10 个场景，先验证质量和耗时再扩大数量。

- [ ] **步骤 4：运行定向测试确认通过**

运行同一步骤 2 的命令，预期 CLI 参数、场景加载、候选工件、显式确认和脱敏测试全部通过。

## 任务 4：让索引只消费合法且有条件的行为样本

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`
- 修改：`bridge/tests/test_profile_index.py`
- 修改：`data/personas/behavior-examples.json`

- [ ] **步骤 1：编写失败测试**

增加以下回归：

```python
def test_behavior_loader_skips_invalid_and_unapproved_candidates(tmp_path: Path) -> None:
    write_behavior_examples(
        tmp_path,
        [
            valid_approved_example("shane-approved"),
            {"exampleId": "missing-reply", "npcId": "Shane", "playerInput": "你好"},
            {"exampleId": "draft-only", "npcId": "Shane", "sourceType": "model_draft"},
        ],
    )

    index = ProfileIndexBuilder(tmp_path).build()

    assert [item["exampleId"] for item in index["behaviorExamples"]] == [
        "shane-approved"
    ]


def test_behavior_examples_require_exact_channel_and_stage_before_topic_match() -> None:
    store = ProfileIndexStore(INDEX_WITH_REMOTE_ACQUAINTANCE_AND_FACE_TO_FACE_FRIEND)

    assert store.behavior_examples(
        "Shane", ["vanilla"], relationship_stage="acquaintance",
        channel="face_to_face", player_input="鸡舍今天忙吗？",
    ) == []
```

已有手工样本的兼容规则要在测试中明确：`sourceType=handcrafted_example` 视为旧版人工确认样本；`model_draft`、`model_review` 和未知生成状态不得进入在线索引。

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_profile_index.py
```

预期：新增加载门槛和条件筛选断言在当前实现上失败，既有排序和 Wizard canonical 测试仍可定位。

- [ ] **步骤 3：实现最小索引改动**

在 `_load_behavior_examples()` 中调用任务 1 的校验器，保留现有字段投影和警告风格：

```python
normalized, errors = validate_behavior_example(
    raw_example,
    require_review=False,
)
if normalized is None:
    warnings.extend(
        f"invalid behavior example: {path.name}:{position}:{error}"
        for error in errors
    )
    continue
if normalized.get("sourceType") not in {"handcrafted_example", "human_approved"}:
    warnings.append(f"unapproved behavior example: {path.name}:{position}")
    continue
examples.append(normalized)
```

不要修改现有 `behavior_examples()` 的“同角色、来源、阶段、渠道、话题”基本筛选逻辑，只增加：

- canonical `Wizard` 归一化；
- `sourceRefs`、`speechFunction`、`topic`、`emotion` 和 review 摘要的安全投影；
- 同一输入下优先选择有相同渠道、阶段和回应动作的样本；
- 没有匹配样本时返回空列表并提供计数诊断，不跨角色借样本。

只有经人工审查的首批样本才更新 `behavior-examples.json`；旧样本不因本任务自动删除，避免破坏现有回归和用户正在查看的资料。

- [ ] **步骤 4：运行定向测试确认通过**

运行同一步骤 2 的命令，预期所有 Profile Index 测试通过，且新诊断不会泄露完整 Prompt 或敏感字段。

## 任务 5：调整在线 Prompt 的条件示例投影

**文件：**

- 修改：`bridge/src/stardew_ai_bridge/prompts.py`
- 修改：`bridge/tests/test_prompts.py`
- 修改：`bridge/src/stardew_ai_bridge/profile_index.py`（仅在现有检索投影无法承载质量字段时）

- [ ] **步骤 1：编写失败测试**

测试条件元数据、成对消息、历史顺序和角色隔离：

```python
def test_prompt_labels_behavior_example_conditions_without_leaking_review_payload() -> None:
    messages = PromptBuilder().build(
        context_with_behavior_example(
            npc_id="Shane",
            channel="face_to_face",
            stage="acquaintance",
            review={"naturalChinese": 2, "hardErrors": []},
        ),
        "鸡舍今天忙吗？",
    )
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "face_to_face" in rendered
    assert "acquaintance" in rendered
    assert "naturalChinese" not in rendered
    assert [message["role"] for message in messages[-3:]] == [
        "user", "assistant", "user"
    ]


def test_prompt_does_not_fill_missing_shane_examples_with_sophia_examples() -> None:
    context = context_without_shane_behavior_examples()

    rendered = json.dumps(PromptBuilder().build(context, "你好"), ensure_ascii=False)

    assert "Sophia 的回复" not in rendered
    assert "behavior_example_assistant" not in rendered
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_prompts.py
```

预期：条件元数据投影和无跨角色填充测试先失败；既有历史、敏感字段和 Prompt 字符预算测试保持可执行。

- [ ] **步骤 3：实现最小 Prompt 改动**

保持现有消息顺序和 `behavior_example_user`／`behavior_example_assistant` 成对结构，仅把可执行条件摘要放入一个短的 system 消息：

```python
messages.append(
    {
        "role": "system",
        "name": "behavior_examples",
        "content": _json({
            "instruction": "只模仿当前 NPC 的回应动作和节奏，不照抄示例。",
            "conditions": [
                {
                    "channel": item.get("channels", []),
                    "relationshipStage": item.get("relationshipStages", []),
                    "speechFunction": item.get("speechFunction"),
                    "topic": item.get("topic"),
                    "emotion": item.get("emotion"),
                }
                for item in safe_context["behaviorExamples"]
            ],
        }),
    }
)
```

实现要求：

- review 分数、审查标签和生成过程不进入在线 Prompt；
- 保持最多 2～4 条高相关行为样本和现有字符预算；
- `remote` 与 `face_to_face` 只投影对应样本，不以另一个渠道的样本填充；
- 历史仍然出现在当前输入前，且只用于承接具体事实；
- Prompt 末尾继续强调当前角色 voiceStyle、关系阶段、渠道和当前输入；
- 缺少行为样本时只依赖角色卡和官方语气证据，不输出“证据不足”的内部文字给 NPC；
- 不使用字符串替换强制改写模型回复。

- [ ] **步骤 4：运行定向测试确认通过**

运行同一步骤 2 的命令，预期 Prompt 全部测试通过，序列化长度仍低于当前项目预算，且新条件摘要不包含 review 或敏感字段。

## 任务 6：建立五个评测配置和可复核评分

**文件：**

- 创建：`bridge/src/stardew_ai_bridge/character_quality_eval.py`
- 创建：`bridge/tests/test_character_quality_eval.py`
- 创建：`data/personas/behavior-quality-scenarios.json`
- 修改：`bridge/src/stardew_ai_bridge/local_benchmark.py`（仅在复用旧评测类型不会破坏兼容性时）

- [ ] **步骤 1：编写失败测试**

测试五个按钮、四个 canonical NPC ID、渠道和连续性评分：

```python
def test_default_character_cases_keep_wizard_and_rasmodia_as_one_identity() -> None:
    assert set(DEFAULT_CHARACTER_PROFILES) == {
        "wizard_rasmodia",
        "sophia",
        "shane",
        "sebastian",
        "alex",
    }
    assert DEFAULT_CHARACTER_PROFILES["wizard_rasmodia"].npc_id == "Wizard"


def test_quality_score_rejects_generic_bookish_reply_and_accepts_continuity() -> None:
    case = case_by_id("wizard-follow-up")

    bad = score_character_reply(case, "综合来看，此事具有重要意义，建议持续关注后续发展。")
    good = score_character_reply(case, "整理完了。第三组稳定，第二组还得重测。")

    assert bad["tags"] >= {"too_formal", "generic_voice"}
    assert good["continuity"] is True
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_character_quality_eval.py
```

预期：新评测模块和评分函数尚不存在而失败。

- [ ] **步骤 3：实现固定评测集**

定义 `CharacterQualityCase` 和 `score_character_reply()`，评分只做可复核的轻量规则，不冒充主观“像不像”结论：

```python
@dataclass(frozen=True)
class CharacterQualityCase:
    case_id: str
    profile_key: str
    npc_id: str
    display_name: str
    source_mods: tuple[str, ...]
    relationship_stage: str
    channel: str
    message: str
    history: tuple[dict[str, str], ...] = ()
    expected_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()


def score_character_reply(
    case: CharacterQualityCase,
    reply: str,
) -> dict[str, object]:
    text = reply.strip()
    lowered = text.casefold()
    expected_hits = sum(term.casefold() in lowered for term in case.expected_terms)
    forbidden_hits = sum(term.casefold() in lowered for term in case.forbidden_terms)
    continuity = any(
        item.get("content", "").casefold() in lowered
        for item in case.history
        if isinstance(item.get("content"), str) and item["content"].strip()
    )
    tags = set()
    if len(text) > 120:
        tags.add("too_formal")
    if not text:
        tags.add("empty_reply")
    return {
        "expectedHits": expected_hits,
        "forbiddenHits": forbidden_hits,
        "continuity": continuity,
        "replyLength": len(text),
        "tags": tags,
        "passed": bool(text) and forbidden_hits == 0,
    }
```

首批场景至少覆盖每个评测配置的：问近况、表达关心、兴趣／工作、远程邀约、面对面续接和一次连续追问。Wizard／Rasmodia 的案例共用 `npcId=Wizard` 和同一历史链。

评分至少包含：`expectedHits`、`forbiddenHits`、`continuity`、`replyLength`、`tags`、`passed`。`too_formal`、`generic_voice`、`repeated_opener`、`wrong_channel` 和 `invented_lore` 作为提示标签，不由简单字符串规则直接改写回复。

- [ ] **步骤 4：运行定向测试确认通过**

运行同一步骤 2 的命令，预期五个配置、身份合并、渠道和连续性测试全部通过。

## 任务 7：建立评测 CLI，并在浏览器查看新结果

**文件：**

- 创建：`scripts/run_character_quality_eval.py`
- 创建：`bridge/tests/test_run_character_quality_eval.py`
- 修改：无；复用 `bridge/src/stardew_ai_bridge/dialogue_lab_page.py` 的现有页面

- [ ] **步骤 1：编写失败测试**

测试评测 CLI 使用实际 `ContextBuilder`／`PromptBuilder`，且只向临时目录写脱敏工件：

```python
def test_eval_cli_uses_selected_profile_index_and_temp_output(
    monkeypatch, tmp_path: Path
) -> None:
    captured: list[list[dict[str, str]]] = []
    module = _load_eval_module()
    monkeypatch.setattr(module, "OllamaNativeProvider", CapturingProvider(captured))

    summary = run_evaluation(
        profile_index=TEST_INDEX,
        output_dir=tmp_path,
        cases=(case_by_id("wizard-follow-up"),),
    )

    assert summary["successful"] == 1
    assert "conversation_history" in {
        item.get("name") for item in captured[0]
    }
    assert all(path.parent == tmp_path for path in tmp_path.iterdir())
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_run_character_quality_eval.py
```

预期：因评测 CLI 尚不存在而失败。

- [ ] **步骤 3：实现评测 CLI**

实现 `run_evaluation()` 和命令行入口，复用现有索引解析和 Prompt 生成：

```text
python scripts/run_character_quality_eval.py \
  --profile-index data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json \
  --output-dir artifacts/character-quality/<run-id> \
  --limit 30
```

实现要求：

- 默认使用当前中文联合索引和隔离 Ollama 环境变量；
- 每个评测按钮至少运行同一组小场景，比较角色差异而非比较不同输入；
- 输出包含 `provider`、`fallback`、耗时、结构化轻量分数和脱敏回复；
- 不读取或覆盖用户已有 Dialogue Lab 会话文件；
- 运行时工件写入 `artifacts/`，不写入角色资料和 Git 跟踪文件；
- `Wizard` 与 `Rasmodia` 的评测结果按同一历史和 canonical ID 聚合。

- [ ] **步骤 4：运行定向测试确认通过**

运行同一步骤 2 的命令，预期评测 CLI 全部通过。

- [ ] **步骤 5：启动或确认 Bridge 后做浏览器复核**

确认 `http://127.0.0.1:5678/health` 返回 `status=ok` 且报告当前运行 Provider，再打开 `http://127.0.0.1:5678/test`：

- 使用干净的临时会话，不删除用户现有记录；
- 逐个点击五个评测按钮；
- 每个配置发送同样的 3～5 轮短对话，至少包含一次追问；
- 观察角色语气、句长、开场重复、魔法词误用和上下文承接；
- 核对 `Wizard`／`Rasmodia` 切换不会产生第二条历史；
- 记录实际回复，不把轻量自动评分当作人工风格结论。

## 任务 8：重建索引、完整回归和交付核验

**文件：**

- 生成：`data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json`
- 修改：`docs/active-work.md`
- 修改：仅在契约需要时修改测试文件

- [ ] **步骤 1：先运行定向测试**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests/test_behavior_quality.py bridge/tests/test_quality_pipeline.py bridge/tests/test_profile_index.py bridge/tests/test_prompts.py bridge/tests/test_character_quality_eval.py bridge/tests/test_generate_behavior_examples.py bridge/tests/test_run_character_quality_eval.py
```

预期：所有定向测试通过，失败时先回到对应任务，不跳过失败继续生成样本。

- [ ] **步骤 2：使用现有脚本重建中文联合索引**

只在确认 approved 样本已经人工确认后重建索引；生成文件仍属于派生工件，不写入密钥、Token、Cookie、用户会话或游戏存档。

- [ ] **步骤 3：运行完整 Bridge 测试**

运行：

```powershell
$env:PYTHONPATH='E:\workspace\projects\stardew-ai-npc\.worktrees\story-memory\bridge\src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe' -B -m pytest -q -p no:cacheprovider bridge/tests
```

必须记录本次实际 `passed`、`failed` 和 warning 数字，不能沿用之前的结论。

- [ ] **步骤 4：确认 Bridge 运行时边界**

核对包装 PowerShell 和真正绑定 `5678` 的 Python 子进程都来自当前工作树；检查：

```text
GET http://127.0.0.1:5678/health
GET http://127.0.0.1:5678/test
POST http://127.0.0.1:5678/api/context/preview
```

`/health` 必须报告 `status=ok` 和实际 Provider；`/api/context/preview` 必须能看到当前角色、阶段、渠道和行为样本数量，但不得包含完整 Prompt 或敏感值。

- [ ] **步骤 5：检查工作树和交付边界**

确认新提交或修改没有包含密钥、Token、Cookie、用户会话、运行日志和正式存档；确认未改动位置、房屋入口、输入法或已验收 UI；在 `docs/active-work.md` 中明确写出：

- 网页／Bridge 质量流水线是否通过；
- 浏览器实际看到的五个配置结果；
- 当前完整测试数字；
- 游戏端 `openLoop` 与跨重启持久化仍未完成的事实（如确实未完成）。

## 计划自检

- 规格中的 Draft、Review、Revise、人工门槛分别由任务 1～3 覆盖；
- 条件 few-shot、来源和阶段筛选由任务 4～5 覆盖；
- 五个评测配置、Wizard/Rasmodia canonical 合并和盲测由任务 6～7 覆盖；
- 测试、完整回归、Bridge 和浏览器验收由任务 8 覆盖；
- `openLoop` 和游戏存档持久化明确列为本计划之外，没有被写成已实现功能；
- 计划没有要求增加实时三模型调用、立即换模型或重写 React；
- 所有实现任务都有失败测试、最小实现和定向验证命令；
- 工件和正式资料之间有明确边界，未审核候选不能进入在线索引。
