"""`story_state._string_list` 的元素规则（B9 第三处"同概念多实现"）。

2026-09-20 统一。原实现逐项 `str(item).strip()`，把**任何**东西字符串化后保留：

    _string_list(b"ab")        -> ['97', '98']      ← 迭代 bytes 得到整数
    _string_list([{"k": 1}])   -> ["{'k': 1}"]      ← 字典被字符串化
    _string_list({"a": 1})     -> ['a']             ← Mapping 被迭代出 key

这些值"看着正常"（都是非空字符串），却与源数据毫无关系——**一旦混进事件匹配或
状态判断，就会静默产生错误的匹配**。

现在元素规则与 `behavior_quality._string_list` 对齐：只接受真正的字符串，
`bytes`／`bytearray`／`Mapping` 整体拒绝，非字符串项直接丢弃。

**唯一的刻意差异**：返回类型仍是 `list[str]`（7 个调用点里有 4 个用
`values.extend(...)`，`None` 会让它们 TypeError），所以用 `[]` 表示"没有"，
而不是像 `behavior_quality` 版那样用 `None` 表示"格式不对"。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.behavior_quality import _string_list as _other
from stardew_ai_bridge.story_state import _string_list


# --- 修掉的旧行为 -----------------------------------------------------------


@pytest.mark.parametrize("value", [b"ab", bytearray(b"ab")])
def test_bytes_are_rejected_instead_of_becoming_digit_strings(value: object) -> None:
    # 旧实现会给出 ['97', '98']——非空、看着正常，实际全错。
    assert _string_list(value) == []


@pytest.mark.parametrize("value", [{"a": 1}, {"npcId": "Shane"}])
def test_mappings_are_rejected_instead_of_yielding_their_keys(value: object) -> None:
    assert _string_list(value) == []


def test_non_string_items_are_dropped_not_stringified() -> None:
    assert _string_list(["x", 3]) == ["x"]
    assert _string_list([{"k": 1}]) == []
    assert _string_list([None, "y"]) == ["y"]


@pytest.mark.parametrize("value", [42, 3.5, None, True, object()])
def test_other_scalars_yield_nothing(value: object) -> None:
    assert _string_list(value) == []


# --- 保留的行为 -------------------------------------------------------------


def test_a_plain_string_becomes_a_single_item() -> None:
    assert _string_list("  Shane  ") == ["Shane"]


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_string_yields_nothing(value: str) -> None:
    assert _string_list(value) == []


def test_items_are_trimmed_and_deduplicated_in_order() -> None:
    assert _string_list([" a ", "b", "a", "  "]) == ["a", "b"]


def test_a_tuple_works_too() -> None:
    assert _string_list(("x", "y")) == ["x", "y"]


def test_the_return_type_stays_a_list() -> None:
    # 调用点用 `values.extend(...)`，返回 None 会让它们 TypeError。
    for value in ["x", ["x"], b"ab", None, 42]:
        assert isinstance(_string_list(value), list)


# --- 跨实现对照 -------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["a", "  ", ["a", "b"], ["a", "a"], [], ["x", 3], b"ab", bytearray(b"ab"), {"k": 1}, None, 42],
)
def test_it_agrees_with_the_behavior_quality_version(value: object) -> None:
    # 两版用不同的“空”约定（[] vs None），但**元素规则必须一致**。
    mine = _string_list(value)
    theirs = _other(value)

    assert mine == (theirs if theirs is not None else [])
