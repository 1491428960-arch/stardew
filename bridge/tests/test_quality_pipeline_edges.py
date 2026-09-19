"""`quality_pipeline.CharacterQualityPipeline` 的完整通道。

2026-09-20 用覆盖率定位到 `quality_pipeline.py` 91%、11 行未覆盖——它们分布在
`run()` 与 `_draft_candidates()` 的**各条拒绝路径**上，以及 `_scenario_defaults()`
的三个字段别名回退。这条流水线是“**离线角色样本**”的通道（草拟 → 审查 → 修订一次 →
复审 → 批准/拒绝），拒绝路径不测就等于不知道坏样本会不会溜进批准名单。

用一个**按调用顺序返回预设响应**的假 generator 驱动，且它在被多调用时直接抛——
这样“实现悄悄多问了一次模型”也会暴露出来。
"""

from __future__ import annotations

import json

import pytest

from stardew_ai_bridge.behavior_quality import REVIEW_DIMENSIONS
from stardew_ai_bridge.quality_pipeline import (
    CharacterQualityPipeline,
    _parse_object,
    _scenario_defaults,
)

_GOOD_DRAFT = {
    "exampleId": "e1",
    "npcId": "Shane",
    "playerInput": "你好",
    "npcReply": "鸡舍那边挺忙的，不过还行。",
}


def _response(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _review(score: int = 2) -> dict[str, object]:
    return {**{dimension: score for dimension in REVIEW_DIMENSIONS}, "hardErrors": [], "tags": []}


class _ScriptedGenerator:
    """按调用顺序返回预设响应；用完再被调用就抛错。"""

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if not self._responses:
            raise AssertionError("generator 被多调用了一次")
        return self._responses.pop(0)


# --- _parse_object 与 _scenario_defaults ------------------------------------


@pytest.mark.parametrize("value", ["{bad json", "[1, 2]", "42", '"text"', "null"])
def test_parse_object_rejects_non_objects(value: str) -> None:
    assert _parse_object(value) is None


def test_parse_object_accepts_an_object() -> None:
    assert _parse_object('{"a": 1}') == {"a": 1}


@pytest.mark.parametrize(
    ("scenario", "field", "expected"),
    [
        ({"channel": "remote"}, "channels", ["remote"]),
        ({"relationshipStage": "close"}, "relationshipStages", ["close"]),
        ({"sourceMod": "SVE"}, "sourceMods", ["SVE"]),
    ],
)
def test_scenario_aliases_fall_back_to_lists(
    scenario: dict[str, object], field: str, expected: list[str]
) -> None:
    assert _scenario_defaults(scenario)[field] == expected


def test_an_explicit_plural_field_wins_over_the_alias() -> None:
    defaults = _scenario_defaults({"channel": "remote", "channels": ["face_to_face"]})

    assert defaults["channels"] == ["face_to_face"]


# --- 正常通道 ---------------------------------------------------------------


def test_a_clean_candidate_can_be_approved() -> None:
    generator = _ScriptedGenerator(_response(_GOOD_DRAFT), _response(_review(2)))

    # 显式 candidate_count=1：默认是 2，那样响应序列要准备两轮
    run = CharacterQualityPipeline(generator).run(
        {"scenarioId": "s"}, candidate_count=1, approved_ids=["e1"]
    )

    assert len(run.candidates) == 1
    assert len(run.approved) == 1
    assert run.rejections == []
    assert run.review_count == 1
    assert run.revision_count == 0


def test_a_clean_candidate_is_not_approved_unless_whitelisted() -> None:
    generator = _ScriptedGenerator(_response(_GOOD_DRAFT), _response(_review(2)))

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=1)

    assert run.approved == []
    assert run.rejections == []


# --- 草拟阶段的拒绝路径 -----------------------------------------------------


def test_a_non_json_draft_is_rejected() -> None:
    generator = _ScriptedGenerator("这不是 JSON")

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=1)

    assert run.candidates == []
    assert [item["reasons"] for item in run.rejections] == [["invalid_draft"]]
    # 失败的草拟用“场景:序号”作占位 id，便于定位是第几次
    assert run.rejections[0]["exampleId"] == "s:1"


def test_an_invalid_draft_payload_is_rejected_with_reasons() -> None:
    generator = _ScriptedGenerator(_response({"exampleId": "e1", "npcId": "Shane"}))

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=1)

    assert run.candidates == []
    assert run.rejections and run.rejections[0]["reasons"]


def test_candidate_count_is_capped_at_three() -> None:
    generator = _ScriptedGenerator("x", "x", "x", "x", "x")

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=10)

    # 只草拟 3 次；生成器若被多调一次会抛错
    assert len(generator.calls) == 3
    assert run.candidates == []


def test_zero_candidates_asks_the_model_nothing() -> None:
    generator = _ScriptedGenerator()

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=0)

    assert generator.calls == []
    assert run.candidates == []
    assert run.reviews == []


# --- 审查阶段的拒绝路径 -----------------------------------------------------


def test_a_non_json_review_is_rejected() -> None:
    generator = _ScriptedGenerator(_response(_GOOD_DRAFT), "不是 JSON")

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=1)

    assert [item["reasons"] for item in run.rejections] == [["invalid_review"]]


def test_a_review_missing_dimensions_is_rejected() -> None:
    generator = _ScriptedGenerator(
        _response(_GOOD_DRAFT),
        _response({"hardErrors": [], "tags": []}),  # 一个维度都没填
    )

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=1)

    assert [item["reasons"] for item in run.rejections] == [["invalid_review"]]
    assert run.reviews == []


# --- 修订阶段 ---------------------------------------------------------------


def test_a_failing_review_triggers_one_revision_that_can_pass() -> None:
    revised = {**_GOOD_DRAFT, "npcReply": "鸡舍那边挺忙的，不过还行吧。"}
    generator = _ScriptedGenerator(
        _response(_GOOD_DRAFT),
        _response(_review(0)),  # 第一次审查不通过
        _response(revised),  # 修订
        _response(_review(2)),  # 复审通过
    )

    run = CharacterQualityPipeline(generator).run(
        {"scenarioId": "s"}, candidate_count=1, approved_ids=["e1"]
    )

    assert run.revision_count == 1
    assert run.review_count == 2
    assert len(run.approved) == 1
    assert run.rejections == []


def test_a_non_json_revision_is_rejected() -> None:
    generator = _ScriptedGenerator(
        _response(_GOOD_DRAFT),
        _response(_review(0)),
        "不是 JSON",
    )

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=1)

    assert [item["reasons"] for item in run.rejections] == [["invalid_revision"]]


def test_a_revision_that_still_fails_review_is_rejected() -> None:
    generator = _ScriptedGenerator(
        _response(_GOOD_DRAFT),
        _response(_review(0)),
        _response({**_GOOD_DRAFT, "npcReply": "还是不行的一句回复。"}),
        _response(_review(0)),  # 复审仍不通过
    )

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=1)

    assert [item["reasons"] for item in run.rejections] == [["review_failed"]]
    assert run.approved == []
    assert run.review_count == 2


def test_a_non_json_second_review_is_rejected() -> None:
    generator = _ScriptedGenerator(
        _response(_GOOD_DRAFT),
        _response(_review(0)),
        _response({**_GOOD_DRAFT, "npcReply": "改过的一句回复内容。"}),
        "不是 JSON",
    )

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=1)

    assert [item["reasons"] for item in run.rejections] == [["invalid_review"]]


def test_a_revision_that_fails_validation_reports_the_first_error() -> None:
    # 修订返回了合法 JSON，但内容本身不合法时，要报出**具体的第一条错误**，
    # 而不是笼统的 invalid_revision——这样才能定位问题。
    generator = _ScriptedGenerator(
        _response(_GOOD_DRAFT),
        _response(_review(0)),
        _response({"npcReply": ""}),  # 合法 JSON，但回复为空
    )

    run = CharacterQualityPipeline(generator).run({"scenarioId": "s"}, candidate_count=1)

    assert len(run.rejections) == 1
    reasons = run.rejections[0]["reasons"]
    assert reasons and reasons != ["invalid_revision"]
