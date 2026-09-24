from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from .behavior_quality import validate_behavior_example
from .dialogue_stage import sample_stage_specificity, stage_hint_applies
from .evidence import (
    has_dialogue_control_residue,
    is_model_evidence_record as _shared_is_model_evidence_record,
)
from .personas import canonical_npc_id, is_female_bachelor_eligible
from .relationship_gating import game_event_completed
from .speech import derive_speech_profile, select_stage_voice_anchors
from .source_aliases import (
    normalize_source_marker,
    source_family,
    source_matches,
    source_variants,
)


_UNRESOLVED_I18N = re.compile(r"\{\{\s*i18n\s*:", re.IGNORECASE)

# 候选上限 —— **不是**"每轮注入几条"，那个由 `prompts._MAX_SPEECH_EVIDENCE` 管。
# 这里决定的是"最多能取出多少条候选"，也就是**轮转池的物理宽度**。
#
# 2026-09-24：这里原先写死 `min(int(limit), 6)`，与 prompts 里的注入上限
# **共用了同一个 6**，于是池子永远只有 6 条可转 —— 实测连续 20 轮只覆盖到
# 5 条素材，池子里其余素材一次都没被建议过。放宽池子**不增加 prompt 体积**
# （每轮仍只注入 1 条），所以才把这两个数字拆开。
_SPEECH_EVIDENCE_CANDIDATES = 24
# 同上。style 池要**明显**宽于 speech 池：`prompts.py` 拿已经取到的
# `speech_texts` 去重 style，而两个数组在索引里内容对称（各 10213 条）——
# speech 池一旦放宽，去重会把 style 的前排整片吃掉，池子不放大就等于清空。
_STYLE_SAMPLE_CANDIDATES = 48


def _normalise_marker(value: object) -> str:
    return normalize_source_marker(value)


def _source_variants(value: object) -> set[str]:
    return source_variants(value)


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
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        next_character = text[index + 1] if index + 1 < len(text) else ""
        if quote is not None:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in {'"', "'"}:
            quote = character
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


def _normalise_single_quoted_strings(text: str) -> str:
    """把 Content Patcher 常见的单引号字符串转换成 JSON 字符串。"""
    result: list[str] = []
    in_double = False
    in_single = False
    escaped = False
    for character in text:
        if in_single:
            if escaped:
                if character == "'":
                    result.append("'")
                elif character == '"':
                    result.append('\\"')
                elif character == "\\":
                    result.append("\\\\")
                else:
                    result.extend(("\\", character))
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == "'":
                result.append('"')
                in_single = False
            elif character == '"':
                result.append('\\"')
            elif ord(character) < 0x20:
                result.append(f"\\u{ord(character):04x}")
            else:
                result.append(character)
            continue

        if in_double:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_double = False
            continue

        if character == "'":
            result.append('"')
            in_single = True
        else:
            result.append(character)
            if character == '"':
                in_double = True

    if in_single and escaped:
        result.append("\\")
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
    normalised = _normalise_single_quoted_strings(_strip_json_comments(text))
    normalised = _escape_control_chars_in_strings(normalised)
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


def _structured_list(value: object) -> list[Mapping[str, Any] | str]:
    """把 persona 中允许的结构化资料统一成可校验的列表。"""

    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, (Mapping, str))]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _get_or_create_profile(
    profiles: dict[str, dict[str, Any]], npc_id: str
) -> tuple[str, dict[str, Any]]:
    """按 Stardew 的大小写不敏感 NPC ID 复用唯一 profile 键。"""

    npc_id = canonical_npc_id(npc_id)
    for existing_id, profile in profiles.items():
        if existing_id.casefold() == npc_id.casefold():
            return existing_id, profile
    profiles[npc_id] = _new_profile(npc_id)
    return npc_id, profiles[npc_id]


_ALLOWED_KNOWLEDGE_SCOPES = {
    "canon_confirmed",
    "runtime_confirmed",
    "player_provided",
}


def _normalise_source_refs(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Iterable):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalise_knowledge_fact(
    raw_fact: Mapping[str, Any],
    *,
    fact_id: str,
    npc_id: str,
    source_mod: str,
    summary: str,
    scope: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "factId": fact_id,
        "npcId": npc_id,
        "sourceMod": source_mod,
        "summary": summary,
        "knowledgeScope": scope,
        "confidence": str(raw_fact.get("confidence", "medium")).strip() or "medium",
        "sourceRefs": _normalise_source_refs(raw_fact.get("sourceRefs", ())),
    }
    required_event_id = str(raw_fact.get("requiredEventId", "")).strip()
    if required_event_id:
        result["requiredEventId"] = required_event_id
    # 常驻标记（专有名词的事实）：从 persona 归一进索引时必须原样带过。
    # 这是同一形态的**第四处**白名单（另外三处：本文件的 `_FACT_FIELDS`、
    # `prompts._compact_knowledge_fact`、`prompts` 的 knowledge_facts 卡）。
    # 少任何一处，数据侧写的 `alwaysOn` 都会静默消失、事实退回普通通道被切片挡住。
    if raw_fact.get("alwaysOn") is True:
        result["alwaysOn"] = True
    return result


def _normalise_known_character(
    raw_relation: Mapping[str, Any],
    *,
    relation_id: str,
    npc_id: str,
    known_npc_id: str,
    source_mod: str,
    summary: str,
    scope: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "relationId": relation_id,
        "npcId": npc_id,
        "knownNpcId": canonical_npc_id(known_npc_id),
        "relation": str(raw_relation.get("relation", "")).strip(),
        "summary": summary,
        "sourceMod": source_mod,
        "knowledgeScope": scope,
        "confidence": str(raw_relation.get("confidence", "medium")).strip()
        or "medium",
        "sourceRefs": _normalise_source_refs(raw_relation.get("sourceRefs", ())),
    }
    required_event_id = str(raw_relation.get("requiredEventId", "")).strip()
    if required_event_id:
        result["requiredEventId"] = required_event_id
    return result


def _is_catalog_npc_id(value: object) -> bool:
    npc_id = str(value).strip()
    if not npc_id or npc_id.casefold() == "rainy":
        return False
    lowered = npc_id.casefold()
    return not lowered.startswith(("marriagedialogue", "roommatedialogue"))


def _append_source_mods(entry: dict[str, Any], values: object) -> None:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable):
        return
    source_mods = entry.setdefault("sourceMods", [])
    if not isinstance(source_mods, list):
        source_mods = []
        entry["sourceMods"] = source_mods
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        if value.strip() not in source_mods:
            source_mods.append(value.strip())


class ProfileIndexBuilder:
    """把人设层和 Content Patcher 资产整理为可追溯的离线索引。"""

    def __init__(self, persona_dir: str | Path) -> None:
        self.persona_dir = Path(persona_dir)

    def build(
        self,
        mod_roots: Iterable[str | Path] = (),
        *,
        corpus_paths: Iterable[str | Path] = (),
        vanilla_root: str | Path | None = None,
        vanilla_events_root: str | Path | None = None,
        vanilla_extra_dialogue_root: str | Path | None = None,
        vanilla_locale: str | None = None,
        runtime_sample_paths: Iterable[str | Path] = (),
        locale: str = "zh-CN",
    ) -> dict[str, object]:
        index: dict[str, object] = {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": [],
            "speechEvidence": [],
            "behaviorExamples": [],
            "voiceCards": {},
            "knowledgeFacts": [],
            "knownCharacters": [],
            "storyEvents": [],
            "sources": [],
            "warnings": [],
        }
        profiles = index["profiles"]
        warnings = index["warnings"]
        knowledge_facts = index["knowledgeFacts"]
        known_characters = index["knownCharacters"]
        story_events = index["storyEvents"]
        assert isinstance(profiles, dict)
        assert isinstance(warnings, list)
        assert isinstance(knowledge_facts, list)
        assert isinstance(known_characters, list)
        assert isinstance(story_events, list)

        self._load_personas(
            profiles,
            warnings,
            knowledge_facts,
            known_characters,
            story_events,
        )
        self._load_behavior_examples(index)
        for root_value in mod_roots:
            root = Path(root_value)
            self._load_mod_root(index, root, locale=locale)
        if (
            vanilla_root is not None
            or vanilla_events_root is not None
            or vanilla_extra_dialogue_root is not None
        ):
            from .corpus import build_dialogue_corpus

            self._merge_corpus_payload(
                index,
                build_dialogue_corpus(
                    vanilla_root=vanilla_root,
                    vanilla_events_root=vanilla_events_root,
                    vanilla_extra_dialogue_root=vanilla_extra_dialogue_root,
                    vanilla_locale=vanilla_locale,
                ),
            )
        for corpus_path in corpus_paths:
            path = Path(corpus_path)
            try:
                payload = _load_json(path)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                warnings.append(f"invalid corpus JSON: {path.name}")
                continue
            self._merge_corpus_payload(index, payload)
        for runtime_sample_path in runtime_sample_paths:
            try:
                from .runtime_samples import load_runtime_samples

                runtime_samples = load_runtime_samples(runtime_sample_path)
            except (OSError, ValueError):
                warnings.append(
                    f"invalid runtime samples: {Path(runtime_sample_path).name}"
                )
                continue
            self._merge_corpus_payload(
                index,
                {"schemaVersion": 1, "records": runtime_samples},
            )
        voice_cards = index["voiceCards"]
        speech_evidence = index["speechEvidence"]
        assert isinstance(voice_cards, dict)
        assert isinstance(speech_evidence, list)
        evidence_by_npc: dict[str, list[Mapping[str, Any]]] = {}
        for record in speech_evidence:
            if not isinstance(record, Mapping):
                continue
            npc_id = str(record.get("npcId", "")).strip()
            if npc_id:
                evidence_by_npc.setdefault(npc_id, []).append(record)
        for npc_id in sorted(evidence_by_npc, key=str.casefold):
            voice_cards[npc_id] = derive_speech_profile(
                npc_id,
                evidence_by_npc[npc_id],
                max_evidence=6,
            )
        return index

    def _load_behavior_examples(self, index: dict[str, object]) -> None:
        """加载人工审核的成对示例，不把它们伪装成原版对白证据。"""

        path = self.persona_dir / "behavior-examples.json"
        if not path.is_file():
            return
        warnings = index["warnings"]
        examples = index["behaviorExamples"]
        assert isinstance(warnings, list)
        assert isinstance(examples, list)
        try:
            payload = _load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            warnings.append(f"invalid behavior examples JSON: {path.name}")
            return
        if payload.get("schemaVersion") != 1:
            warnings.append(f"unsupported behavior examples schema: {path.name}")
            return
        raw_examples = payload.get("examples", ())
        if not isinstance(raw_examples, list):
            warnings.append(f"invalid behavior examples list: {path.name}")
            return

        seen_ids: set[str] = set()
        for position, raw_example in enumerate(raw_examples):
            if not isinstance(raw_example, Mapping):
                warnings.append(f"invalid behavior example: {path.name}:{position}")
                continue
            normalized, errors = validate_behavior_example(
                raw_example,
                require_review=False,
            )
            if normalized is None:
                detail = ",".join(errors) if errors else "invalid:example"
                warnings.append(
                    f"invalid behavior example: {path.name}:{position}:{detail}"
                )
                continue
            example_id = str(normalized["exampleId"])
            if example_id in seen_ids:
                warnings.append(f"duplicate behavior example: {example_id}")
                continue
            source_type = str(normalized.get("sourceType", "")).strip()
            if source_type not in {"handcrafted_example", "human_approved"}:
                warnings.append(
                    f"unapproved behavior example: {path.name}:{position}"
                )
                continue
            seen_ids.add(example_id)

            record: dict[str, Any] = {
                "exampleId": example_id,
                "npcId": normalized["npcId"],
                "playerInput": normalized["playerInput"],
                "npcReply": normalized["npcReply"],
                "sourceType": source_type,
            }
            for field in (
                "sourceMods",
                "channels",
                "relationshipStages",
                "topicKeywords",
                "sourceRefs",
            ):
                values = normalized.get(field)
                if isinstance(values, list) and values:
                    record[field] = values
            for field in ("speechFunction", "topic", "emotion"):
                value = normalized.get(field)
                if isinstance(value, str) and value:
                    record[field] = value
            for field in ("initiativeExpectation", "initiativeKind"):
                value = normalized.get(field)
                if isinstance(value, str) and value:
                    record[field] = value
            examples.append(record)

    @staticmethod
    def _merge_corpus_payload(
        index: dict[str, object], payload: Mapping[str, Any]
    ) -> None:
        from .corpus import (
            _normalise_source_path,
            clean_dialogue_variants,
            infer_dialogue_conditions,
        )

        profiles = index["profiles"]
        samples = index["styleSamples"]
        speech_evidence = index["speechEvidence"]
        sources = index["sources"]
        warnings = index["warnings"]
        assert isinstance(profiles, dict)
        assert isinstance(samples, list)
        assert isinstance(speech_evidence, list)
        assert isinstance(sources, list)
        assert isinstance(warnings, list)

        raw_sources = payload.get("sources", ())
        if isinstance(raw_sources, list):
            for raw_source in raw_sources:
                if not isinstance(raw_source, Mapping):
                    continue
                source_mod = str(raw_source.get("sourceMod", "")).strip()
                root = str(raw_source.get("root", "")).strip()
                if not source_mod or not root:
                    continue
                source = {"sourceMod": source_mod, "root": Path(root).name}
                if source not in sources:
                    sources.append(source)

        raw_warnings = payload.get("warnings", ())
        if isinstance(raw_warnings, list):
            warnings.extend(
                warning.strip()
                for warning in raw_warnings
                if isinstance(warning, str) and warning.strip()
            )

        existing_ids = {
            str(item.get("sampleId"))
            for item in [*samples, *speech_evidence]
            if isinstance(item, Mapping) and item.get("sampleId")
        }
        raw_records = payload.get("records", ())
        if not isinstance(raw_records, list):
            return
        for raw_record in raw_records:
            if not isinstance(raw_record, Mapping):
                continue
            if not _is_model_evidence_record(raw_record):
                continue
            npc_id = str(raw_record.get("npcId", "")).strip()
            source_mod = str(raw_record.get("sourceMod", "")).strip() or "unknown"
            source_key = str(raw_record.get("sourceKey", "")).strip()
            resolved_text = raw_record.get("resolvedText")
            raw_text = (
                resolved_text
                if isinstance(resolved_text, str) and resolved_text.strip()
                else raw_record.get("text")
            )
            if (
                not npc_id
                or not source_key
                or not isinstance(raw_text, str)
                or not raw_text.strip()
            ):
                continue
            source_path = _normalise_source_path(
                str(raw_record.get("sourcePath", "unknown.json"))
            )
            sample_id = str(raw_record.get("sampleId", "")).strip() or (
                f"{source_mod}:{source_path}:{source_key}"
            )
            conditions = raw_record.get("conditions")
            if not isinstance(conditions, Mapping) or not conditions:
                conditions = infer_dialogue_conditions(source_path, source_key)
            raw_variants = raw_record.get("dialogueVariants")
            if isinstance(resolved_text, str) and resolved_text.strip():
                # 旧 corpus 可能从未解析的模板切出残缺 dialogueVariants；
                # 一旦存在可用 resolvedText，必须只从它重新清洗，不能让
                # stale variants 抢回模型证据窗口。
                variants = clean_dialogue_variants(resolved_text)
            elif isinstance(raw_variants, list):
                variants = [
                    cleaned
                    for variant in raw_variants
                    if isinstance(variant, str)
                    for cleaned in clean_dialogue_variants(variant)
                    if not has_dialogue_control_residue(cleaned)
                ]
            else:
                variants = [
                    cleaned
                    for cleaned in clean_dialogue_variants(raw_text)
                    if not has_dialogue_control_residue(cleaned)
                ]
            variants = [
                cleaned
                for cleaned in variants
                if not has_dialogue_control_residue(cleaned)
            ]
            if not variants:
                # 清洗为空意味着这里只有控制脚本、叙述分支或无效占位符；
                # 不能退回为完整原文，否则残渣会再次进入 styleSamples。
                continue
            canonical_npc_id, profile = _get_or_create_profile(profiles, npc_id)
            if source_mod not in profile["sourceMods"]:
                profile["sourceMods"].append(source_mod)
            if source_path not in profile["sourceFiles"]:
                profile["sourceFiles"].append(source_path)
            for variant_index, text in enumerate(dict.fromkeys(variants)):
                variant_sample_id = sample_id
                if variant_index:
                    variant_sample_id = f"{sample_id}:variant-{variant_index}"
                sample: dict[str, Any] = {
                    "sampleId": variant_sample_id,
                    "npcId": canonical_npc_id,
                    "sourceMod": source_mod,
                    "sourcePath": source_path,
                    "sourceKey": source_key,
                    "text": text,
                    "evidenceKind": str(
                        raw_record.get("evidenceKind", "dialogue")
                    ).strip()
                    or "dialogue",
                }
                if isinstance(conditions, Mapping) and conditions:
                    sample["conditions"] = dict(conditions)
                for field in (
                    "sourceSampleId",
                    "candidateKey",
                    "capturedAt",
                    "gameState",
                    "eventId",
                    "eventLineIndex",
                    "eventConditions",
                    "participants",
                ):
                    value = raw_record.get(field)
                    if isinstance(value, str) and value.strip():
                        sample[field] = value.strip()
                    elif field == "eventLineIndex" and isinstance(value, int):
                        sample[field] = value
                    elif field == "gameState" and isinstance(value, Mapping) and value:
                        sample[field] = dict(value)
                    elif field == "eventConditions" and isinstance(value, Mapping) and value:
                        sample[field] = dict(value)
                    elif field == "participants" and isinstance(value, list) and value:
                        sample[field] = [
                            str(item).strip()
                            for item in value
                            if str(item).strip()
                        ]
                if variant_sample_id in existing_ids:
                    # 直扫 Mod 时可能先留下同 ID 的 i18n 占位符；如果后续
                    # corpus 已经解析出实际对白，应以解析文本替换占位符，
                    # 否则已解析语料永远进不了语气检索层。
                    replaced = False
                    for collection in (samples, speech_evidence):
                        for existing_index, existing in enumerate(collection):
                            if (
                                not isinstance(existing, Mapping)
                                or existing.get("sampleId") != variant_sample_id
                                or not _UNRESOLVED_I18N.search(
                                    str(existing.get("text", ""))
                                )
                            ):
                                continue
                            collection[existing_index] = dict(sample)
                            replaced = True
                    if replaced:
                        continue
                    continue
                samples.append(sample)
                speech_evidence.append(dict(sample))
                existing_ids.add(variant_sample_id)

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
        knowledge_facts: list[dict[str, Any]],
        known_characters: list[dict[str, Any]],
        story_events: list[dict[str, Any]],
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
            if path.name.casefold() == "behavior-examples.json":
                continue
            try:
                payload = _load_json(path)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                warnings.append(f"invalid JSON: {path.name}")
                continue
            entries = payload.get("personas", payload)
            if not isinstance(entries, Mapping):
                warnings.append(f"invalid personas mapping: {path.name}")
                continue
            # 只保留映射形态的条目：persona 条目必然是映射，而行为样例等数据文件的
            # 顶层键（如 schemaVersion／description／scenarios）不是。整份文件都没有
            # persona 条目时**静默跳过**——它与上面按文件名跳过的 behavior-examples.json
            # 属于同一类情况（目录里放了数据文件），不该刷成索引警告（B13）。
            persona_entries = {
                raw_npc_id: raw_persona
                for raw_npc_id, raw_persona in entries.items()
                if isinstance(raw_persona, Mapping)
            }
            if not persona_entries:
                continue
            entries = persona_entries
            markers = _as_markers(payload, path)
            layer = markers[0]
            source_ids = markers[1:] if len(markers) > 1 else []
            is_vanilla = _normalise_marker(layer) == "vanilla"
            for raw_npc_id, raw_persona in entries.items():
                # persona_entries（上面）已保证每条都是 Mapping，这里不再重复检查
                npc_id = str(raw_npc_id).strip()
                if not npc_id:
                    warnings.append(f"empty npcId: {path.name}")
                    continue
                canonical_npc_id, profile = _get_or_create_profile(profiles, npc_id)
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
                fact_inputs = [
                    (raw_persona.get("knowledgeFacts"), False),
                    (raw_persona.get("biography"), True),
                ]
                for raw_value, is_biography in fact_inputs:
                    for position, raw_fact in enumerate(_structured_list(raw_value)):
                        if isinstance(raw_fact, str):
                            raw_fact = {
                                "factId": f"{canonical_npc_id}:biography:{position}",
                                "summary": raw_fact,
                                "knowledgeScope": "canon_confirmed",
                            }
                        fact_id = str(raw_fact.get("factId", "")).strip()
                        if is_biography and not fact_id:
                            fact_id = f"{canonical_npc_id}:biography:{position}"
                        summary = str(raw_fact.get("summary", "")).strip()
                        scope = str(
                            raw_fact.get("knowledgeScope", "canon_confirmed")
                        ).strip()
                        if (
                            not fact_id
                            or not summary
                            or scope.casefold() not in _ALLOWED_KNOWLEDGE_SCOPES
                            or any(
                                item.get("factId") == fact_id
                                for item in knowledge_facts
                                if isinstance(item, Mapping)
                            )
                        ):
                            continue
                        knowledge_facts.append(
                            _normalise_knowledge_fact(
                                raw_fact,
                                fact_id=fact_id,
                                npc_id=canonical_npc_id,
                                source_mod=layer,
                                summary=summary,
                                scope=scope,
                            )
                        )

                for position, raw_relation in enumerate(
                    _structured_list(raw_persona.get("knownCharacters"))
                ):
                    if isinstance(raw_relation, str):
                        continue
                    known_npc_id = str(
                        raw_relation.get("knownNpcId", raw_relation.get("subjectNpcId", ""))
                    ).strip()
                    summary = str(raw_relation.get("summary", "")).strip()
                    scope = str(
                        raw_relation.get("knowledgeScope", "canon_confirmed")
                    ).strip()
                    if (
                        not known_npc_id
                        or not summary
                        or scope.casefold() not in _ALLOWED_KNOWLEDGE_SCOPES
                    ):
                        continue
                    relation_id = str(
                        raw_relation.get(
                            "relationId",
                            f"{canonical_npc_id}:knows:{known_npc_id}:{position}",
                        )
                    ).strip()
                    if any(
                        item.get("relationId") == relation_id
                        for item in known_characters
                        if isinstance(item, Mapping)
                    ):
                        continue
                    known_characters.append(
                        _normalise_known_character(
                            raw_relation,
                            relation_id=relation_id,
                            npc_id=canonical_npc_id,
                            known_npc_id=known_npc_id,
                            source_mod=layer,
                            summary=summary,
                            scope=scope,
                        )
                    )

                for position, raw_event in enumerate(
                    _structured_list(raw_persona.get("storyEvents"))
                ):
                    if isinstance(raw_event, str):
                        continue
                    event_id = str(raw_event.get("eventId", "")).strip()
                    summary = str(raw_event.get("summary", "")).strip()
                    if not event_id or not summary:
                        continue
                    participants = raw_event.get("participants", [canonical_npc_id])
                    if isinstance(participants, str):
                        participants = [participants]
                    if not isinstance(participants, Iterable):
                        participants = [canonical_npc_id]
                    participant_ids = list(
                        dict.fromkeys(
                            canonical_npc_id_value
                            for canonical_npc_id_value in (
                                str(item).strip()
                                for item in participants
                                if str(item).strip()
                            )
                        )
                    )
                    if canonical_npc_id.casefold() not in {
                        item.casefold() for item in participant_ids
                    }:
                        participant_ids.insert(0, canonical_npc_id)
                    if any(
                        item.get("eventId") == event_id
                        for item in story_events
                        if isinstance(item, Mapping)
                    ):
                        continue
                    story_events.append(
                        {
                            "eventId": event_id,
                            "sourceMod": layer,
                            "sourceKey": str(raw_event.get("sourceKey", "")).strip(),
                            "participants": participant_ids,
                            "status": str(raw_event.get("status", "pending")).strip()
                            or "pending",
                            "summary": summary,
                            "canonical": bool(raw_event.get("canonical", True)),
                            **(
                                {"requiredEventId": str(raw_event["requiredEventId"]).strip()}
                                if str(raw_event.get("requiredEventId", "")).strip()
                                else {}
                            ),
                        }
                    )

    def _load_mod_root(
        self,
        index: dict[str, object],
        root: Path,
        *,
        locale: str = "zh-CN",
    ) -> None:
        warnings = index["warnings"]
        sources = index["sources"]
        profiles = index["profiles"]
        samples = index["styleSamples"]
        speech_evidence = index["speechEvidence"]
        assert isinstance(warnings, list)
        assert isinstance(sources, list)
        assert isinstance(profiles, dict)
        assert isinstance(samples, list)
        assert isinstance(speech_evidence, list)
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
                warnings.append(f"invalid JSON: {root.name}/manifest.json")
        sources.append({"sourceMod": source_mod, "root": root.name})
        from .corpus import _load_i18n_catalogs

        i18n_catalogs = _load_i18n_catalogs(
            root,
            locale=locale,
            warnings=warnings,
        )

        for path in sorted(root.rglob("*.json"), key=lambda item: item.as_posix().casefold()):
            if path == manifest or path.name.casefold() in {"config.json"}:
                continue
            if any(part.casefold() == "i18n" for part in path.relative_to(root).parts):
                continue
            file_name = path.name.casefold()
            try:
                payload = _load_json(path)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                # 任意命名的 Content Patcher 文件也应被扫描；明显无关的坏 JSON
                # 不应把整个索引变成 warning，旧的 dialogue/content 文件仍保留诊断。
                if "dialogue" in file_name or file_name == "content.json":
                    warnings.append(
                        f"invalid JSON: {root.name}/{_relative_path(path, root)}"
                    )
                continue
            self._extract_dialogue_changes(
                payload,
                source_mod=source_mod,
                source_path=_relative_path(path, root),
                profiles=profiles,
                samples=samples,
                speech_evidence=speech_evidence,
                warnings=warnings,
                i18n_catalogs=i18n_catalogs,
                locale=locale,
            )

    @staticmethod
    def _extract_dialogue_changes(
        payload: Mapping[str, Any],
        *,
        source_mod: str,
        source_path: str,
        profiles: dict[str, dict[str, Any]],
        samples: list[dict[str, Any]],
        speech_evidence: list[dict[str, Any]],
        warnings: list[str],
        i18n_catalogs: Mapping[str, Mapping[str, Any]] | None = None,
        locale: str = "zh-CN",
    ) -> None:
        # 统一使用 corpus 提取器，确保离线导出与运行时索引的字段和条件一致。
        from .corpus import clean_dialogue_variants, extract_content_patcher_dialogue

        extracted, extracted_warnings = extract_content_patcher_dialogue(
            payload,
            source_mod=source_mod,
            source_path=source_path,
            i18n_catalogs=i18n_catalogs,
            locale=locale,
        )
        warnings.extend(extracted_warnings)
        for record in extracted:
            npc_id = str(record.get("npcId", "")).strip()
            if not npc_id:
                continue
            canonical_npc_id, profile = _get_or_create_profile(profiles, npc_id)
            if source_mod not in profile["sourceMods"]:
                profile["sourceMods"].append(source_mod)
            if source_path not in profile["sourceFiles"]:
                profile["sourceFiles"].append(source_path)
            raw_text = record.get("text")
            if not isinstance(raw_text, str) or not raw_text.strip():
                continue
            raw_variants = record.get("dialogueVariants")
            resolved_text = record.get("resolvedText")
            if isinstance(resolved_text, str) and resolved_text.strip():
                variants = clean_dialogue_variants(resolved_text)
            elif _UNRESOLVED_I18N.search(raw_text):
                # 未解析的 i18n 先保留占位符，供后续 corpus 的已解析文本按
                # sampleId 替换；检索层会过滤占位符，不把它当作可模仿对白。
                variants = [raw_text.strip()]
            elif isinstance(raw_variants, list):
                variants = [
                    cleaned
                    for variant in raw_variants
                    if isinstance(variant, str)
                    for cleaned in clean_dialogue_variants(variant)
                ]
            else:
                variants = clean_dialogue_variants(raw_text)
            if not variants:
                # 不把控制表达式、叙述分支或无效文本退回成可模仿的原文。
                continue
            for variant_index, variant_text in enumerate(dict.fromkeys(variants)):
                sample = dict(record)
                sample["sampleId"] = str(record.get("sampleId", "")).strip() or (
                    f"{source_mod}:{source_path}:{record.get('sourceKey', '')}"
                )
                if variant_index:
                    sample["sampleId"] += f":variant-{variant_index}"
                sample["npcId"] = canonical_npc_id
                sample["text"] = variant_text
                # 原始控制脚本仅保留在 corpus 审计文件，不进入派生索引。
                sample.pop("dialogueVariants", None)
                samples.append(sample)
                speech_evidence.append(dict(sample))


def _source_matches(candidate: object, source_mods: Iterable[str]) -> bool:
    return source_matches(candidate, source_mods)


def _behavior_source_matches(
    candidate_sources: object,
    source_mods: Iterable[str],
    *,
    npc_id: str = "",
) -> bool:
    """匹配行为示例来源，同时允许已确认的通用娘化样本回到 vanilla。"""

    if isinstance(candidate_sources, str):
        candidate_sources = [candidate_sources]
    if not isinstance(candidate_sources, Iterable):
        return True
    candidates = [
        str(item).strip()
        for item in candidate_sources
        if str(item).strip()
    ]
    if not candidates:
        return True
    if (
        any(source_family(candidate) == "femalebachelors" for candidate in candidates)
        and not is_female_bachelor_eligible(npc_id)
    ):
        return False
    source_mod_list = [
        str(item).strip()
        for item in source_mods
        if isinstance(item, str) and item.strip()
    ]
    if not source_mod_list:
        return False
    # Shane/Sebastian 的 female-bachelors 行为样本只记录通用的回应动作、
    # 句长和口语节奏，不包含娘化称谓或专属剧情。它们仍保留原始来源，
    # 但在未启用娘化包的 vanilla 场景也需要可用，否则普通评测场景会
    # 完全失去这层人工示范。原文 style/speech evidence 不走这条兼容路径。
    if any(source_family(candidate) == "femalebachelors" for candidate in candidates):
        if any(source_family(source) == "vanilla" for source in source_mod_list):
            return True
    return any(source_matches(candidate, source_mod_list) for candidate in candidates)


def _behavior_dimension_matches(
    record: Mapping[str, Any],
    field: str,
    requested: str,
) -> bool:
    if not requested:
        return True
    values = record.get(field)
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable):
        return True
    normalised = {
        str(value).strip().casefold()
        for value in values
        if str(value).strip()
    }
    return not normalised or "any" in normalised or requested.casefold() in normalised


_TOPIC_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("motorcycle", ("摩托车", "机车", "修车", "发动机", "骑车", "车库")),
    ("music", ("音乐", "乐队", "吉他", "鼓手", "演出", "曲子")),
    ("programming", ("编程", "代码", "程序", "电脑", "bug")),
    (
        "training",
        (
            "训练",
            "练",
            "锻炼",
            "健身",
            "跑步",
            "运动",
            "俯卧撑",
            "投球",
            "打球",
            "四分卫",
        ),
    ),
    ("chicken", ("鸡舍", "小鸡", "鸡", "饲料", "农场")),
    ("vineyard", ("葡萄园", "葡萄", "酿酒", "酒", "藤架", "采摘")),
    ("painting", ("画画", "绘画", "画作", "作品", "颜色")),
    (
        "writing",
        ("稿子", "稿", "写作", "写", "纸", "句子", "文字", "创作", "文章", "小说", "诗"),
    ),
    ("research", ("研究", "实验", "符文", "数据", "记录", "图书馆")),
    ("weather", ("天气", "下雨", "雨天", "雨", "风", "晴天")),
    ("food", ("咖啡", "早餐", "午饭", "吃饭", "食物", "披萨", "鸡蛋")),
)
_GENERIC_TOPIC_KEYWORDS = {
    "你好",
    "最近",
    "怎么样",
    "今天",
    "状态",
    "过得",
    "还好吗",
    "早上",
}

_MAGIC_EVIDENCE_MARKERS = (
    "魔法",
    "星界",
    "预兆",
    "符文",
    "咒语",
    "巫术",
    "观星",
    "占星",
    "灵魂",
    "黑暗",
    "元素",
    "实验",
)


def _matching_topic_groups(text: str) -> set[str]:
    folded = text.casefold()
    return {
        name
        for name, aliases in _TOPIC_ALIASES
        if any(alias.casefold() in folded for alias in aliases)
    }


def _topic_alias_group(keyword: str) -> str | None:
    folded = keyword.strip().casefold()
    for name, aliases in _TOPIC_ALIASES:
        if any(folded == alias.casefold() for alias in aliases):
            return name
    return None


def _longest_common_phrase_length(left: object, right: object) -> int:
    """返回两段输入中最长的连续中文/字母数字短语长度。"""

    if not isinstance(left, str) or not isinstance(right, str):
        return 0
    left_chars = [char.casefold() for char in left if char.isalnum()]
    right_chars = [char.casefold() for char in right if char.isalnum()]
    if not left_chars or not right_chars:
        return 0

    previous = [0] * (len(right_chars) + 1)
    longest = 0
    for left_char in left_chars:
        current = [0]
        for index, right_char in enumerate(right_chars, start=1):
            if left_char == right_char:
                current.append(previous[index - 1] + 1)
                longest = max(longest, current[-1])
            else:
                current.append(0)
        previous = current
    return longest


def _behavior_topic_score(record: Mapping[str, Any], player_input: str) -> int:
    if not player_input.strip():
        return 0
    folded_input = player_input.casefold()
    input_groups = _matching_topic_groups(player_input)
    keywords = record.get("topicKeywords", ())
    if isinstance(keywords, str):
        keywords = [keywords]
    if not isinstance(keywords, Iterable):
        return 0
    score = 0
    matched_groups: set[str] = set()
    exact_matches = 0
    for keyword in keywords:
        if not isinstance(keyword, str) or not keyword.strip():
            continue
        folded_keyword = keyword.strip().casefold()
        alias_group = _topic_alias_group(keyword)
        exact_match = folded_keyword in folded_input
        group_match = alias_group in input_groups
        if (
            input_groups
            and alias_group is None
            and folded_keyword in _GENERIC_TOPIC_KEYWORDS
        ):
            # “今天/最近/怎么样”只描述提问形式。输入已经含有明确话题时，
            # 这些词不能让 daily_status 抢走当前话题示例。
            continue
        if exact_match:
            # 实际出现在玩家输入中的短语比同组推断更可靠；同一个词组
            # 即使同时命中多个关键词，也只按一次具体短语计分；较长的
            # 具体对象/状态词比“现在”等形式词更有区分度。
            exact_matches += 1
            score += 2 + min(max(len(folded_keyword) - 1, 0), 4)
        if group_match and alias_group not in matched_groups:
            # 同一话题组只计一次，避免“编程/代码/程序/电脑”因样本字段
            # 更长而压过真正更具体的调试或邀约示例。
            matched_groups.add(alias_group)
            score += 3
    if input_groups and not matched_groups and exact_matches == 0:
        return 0
    # 连续共同短语比孤立共享名词更能表示玩家真正的意图：例如“改天一起”
    # 应压过仅因“记录”命中的整理工作示例。长度为 1 的共同字不计分，
    # 避免“吗/的/了”等语气字把无关示例抬高。
    common_phrase_length = _longest_common_phrase_length(
        player_input,
        record.get("playerInput"),
    )
    if common_phrase_length >= 2:
        score += max(0, common_phrase_length - 1) * 4
    return score


def _evidence_topic_score(record: Mapping[str, Any], player_input: str) -> int:
    """把当前输入命中的话题原文排在无关兴趣样本前。"""

    input_groups = _matching_topic_groups(player_input)
    if not input_groups:
        return 0
    folded_input = player_input.casefold()
    evidence_text = " ".join(
        str(record.get(field, ""))
        for field in ("text", "sourceKey")
    ).casefold()
    score = 0
    for name, aliases in _TOPIC_ALIASES:
        if name not in input_groups:
            continue
        input_aliases = {
            alias.casefold()
            for alias in aliases
            if alias.casefold() in folded_input
        }
        evidence_aliases = {
            alias.casefold()
            for alias in aliases
            if alias.casefold() in evidence_text
        }
        exact_aliases = input_aliases & evidence_aliases
        if exact_aliases:
            # 玩家明确提到的词优先于同一话题组里的邻近词，例如“葡萄”
            # 应排在只提到“酒吧”的台词之前。
            score += 8 + sum(min(len(alias), 6) for alias in exact_aliases)
        elif evidence_aliases:
            score += 2
    return score


def _unrelated_magic_priority(record: Mapping[str, Any], player_input: str) -> int:
    """未被当前输入点名的魔法样本排在普通日常样本之后。"""

    folded_input = player_input.casefold()
    if any(marker.casefold() in folded_input for marker in _MAGIC_EVIDENCE_MARKERS):
        return 0
    evidence_text = " ".join(
        str(record.get(field, ""))
        for field in ("text", "sourceKey")
    ).casefold()
    return int(
        any(marker.casefold() in evidence_text for marker in _MAGIC_EVIDENCE_MARKERS)
    )


def _source_priority(source_mod: object) -> int:
    marker = _normalise_marker(source_mod)
    if marker == "vanilla":
        return 10
    if any(token in marker for token in ("rasmodia", "romras", "romanceablerasmodius")):
        return 30
    if "sve" in marker or "flashshifter" in marker:
        return 20
    return 0


def _relationship_stage_matches(
    record: Mapping[str, Any],
    relationship_stage: str,
    *,
    allow_lower_stage: bool = False,
) -> bool:
    """这条记录能不能用在当前关系阶段；判定统一在 `dialogue_stage`。

    2026-09-20（语义层审计 P1 第 25 条）：这里此前是「阶段条件是否适用」的
    三套判定之一（另外两套在 `speech`），而且它与 `_relationship_specificity_priority`
    各自读一次 `conditions`、各自推断一次。现在读取、推断、匹配、排序都从
    `dialogue_stage` 派生，本函数只声明自己用哪种应用方式：

    - 头一次尝试（`allow_lower_stage=False`）→ `at_most_present`，但**排除
      stranger**：允许复用更早阶段的日常对白（朋友阶段可以借用相识阶段原话），
      但不退回无心级的初识寒暄；
    - 明确话题没有当前阶段命中时的回退（`allow_lower_stage=True`）→ 连
      stranger 一起算进候选。
    """

    return stage_hint_applies(
        record,
        relationship_stage,
        policy="at_most_present",
        infer=True,
        include_stranger=allow_lower_stage,
    )


def _relationship_specificity_priority(
    record: Mapping[str, Any],
    relationship_stage: str,
) -> int:
    """同阶段对白优先于没有阶段条件的特殊场景对白。"""

    if _is_event_dialogue_record(record):
        # 这里的事件素材已经通过 completed_event_ids 闸门；既然它是角色
        # 真实经历，就应先于婚后/日常锚点进入窗口，随后仍由事件配额限量。
        return 0
    return sample_stage_specificity(record, relationship_stage)


def _evidence_priority(record: Mapping[str, Any]) -> int:
    """运行时实况优先于静态候选，但保留静态样本作为补充。"""

    return 0 if record.get("evidenceKind") == "runtime_dialogue" else 1


def _is_event_dialogue_record(record: Mapping[str, Any]) -> bool:
    return str(record.get("evidenceKind", "")).strip().casefold() == "event_dialogue"


def _event_dialogue_is_completed(
    record: Mapping[str, Any],
    completed_event_ids: set[str],
) -> bool:
    """事件对白只能在游戏状态确认该事件后进入生成证据。

    2026-09-20（语义层审计 #28）：此前这里**必须**由 `sourceMod` 合成前缀
    （`Vanilla:56`）才认，而 `relationship_gating` 认的是「两边都能带前缀」。
    现在统一到共享实现；`sourceMod` 仍然参与，但不再是非它不可的额外门槛。
    """

    if not _is_event_dialogue_record(record):
        return True
    event_id = str(record.get("eventId", "")).strip().casefold()
    if not event_id or not completed_event_ids:
        return False
    source_mod = str(record.get("sourceMod", "")).strip().casefold()
    accepted = {event_id}
    if source_mod:
        accepted.add(f"{source_mod}:{event_id}")
    return any(
        game_event_completed(candidate, completed_event_ids)
        for candidate in accepted
    )


def _dialogue_path_priority(record: Mapping[str, Any]) -> int:
    """把日常对白排在事件文案前，避免有限样本窗口被剧情独白占满。"""

    path = str(record.get("sourcePath", "")).replace("\\", "/").casefold()
    if path.startswith("characters/dialogue/"):
        return 0
    if "/dialogue/standard/" in path or "/dialogue/integrated/" in path:
        return 0
    if "/dialogue/shared" in path:
        return 1
    if "/dialogue/festival" in path:
        return 2
    if "/dialogue/" in path:
        return 2
    if "/events/" in path or path.startswith("events/"):
        return 4
    if "/code/" in path or path.startswith("code/"):
        return 4
    return 3


_WEEKDAY_DIALOGUE_KEY = re.compile(r"^(?:mon|tue|wed|thu|fri|sat|sun)$")
_WEEKDAY_VARIANT_DIALOGUE_KEY = re.compile(
    r"^(?:mon|tue|wed|thu|fri|sat|sun)\d+$",
)
_RELATION_DIALOGUE_KEY = re.compile(r"^(?:neutral|good|bad)_\d+$")
_SEASON_DIALOGUE_KEY = re.compile(
    r"^(?:spring|summer|fall|winter)(?:_|$)",
    re.IGNORECASE,
)
_EVENT_DIALOGUE_KEY = re.compile(
    r"^(?:event|festival|flowerdance|eggfestival|luau|moonlightjellies|stardewvalleyfair|spiritseve|winterstar|wedding|married|roommate|divorced)",
    re.IGNORECASE,
)
_SPECIAL_SCENE_DIALOGUE_KEY = re.compile(
    r"^(?:breakup|dumped|secondchance|movieinvitation|dumpster|fair_|"
    r"hitbyslingshot|spouse|wipedmemory)",
    re.IGNORECASE,
)
_GIFT_DIALOGUE_KEY = re.compile(
    r"(?:accept(?:_|$)|gift|birthday|bouquet|mermaid|stardrop|spousegift|give_flowers)",
    re.IGNORECASE,
)
_TRIGGERED_DIALOGUE_KEY = re.compile(
    r"^(?:greenrain|resort|desertfestival|firstvisit(?:_|$)|"
    r"fishcaught(?:_|$)|cropmatured(?:_|$)|purchasedanimal(?:_|$)|"
    r"achievement(?:_|$)|animalshop(?:_|$)|communitycenter(?:_|$)|"
    r"busstop(?:_|$)|cc_|city_|apples_|"
    r"claire_event(?:_|$)|custom_|bluemoonvineyard(?:_|$)|"
    r"archaeologyhouse(?:_|$)|forest(?:west)?(?:_|$)|mountain(?:_|$)|"
    r"beach(?:_|$)|pamhouseupgrade(?:_|$))",
    re.IGNORECASE,
)
_MEMORY_DIALOGUE_KEY = re.compile(r"(?:^|_)memory(?:_|$)", re.IGNORECASE)
_RELATIONSHIP_ONLY_DIALOGUE_KEY = re.compile(
    r"^(?:dating|engage|engaged|give_pendant|reject|refusal|dance(?:_|)rejection)",
    re.IGNORECASE,
)
_RELATION_RESPONSE_KEY = re.compile(
    r"^(?:neutral|good|bad)(?:_\d+)?$",
    re.IGNORECASE,
)


def _is_model_evidence_record(record: Mapping[str, Any]) -> bool:
    """只把可脱离特殊触发条件的静态对白放入模型证据窗口。"""
    return _shared_is_model_evidence_record(record)


def _dialogue_key_priority(record: Mapping[str, Any]) -> int:
    """同一文件内优先平日/关系短句，再取季节与事件台词。"""

    if _is_event_dialogue_record(record):
        # 已完成事件是角色真实经历的高代表性语料；它进入 speechEvidence
        # 时排在普通日常之前，但由 _select_evidence_candidates 限量，
        # 不让一整段剧情独占窗口。
        return 0
    key = str(record.get("sourceKey", "")).strip().casefold()
    if _dialogue_path_priority(record) >= 4:
        return 5
    if _WEEKDAY_DIALOGUE_KEY.fullmatch(key):
        return 0
    if _RELATION_DIALOGUE_KEY.fullmatch(key):
        return 1
    if key == "introduction":
        return 2
    if _EVENT_DIALOGUE_KEY.match(key):
        return 5
    if _SEASON_DIALOGUE_KEY.match(key):
        return 4
    if _WEEKDAY_VARIANT_DIALOGUE_KEY.fullmatch(key):
        return 3
    return 2


_GENERIC_SMALL_TALK_PHRASES = {
    "你好",
    "早上",
    "早上好",
    "最近",
    "怎么样",
    "今天",
    "状态",
    "过得",
    "还好吗",
    "最近怎么样",
}


def _is_generic_small_talk_input(player_input: str) -> bool:
    remaining = str(player_input).strip()
    if not remaining:
        return False
    for phrase in sorted(_GENERIC_SMALL_TALK_PHRASES, key=len, reverse=True):
        remaining = remaining.replace(phrase, "")
    remaining = re.sub(r"[，。！？!?、；;：:,\.\s]", "", remaining)
    return not remaining


def _dialogue_selection_key_priority(
    record: Mapping[str, Any], player_input: str
) -> int:
    """泛日常生成时把覆盖层 Introduction 留给无普通日常对白的情况。"""

    if _is_event_dialogue_record(record):
        return -1
    if (
        _is_generic_small_talk_input(player_input)
        and str(record.get("sourceKey", "")).strip().casefold() == "introduction"
    ):
        return 4
    return _dialogue_key_priority(record)

# 「内容分档」与索引原序压成同一个整数的步长。
#
# 候选元组的最后一位是 sample 本身（dict 不可比较，必须留在末尾），
# 所以**不能**把新字段追加在它前面 —— 那会让 sample 的下标从 8 变成 9，
# 牵连本文件 10 处 `item[8]` 取用点。压成一个整数则元组形状与全部下标稳定。
# 约束：索引总条数必须 < 该步长，否则档位会串。实测本索引 10213 条
# （索菲亚最大下标 10195），余量充足。
_EVIDENCE_CONTENT_STRIDE = 1_000_000

# 内容分档的字符长度阈值。
_EVIDENCE_CONTENT_MIN_CHARS = 8
_EVIDENCE_CONTENT_RICH_CHARS = 30


def _evidence_content_priority(sample: Mapping[str, Any]) -> int:
    """按文本长度给候选分档：0 = 有实质内容，1 = 普通，2 = 纯应答语。

    为什么需要：`_select_evidence_candidates` 的七个排序键在 topic 路径下
    经常**全部并列**（没有本轮玩家输入 ⇒ 话题分为 0；同阶段 ⇒ 具体度相同；
    同为静态语料 ⇒ 证据优先级相同），此时唯一区分度是 `original_index`
    —— 那是**索引里的物理位置，与内容质量无关**。

    实测后果（2026-09-23）：索菲亚的 `speech_evidence` 永远取到 eventId
    `5000009` 里的应答语（「嗨，伙计们！」「嘿！」「好耶！」「！！！」），
    而她真正有内容的句子（祖祖城动漫展、Cosplay、《粉红公主十字军》、
    父母遗产）躺在 `idx 7134-7541`，永远取不到。

    分档只作为 `original_index` **之前**的次级键：不改变任何既有优先级
    （阶段、来源、路径、来源配额都照旧），只在原本并列的候选之间让有内容的
    排前面；档内仍保持索引原序，因此结果稳定可复现。
    """

    text = sample.get("text")
    length = len(text.strip()) if isinstance(text, str) else 0
    if length >= _EVIDENCE_CONTENT_RICH_CHARS:
        return 0
    if length >= _EVIDENCE_CONTENT_MIN_CHARS:
        return 1
    return 2


def _evidence_order_key(sample: Mapping[str, Any], original_index: int) -> int:
    """把「内容分档」与「索引原序」压成一个可比较整数，保持元组形状不变。

    效果等价于在 `original_index` 前插入一个 `_evidence_content_priority`
    字段（分档优先、档内按原序），但元组长度与 `item[8]` 下标全部不变。
    """

    return (
        _evidence_content_priority(sample) * _EVIDENCE_CONTENT_STRIDE
        + int(original_index)
    )

def _select_evidence_candidates(
    candidates: list[tuple[int, int, int, int, int, int, int, int, dict[str, Any]]],
    capped_limit: int,
) -> list[dict[str, Any]]:
    """保留稳定日常节奏，同时给已启用的 Mod 来源留出证据位。"""

    ranked = sorted(candidates)
    # 同一句对白可能同时来自 integrated/standard 文件，或在旧索引中
    # 以多个 sampleId 保留。它们对模型提供的是同一份证据，必须先去重，
    # 再执行来源配额，否则覆盖层会用重复文本挤掉原版日常节奏。
    unique_ranked: list[
        tuple[int, int, int, int, int, int, int, int, dict[str, Any]]
    ] = []
    seen_texts: set[str] = set()
    for item in ranked:
        text = " ".join(str(item[8].get("text", "")).split()).casefold()
        if text and text in seen_texts:
            continue
        if text:
            seen_texts.add(text)
        unique_ranked.append(item)
    ranked = unique_ranked

    def bounded_event_results(
        items: list[tuple[int, int, int, int, int, int, int, int, dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        event_cap = min(3, max(1, capped_limit // 3))
        selected: list[dict[str, Any]] = []
        event_count = 0
        for item in items:
            if _is_event_dialogue_record(item[8]):
                if event_count >= event_cap:
                    continue
                event_count += 1
            selected.append(item[8])
            if len(selected) >= capped_limit:
                break
        return selected

    if any(item[0] < 0 for item in ranked):
        # 只要当前输入已经命中明确话题，就让话题相关性优先于来源配额。
        # 否则覆盖层的 Introduction 可能挤掉 vanilla 中真正回答“研究”、
        # “训练”等问题的日常对白，模型拿到的证据就会再次偏题。
        return bounded_event_results(ranked)
    source_specific = [
        item for item in ranked
        # 候选元组已经保存了完整原记录的 key/path 优先级；这里不能再从
        # 为返回值裁剪过的 item[8] 读取 sourcePath，否则 style/speech 字段
        # 不含审计路径时会把所有覆盖层误判成普通路径。
        if _normalise_marker(item[8].get("sourceMod")) != "vanilla"
        and (
            item[4] <= 3
            # 已完成事件是高代表性的经历素材，不能被来源配额在这里
            # 直接筛掉；bounded_event_results 仍会限制它最多占窗口约三分之一。
            or _is_event_dialogue_record(item[8])
        )
        # path=3 也表示未提供路径的合成/旧索引记录；只要 key 仍是
        # 普通对白，就不能因为缺少审计路径而丢掉覆盖层的语气证据。
        # 事件/代码路径仍为 4，且 key 优先级会另外排除季节与特殊触发。
        and (
            item[5] <= 3
            or _is_event_dialogue_record(item[8])
        )
    ]
    vanilla_fallback = [
        item for item in ranked
        if _normalise_marker(item[8].get("sourceMod")) == "vanilla"
    ]
    if not source_specific or not vanilla_fallback:
        return bounded_event_results(ranked)

    if len(ranked) <= capped_limit:
        # 即使候选总数没有超过窗口，也要让当前启用的覆盖层先于原版
        # 进入模型上下文；否则同样数量的 vanilla 日常样本会把覆盖层
        # 的语言风格推到原文证据之后。
        return bounded_event_results(source_specific + vanilla_fallback)

    # 证据窗口不能被 vanilla 周对白完全占满；同时只预留少量覆盖层，
    # 避免事件/季节长文案完全替代原版的日常节奏。
    reserved = min(len(source_specific), max(1, min(3, capped_limit // 2)))
    selected = source_specific[:reserved] + vanilla_fallback[:capped_limit - reserved]
    if len(selected) < capped_limit:
        selected.extend(source_specific[reserved:capped_limit - len(selected) + reserved])
    # 保留“先覆盖层、后 vanilla”的配额顺序。再次按完整排序键合并会让
    # 日常 vanilla 样本重新压过季节/事件形式的覆盖层证据。
    return bounded_event_results(selected)


def _dialogue_condition_label(record: Mapping[str, Any]) -> str:
    conditions = record.get("conditions")
    if isinstance(conditions, Mapping):
        stage = conditions.get("relationshipStage", conditions.get("relationship_stage"))
        if isinstance(stage, str) and stage.strip():
            return stage.strip().casefold()
    from .corpus import infer_dialogue_conditions

    inferred_stage = infer_dialogue_conditions(
        str(record.get("sourcePath", "")),
        str(record.get("sourceKey", "")),
    ).get("relationshipStage", "").strip().casefold()
    return inferred_stage or "unconditional"


def _normalise_dialogue_provenance(record: Mapping[str, Any]) -> dict[str, Any]:
    """为旧派生索引补齐婚后对白的证据类型和阶段条件。"""

    result = dict(record)
    from .corpus import classify_dialogue_target, infer_dialogue_conditions

    source_path = str(result.get("sourcePath", ""))
    source_key = str(result.get("sourceKey", ""))
    _, inferred_kind = classify_dialogue_target(source_path)
    current_kind = str(result.get("evidenceKind", "")).strip().casefold()
    if inferred_kind in {"marriage_dialogue", "roommate_dialogue"} and current_kind in {
        "",
        "dialogue",
    }:
        result["evidenceKind"] = inferred_kind
    conditions = result.get("conditions")
    has_stage = isinstance(conditions, Mapping) and any(
        str(key).casefold() in {"relationshipstage", "relationship_stage"}
        and isinstance(value, str)
        and value.strip()
        for key, value in conditions.items()
    )
    if not has_stage:
        inferred_conditions = infer_dialogue_conditions(source_path, source_key)
        if inferred_conditions:
            merged_conditions = (
                dict(conditions) if isinstance(conditions, Mapping) else {}
            )
            merged_conditions.update(inferred_conditions)
            result["conditions"] = merged_conditions
    return result


def _representative_source_family(record: Mapping[str, Any]) -> str:
    """把同一 Mod 的不同加载标记归并，避免代表区重复占用来源位。"""

    marker = _normalise_marker(record.get("sourceMod"))
    return source_family(marker)


def _representative_category(record: Mapping[str, Any]) -> str:
    """给日常原文分桶，保证置顶区不被同一种 sourceKey 占满。"""

    key = str(record.get("sourceKey", "")).strip().casefold()
    if key == "introduction":
        return "introduction"
    if _WEEKDAY_DIALOGUE_KEY.fullmatch(key):
        return "weekday"
    if _RELATION_DIALOGUE_KEY.fullmatch(key):
        return "relationship"
    if _WEEKDAY_VARIANT_DIALOGUE_KEY.fullmatch(key):
        return "weekday_variant"
    return "other_daily"


def _select_representative_dialogues(
    records: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """从完整原文中稳定选出少量参照，不把事件/来源误当成唯一口吻。"""

    if limit <= 0 or not records:
        return []
    ranked = sorted(
        enumerate(records),
        key=lambda item: (
            _dialogue_key_priority(item[1]),
            _dialogue_path_priority(item[1]),
            _evidence_priority(item[1]),
            _source_priority(item[1].get("sourceMod")),
            item[0],
        ),
    )
    selected: list[dict[str, Any]] = []
    selected_sources: set[str] = set()
    selected_stages: set[str] = set()
    selected_categories: set[str] = set()
    selected_texts: set[str] = set()

    general = [
        item
        for item in ranked
        if str(item[1].get("evidenceKind", "")).strip().casefold()
        not in {"marriage_dialogue", "roommate_dialogue", "event_dialogue"}
        and _is_model_evidence_record(item[1])
        and _dialogue_key_priority(item[1]) <= 3
    ]
    special = [item for item in ranked if item not in general]

    # 第一遍只从可脱离特殊触发条件的日常对白中覆盖来源/阶段，
    # 防止婚后、事件或季节文案抢占“这个角色平时怎么说话”的参照位。
    def add_if_diverse(record: dict[str, Any], *, require_diversity: bool) -> bool:
        source = _representative_source_family(record)
        stage = _dialogue_condition_label(record)
        category = _representative_category(record)
        text = str(record.get("text", "")).strip().casefold()
        if text in selected_texts:
            return False
        if require_diversity and source in selected_sources and stage in selected_stages:
            return False
        selected.append(record)
        selected_sources.add(source)
        if stage:
            selected_stages.add(stage)
        selected_categories.add(category)
        selected_texts.add(text)
        return len(selected) >= limit

    def add_first_matching(predicate: Any) -> bool:
        for _, record in general:
            if not predicate(record):
                continue
            previous_count = len(selected)
            reached_limit = add_if_diverse(record, require_diversity=False)
            if len(selected) > previous_count:
                return reached_limit
        return False

    # 先确保代表区至少能看见几种不同的日常表达结构，再按来源和关系阶段扩展。
    for category in (
        "weekday",
        "relationship",
        "introduction",
        "weekday_variant",
        "other_daily",
    ):
        if add_first_matching(
            lambda record, expected=category: _representative_category(record)
            == expected
        ):
            return selected

    source_families: list[str] = []
    for _, record in general:
        source = _representative_source_family(record)
        if source not in source_families:
            source_families.append(source)
    for source in source_families:
        if add_first_matching(
            lambda record, expected=source: _representative_source_family(record)
            == expected
        ):
            return selected

    for stage in (
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
        "parent",
        "unconditional",
    ):
        if add_first_matching(
            lambda record, expected=stage: _dialogue_condition_label(record)
            == expected
        ):
            return selected

    for _, record in general:
        if add_if_diverse(record, require_diversity=True):
            return selected
    for _, record in general:
        if add_if_diverse(record, require_diversity=False):
            return selected
    for _, record in special:
        if add_if_diverse(record, require_diversity=True):
            return selected

    # 来源/阶段不足时再按稳定排序补齐，仍然不重复完全相同的文本。
    for _, record in ranked:
        if add_if_diverse(record, require_diversity=False):
            break
    return selected


class ProfileIndexStore:
    """只读检索派生索引，并把来源路径等构建元数据隔离在 Bridge 外。"""

    _STYLE_FIELDS = (
        "sampleId",
        "npcId",
        "sourceMod",
        "sourceKey",
        "text",
        "evidenceKind",
        "eventId",
        "eventLineIndex",
        "eventConditions",
        "participants",
    )
    _EVENT_FIELDS = (
        "eventId",
        "sourceMod",
        "sourceKey",
        "participants",
        "status",
        "gameDate",
        "summary",
        "canonical",
        "requiredEventId",
    )
    _SPEECH_FIELDS = (
        "sampleId",
        "npcId",
        "sourceMod",
        "sourceKey",
        "text",
        "evidenceKind",
        "conditions",
        "eventId",
        "eventLineIndex",
        "eventConditions",
        "participants",
    )
    _REFERENCE_FIELDS = (
        "sampleId",
        "npcId",
        "sourceMod",
        "sourcePath",
        "sourceKey",
        "text",
        "evidenceKind",
        "conditions",
        "eventId",
        "eventLineIndex",
        "eventConditions",
        "participants",
    )
    _FACT_FIELDS = (
        "factId",
        "npcId",
        "sourceMod",
        "summary",
        "knowledgeScope",
        "confidence",
        "sourceRefs",
        "requiredEventId",
        # 常驻标记（专有名词：宠物及其名字、家人、地名、角色自己的物件）。
        # 这是**第三处**同型白名单：数据侧标了 `alwaysOn`，只要 `_FACT_FIELDS`
        # 或 `prompts._compact_knowledge_fact` 有一处没列它，标记就会静默消失，
        # 事实退回普通通道、又被 `knowledgeFacts[:1]` 切片挡住 —— 表面上数据
        # "写进去了"，行为上一点没变。改数据形态时三处都要一起动。
        "alwaysOn",
    )
    _KNOWN_CHARACTER_FIELDS = (
        "relationId",
        "npcId",
        "knownNpcId",
        "relation",
        "summary",
        "sourceMod",
        "knowledgeScope",
        "confidence",
        "sourceRefs",
        "requiredEventId",
    )
    _BEHAVIOR_FIELDS = (
        "exampleId",
        "npcId",
        "sourceMods",
        "channels",
        "relationshipStages",
        "speechFunction",
        "topic",
        "topicKeywords",
        "emotion",
        "playerInput",
        "npcReply",
        "sourceType",
        "sourceRefs",
        "initiativeExpectation",
        "initiativeKind",
    )

    def __init__(self, index_path: str | Path) -> None:
        self.index_path = Path(index_path)
        self._index = self._load()

    def npc_catalog(self) -> list[dict[str, Any]]:
        """返回索引中的完整 NPC 目录，不按恋爱资格裁剪。"""

        catalog: dict[str, dict[str, Any]] = {}

        def ensure(raw_npc_id: object) -> dict[str, Any] | None:
            npc_id = canonical_npc_id(raw_npc_id)
            if not _is_catalog_npc_id(npc_id):
                return None
            key = npc_id.casefold()
            if key not in catalog:
                catalog[key] = {
                    "npcId": npc_id,
                    "displayName": npc_id,
                    "sourceMods": [],
                    "hasDialogueEvidence": False,
                }
            return catalog[key]

        profiles = self._index.get("profiles", {})
        if isinstance(profiles, Mapping):
            for profile_key, raw_profile in profiles.items():
                if not isinstance(raw_profile, Mapping):
                    raw_profile = {}
                entry = ensure(raw_profile.get("npcId", profile_key))
                if entry is None:
                    continue
                display_name = raw_profile.get("displayName")
                if isinstance(display_name, str) and display_name.strip():
                    entry["displayName"] = display_name.strip()
                _append_source_mods(entry, raw_profile.get("sourceMods", ()))
                entry["hasDialogueEvidence"] = bool(
                    entry["hasDialogueEvidence"]
                    or raw_profile.get("hasDialogueEvidence", False)
                )

        for field_name in ("styleSamples", "speechEvidence"):
            records = self._index.get(field_name, [])
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                entry = ensure(record.get("npcId", ""))
                if entry is None:
                    continue
                _append_source_mods(entry, [record.get("sourceMod")])
                text = record.get("text")
                entry["hasDialogueEvidence"] = bool(
                    entry["hasDialogueEvidence"]
                    or isinstance(text, str)
                    and bool(text.strip())
                )

        voice_cards = self._index.get("voiceCards", {})
        if isinstance(voice_cards, Mapping):
            for card_key, raw_card in voice_cards.items():
                raw_card = raw_card if isinstance(raw_card, Mapping) else {}
                entry = ensure(raw_card.get("npcId", card_key))
                if entry is None:
                    continue
                _append_source_mods(entry, [raw_card.get("sourceMod")])

        return sorted(
            catalog.values(),
            key=lambda item: (
                str(item.get("displayName", "")).casefold(),
                str(item.get("npcId", "")).casefold(),
            ),
        )

    def style_samples(
        self,
        npc_id: str,
        source_mods: Iterable[str],
        limit: int = 8,
        *,
        relationship_stage: str = "",
        player_input: str = "",
    ) -> list[dict[str, Any]]:
        if not isinstance(npc_id, str) or not npc_id.strip():
            return []
        canonical_id = canonical_npc_id(npc_id)
        capped_limit = max(0, min(int(limit), _STYLE_SAMPLE_CANDIDATES))
        if capped_limit == 0:
            return []
        source_mod_list = tuple(source_mods)

        def collect_candidates(
            *, allow_lower_stage: bool = False
        ) -> list[tuple[int, int, int, int, int, int, int, int, dict[str, Any]]]:
            candidates: list[
                tuple[int, int, int, int, int, int, int, int, dict[str, Any]]
            ] = []
            for original_index, raw_sample in enumerate(
                self._index.get("styleSamples", [])
            ):
                if not isinstance(raw_sample, Mapping):
                    continue
                raw_sample = _normalise_dialogue_provenance(raw_sample)
                if (
                    canonical_npc_id(raw_sample.get("npcId", "")).casefold()
                    != canonical_id.casefold()
                ):
                    continue
                if not _source_matches(raw_sample.get("sourceMod"), source_mod_list):
                    continue
                if not _relationship_stage_matches(
                    raw_sample,
                    relationship_stage,
                    allow_lower_stage=allow_lower_stage,
                ):
                    continue
                text = raw_sample.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                if has_dialogue_control_residue(text):
                    continue
                if _UNRESOLVED_I18N.search(text):
                    # 原始索引保留模板供审计，但模板不是可模仿的实际台词。
                    continue
                if not _is_model_evidence_record(raw_sample):
                    continue
                candidates.append(
                    (
                        -_evidence_topic_score(raw_sample, player_input),
                        _relationship_specificity_priority(
                            raw_sample, relationship_stage
                        ),
                        _evidence_priority(raw_sample),
                        _unrelated_magic_priority(raw_sample, player_input),
                        _dialogue_selection_key_priority(raw_sample, player_input),
                        _dialogue_path_priority(raw_sample),
                        -_source_priority(raw_sample.get("sourceMod")),
                        _evidence_order_key(raw_sample, original_index),
                        self._canonicalize_selected_npc(
                            self._select_fields(raw_sample, self._STYLE_FIELDS)
                        ),
                    )
                )
            return candidates

        candidates = collect_candidates()
        has_vanilla_base = any(
            source_family(item[8].get("sourceMod")) == "vanilla"
            for item in candidates
        )
        if not has_vanilla_base and any(
            source_family(marker) == "vanilla" for marker in source_mod_list
        ):
            # 高关系阶段的覆盖层可能有婚后/家庭台词，但没有可用的日常
            # 基底。此时只把 vanilla 的较早阶段日常对白作为语气回退，
            # 保留当前阶段的覆盖层事实，不让覆盖层吞掉原版口吻。
            candidates.extend(
                item
                for item in collect_candidates(allow_lower_stage=True)
                if source_family(item[8].get("sourceMod")) == "vanilla"
            )
        return _select_evidence_candidates(candidates, capped_limit)

    def story_events(
        self,
        npc_id: str,
        source_mods: Iterable[str],
        limit: int = 8,
        completed_event_ids: Iterable[str] = (),
    ) -> list[dict[str, Any]]:
        if not isinstance(npc_id, str) or not npc_id.strip():
            return []
        canonical_id = canonical_npc_id(npc_id)
        capped_limit = max(0, min(int(limit), 8))
        if capped_limit == 0:
            return []
        completed_keys = {
            value.strip().casefold()
            for value in completed_event_ids
            if isinstance(value, str) and value.strip()
        }
        result: list[dict[str, Any]] = []
        for raw_event in self._index.get("storyEvents", []):
            if not isinstance(raw_event, Mapping):
                continue
            participants = raw_event.get("participants", ())
            if not isinstance(participants, list) or not any(
                isinstance(participant, str)
                and canonical_npc_id(participant).casefold()
                == canonical_id.casefold()
                for participant in participants
            ):
                continue
            if not _source_matches(raw_event.get("sourceMod"), source_mods):
                continue
            # 2026-09-20（语义层审计 #28）：四处门控统一到 relationship_gating
            # 的宽口径 —— 命名空间前缀两个方向都认，分隔符差异容忍。
            required_event = raw_event.get("requiredEventId")
            if isinstance(required_event, str) and required_event.strip():
                if not game_event_completed(required_event, completed_keys):
                    continue
            selected = self._select_fields(raw_event, self._EVENT_FIELDS)
            event_ids = [
                str(raw_event.get(field, "")).strip()
                for field in ("eventId", "sourceKey")
                if raw_event.get(field)
            ]
            if any(
                game_event_completed(event_id, completed_keys)
                for event_id in event_ids
            ):
                selected["status"] = "completed"
            result.append(selected)
            if len(result) >= capped_limit:
                break
        return result

    def known_characters(
        self,
        npc_id: str,
        source_mods: Iterable[str],
        *,
        limit: int = 8,
        completed_event_ids: Iterable[str] = (),
        allowed_scopes: Iterable[str] = (
            "canon_confirmed",
            "runtime_confirmed",
            "player_provided",
        ),
    ) -> list[dict[str, Any]]:
        if not isinstance(npc_id, str) or not npc_id.strip():
            return []
        canonical_id = canonical_npc_id(npc_id)
        capped_limit = max(0, min(int(limit), 8))
        if capped_limit == 0:
            return []
        scope_keys = {
            str(scope).strip().casefold()
            for scope in allowed_scopes
            if str(scope).strip()
        }
        completed_keys = {
            value.strip().casefold()
            for value in completed_event_ids
            if isinstance(value, str) and value.strip()
        }
        records = self._index.get("knownCharacters", [])
        if not isinstance(records, list):
            return []
        result: list[dict[str, Any]] = []
        for raw_relation in records:
            if not isinstance(raw_relation, Mapping):
                continue
            owner = canonical_npc_id(raw_relation.get("npcId", ""))
            if owner.casefold() != canonical_id.casefold():
                continue
            if not _source_matches(raw_relation.get("sourceMod"), source_mods):
                continue
            scope = str(raw_relation.get("knowledgeScope", "")).strip().casefold()
            if scope not in scope_keys:
                continue
            if str(raw_relation.get("confidence", "medium")).strip().casefold() == "low":
                continue
            required_event = raw_relation.get("requiredEventId")
            if isinstance(required_event, str) and required_event.strip():
                if not game_event_completed(required_event, completed_keys):
                    continue
            known_npc_id = str(
                raw_relation.get("knownNpcId", raw_relation.get("subjectNpcId", ""))
            ).strip()
            if not _is_catalog_npc_id(known_npc_id):
                continue
            selected = self._select_fields(raw_relation, self._KNOWN_CHARACTER_FIELDS)
            selected["npcId"] = canonical_id
            selected["knownNpcId"] = canonical_npc_id(known_npc_id)
            result.append(selected)
            if len(result) >= capped_limit:
                break
        return result

    def speech_evidence(
        self,
        npc_id: str,
        source_mods: Iterable[str],
        *,
        relationship_stage: str = "",
        player_input: str = "",
        limit: int = 6,
        completed_event_ids: Iterable[str] = (),
    ) -> list[dict[str, Any]]:
        if not isinstance(npc_id, str) or not npc_id.strip():
            return []
        canonical_id = canonical_npc_id(npc_id)
        capped_limit = max(0, min(int(limit), _SPEECH_EVIDENCE_CANDIDATES))
        if capped_limit == 0:
            return []
        raw_evidence = self._index.get("speechEvidence")
        schema_version = self._index.get("schemaVersion")
        if "speechEvidence" not in self._index or (
            schema_version == 1 and not isinstance(raw_evidence, list)
        ):
            # 仅对旧版或字段缺失的索引回退；schema 2 的显式空列表必须保持为空。
            raw_evidence = self._index.get("styleSamples", [])
        elif not isinstance(raw_evidence, list):
            raw_evidence = []
        completed_keys = {
            value.strip().casefold()
            for value in completed_event_ids
            if isinstance(value, str) and value.strip()
        }

        def collect_candidates(
            *, allow_lower_stage: bool = False
        ) -> list[tuple[int, int, int, int, int, int, int, int, dict[str, Any]]]:
            candidates: list[
                tuple[int, int, int, int, int, int, int, int, dict[str, Any]]
            ] = []
            for original_index, raw_sample in enumerate(raw_evidence):
                if not isinstance(raw_sample, Mapping):
                    continue
                raw_sample = _normalise_dialogue_provenance(raw_sample)
                if (
                    canonical_npc_id(raw_sample.get("npcId", "")).casefold()
                    != canonical_id.casefold()
                ):
                    continue
                if not _source_matches(raw_sample.get("sourceMod"), source_mods):
                    continue
                if not _event_dialogue_is_completed(raw_sample, completed_keys):
                    continue
                if not _relationship_stage_matches(
                    raw_sample,
                    relationship_stage,
                    allow_lower_stage=allow_lower_stage,
                ):
                    continue
                if allow_lower_stage and _dialogue_key_priority(raw_sample) > 3:
                    # 回退只补充稳定的日常对白，不把季节、事件或特殊触发
                    # 文案当成当前话题的语气依据。
                    continue
                text = raw_sample.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                if has_dialogue_control_residue(text):
                    continue
                if _UNRESOLVED_I18N.search(text):
                    continue
                if not _is_model_evidence_record(raw_sample):
                    continue
                candidates.append(
                    (
                        -_evidence_topic_score(raw_sample, player_input),
                        _relationship_specificity_priority(
                            raw_sample, relationship_stage
                        ),
                        _evidence_priority(raw_sample),
                        _unrelated_magic_priority(raw_sample, player_input),
                        _dialogue_selection_key_priority(raw_sample, player_input),
                        _dialogue_path_priority(raw_sample),
                        -_source_priority(raw_sample.get("sourceMod")),
                        _evidence_order_key(raw_sample, original_index),
                        self._canonicalize_selected_npc(
                            self._select_fields(raw_sample, self._SPEECH_FIELDS)
                        ),
                    )
                )
            return candidates

        candidates = collect_candidates()
        if _matching_topic_groups(player_input) and not any(
            _evidence_topic_score(item[8], player_input) > 0
            for item in candidates
        ):
            candidates = collect_candidates(allow_lower_stage=True)
        return _select_evidence_candidates(candidates, capped_limit)

    def dialogue_reference(
        self,
        npc_id: str,
        *,
        representative_limit: int = 16,
    ) -> dict[str, Any]:
        """返回网页参照用的完整已解析对白及一组稳定置顶样本。"""

        if not isinstance(npc_id, str) or not npc_id.strip():
            return {
                "npcId": "",
                "total": 0,
                "representatives": [],
                "dialogues": [],
            }
        canonical_id = canonical_npc_id(npc_id)
        raw_evidence = self._index.get("speechEvidence")
        schema_version = self._index.get("schemaVersion")
        if "speechEvidence" not in self._index or (
            schema_version == 1 and not isinstance(raw_evidence, list)
        ):
            raw_evidence = self._index.get("styleSamples", [])
        if not isinstance(raw_evidence, list):
            raw_evidence = []

        dialogues: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for raw_sample in raw_evidence:
            if not isinstance(raw_sample, Mapping):
                continue
            if canonical_npc_id(raw_sample.get("npcId", "")).casefold() != canonical_id.casefold():
                continue
            text = raw_sample.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            if _UNRESOLVED_I18N.search(text):
                continue
            if has_dialogue_control_residue(text):
                # 原文浏览页是给人复核语气用的；控制脚本、旁白和动作残渣
                # 不能混进可见对白，否则用户会把它误判成角色语言风格。
                continue
            sample_id = str(raw_sample.get("sampleId", "")).strip()
            if sample_id and sample_id in seen_ids:
                continue
            selected = self._canonicalize_selected_npc(
                self._select_fields(raw_sample, self._REFERENCE_FIELDS)
            )
            if not selected.get("sampleId"):
                selected["sampleId"] = f"{canonical_id}:{len(dialogues)}"
            seen_ids.add(str(selected["sampleId"]))
            dialogues.append(selected)

        capped_representative_limit = max(0, min(int(representative_limit), 16))
        representatives = _select_representative_dialogues(
            dialogues,
            capped_representative_limit,
        )
        return {
            "npcId": canonical_id,
            "total": len(dialogues),
            "representatives": representatives,
            "dialogues": dialogues,
        }

    def behavior_examples(
        self,
        npc_id: str,
        source_mods: Iterable[str],
        *,
        relationship_stage: str = "",
        channel: str = "",
        player_input: str = "",
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        if not isinstance(npc_id, str) or not npc_id.strip():
            return []
        canonical_id = canonical_npc_id(npc_id)
        capped_limit = max(0, min(int(limit), 6))
        if capped_limit == 0:
            return []
        source_mod_list = list(source_mods)
        candidates: list[tuple[int, int, dict[str, Any]]] = []
        # 泛寒暄（「你好」「今天过得怎么样」）里没有可提取的具体对象，主题型样例
        # 的得分必然是 0。原先把它们直接丢掉，于是 39/44 角色的行为样例注入数是
        # **0** —— 而这恰是玩家最常用的开场。这里把它们留作兜底候选：只有本轮
        # 一条得分样例都没有、且输入确实是泛寒暄时才启用（2026-09-21）。
        # 兜底不绕过上面任何一道门（来源 Mod / 关系阶段 / 渠道）。
        generic_input = bool(player_input.strip()) and _is_generic_small_talk_input(
            player_input
        )
        fallback: list[tuple[int, int, dict[str, Any]]] = []
        raw_examples = self._index.get("behaviorExamples", [])
        if not isinstance(raw_examples, list):
            return []
        for original_index, raw_example in enumerate(raw_examples):
            if not isinstance(raw_example, Mapping):
                continue
            if canonical_npc_id(raw_example.get("npcId", "")).casefold() != canonical_id.casefold():
                continue
            if not _behavior_source_matches(
                raw_example.get("sourceMods"),
                source_mod_list,
                npc_id=canonical_id,
            ):
                continue
            if not _behavior_dimension_matches(
                raw_example, "relationshipStages", relationship_stage
            ):
                continue
            if not _behavior_dimension_matches(raw_example, "channels", channel):
                continue
            score = _behavior_topic_score(raw_example, player_input)
            if player_input.strip() and score == 0 and not generic_input:
                continue
            selected = self._select_fields(raw_example, self._BEHAVIOR_FIELDS)
            selected["npcId"] = canonical_npc_id(selected.get("npcId", canonical_id))
            if player_input.strip() and score == 0:
                # 排序键取正数：它们永远排在所有得分样例之后。
                fallback.append((1, original_index, selected))
                continue
            candidates.append((-score, original_index, selected))
        if not candidates and fallback:
            candidates = fallback
        candidates.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in candidates[:capped_limit]]

    def voice_card(
        self,
        npc_id: str,
        source_mods: Iterable[str] = (),
        *,
        relationship_stage: str = "",
    ) -> dict[str, Any]:
        if not isinstance(npc_id, str) or not npc_id.strip():
            return {}
        raw_cards = self._index.get("voiceCards", {})
        if not isinstance(raw_cards, Mapping):
            return {}
        canonical_id = canonical_npc_id(npc_id)
        source_mod_list = tuple(source_mods)
        matches: list[tuple[int, Mapping[str, Any]]] = []
        for raw_npc_id, raw_card in raw_cards.items():
            if canonical_npc_id(raw_npc_id).casefold() != canonical_id.casefold():
                continue
            if not isinstance(raw_card, Mapping):
                continue
            exactness = 0 if str(raw_npc_id).casefold() == canonical_id.casefold() else 1
            matches.append((exactness, raw_card))
        if matches:
            selected = deepcopy(dict(sorted(matches, key=lambda item: item[0])[0][1]))
            selected["npcId"] = canonical_id
            raw_anchors = selected.get("voiceAnchors")
            if isinstance(raw_anchors, list):
                requested_sources = [
                    value for value in source_mod_list
                    if isinstance(value, str) and value.strip()
                ]
                specific: list[dict[str, Any]] = []
                vanilla: list[dict[str, Any]] = []
                for raw_anchor in raw_anchors:
                    if not isinstance(raw_anchor, Mapping):
                        continue
                    source_mod = raw_anchor.get("sourceMod", "")
                    if requested_sources and not source_matches(
                        source_mod, requested_sources
                    ):
                        continue
                    anchor = dict(raw_anchor)
                    if normalize_source_marker(source_mod) == "vanilla":
                        vanilla.append(anchor)
                    else:
                        specific.append(anchor)
                # 已启用的内容包对白优先于原版对白；原版仍作为补充，
                # 避免只有少量覆盖层语料时语气锚点窗口为空。
                selected["voiceAnchors"] = (specific + vanilla)[:8]
            if str(relationship_stage).strip():
                raw_evidence = self._index.get("speechEvidence")
                schema_version = self._index.get("schemaVersion")
                if "speechEvidence" not in self._index or (
                    schema_version == 1 and not isinstance(raw_evidence, list)
                ):
                    raw_evidence = self._index.get("styleSamples", [])
                if not isinstance(raw_evidence, list):
                    raw_evidence = []
                requested_sources = [
                    value
                    for value in source_mod_list
                    if isinstance(value, str) and value.strip()
                ]

                def collect_stage_candidates(
                    *, allow_nearby_stage: bool = False
                ) -> list[dict[str, Any]]:
                    stage_candidates: list[dict[str, Any]] = []
                    requested = str(relationship_stage).strip().casefold()
                    for raw_sample in raw_evidence:
                        if not isinstance(raw_sample, Mapping):
                            continue
                        sample = _normalise_dialogue_provenance(raw_sample)
                        if canonical_npc_id(sample.get("npcId", "")).casefold() != (
                            canonical_id.casefold()
                        ):
                            continue
                        if requested_sources and not source_matches(
                            sample.get("sourceMod", ""), requested_sources
                        ):
                            continue
                        if not _relationship_stage_matches(
                            sample, str(relationship_stage)
                        ):
                            if not allow_nearby_stage or requested != "dating":
                                continue
                            conditions = sample.get("conditions")
                            actual = (
                                conditions.get(
                                    "relationshipStage",
                                    conditions.get("relationship_stage", ""),
                                )
                                if isinstance(conditions, Mapping)
                                else ""
                            )
                            if not isinstance(actual, str) or actual.strip().casefold() not in {
                                "stranger",
                                "acquaintance",
                                "friend",
                                "close",
                            }:
                                continue
                        stage_candidates.append(sample)
                    return stage_candidates

                def stage_label(sample: Mapping[str, Any]) -> str:
                    conditions = sample.get("conditions")
                    if not isinstance(conditions, Mapping):
                        return ""
                    value = conditions.get(
                        "relationshipStage",
                        conditions.get("relationship_stage", ""),
                    )
                    return value.strip().casefold() if isinstance(value, str) else ""

                stage_candidates = collect_stage_candidates()
                has_dating_stage = any(
                    stage_label(item) in {"dating", "close", "friend", "acquaintance"}
                    for item in stage_candidates
                )
                if not stage_candidates or (
                    str(relationship_stage).strip().casefold() == "dating"
                    and not has_dating_stage
                ):
                    # 某些索引没有 dating 或更近阶段原文；只在这时把
                    # stranger 作为最后阶段回退，避免它压过 close/friend。
                    stage_candidates = collect_stage_candidates(
                        allow_nearby_stage=True
                    )
                stage_anchors = select_stage_voice_anchors(
                    stage_candidates,
                    npc_id=canonical_id,
                    relationship_stage=str(relationship_stage),
                    max_count=8,
                )
                if stage_anchors:
                    selected["voiceAnchors"] = stage_anchors
            return selected
        return {}

    def knowledge_facts(
        self,
        npc_id: str,
        source_mods: Iterable[str],
        *,
        limit: int = 8,
        completed_event_ids: Iterable[str] = (),
        allowed_scopes: Iterable[str] = (
            "canon_confirmed",
            "runtime_confirmed",
            "player_provided",
        ),
    ) -> list[dict[str, Any]]:
        if not isinstance(npc_id, str) or not npc_id.strip():
            return []
        canonical_id = canonical_npc_id(npc_id)
        capped_limit = max(0, min(int(limit), 8))
        if capped_limit == 0:
            return []
        scope_keys = {
            str(scope).strip().casefold()
            for scope in allowed_scopes
            if str(scope).strip()
        }
        completed_keys = {
            value.strip().casefold()
            for value in completed_event_ids
            if isinstance(value, str) and value.strip()
        }
        candidates: list[tuple[int, int, dict[str, Any]]] = []
        for position, raw_fact in enumerate(self._index.get("knowledgeFacts", [])):
            if not isinstance(raw_fact, Mapping):
                continue
            if canonical_npc_id(raw_fact.get("npcId", "")).casefold() != canonical_id.casefold():
                continue
            if not _source_matches(raw_fact.get("sourceMod"), source_mods):
                continue
            scope = str(raw_fact.get("knowledgeScope", "")).strip().casefold()
            if scope not in scope_keys:
                continue
            confidence = str(raw_fact.get("confidence", "")).strip().casefold()
            if confidence == "low":
                continue
            required_event = raw_fact.get("requiredEventId")
            if isinstance(required_event, str) and required_event.strip():
                if not game_event_completed(required_event, completed_keys):
                    continue
            selected = self._canonicalize_selected_npc(
                self._select_fields(raw_fact, self._FACT_FIELDS)
            )
            candidates.append((_source_priority(raw_fact.get("sourceMod")), position, selected))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in candidates[:capped_limit]]

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, Mapping) or payload.get("schemaVersion") not in {1, 2}:
            return {}
        loaded = dict(payload)
        # 已有派生索引可能早于语料清洗规则生成；加载时做同一项无损清理，
        # 这样无需覆盖用户的生成文件，当前运行进程也不会把残片送入 Prompt。
        from .corpus import clean_dialogue_noise

        def clean_records(value: object) -> list[object]:
            if not isinstance(value, list):
                return []
            records: list[object] = []
            for item in value:
                if not isinstance(item, Mapping):
                    records.append(item)
                    continue
                cleaned = dict(item)
                text = cleaned.get("text")
                if isinstance(text, str):
                    cleaned["text"] = clean_dialogue_noise(text)
                records.append(cleaned)
            return records

        for field in ("styleSamples", "speechEvidence"):
            if field in loaded:
                loaded[field] = clean_records(loaded[field])
        raw_cards = loaded.get("voiceCards")
        if isinstance(raw_cards, Mapping):
            cards: dict[str, object] = {}
            for key, raw_card in raw_cards.items():
                if not isinstance(raw_card, Mapping):
                    cards[str(key)] = raw_card
                    continue
                card = dict(raw_card)
                if "voiceAnchors" in card:
                    card["voiceAnchors"] = clean_records(card["voiceAnchors"])
                cards[str(key)] = card
            loaded["voiceCards"] = cards
        return loaded

    @staticmethod
    def _canonicalize_selected_npc(value: dict[str, Any]) -> dict[str, Any]:
        if "npcId" in value:
            value["npcId"] = canonical_npc_id(value["npcId"])
        return value

    @staticmethod
    def _select_fields(
        value: Mapping[str, Any],
        fields: Iterable[str],
    ) -> dict[str, Any]:
        return {
            field: value[field]
            for field in fields
            if field in value and value[field] not in (None, "", [], {})
        }
