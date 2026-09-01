"""统一管理游戏运行时和资料库使用的 Mod 来源标记。"""

from __future__ import annotations

from collections.abc import Iterable


_SOURCE_FAMILIES: dict[str, frozenset[str]] = {
    "sve": frozenset(
        {
            "sve",
            "stardewvalleyexpanded",
            "flashshifter.svecode",
            "flashshifter.stardewvalleyexpandedcp",
            "flashshifter.sveftm",
        }
    ),
    "femalebachelors": frozenset(
        {
            "femalebachelors",
            "invatorzen.idcsm",
            "femalebachelorsbeach",
            "femalebachelorswinter",
        }
    ),
    "romanceablerasmodius": frozenset(
        {
            "romanceablerasmodius",
            "romanceablerasmodia",
            "romras",
            "nom0ri.romras",
            "parrot.romras",
            "dacar.seasromrasmodia",
        }
    ),
}


def normalize_source_marker(value: object) -> str:
    return "".join(character.lower() for character in str(value) if character.isalnum())


def source_family(value: object) -> str:
    """返回来源族；未知来源保持自身规范化标记。"""

    marker = normalize_source_marker(value)
    for family, members in _SOURCE_FAMILIES.items():
        if marker == family or marker in {
            normalize_source_marker(member) for member in members
        }:
            return family
    return marker


def source_variants(value: object) -> set[str]:
    """返回同一来源可能出现的规范化标记，兼容带前缀的 UniqueID。"""

    marker = normalize_source_marker(value)
    family = source_family(marker)
    variants = {marker, family}
    members = _SOURCE_FAMILIES.get(family)
    if members is not None:
        variants.update(normalize_source_marker(member) for member in members)
    else:
        for candidate_family, candidate_members in _SOURCE_FAMILIES.items():
            normalized_members = {
                normalize_source_marker(member) for member in candidate_members
            }
            if any(
                member in marker or marker in member
                for member in (candidate_family, *normalized_members)
                if member
            ):
                variants.add(candidate_family)
                variants.update(normalized_members)
    return variants


def source_matches(candidate: object, requested_sources: Iterable[object]) -> bool:
    """判断索引来源是否属于当前启用的来源族。"""

    candidate_marker = normalize_source_marker(candidate)
    if candidate_marker == "vanilla":
        return True
    if not candidate_marker:
        return False
    candidate_variants = source_variants(candidate)
    requested = {
        variant
        for source in requested_sources
        if normalize_source_marker(source)
        for variant in source_variants(source)
    }
    if not requested:
        return False
    return any(
        candidate_variant == requested_variant
        or candidate_variant in requested_variant
        or requested_variant in candidate_variant
        for candidate_variant in candidate_variants
        for requested_variant in requested
    )
