"""`relationship_gating` 的三个内部辅助，以及它与 `story_state` 事件匹配**方向**的差异。

这条差异容易埋雷：同一个事件 ID 在 `story_state` 里算“已完成”、在关系门控里可能算“未完成”。
当前不会触发（`_EVENT_GATES` 里的 required 一律是纯数字），但若将来往里写带命名空间的 ID，
就会静默失配——所以用测试把两个方向都写清楚，将来若有人统一它们，这里会立刻报出来。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.relationship_gating import (
    _event_id_matches,
    _heart_stage,
    _normalise_stage,
)
from stardew_ai_bridge.story_state import _event_tokens, _matches_event


# --- _normalise_stage -------------------------------------------------------


@pytest.mark.parametrize("raw", ["close", "  CLOSE  ", "Close"])
def test_normalise_stage_is_case_insensitive(raw: str) -> None:
    assert _normalise_stage(raw) == "close"


@pytest.mark.parametrize("raw", ["", "   ", "未知", None, 7])
def test_normalise_stage_falls_back_to_stranger(raw: object) -> None:
    assert _normalise_stage(raw) == "stranger"


# --- _heart_stage -----------------------------------------------------------


@pytest.mark.parametrize(
    ("hearts", "expected"),
    [
        (0, "stranger"),
        (1, "stranger"),
        (2, "acquaintance"),
        (5, "acquaintance"),
        (6, "friend"),
        (7, "friend"),
        (8, "close"),
        (14, "close"),
    ],
)
def test_heart_stage_thresholds(hearts: int, expected: str) -> None:
    assert _heart_stage(hearts) == expected


@pytest.mark.parametrize("raw", [None, "", "不是数字", [], {}])
def test_heart_stage_returns_none_when_it_cannot_tell(raw: object) -> None:
    # 返回 None 表示“无从判断”，调用方据此跳过事件锁——**不能**默认成 stranger。
    assert _heart_stage(raw) is None


def test_heart_stage_accepts_numeric_strings() -> None:
    assert _heart_stage("8") == "close"


# --- _event_id_matches ------------------------------------------------------


def test_event_id_matches_exact_and_namespaced_completed_values() -> None:
    assert _event_id_matches("56", {"56"}) is True
    assert _event_id_matches("56", {"mod.pack:56"}) is True  # 基线带前缀 → 命中
    assert _event_id_matches("  EventA  ", {"eventa"}) is True  # 空白与大小写不敏感
    assert _event_id_matches("56", {"57"}) is False


def test_event_id_matches_does_not_split_a_namespaced_required_id() -> None:
    # 与 story_state 的方向**相反**：这里不会把候选自身的前缀拆掉。
    assert _event_id_matches("mod.pack:56", {"56"}) is False


def test_the_two_event_matchers_disagree_only_on_a_namespaced_candidate() -> None:
    # 把差异固化成一条可执行说明：两边都容忍前缀，但方向不同。
    # ① 基线是短名、候选带前缀：只有 story_state 认。
    assert _matches_event("mod.pack:56", _event_tokens("56")) is True
    assert _event_id_matches("mod.pack:56", {"56"}) is False

    # ② 基线带前缀、候选是短名：两边都认。
    assert _matches_event("56", _event_tokens("mod.pack:56")) is True
    assert _event_id_matches("56", {"mod.pack:56"}) is True
