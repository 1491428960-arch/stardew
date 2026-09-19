"""来源标记的三处实现：谁复用了谁、哪里只差一个 `strip`。

查完前四处“同概念多实现”之后，这里是一个**正面发现**：`profile_index` 的那三个函数其实是
**薄包装**，直接委托给 `source_aliases`（见 `profile_index.py` 第 18-23 行的 import），
行为零差异——说明项目并非到处重复实现。

真正有差异的是**来源标记提取**：`profile_index._as_markers` 与 `personas._mod_markers`
几乎逐字相同，唯一区别是前者对 marker 调了 `strip()`、后者保留原值。因为两边最终都经
`source_matches` 归一化后再比较，**当前无实际影响**；但差异本身值得固化，免得将来有人只改一边。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stardew_ai_bridge.personas import _mod_markers, merge_persona
from stardew_ai_bridge.profile_index import (
    _as_markers,
    _normalise_marker,
    _source_matches,
    _source_variants,
)
from stardew_ai_bridge.source_aliases import (
    normalize_source_marker,
    source_matches,
    source_variants,
)


# --- 正面契约：profile_index 复用 source_aliases ------------------------------


@pytest.mark.parametrize(
    "value",
    ["Vanilla", "FlashShifter.SVE", "Nom0ri.RomRas", "", None, "  Female-Bachelors  "],
)
def test_profile_index_marker_normalisation_delegates_to_source_aliases(
    value: object,
) -> None:
    assert _normalise_marker(value) == normalize_source_marker(value)


@pytest.mark.parametrize("value", ["SVE", "FlashShifter.SVE", "vanilla", "unknown"])
def test_profile_index_variants_delegate_to_source_aliases(value: str) -> None:
    assert _source_variants(value) == source_variants(value)


@pytest.mark.parametrize(
    ("candidate", "requested"),
    [
        ("sve", ["sve"]),
        ("FlashShifter.SVE", ["sve"]),
        ("vanilla", ["sve"]),
        ("unknown", ["sve"]),
    ],
)
def test_profile_index_matching_delegates_to_source_aliases(
    candidate: str, requested: list[str]
) -> None:
    assert _source_matches(candidate, requested) == source_matches(candidate, requested)


# --- 差异：strip 与否（第五处“同概念多实现”）---------------------------------


def test_the_two_marker_extractors_differ_only_on_whitespace() -> None:
    payload = {"mod": "  vanilla  "}
    path = Path("padded.json")

    assert _as_markers(payload, path) == ["vanilla"]  # 剥掉了空白
    assert _mod_markers(payload, path) == ["  vanilla  "]  # 保留原值


def test_source_mods_entries_are_also_only_trimmed_by_one_side() -> None:
    payload = {"sourceMods": ["a", " b "]}

    assert _as_markers(payload, Path("x.json")) == ["x", "a", "b"]
    assert _mod_markers(payload, Path("x.json")) == ["x", "a", " b "]


def test_the_whitespace_difference_has_no_effect_because_matching_normalises() -> None:
    # 这是“当前无实际影响”的依据：匹配前两边都会被规范化。
    assert source_matches("  SVE  ", ["sve"]) is True
    assert source_matches("sve", ["  SVE  "]) is True


# --- 消费方：带空白的 overlay 键照样能命中 ------------------------------------


def test_overlay_key_with_surrounding_whitespace_still_applies() -> None:
    persona = {
        "npcId": "Wizard",
        "displayName": "法师",
        "modOverlay": {"  Rasmodia  ": {"displayName": "拉兹莫迪娅"}},
    }

    merged = merge_persona(persona, source_mods=["Rasmodia"])

    assert merged["displayName"] == "拉兹莫迪娅"


def test_overlay_is_not_applied_when_the_source_is_not_enabled() -> None:
    # 反向确认：来源没启用时覆盖层必须不生效（这是 merge_persona 的文档承诺）。
    persona = {
        "npcId": "Wizard",
        "displayName": "法师",
        "modOverlay": {"Rasmodia": {"displayName": "拉兹莫迪娅"}},
    }

    merged = merge_persona(persona, source_mods=["SVE"])

    assert merged["displayName"] == "法师"
