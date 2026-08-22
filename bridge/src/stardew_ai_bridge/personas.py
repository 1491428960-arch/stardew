from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


_MOD_ALIASES: dict[str, set[str]] = {
    "sve": {
        "flashshifter.svecode",
        "flashshifter.stardewvalleyexpandedcp",
        "flashshifter.sveftm",
    },
    "femalebachelors": {
        "invatorzen.idcsm",
        "femalebachelorsbeach",
        "femalebachelorswinter",
    },
    "romanceablerasmodius": {
        "nom0ri.romras",
        "parrot.romras",
        "dacar.seasromrasmodia",
    },
}


def _normalise_marker(value: object) -> str:
    return "".join(character.lower() for character in str(value) if character.isalnum())


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in overlay.items():
        if (
            isinstance(merged.get(key), Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _marker_matches(marker: object, source_mods: set[str]) -> bool:
    normalised_marker = _normalise_marker(marker)
    return normalised_marker in source_mods or bool(
        _MOD_ALIASES.get(normalised_marker, set()) & source_mods
    )


def merge_persona(
    persona: Mapping[str, Any],
    source_mods: Iterable[str] = (),
) -> dict[str, Any]:
    """合并已声明的 Mod 覆盖层，并保证未启用的覆盖层不生效。"""

    source_mod_list = list(source_mods)
    overlays = persona.get("modOverlay", {})
    if not isinstance(overlays, Mapping):
        overlays = {}

    merged = copy.deepcopy(dict(persona))
    merged["modOverlay"] = {}
    applied_markers: set[str] = set()
    for source_mod in source_mod_list:
        for marker, overlay in overlays.items():
            marker_key = str(marker)
            if (
                marker_key in applied_markers
                or not _marker_matches(marker, {_normalise_marker(source_mod)})
                or not isinstance(overlay, Mapping)
            ):
                continue
            merged = _deep_merge(merged, overlay)
            merged["modOverlay"][marker_key] = copy.deepcopy(dict(overlay))
            applied_markers.add(marker_key)
    return merged


def _mod_markers(payload: Mapping[str, Any], path: Path) -> list[str]:
    markers: list[str] = []
    primary_marker = payload.get("mod", path.stem)
    if isinstance(primary_marker, str) and primary_marker.strip():
        markers.append(primary_marker)

    raw_markers = payload.get("sourceMods", ())
    if isinstance(raw_markers, str):
        raw_markers = [raw_markers]
    if isinstance(raw_markers, Iterable):
        markers.extend(
            str(marker)
            for marker in raw_markers
            if str(marker).strip()
        )
    return list(dict.fromkeys(markers)) or [path.stem]


class PersonaStore:
    """从 data/personas 下的 JSON 资料加载 NPC 基础资料和 Mod 覆盖层。"""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else (
            Path(__file__).resolve().parents[3] / "data" / "personas"
        )
        self._personas = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        personas: dict[str, dict[str, Any]] = {}
        paths = sorted(
            self.data_dir.glob("*.json"),
            key=lambda path: (path.stem.casefold() != "vanilla", path.name.casefold()),
        )
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries = payload.get("personas", payload)
            if not isinstance(entries, Mapping):
                continue
            markers = _mod_markers(payload, path)
            is_vanilla = any(
                _normalise_marker(marker) == "vanilla" for marker in markers
            )
            for npc_id, raw_persona in entries.items():
                if not isinstance(raw_persona, Mapping):
                    continue
                npc_key = str(npc_id)
                if is_vanilla:
                    personas[npc_key] = copy.deepcopy(dict(raw_persona))
                    personas[npc_key].setdefault("npcId", npc_key)
                    personas[npc_key].setdefault("modOverlay", {})
                    continue
                base = personas.setdefault(
                    npc_key,
                    {
                        "npcId": npc_key,
                        "displayName": npc_key,
                        "pronouns": {},
                        "coreTraits": [],
                        "addressing": {},
                        "modOverlay": {},
                    },
                )
                for marker in markers:
                    base.setdefault("modOverlay", {})[marker] = copy.deepcopy(
                        dict(raw_persona)
                    )
        return personas

    def get_persona(
        self,
        npc_id: str,
        source_mods: Iterable[str] = (),
    ) -> dict[str, Any]:
        key = next(
            (candidate for candidate in self._personas if candidate.casefold() == npc_id.casefold()),
            npc_id,
        )
        base = self._personas.get(
            key,
            {
                "npcId": npc_id,
                "displayName": npc_id,
                "pronouns": {},
                "coreTraits": [],
                "addressing": {},
                "modOverlay": {},
            },
        )
        return merge_persona(base, source_mods)

    def load(self, npc_id: str, source_mods: Iterable[str] = ()) -> dict[str, Any]:
        return self.get_persona(npc_id, source_mods)

    def get(self, npc_id: str, source_mods: Iterable[str] = ()) -> dict[str, Any]:
        return self.get_persona(npc_id, source_mods)
