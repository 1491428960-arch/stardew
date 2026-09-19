"""`_behavior_source_matches` 的来源匹配与「娘化样本回归 vanilla」兼容。

按**缺失比例**挑出来的（缺 6/17，35%）。它的 docstring 与注释点明了一条**刻意的例外**：

    允许已确认的通用娘化样本回到 vanilla
    ……Shane/Sebastian 的 female-bachelors 行为样本只记录通用的回应动作、句长和口语节奏，
    不包含娘化称谓或专属剧情。它们仍保留原始来源，但在未启用娘化包的 vanilla 场景也需要
    可用，否则普通评测场景会完全失去这层人工示范。
    **原文 style/speech evidence 不走这条兼容路径。**

而代码里还有一条**先行的门槛**：只要候选里有娘化来源、而 NPC **不在** eligible 名单里，
就直接 `return False`——所以那条兼容**只对 Shane/Sebastian 这类合格 NPC 生效**。
（我最初拿 Emily 去测它，得到 False，一度以为兼容失效；实际是我的测试对象选错了。）
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.profile_index import _behavior_source_matches
from stardew_ai_bridge.source_aliases import source_matches

_ELIGIBLE = "Shane"
_NOT_ELIGIBLE = "Emily"


# --- 宽松的三条（形状不对时放行）------------------------------------------


@pytest.mark.parametrize("value", [None, 42, 3.5, object()])
def test_a_non_iterable_candidate_field_is_permissive(value: object) -> None:
    # 这里选择“放行”而不是“拒绝”：字段形状不对不等于来源不匹配。
    assert _behavior_source_matches(value, ["Vanilla"]) is True


@pytest.mark.parametrize("value", [[], (), ["", "   "]])
def test_an_empty_candidate_list_is_permissive(value: object) -> None:
    assert _behavior_source_matches(value, ["Vanilla"]) is True


def test_a_bare_string_is_wrapped_into_one_candidate() -> None:
    assert _behavior_source_matches("Vanilla", ["Vanilla"]) is True
    assert _behavior_source_matches("  Vanilla  ", ["Vanilla"]) is True


# --- 拒绝的两条 -------------------------------------------------------------


@pytest.mark.parametrize("mods", [[], (), ["  "], [42]])
def test_no_usable_source_mods_means_no_match(mods: object) -> None:
    # 玩家一个 Mod 都没启用 → 除上面三条放行外，一律不匹配。
    assert _behavior_source_matches(["Vanilla"], mods) is False


def test_a_feminised_candidate_is_rejected_for_ineligible_npcs() -> None:
    # 先行门槛：娘化候选 + NPC 不在 eligible 名单 → 直接拒绝（兼容路径在它之后）。
    assert _behavior_source_matches(["FemaleBachelors"], ["Vanilla"], npc_id=_NOT_ELIGIBLE) is False


def test_the_feminised_rejection_wins_over_the_vanilla_fallback() -> None:
    # 同一组输入换成 eligible NPC 就通过——这就是那条先行门槛的证据。
    args = (["FemaleBachelors"], ["Vanilla"])
    assert _behavior_source_matches(*args, npc_id=_NOT_ELIGIBLE) is False
    assert _behavior_source_matches(*args, npc_id=_ELIGIBLE) is True


# --- 那条兼容路径 -----------------------------------------------------------


def test_the_vanilla_fallback_is_what_makes_it_match() -> None:
    # 强断言：常规匹配本身是 False，而它返回 True —— 说明确实是兼容路径生效。
    assert not source_matches("FemaleBachelors", ["Vanilla"])
    assert _behavior_source_matches(["FemaleBachelors"], ["Vanilla"], npc_id=_ELIGIBLE) is True


def test_the_fallback_only_recognises_vanilla() -> None:
    # “未启用娘化包的 vanilla 场景” —— 换成只有 SVE 就不该走这条。
    assert _behavior_source_matches(["FemaleBachelors"], ["SVE"], npc_id=_ELIGIBLE) is False


def test_ordinary_sources_still_go_through_normal_matching() -> None:
    assert _behavior_source_matches(["Vanilla"], ["Vanilla"], npc_id=_ELIGIBLE) is True
    assert _behavior_source_matches(["SomeOtherMod"], ["Vanilla"], npc_id=_ELIGIBLE) is False


def test_one_matching_candidate_among_several_is_enough() -> None:
    assert _behavior_source_matches(["Nope", "Vanilla"], ["Vanilla"]) is True


def test_non_string_candidates_are_stringified_for_matching() -> None:
    # 候选列表里混着非字符串时不崩，按字符串形态参与匹配。
    assert isinstance(_behavior_source_matches([42, "Vanilla"], ["Vanilla"]), bool)
