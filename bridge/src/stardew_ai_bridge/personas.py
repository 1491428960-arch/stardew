from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


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
    return _normalise_marker(marker) in source_mods


def merge_persona(
    persona: Mapping[str, Any],
    source_mods: Iterable[str] = (),
) -> dict[str, Any]:
    """合并已声明的 Mod 覆盖层，并保证未启用的覆盖层不生效。"""

    active_mods = {_normalise_marker(mod) for mod in source_mods}
    overlays = persona.get("modOverlay", {})
    if not isinstance(overlays, Mapping):
        overlays = {}

    merged = copy.deepcopy(dict(persona))
    merged["modOverlay"] = {}
    for marker, overlay in overlays.items():
        if not _marker_matches(marker, active_mods) or not isinstance(overlay, Mapping):
            continue
        merged = _deep_merge(merged, overlay)
        merged["modOverlay"][str(marker)] = copy.deepcopy(dict(overlay))
    return merged


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
            marker = str(payload.get("mod", path.stem))
            is_vanilla = _normalise_marker(marker) == "vanilla"
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
