"""`relationship_gating` 的三个内部辅助，以及它与 `story_state` 事件匹配的**统一契约**。

这里原本钉着一条「方向不同」的差异（同一个事件 ID 在 `story_state` 里算“已完成”、
在关系门控里可能算“未完成”），并写明“将来若有人统一它们，这里会立刻报出来”。

2026-09-20（语义层审计 #28）**统一已经发生**：两处都改为调用
`relationship_gating.game_event_completed`，命名空间前缀**两个方向都认**。
所以下面改成钉新契约——`required="mod.pack:56"` + `completed={"56"}` 从此也命中。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.relationship_gating import (
    _event_id_matches,
    _heart_stage,
    _normalise_stage,
    game_event_completed,
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


def test_event_id_matches_also_splits_a_namespaced_required_id() -> None:
    """#28 统一后：候选自身带前缀也命中基线，**不再**是单向的。"""
    assert _event_id_matches("mod.pack:56", {"56"}) is True
    assert _event_id_matches("mod.pack:56", {"mod.pack:56"}) is True
    assert _event_id_matches("mod.pack:56", {"57"}) is False


def test_the_two_event_matchers_agree_in_both_directions() -> None:
    """两个入口对同一组输入必须给出同一答案（它们现在共用一个实现）。"""
    assert _matches_event("mod.pack:56", _event_tokens("56")) is True
    assert _event_id_matches("mod.pack:56", {"56"}) is True

    assert _matches_event("56", _event_tokens("mod.pack:56")) is True
    assert _event_id_matches("56", {"mod.pack:56"}) is True

    # 无关事件仍然是 False，两个方向都别放宽。
    assert _matches_event("57", _event_tokens("mod.pack:56")) is False
    assert _event_id_matches("57", {"mod.pack:56"}) is False


def test_the_shared_implementation_is_what_the_public_name_resolves_to() -> None:
    """`game_event_completed` 是唯一实现：`story_state` 侧的入口也认它。"""

    assert game_event_completed("56", {"flashshifter.SVE:56"}) is True
    assert game_event_completed("flashshifter.SVE:56", {"56"}) is True
