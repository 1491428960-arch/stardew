"""8 个“1～3 行小函数”的补测。

2026-09-20 用**函数级覆盖率排序**（读 `.coverage` + AST，按缺失比例排）挑出它们：
排除掉抽象方法（Protocol 的 `generate`／`access_token`／`name`）与已确认的死代码
（两个 `*_catalog`、`guard_response`）之后，剩下这些**确实是逻辑、只是太小而被漏掉**的。

小函数被漏掉通常不是因为难，而是因为“看起来不值得单独写测试”——但正是这类转发与
别名最容易在重构时静默走样。
"""

from __future__ import annotations

import dataclasses
import json

from stardew_ai_bridge.character_quality_eval import (
    DEFAULT_CASES,
    _turn_affection_anchors,
)
from stardew_ai_bridge.config import BridgeSettings
from stardew_ai_bridge.guard import GuardResult, _affection_intensity
from stardew_ai_bridge.personas import PersonaStore


# --- guard._affection_intensity --------------------------------------------


def _quality_context(payload: object) -> list[dict[str, str]]:
    return [
        {"role": "system", "name": "quality_context", "content": json.dumps(payload)}
    ]


def test_affection_intensity_is_empty_without_the_card() -> None:
    assert _affection_intensity([]) == ""
    assert _affection_intensity([{"role": "user", "content": "你好"}]) == ""


def test_affection_intensity_is_normalised() -> None:
    # `strip()` + `casefold()`：让 "  Light  " 与 "light" 等价。
    assert _affection_intensity(_quality_context({"flirtIntensity": "  Light  "})) == "light"


def test_affection_intensity_ignores_non_string_values() -> None:
    assert _affection_intensity(_quality_context({"flirtIntensity": 3})) == ""
    assert _affection_intensity(_quality_context({"flirtIntensity": None})) == ""


# --- GuardResult.get / as_dict ---------------------------------------------


def _result() -> GuardResult:
    return GuardResult(accepted=True, reason="ok", text="你好")


def test_guard_result_get_reads_known_keys() -> None:
    result = _result()

    assert result.get("accepted") is True
    assert result.get("reason") == "ok"
    assert result.get("text") == "你好"


def test_guard_result_get_returns_the_default_for_unknown_keys() -> None:
    result = _result()

    assert result.get("nope") is None
    assert result.get("nope", "fallback") == "fallback"


def test_guard_result_as_dict_exposes_exactly_three_fields() -> None:
    assert _result().as_dict() == {"accepted": True, "reason": "ok", "text": "你好"}


# --- config 的两个别名属性 -------------------------------------------------


def test_provider_properties_are_aliases_of_local_and_cloud() -> None:
    # 两个属性只是转发；钉住“别名不许分叉”。
    settings = BridgeSettings.from_env()

    assert settings.local_provider is settings.local
    assert settings.cloud_provider is settings.cloud


# --- personas 的两个别名方法 -----------------------------------------------


def test_persona_store_load_and_get_match_get_persona() -> None:
    store = PersonaStore()
    expected = store.get_persona("Shane")

    assert store.load("Shane") == expected
    assert store.get("Shane") == expected


def test_persona_store_aliases_accept_source_mods() -> None:
    store = PersonaStore()

    assert store.load("Shane", ["SVE"]) == store.get_persona("Shane", ["SVE"])
    assert store.get("Shane", ()) == store.get_persona("Shane", ())


# --- character_quality_eval._turn_affection_anchors ------------------------


def test_turn_affection_anchors_is_empty_for_none() -> None:
    assert _turn_affection_anchors(None) == set()


def test_turn_affection_anchors_normalises_the_expected_terms() -> None:
    turn = dataclasses.replace(
        DEFAULT_CASES[0].dialogue_turns()[0], expected_terms=("鸡舍", "  Mon1  ")
    )

    anchors = _turn_affection_anchors(turn)

    assert anchors  # 非空
    # 归一化后的形态（去空白/大小写折叠）与原样写法都能被同一个集合覆盖
    assert anchors == _turn_affection_anchors(
        dataclasses.replace(
            DEFAULT_CASES[0].dialogue_turns()[0], expected_terms=("鸡舍", "mon1")
        )
    )
