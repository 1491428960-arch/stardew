from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def _normalise_marker(value: object) -> str:
    return "".join(character.lower() for character in str(value) if character.isalnum())


def _as_markers(payload: Mapping[str, Any], path: Path) -> list[str]:
    primary = payload.get("mod", path.stem)
    markers: list[str] = []
    if isinstance(primary, str) and primary.strip():
        markers.append(primary.strip())
    raw_source_mods = payload.get("sourceMods", ())
    if isinstance(raw_source_mods, str):
        raw_source_mods = [raw_source_mods]
    if isinstance(raw_source_mods, Iterable):
        markers.extend(
            str(marker).strip()
            for marker in raw_source_mods
            if str(marker).strip()
        )
    return list(dict.fromkeys(markers)) or [path.stem]


def _strip_json_comments(text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        next_character = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            result.append(character)
            index += 1
            continue
        if character == "/" and next_character == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if character == "/" and next_character == "*":
            index += 2
            while index + 1 < len(text) and text[index:index + 2] != "*/":
                index += 1
            index = min(index + 2, len(text))
            continue
        result.append(character)
        index += 1
    return "".join(result)


def _remove_trailing_commas(text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if in_string:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            result.append(character)
            index += 1
            continue
        if character == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "}]":
                index += 1
                continue
        result.append(character)
        index += 1
    return "".join(result)


def _escape_control_chars_in_strings(text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                result.append(character)
                escaped = False
            elif character == "\\":
                result.append(character)
                escaped = True
            elif character == '"':
                result.append(character)
                in_string = False
            elif ord(character) < 0x20:
                result.append(f"\\u{ord(character):04x}")
            else:
                result.append(character)
            continue
        result.append(character)
        if character == '"':
            in_string = True
    return "".join(result)


def _load_json(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    normalised = _escape_control_chars_in_strings(_strip_json_comments(text))
    payload = json.loads(_remove_trailing_commas(normalised))
    if not isinstance(payload, Mapping):
        raise ValueError("JSON 根节点必须是对象")
    return payload


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _new_profile(npc_id: str) -> dict[str, Any]:
    return {
        "npcId": npc_id,
        "displayName": npc_id,
        "pronouns": {},
        "addressing": {},
        "coreTraits": [],
        "sourceMods": [],
        "sourceModIds": [],
        "sourceFiles": [],
        "overlays": {},
    }


class ProfileIndexBuilder:
    """把人设层和 Content Patcher 资产整理为可追溯的离线索引。"""

    def __init__(self, persona_dir: str | Path) -> None:
        self.persona_dir = Path(persona_dir)

    def build(self, mod_roots: Iterable[str | Path] = ()) -> dict[str, object]:
        index: dict[str, object] = {
            "schemaVersion": 1,
            "profiles": {},
            "styleSamples": [],
            "storyEvents": [],
            "sources": [],
            "warnings": [],
        }
        profiles = index["profiles"]
        warnings = index["warnings"]
        assert isinstance(profiles, dict)
        assert isinstance(warnings, list)

        self._load_personas(profiles, warnings)
        for root_value in mod_roots:
            root = Path(root_value)
            self._load_mod_root(index, root)
        return index

    @staticmethod
    def write(index: Mapping[str, object], output_path: str | Path) -> None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(index, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)

    def _load_personas(
        self,
        profiles: dict[str, dict[str, Any]],
        warnings: list[str],
    ) -> None:
        if not self.persona_dir.is_dir():
            warnings.append(f"persona directory not found: {self.persona_dir.name}")
            return
        for path in sorted(
            self.persona_dir.glob("*.json"),
            key=lambda item: (
                item.stem.casefold() != "vanilla",
                item.name.casefold(),
            ),
        ):
            try:
                payload = _load_json(path)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                warnings.append(f"invalid JSON: {path.name}")
                continue
            entries = payload.get("personas", payload)
            if not isinstance(entries, Mapping):
                warnings.append(f"invalid personas mapping: {path.name}")
                continue
            markers = _as_markers(payload, path)
            layer = markers[0]
            source_ids = markers[1:] if len(markers) > 1 else []
            is_vanilla = _normalise_marker(layer) == "vanilla"
            for raw_npc_id, raw_persona in entries.items():
                if not isinstance(raw_persona, Mapping):
                    warnings.append(f"invalid persona: {path.name}:{raw_npc_id}")
                    continue
                npc_id = str(raw_npc_id).strip()
                if not npc_id:
                    warnings.append(f"empty npcId: {path.name}")
                    continue
                profile = profiles.setdefault(npc_id, _new_profile(npc_id))
                if is_vanilla:
                    for key in ("displayName", "pronouns", "addressing", "coreTraits"):
                        if key in raw_persona:
                            profile[key] = raw_persona[key]
                else:
                    profile["overlays"][layer] = dict(raw_persona)
                if layer not in profile["sourceMods"]:
                    profile["sourceMods"].append(layer)
                for source_id in source_ids:
                    if source_id not in profile["sourceModIds"]:
                        profile["sourceModIds"].append(source_id)
                if path.name not in profile["sourceFiles"]:
                    profile["sourceFiles"].append(path.name)

    def _load_mod_root(self, index: dict[str, object], root: Path) -> None:
        warnings = index["warnings"]
        sources = index["sources"]
        samples = index["styleSamples"]
        assert isinstance(warnings, list)
        assert isinstance(sources, list)
        assert isinstance(samples, list)
        if not root.is_dir():
            warnings.append(f"mod root not found: {root.name}")
            return

        source_mod = root.name
        manifest = root / "manifest.json"
        if manifest.is_file():
            try:
                payload = _load_json(manifest)
                source_mod = str(payload.get("UniqueID") or source_mod)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                warnings.append(f"invalid JSON: manifest.json")
        sources.append({"sourceMod": source_mod, "root": root.name})

        for path in sorted(root.rglob("*.json"), key=lambda item: item.as_posix().casefold()):
            if path == manifest or path.name.casefold() in {"config.json"}:
                continue
            if any(part.casefold() == "i18n" for part in path.relative_to(root).parts):
                continue
            if "dialogue" not in path.name.casefold():
                continue
            try:
                payload = _load_json(path)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                warnings.append(f"invalid JSON: {_relative_path(path, root)}")
                continue
            self._extract_dialogue_changes(
                payload,
                source_mod=source_mod,
                source_path=_relative_path(path, root),
                samples=samples,
            )

    @staticmethod
    def _extract_dialogue_changes(
        payload: Mapping[str, Any],
        *,
        source_mod: str,
        source_path: str,
        samples: list[dict[str, Any]],
    ) -> None:
        changes = payload.get("Changes")
        if not isinstance(changes, list):
            return
        for change in changes:
            if not isinstance(change, Mapping):
                continue
            if str(change.get("Action", "")).casefold() != "editdata":
                continue
            target = str(change.get("Target", ""))
            prefix = "Characters/Dialogue/"
            if not target.startswith(prefix):
                continue
            npc_id = target[len(prefix):].strip("/")
            for stage_prefix in ("MarriageDialogue", "RoommateDialogue"):
                if npc_id.startswith(stage_prefix):
                    npc_id = npc_id[len(stage_prefix):]
                    break
            entries = change.get("Entries")
            if not npc_id or not isinstance(entries, Mapping):
                continue
            for source_key, raw_text in entries.items():
                if not isinstance(raw_text, str) or not raw_text.strip():
                    continue
                samples.append(
                    {
                        "sampleId": f"{source_mod}:{source_path}:{source_key}",
                        "npcId": npc_id,
                        "sourceMod": source_mod,
                        "sourcePath": source_path,
                        "sourceKey": str(source_key),
                        "text": raw_text.strip(),
                        "evidenceKind": "dialogue",
                    }
                )
