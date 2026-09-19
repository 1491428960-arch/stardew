"""来源标记归一化与匹配的直测。

`source_matches()` 被 personas / profile_index / prompts 二十多处调用，
但此前没有专门测试文件，只被间接覆盖；这里把归一化、来源族、
变体推导与匹配的边界钉住。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.source_aliases import (
    normalize_source_marker,
    source_family,
    source_matches,
    source_variants,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("vanilla", "vanilla"),
        ("Vanilla", "vanilla"),
        ("FlashShifter.StardewValleyExpandedCP", "flashshifterstardewvalleyexpandedcp"),
        ("Nom0ri.RomRas", "nom0riromras"),
        ("  female-bachelors  ", "femalebachelors"),
        ("", ""),
        (None, "none"),
    ],
)
def test_normalize_source_marker_keeps_only_alphanumerics(value: object, expected: str) -> None:
    assert normalize_source_marker(value) == expected


@pytest.mark.parametrize(
    ("value", "family"),
    [
        ("FlashShifter.StardewValleyExpandedCP", "sve"),
        ("FlashShifter.SVECode", "sve"),
        ("Nom0ri.RomRas", "romanceablerasmodius"),
        ("Invatorzen.IDCSM", "femalebachelors"),
        ("SomeUnknownMod", "someunknownmod"),
        ("", ""),
    ],
)
def test_source_family_maps_known_mods_and_keeps_unknown_ones(value: str, family: str) -> None:
    assert source_family(value) == family


def test_source_variants_include_every_family_member() -> None:
    variants = source_variants("FlashShifter.StardewValleyExpandedCP")

    assert "sve" in variants
    assert "flashshifterstardewvalleyexpandedcp" in variants
    assert "stardewvalleyexpanded" in variants
    # 不相关族不应混进来
    assert "femalebachelors" not in variants


def test_source_variants_of_a_prefixed_unique_id_still_find_the_family() -> None:
    # 运行时采集到的可能是带前缀的 UniqueID，前缀不该让它失去归属。
    variants = source_variants("FlashShifter.SVE.FTM.Extra")

    assert "sve" in variants


def test_vanilla_matches_any_requested_source() -> None:
    assert source_matches("vanilla", ["sve"]) is True
    assert source_matches("Vanilla", ()) is True


def test_blank_candidate_never_matches() -> None:
    # 没有来源标记的候选不能算作命中（未覆盖分支）。
    assert source_matches("", ["vanilla"]) is False
    assert source_matches(None, ["vanilla"]) is False
    assert source_matches("   ", ["vanilla"]) is False


def test_blank_request_list_never_matches_non_vanilla() -> None:
    # 请求列表为空表示"没有启用任何来源族"，此时非 vanilla 一律不匹配。
    assert source_matches("FlashShifter.StardewValleyExpandedCP", []) is False
    assert source_matches("FlashShifter.StardewValleyExpandedCP", [None, "  "]) is False


def test_matching_is_alias_and_case_insensitive() -> None:
    assert source_matches("FlashShifter.SVECode", ["sve"]) is True
    assert source_matches("sve", ["FlashShifter.StardewValleyExpandedCP"]) is True
    assert source_matches("Nom0ri.RomRas", ["RomanceableRasmodia"]) is True


def test_unrelated_sources_do_not_match() -> None:
    assert source_matches("SomeUnknownMod", ["sve"]) is False
    assert source_matches("FlashShifter.SVECode", ["femalebachelors"]) is False
