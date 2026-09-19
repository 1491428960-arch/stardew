from __future__ import annotations

import json
from typing import Iterable

import pytest

try:
    from stardew_ai_bridge.behavior_quality import REVIEW_DIMENSIONS
    from stardew_ai_bridge.quality_pipeline import CharacterQualityPipeline
except ModuleNotFoundError:
    REVIEW_DIMENSIONS = ()
    CharacterQualityPipeline = None  # type: ignore[assignment]


SCENARIO = {
    "scenarioId": "shane-acquaintance-coop",
    "npcId": "Shane",
    "sourceMods": ["vanilla"],
    "channels": ["face_to_face"],
    "relationshipStages": ["acquaintance"],
    "speechFunction": "answer_directly",
    "topic": "chicken",
    "emotion": "tired_dry_humor",
    "playerInput": "鸡舍今天忙吗？",
}


def draft_json(reply: str, example_id: str) -> str:
    return json.dumps(
        {
            "exampleId": example_id,
            "npcId": "Shane",
            "sourceMods": ["vanilla"],
            "channels": ["face_to_face"],
            "relationshipStages": ["acquaintance"],
            "speechFunction": "answer_directly",
            "topic": "chicken",
            "emotion": "tired_dry_humor",
            "playerInput": SCENARIO["playerInput"],
            "npcReply": reply,
            "sourceType": "model_draft",
        },
        ensure_ascii=False,
    )


def revised_json(reply: str, example_id: str) -> str:
    value = json.loads(draft_json(reply, example_id))
    value["sourceType"] = "model_revision"
    return json.dumps(value, ensure_ascii=False)


def review_json(tag: str | None = None) -> str:
    value = {
        "stardewVoice": 1 if tag else 2,
        "characterDistinctiveness": 2,
        "relationshipFit": 2,
        "channelFit": 2,
        "topicResponse": 2,
        "contextContinuity": 2,
        "naturalChinese": 1 if tag else 2,
        "boundarySafety": 2,
        "hardErrors": [],
        "tags": [tag] if tag else [],
    }
    return json.dumps(value, ensure_ascii=False)


class ScriptedGenerator:
    def __init__(self, outputs: Iterable[str]) -> None:
        self.outputs = list(outputs)
        self.calls: list[list[dict[str, str]]] = []

    def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if not self.outputs:
            raise AssertionError("测试生成器输出已耗尽")
        return self.outputs.pop(0)


def test_pipeline_requires_real_implementation() -> None:
    if CharacterQualityPipeline is None:
        pytest.fail("Task 2 Draft/Review/Revise 流水线尚未实现")


def test_pipeline_revises_once_and_only_explicit_ids_are_approved() -> None:
    if CharacterQualityPipeline is None:
        pytest.fail("Task 2 Draft/Review/Revise 流水线尚未实现")
    generator = ScriptedGenerator(
        [
            draft_json("感谢你的关心。综合来看，鸡舍运营情况总体良好。", "draft-1"),
            review_json("too_formal"),
            revised_json("还行。没着火，就算顺利。", "draft-1"),
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
    assert [item["npcReply"] for item in run.approved] == [
        "还行。没着火，就算顺利。"
    ]
    assert [messages[0]["name"] for messages in generator.calls] == [
        "draft",
        "review",
        "revise",
        "review",
    ]


def test_pipeline_rejects_invalid_review_without_revision_loop() -> None:
    if CharacterQualityPipeline is None:
        pytest.fail("Task 2 Draft/Review/Revise 流水线尚未实现")
    generator = ScriptedGenerator(
        [draft_json("候选回复", "draft-1"), "不是 JSON"]
    )

    run = CharacterQualityPipeline(generator).run(
        scenario=SCENARIO,
        candidate_count=1,
    )

    assert run.approved == []
    assert run.revision_count == 0
    assert run.review_count == 0
    assert run.rejections[0]["reasons"] == ["invalid_review"]
    assert len(generator.calls) == 2


def test_pipeline_does_not_approve_candidate_without_explicit_id() -> None:
    if CharacterQualityPipeline is None:
        pytest.fail("Task 2 Draft/Review/Revise 流水线尚未实现")
    generator = ScriptedGenerator(
        [draft_json("候选回复", "draft-1"), review_json()]
    )

    run = CharacterQualityPipeline(generator).run(
        scenario=SCENARIO,
        candidate_count=1,
    )

    assert run.approved == []
    assert run.rejections == []


def test_pipeline_draft_instruction_requires_npc_reply_field() -> None:
    generator = ScriptedGenerator(
        [draft_json("候选回复", "draft-1"), review_json()]
    )

    CharacterQualityPipeline(generator).run(
        scenario=SCENARIO,
        candidate_count=1,
    )

    assert "npcReply" in generator.calls[0][0]["content"]


def test_pipeline_copies_affection_metadata_into_candidate_defaults() -> None:
    generator = ScriptedGenerator(
        [draft_json("可以。你挑个时间。", "draft-initiative"), review_json()]
    )
    scenario = {
        **SCENARIO,
        "initiativeExpectation": "proactive",
        "initiativeKind": "specific_plan",
    }

    run = CharacterQualityPipeline(generator).run(
        scenario=scenario,
        candidate_count=1,
    )

    assert run.candidates[0]["initiativeExpectation"] == "proactive"
    assert run.candidates[0]["initiativeKind"] == "specific_plan"


def test_pipeline_review_instruction_lists_fixed_dimensions_and_score_range() -> None:
    generator = ScriptedGenerator(
        [draft_json("候选回复", "draft-1"), review_json()]
    )

    CharacterQualityPipeline(generator).run(
        scenario=SCENARIO,
        candidate_count=1,
    )

    instruction = generator.calls[1][0]["content"]
    assert all(dimension in instruction for dimension in REVIEW_DIMENSIONS)
    assert "0～2" in instruction
    assert "hardErrors" in instruction
    assert "tags" in instruction


def test_pipeline_rejects_when_the_revision_itself_is_invalid() -> None:
    # 首审不通过 → 修订一次；修订输出非法时该候选直接进拒绝列表，不再复审。
    generator = ScriptedGenerator(
        [
            draft_json("感谢你的关心。综合来看，鸡舍运营情况总体良好。", "draft-1"),
            review_json("too_formal"),
            "不是 JSON",
        ]
    )

    run = CharacterQualityPipeline(generator).run(
        scenario=SCENARIO,
        candidate_count=1,
    )

    assert run.approved == []
    assert run.revision_count == 0
    assert run.review_count == 1
    assert [item["exampleId"] for item in run.rejections] == ["draft-1"]
    assert run.rejections[0]["reasons"]


def test_pipeline_rejects_when_the_revision_cannot_be_reviewed() -> None:
    generator = ScriptedGenerator(
        [
            draft_json("感谢你的关心。综合来看，鸡舍运营情况总体良好。", "draft-1"),
            review_json("too_formal"),
            revised_json("还行。没着火，就算顺利。", "draft-1"),
            "不是 JSON",
        ]
    )

    run = CharacterQualityPipeline(generator).run(
        scenario=SCENARIO,
        candidate_count=1,
    )

    assert run.approved == []
    # 修订本身是合法的，所以它进了 revised；但复审读不出来，不能批准。
    assert run.revision_count == 1
    assert [item["exampleId"] for item in run.rejections] == ["draft-1"]


def test_pipeline_rejects_when_the_revised_text_still_fails_review() -> None:
    generator = ScriptedGenerator(
        [
            draft_json("感谢你的关心。综合来看，鸡舍运营情况总体良好。", "draft-1"),
            review_json("too_formal"),
            revised_json("还是不对劲的一句话。", "draft-1"),
            # 用与首审相同的失败 tag：并非任意 tag 都会让 review_passes 判负。
            review_json("too_formal"),
        ]
    )

    run = CharacterQualityPipeline(generator).run(
        scenario=SCENARIO,
        candidate_count=1,
    )

    assert run.approved == []
    assert run.revision_count == 1
    assert run.review_count == 2
    assert [item["exampleId"] for item in run.rejections] == ["draft-1"]
