"""`_text`、非负整数守门、阶段归一化的**跨实现对照**。

这里是“同概念多实现”的对照测试：与其在两个文件里各写一遍同样的边界断言（那只是**看起来**
覆盖更多），不如**显式断言两个实现的关系**——要么必须一致，要么按各自的设计**刻意不同**。
一次独立复核正是这样建议的。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.behavior_quality import _text as behavior_text
from stardew_ai_bridge.prompts import _text as prompt_text
from stardew_ai_bridge.providers import _non_negative_count
from stardew_ai_bridge.quality_results import (
    _non_negative_int,
    _non_negative_number,
    _text as result_text,
)
from stardew_ai_bridge.relationship_gating import _normalise_stage as gating_normalise
from stardew_ai_bridge.story_state import _normalise_stage as story_normalise


# --- 三个 _text：后两个一致，第一个刻意用 None 区分“字段缺失” ----------------


@pytest.mark.parametrize("value", ["  x  ", "x"])
def test_all_three_text_helpers_trim_strings(value: str) -> None:
    assert behavior_text(value) == prompt_text(value) == result_text(value) == "x"


@pytest.mark.parametrize("value", ["", "   ", None, 42, ["x"]])
def test_results_text_uses_none_where_the_others_use_an_empty_string(value: object) -> None:
    # 这是差异本身：results 侧要区分“字段缺失”与“空文本”，另两处不需要。
    assert result_text(value) is None
    assert behavior_text(value) == ""
    assert prompt_text(value) == ""


def test_only_prompt_text_truncates_by_default() -> None:
    long_text = "字" * 300

    assert len(prompt_text(long_text)) == 240  # 默认 limit
    assert len(prompt_text(long_text, limit=10)) == 10
    assert result_text(long_text) == long_text
    assert behavior_text(long_text) == long_text


# --- 非负整数守门：两个实现必须一致 -----------------------------------------


@pytest.mark.parametrize("value", [True, False, 0, 5, -1, "10", None, [], {}, 1.5])
def test_the_two_non_negative_guards_agree(value: object) -> None:
    # 与其在两个文件里各写一遍同样的边界，不如直接断言“两者一致”。
    assert _non_negative_count(value) == _non_negative_int(value)


def test_only_the_number_guard_accepts_floats() -> None:
    assert _non_negative_count(1.5) is None
    assert _non_negative_int(1.5) is None
    assert _non_negative_number(1.5) == 1.5
    assert _non_negative_number(-0.5) is None


# --- 阶段归一化：两个实现必须一致 -------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["close", "  CLOSE  ", "", "   ", "未知", None, 7, "married", "parent", "stranger"],
)
def test_the_two_stage_normalisers_agree(value: object) -> None:
    # `story_state` 与 `relationship_gating` 各有一个私有 `_normalise_stage`，
    # 服务不同判定路径，但“未知阶段回落 stranger”的语义必须一致。
    assert story_normalise(value) == gating_normalise(value)


@pytest.mark.parametrize("value", ["close", "married", "parent", "stranger"])
def test_known_stages_survive_normalisation(value: str) -> None:
    assert story_normalise(value) == value
    assert gating_normalise(value) == value
