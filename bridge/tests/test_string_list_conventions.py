"""两个同名 `_string_list` 的约定（B9 第三处"同概念多实现"，**已于第 136 项统一**）。

统一前两者实质不同：

- `story_state._string_list`：**总是**返回 list；非字符串项被 `str()` 转换后**保留**；
  Mapping 迭代出**键**、bytes 迭代出**整数**——会静默产出看着正常、其实错的数据
  （`b"ab"` → `["97", "98"]`，`[{"k": 1}]` → `["{'k': 1}"]`）。
- `behavior_quality._string_list`：**格式不对时返回 `None`**；非字符串项**丢弃**；
  **排除** Mapping 与 bytes。

**现在元素规则已一致**：只接受真正的字符串，`bytes`／`bytearray`／`Mapping` 整体拒绝，
非字符串项直接丢弃。

**刻意保留的唯一差异是"空约定"**：`story_state` 版返回 `list[str]`（7 个调用点里有 4 个
用 `values.extend(...)`，`None` 会让它们 TypeError），所以用 `[]` 表示"没有"；
`behavior_quality` 版返回 `list[str] | None`，用 `None` 表示"这个字段不是列表"。

本文件因此从"差异说明"改写成"**已统一 + 空约定差异**"。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.behavior_quality import (
    _string_list as behavior_string_list,
    _text as behavior_text,
)
from stardew_ai_bridge.story_state import _string_list as story_string_list


# --- behavior_quality 的约定 -------------------------------------------------


def test_behavior_string_list_returns_none_for_wrong_shapes() -> None:
    # 用 None 表示“这个字段不是列表”，与“空列表”区分开。
    assert behavior_string_list(None) is None
    assert behavior_string_list(42) is None
    assert behavior_string_list({"k": "v"}) is None  # Mapping 不算列表
    assert behavior_string_list(b"ab") is None  # bytes 也不算


def test_behavior_string_list_drops_non_string_items() -> None:
    assert behavior_string_list(["a", 1, None, "  ", "a"]) == ["a"]


def test_behavior_string_list_wraps_and_deduplicates_strings() -> None:
    assert behavior_string_list("  a  ") == ["a"]
    # 空字符串是“合法的空内容”，返回空列表而不是 None
    assert behavior_string_list("") == []
    assert behavior_string_list(["b", "a", "b"]) == ["b", "a"]
    assert behavior_string_list(("x",)) == ["x"]


def test_behavior_text_helper_returns_empty_string_for_non_strings() -> None:
    assert behavior_text("  x  ") == "x"
    assert behavior_text(None) == ""
    assert behavior_text(42) == ""


# --- story_state 的约定（元素规则已对齐）------------------------------------


def test_story_string_list_always_returns_a_list() -> None:
    # 这是与另一版**唯一**的差别：用 [] 而不是 None。
    assert story_string_list(None) == []
    assert story_string_list(42) == []


def test_story_string_list_now_drops_non_string_items() -> None:
    # 统一前是 ["a", "1", "None"]；现在与 behavior_quality 一致。
    assert story_string_list(["a", 1, None, "  ", "a"]) == ["a"]


def test_story_string_list_rejects_mappings_and_bytes() -> None:
    # 统一前分别是 ["k"] 与 ["97", "98"]——看着正常，其实与源数据无关。
    assert story_string_list({"k": "v"}) == []
    assert story_string_list(b"ab") == []
    assert story_string_list(bytearray(b"ab")) == []


# --- 两版的一致性与唯一差异 -------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        42,
        {"k": "v"},
        b"ab",
        bytearray(b"ab"),
        ["a", 1],
        [{"k": 1}],
        "x",
        "  ",
        [],
        "",
        ("x", "y"),
    ],
)
def test_the_two_helpers_only_differ_in_their_empty_convention(value: object) -> None:
    # 元素规则已统一；差别只在“没有”用 [] 还是用 None。
    mine = story_string_list(value)
    theirs = behavior_string_list(value)

    assert mine == (theirs if theirs is not None else [])


def test_the_empty_convention_difference_is_real_and_intentional() -> None:
    # 钉住这个差异本身：它是有意的（调用方用 extend），不是漏改。
    assert story_string_list(None) == []
    assert behavior_string_list(None) is None
