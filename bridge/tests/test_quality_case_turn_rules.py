"""`validate_quality_cases` 的**逐回合**校验（补第 113 项漏掉的部分）。

第 113 项补了这个函数的**案例级**规则（枚举、`relationship_world` 结构、露骨调情两道门槛），
但**逐回合循环里的 7 条规则**当时没覆盖。它们管的是“回合的主动性、关系焦点与关系演员”：

- **主动性**：期望值与种类的枚举，以及“**期望不是 `none` 就不能给 `none` 种类**”——
  除非是 `adaptive` + `responsive` + `answer_plus_detail`/`answer_only` 这组特例；
- **关系焦点**：枚举，且**一旦声明了焦点就必须给出 `relationshipWorld`**；
- **关系演员**：只能是空／`player`／`npc`，且**演员是 `player` 时必须给出目标 NPC**。

判错的后果很具体：**评测跑完才发现案例本身自相矛盾**（例如声明了焦点却没有世界观数据），
而那时 token 已经花掉了。
"""

from __future__ import annotations

import dataclasses

import pytest

from stardew_ai_bridge.character_quality_eval import (
    DEFAULT_CASES,
    validate_quality_cases,
)

_BASE = DEFAULT_CASES[0]
_TURN = _BASE.dialogue_turns()[0]


def _case(**turn_overrides: object):
    """把基础案例的第一个回合改掉，其余保持不动。"""
    turn = dataclasses.replace(_TURN, **turn_overrides)
    return dataclasses.replace(_BASE, turns=(turn,))


def _errors(**turn_overrides: object) -> list[str]:
    return validate_quality_cases([_case(**turn_overrides)])


def _has(errors: list[str], prefix: str) -> bool:
    return any(error.startswith(prefix) for error in errors)


def test_the_untouched_base_case_is_clean() -> None:
    # 基线：不改任何字段时不该有逐回合错误。
    assert _errors() == []


# --- 主动性枚举 -------------------------------------------------------------


def test_an_unknown_initiative_expectation_is_reported() -> None:
    assert _has(_errors(initiative_expectation="nonsense"), "initiative_expectation:")


def test_an_unknown_initiative_kind_is_reported() -> None:
    assert _has(_errors(initiative_kind="nonsense"), "initiative_kind:")


# --- “期望不是 none，就得给种类” ---------------------------------------------


def test_an_expectation_without_a_kind_is_reported() -> None:
    errors = _errors(initiative_expectation="proactive", initiative_kind="none")

    assert _has(errors, "initiative_kind_required:")


def test_expectation_none_needs_no_kind() -> None:
    # 第一个条件不成立，所以不报。
    assert _errors(initiative_expectation="none", initiative_kind="none") == []


def test_a_kind_is_fine_without_an_expectation() -> None:
    # 用真实的 kind 值（`care_action` 在枚举里——我最初写的 `question` 不在，因此被报了错）。
    assert _errors(initiative_expectation="none", initiative_kind="care_action") == []


def test_the_adaptive_responsive_exception_is_honoured() -> None:
    # 唯一豁免组合：adaptive + responsive + answer_plus_detail／answer_only。
    # 注意 `follow_up_mode` 是**案例级**字段（基础案例是 `fixed`），所以这里要显式改案例，
    # 光改回合不够——我第一版就只改了回合，于是豁免没生效。
    turn = dataclasses.replace(
        _TURN,
        initiative_expectation="responsive",
        initiative_kind="none",
        turn_plan_mode="answer_plus_detail",
    )
    case = dataclasses.replace(_BASE, turns=(turn,), follow_up_mode="adaptive")

    assert not _has(validate_quality_cases([case]), "initiative_kind_required:")


def test_the_exception_does_not_apply_to_other_turn_plans() -> None:
    errors = _errors(
        initiative_expectation="responsive",
        initiative_kind="none",
        turn_plan_mode="answer_plus_lead",
    )

    assert _has(errors, "initiative_kind_required:")


def test_the_exception_does_not_apply_to_proactive() -> None:
    errors = _errors(
        initiative_expectation="proactive",
        initiative_kind="none",
        turn_plan_mode="answer_plus_detail",
    )

    assert _has(errors, "initiative_kind_required:")


# --- 关系焦点 ---------------------------------------------------------------


def test_an_unknown_relationship_focus_is_reported() -> None:
    assert _has(_errors(relationship_focus="nonsense"), "invalid:relationship_focus:")


def test_a_focus_without_a_relationship_world_is_reported() -> None:
    # 声明了焦点却没有世界观数据 → 案例自相矛盾（基础案例的 world 为 None 时）。
    case = dataclasses.replace(_case(relationship_focus="jealousy"), relationship_world=None)

    assert _has(validate_quality_cases([case]), "relationship_world_required:")


def test_a_focus_with_a_relationship_world_is_fine() -> None:
    case = dataclasses.replace(
        _case(relationship_focus="jealousy"),
        relationship_world={"views": [{"visibility": "known"}]},
    )

    assert validate_quality_cases([case]) == []


def test_no_focus_needs_no_world() -> None:
    case = dataclasses.replace(_case(relationship_focus=""), relationship_world=None)

    assert validate_quality_cases([case]) == []


# --- 关系演员 ---------------------------------------------------------------


@pytest.mark.parametrize("actor", ["nonsense", "Player", "NPC", "both"])
def test_an_unknown_relationship_actor_is_reported(actor: str) -> None:
    # 只允许空、`player`、`npc`——大小写敏感。
    assert _has(_errors(relationship_actor=actor), "invalid:relationship_actor:")


@pytest.mark.parametrize("actor", ["", "player", "npc"])
def test_the_three_documented_actors_are_accepted(actor: str) -> None:
    case = dataclasses.replace(
        _case(relationship_actor=actor, relationship_focus=""),
        relationship_world=None,
    )

    assert not _has(validate_quality_cases([case]), "invalid:relationship_actor:")


def test_a_player_actor_needs_a_target() -> None:
    errors = _errors(relationship_actor="player", relationship_target_npc_id="")

    assert _has(errors, "relationship_target_required:")


def test_a_player_actor_with_a_target_is_fine() -> None:
    assert _errors(relationship_actor="player", relationship_target_npc_id="Emily") == []


def test_an_npc_actor_needs_no_target() -> None:
    assert _errors(relationship_actor="npc", relationship_target_npc_id="") == []
