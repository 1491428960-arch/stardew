"""`diagnose_relationship_quality` 的关系世界观边界诊断。

按**缺失行数**排序挑出来的（缺 8/33，比例高）。docstring 写着“按当前 NPC 的视角检查
关系世界观边界，**不把情绪本身判为错误**”——所以要测的重点不是“会不会报错”，而是
**它只在越界时报，而不是在涉及关系时就报**。

它按 `turn.relationship_focus` 分七种，其中五种会产标签、两种（`direct_disclosure`
与 `jealousy`）**刻意不产**——后者正是“不把情绪本身判为错误”的落点，所以下面有一条
负对照专门钉它。
"""

from __future__ import annotations

import dataclasses

import pytest

from stardew_ai_bridge.character_quality_eval import (
    DEFAULT_CASES,
    _RELATIONSHIP_FOCUS_VALUES,
    diagnose_relationship_quality,
    relationship_turn_metadata,
)

_BASE = DEFAULT_CASES[0]
_WORLD = {"views": [{"visibility": "unknown"}]}


def _turn(focus: str):
    return dataclasses.replace(_BASE.dialogue_turns()[0], relationship_focus=focus)


def _case(world: object = _WORLD):
    return dataclasses.replace(_BASE, relationship_world=world)


def _tags(focus: str, reply: str, world: object = _WORLD) -> list[str]:
    result = diagnose_relationship_quality(_case(world), _turn(focus), reply)
    return list(result["tags"])  # type: ignore[arg-type]


# --- 三个早退 ---------------------------------------------------------------


def test_no_relationship_world_yields_no_tags() -> None:
    assert diagnose_relationship_quality(_case(None), _turn("unknown_view"), "我知道你在交往。") == {"tags": []}


def test_a_missing_turn_yields_no_tags() -> None:
    assert diagnose_relationship_quality(_case(), None, "我知道你在交往。") == {"tags": []}


def test_a_turn_without_focus_yields_no_tags() -> None:
    assert _tags("", "我知道你在交往。") == []


def test_every_documented_focus_is_accepted() -> None:
    # 七个值都该能走通而不抛异常。
    assert set(_RELATIONSHIP_FOCUS_VALUES) == {
        "direct_disclosure",
        "jealousy",
        "mediation",
        "public_wedding",
        "recovery",
        "suspected_view",
        "unknown_view",
    }
    for focus in _RELATIONSHIP_FOCUS_VALUES:
        diagnose_relationship_quality(_case(), _turn(focus), "随便一句回复。")


# --- 把“未知”当成“已知” -------------------------------------------------------


def test_unknown_view_asserted_with_certainty_is_flagged() -> None:
    assert _tags("unknown_view", "我知道你在和艾米丽交往。") == ["unknown_view_misread"]


@pytest.mark.parametrize(
    "reply",
    [
        "我好像听说过，但不太确定。",
        "不知道，别猜了，问当事人吧。",
    ],
)
def test_unknown_view_with_uncertainty_is_not_flagged(reply: str) -> None:
    # 带不确定词就不算“当成已知”——这正是 docstring 说的“不把情绪/口吻本身判为错误”。
    assert _tags("unknown_view", reply) == []


def test_unknown_view_without_relation_markers_is_not_flagged() -> None:
    assert _tags("unknown_view", "我知道今天天气不错。") == []


def test_suspected_view_asserted_with_certainty_is_flagged() -> None:
    assert _tags("suspected_view", "我知道你在和艾米丽交往。") == ["suspected_as_fact"]


def test_suspected_view_with_uncertainty_is_not_flagged() -> None:
    assert _tags("suspected_view", "我好像听说过这件事。") == []


# --- 公开婚礼 ---------------------------------------------------------------


def test_a_public_wedding_turn_without_wedding_words_is_flagged() -> None:
    # 该场景要求提到“婚礼/结婚/公开”，没提就是可见性没交代。
    assert _tags("public_wedding", "今天天气不错。") == ["public_wedding_visibility"]


@pytest.mark.parametrize("reply", ["我们下个月办婚礼。", "我们已经结婚了。", "这件事是公开的。"])
def test_public_wedding_with_wedding_words_is_not_flagged(reply: str) -> None:
    assert _tags("public_wedding", reply) == []


# --- 调解 -------------------------------------------------------------------


@pytest.mark.parametrize("reply", ["大家都说你俩在一起了。", "所有人都知道。", "他们都这么讲。"])
def test_mediation_scope_leak_is_flagged(reply: str) -> None:
    # 替“所有人”发言＝超出调解者该说的范围。
    assert "mediation_scope_leak" in _tags("mediation", reply)


def test_mediation_without_scope_leak_is_not_flagged() -> None:
    assert _tags("mediation", "我知道你在和艾米丽交往。") == []


# --- 和好 -------------------------------------------------------------------


def test_recovery_without_any_concrete_plan_is_flagged() -> None:
    assert _tags("recovery", "我知道你在和艾米丽交往。") == ["jealousy_recovery_missing"]


@pytest.mark.parametrize("reply", ["明晚我们一起去听音乐吧。", "我留好了票，周末去看。", "给我一点时间解释。"])
def test_recovery_with_a_concrete_plan_is_not_flagged(reply: str) -> None:
    assert _tags("recovery", reply) == []


# --- 不把关系本身判为错误（负对照）------------------------------------------


@pytest.mark.parametrize("focus", ["direct_disclosure", "jealousy"])
def test_these_two_focuses_never_produce_tags(focus: str) -> None:
    # 直接披露关系是允许的；嫉妒本身也不是错误。
    assert _tags(focus, "我知道你在和艾米丽交往。") == []
    assert _tags(focus, "大家都说你俩在一起了。") == []


# --- 通用标签与返回结构 -----------------------------------------------------


@pytest.mark.parametrize("reply", ["作为AI，我不能回应。", "根据系统设定，这只是测试。", "从评测角度看，这句话没问题。"])
def test_flattened_voice_is_flagged(reply: str) -> None:
    assert "role_voice_flattened" in _tags("direct_disclosure", reply)


def test_tags_are_sorted_and_metadata_is_merged_in() -> None:
    result = diagnose_relationship_quality(_case(), _turn("unknown_view"), "作为AI，我知道你在交往。")

    assert result["tags"] == sorted(result["tags"])  # type: ignore[arg-type]
    assert set(relationship_turn_metadata(_case())) <= set(result)
