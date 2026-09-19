"""`story_state` 的内部辅助：事件 token 化、事件匹配、列表规范化与事件规则应用。

`story_state.py` 负责把“已完成剧情事件”折算成可披露状态；原有 5 条测试都是端到端行为契约
（阶段信任、事件解锁、坏心情不抹除信任……），但**7 个内部辅助函数没有直接测试**，
而它们决定了“哪些事件算已完成”——匹配语义一旦偏掉，剧情状态判断会整体走样。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.story_state import (
    _apply_event_rule,
    _event_ids,
    _event_state_ids,
    _event_tokens,
    _matches_event,
    _normalise_stage,
    _string_list,
)


# --- _normalise_stage -------------------------------------------------------


@pytest.mark.parametrize("raw", ["close", "  CLOSE  ", "Close"])
def test_normalise_stage_accepts_known_stages_case_insensitively(raw: str) -> None:
    assert _normalise_stage(raw) == "close"


@pytest.mark.parametrize("raw", ["", "   ", "不存在的阶段", None, 42])
def test_normalise_stage_falls_back_to_stranger(raw: object) -> None:
    assert _normalise_stage(raw) == "stranger"


# --- _event_tokens ----------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   "])
def test_event_tokens_is_empty_for_blank_values(raw: object) -> None:
    assert _event_tokens(raw) == set()


def test_event_tokens_stringifies_none_instead_of_treating_it_as_blank() -> None:
    # 容易误解的一点（我第一版就写错了）：None 会被 `str()` 成 "None" → {"none"}，
    # **不是**空集。生产路径不会传 None（上游 `_string_list` 已过滤空白），所以不算缺陷；
    # 但若将来有代码直接拿原始字段调它，就可能与字面事件名 "none" 误匹配。
    assert _event_tokens(None) == {"none"}


def test_event_tokens_lowercases_and_strips() -> None:
    assert "eventa" in _event_tokens("  EventA  ")


def test_event_tokens_also_emits_the_segment_after_the_last_colon() -> None:
    # 命名空间前缀不该让同一个事件匹配不上：Mod.Pack:EventX 也要产出 eventx。
    tokens = _event_tokens("Mod.Pack:EventX")

    assert "mod.pack:eventx" in tokens
    assert "eventx" in tokens


def test_event_tokens_never_returns_blank_tokens() -> None:
    assert all(token for token in _event_tokens(":::"))


# --- _matches_event ---------------------------------------------------------


def test_matches_event_compares_against_the_completed_token_set() -> None:
    completed = _event_tokens("EventA")

    assert _matches_event("EventA", completed) is True
    assert _matches_event("eventa", completed) is True  # 大小写不敏感
    assert _matches_event("EventB", completed) is False


def test_matches_event_is_false_for_a_blank_candidate() -> None:
    assert _matches_event("", _event_tokens("EventA")) is False
    assert _matches_event("   ", _event_tokens("EventA")) is False


def test_matches_event_ignores_the_namespace_prefix() -> None:
    # 已完成集合里存的是短名时，带前缀的候选同样要命中。
    assert _matches_event("Mod.Pack:EventX", _event_tokens("EventX")) is True


# --- _string_list -----------------------------------------------------------


def test_string_list_wraps_a_single_string() -> None:
    assert _string_list("  a  ") == ["a"]
    assert _string_list("   ") == []
    assert _string_list("") == []


def test_string_list_rejects_non_iterables() -> None:
    assert _string_list(None) == []
    assert _string_list(42) == []


def test_string_list_deduplicates_and_keeps_order() -> None:
    assert _string_list(["b", "a", "b", " a "]) == ["b", "a"]


def test_string_list_drops_non_string_items() -> None:
    # 第 136 项统一后：非字符串项被**丢弃**，不再 str() 保留（旧断言是 ["1", "None", "x"]）。
    assert _string_list([1, None, "  ", "x"]) == ["x"]


# --- _event_ids / _event_state_ids -----------------------------------------


def test_event_ids_collects_from_all_supported_keys_and_deduplicates() -> None:
    ids = _event_ids(
        {
            "eventId": "A",
            "requiredEventId": ["B", "A"],
            "sourceKey": "C",
            "eventIds": "D",
        }
    )

    assert ids == ["A", "B", "C", "D"]


def test_event_state_ids_collects_from_all_supported_keys_and_deduplicates() -> None:
    ids = _event_state_ids(
        {
            "storyStateId": "s1",
            "stateId": ["s2", "s1"],
            "completedStoryState": "s3",
            "completedStoryStates": ["s4"],
        }
    )

    assert ids == ["s1", "s2", "s3", "s4"]


def test_event_id_helpers_tolerate_missing_and_blank_keys() -> None:
    assert _event_ids({}) == []
    assert _event_state_ids({}) == []
    assert _event_ids({"eventId": "   "}) == []


# --- _apply_event_rule -----------------------------------------------------


def _fresh_state() -> dict[str, object]:
    return {"completedStoryStates": [], "allowedDisclosure": [], "initiativeBias": ""}


def test_apply_event_rule_does_nothing_until_the_event_is_completed() -> None:
    state = _fresh_state()

    _apply_event_rule(
        state,
        {"eventId": "A", "completedStoryStates": ["s1"], "allowedDisclosure": ["d1"]},
        completed=set(),
    )

    assert state["completedStoryStates"] == []
    assert state["allowedDisclosure"] == []


def test_apply_event_rule_accepts_an_explicit_completed_status() -> None:
    state = _fresh_state()

    _apply_event_rule(
        state,
        {
            "eventId": "A",
            "status": "  Completed  ",
            "completedStoryStates": ["s1"],
            "allowedDisclosure": "d1",
        },
        completed=set(),
    )

    assert state["completedStoryStates"] == ["s1"]
    assert state["allowedDisclosure"] == ["d1"]


def test_apply_event_rule_matches_by_event_id_when_status_is_absent() -> None:
    state = _fresh_state()

    _apply_event_rule(
        state,
        {"eventId": "EventA", "completedStoryStates": ["s1"]},
        completed=_event_tokens("EventA"),
    )

    assert state["completedStoryStates"] == ["s1"]


def test_apply_event_rule_is_idempotent() -> None:
    state = _fresh_state()
    event = {
        "eventId": "EventA",
        "status": "completed",
        "completedStoryStates": ["s1"],
        "allowedDisclosure": ["d1"],
        "initiativeBias": "proactive",
    }

    _apply_event_rule(state, event, completed=set())
    _apply_event_rule(state, event, completed=set())

    assert state["completedStoryStates"] == ["s1"]
    assert state["allowedDisclosure"] == ["d1"]
    assert state["initiativeBias"] == "proactive"


def test_apply_event_rule_leaves_initiative_untouched_when_blank() -> None:
    state = _fresh_state()
    state["initiativeBias"] = "keep-me"

    _apply_event_rule(
        state,
        {"eventId": "A", "status": "completed", "initiativeBias": "   "},
        completed=set(),
    )

    assert state["initiativeBias"] == "keep-me"
