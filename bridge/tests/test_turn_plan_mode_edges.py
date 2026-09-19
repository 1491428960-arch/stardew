"""`_turn_plan_mode` 的四层回退。

按“缺失行数”排序挑出来的（缺 7/17）。它是评测案例的“**回合窄目标**”读取器：
新案例直接写 `turnPlanMode`，旧案例可能只有 `turn_plan_mode`，再旧的把 mode 藏在
`turnPlan` 里——所以要兼容三种形态，且**两种载体**（Mapping 与对象）各来一遍。

docstring 写明“旧案例没有该字段时返回空字符串”，这条契约也在下面钉住。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stardew_ai_bridge.character_quality_eval import (
    DEFAULT_CASES,
    _TURN_PLAN_MODES,
    _turn_plan_mode,
)

_KNOWN = sorted(_TURN_PLAN_MODES)


def test_all_documented_modes_are_accepted() -> None:
    # 六种窄目标都该被认出来，而不是只认前几个。
    assert len(_KNOWN) >= 6
    for mode in _KNOWN:
        assert _turn_plan_mode({"turnPlanMode": mode}) == mode


def test_none_yields_an_empty_string() -> None:
    assert _turn_plan_mode(None) == ""


# --- 三种形态（Mapping 载体）-----------------------------------------------


def test_camel_case_field_is_read_first() -> None:
    assert _turn_plan_mode({"turnPlanMode": _KNOWN[0]}) == _KNOWN[0]


def test_snake_case_field_is_the_fallback() -> None:
    assert _turn_plan_mode({"turn_plan_mode": _KNOWN[1]}) == _KNOWN[1]


def test_nested_turn_plan_mode_is_the_last_resort() -> None:
    # 更旧的案例把 mode 塞在 turnPlan 里。
    assert _turn_plan_mode({"turnPlan": {"mode": _KNOWN[0]}}) == _KNOWN[0]


def test_an_empty_primary_field_falls_through_to_the_nested_one() -> None:
    payload = {"turnPlanMode": "", "turnPlan": {"mode": _KNOWN[2]}}

    assert _turn_plan_mode(payload) == _KNOWN[2]


# --- 两种载体（对象）--------------------------------------------------------


def test_an_object_attribute_is_read() -> None:
    turn = SimpleNamespace(turn_plan_mode=_KNOWN[0])

    assert _turn_plan_mode(turn) == _KNOWN[0]


def test_an_object_falls_back_to_its_nested_plan() -> None:
    turn = SimpleNamespace(turn_plan_mode="", turn_plan={"mode": _KNOWN[3]})

    assert _turn_plan_mode(turn) == _KNOWN[3]


def test_an_object_without_the_field_yields_an_empty_string() -> None:
    # 老案例对象没有这两个字段，属于 docstring 承诺的“返回空字符串”。
    assert _turn_plan_mode(SimpleNamespace()) == ""


# --- 归一化与拒绝 -----------------------------------------------------------


def test_the_value_is_trimmed_and_case_folded() -> None:
    assert _turn_plan_mode({"turnPlanMode": f"  {_KNOWN[0].upper()}  "}) == _KNOWN[0]


@pytest.mark.parametrize("value", ["nonsense", "", "  ", 3, None, ["answer_only"]])
def test_unknown_or_non_string_values_are_rejected(value: object) -> None:
    assert _turn_plan_mode({"turnPlanMode": value}) == ""


@pytest.mark.parametrize("value", ["x", 3, ["a"]])
def test_a_non_mapping_turn_plan_is_ignored(value: object) -> None:
    assert _turn_plan_mode({"turnPlan": value}) == ""


def test_a_shipped_case_without_the_field_reads_as_empty() -> None:
    # 真实案例里确实有这种老数据；它必须安静地返回空，而不是抛异常。
    assert _turn_plan_mode(DEFAULT_CASES[0].dialogue_turns()[0]) == ""
