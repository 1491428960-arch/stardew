"""对白语料的统一提取与离线导出。

这个模块只负责把可追溯的对白证据整理成稳定 JSON，不负责调用模型，也不做向量化。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .profile_index import _load_json


_DIALOGUE_PREFIX = "characters/dialogue/"
_LOCALE_SUFFIX = re.compile(r"\.[a-z]{2}(?:-[a-z]{2})?$", re.IGNORECASE)
_I18N_TOKEN = re.compile(
    r"\{\{\s*i18n\s*:\s*([^{}|]+?)"
    r"(?:\s+\{\{[^{}]*\}\})?(?:\s*\|[^{}]*)?\s*\}\}",
    re.IGNORECASE,
)
_I18N_DYNAMIC_PREFIX = re.compile(
    r"\{\{\s*i18n\s*:\s*([^{}|]*?)(?P<delimiter>\{\{|\||\}\})",
    re.IGNORECASE,
)
_I18N_REFERENCE = re.compile(r"\{\{\s*i18n\s*:", re.IGNORECASE)
_DEFAULT_I18N_CANDIDATE_LIMIT = 24
_WEEKDAY_DIALOGUE_KEY = re.compile(
    r"^(?:(?:spring|summer|fall|winter)_)?"
    r"(?:mon|tue|wed|thu|fri|sat|sun)(?P<hearts>\d+)?$",
    re.IGNORECASE,
)
_DIALOGUE_MARKER = re.compile(r"#?\$[A-Za-z0-9]+#?", re.IGNORECASE)
_DIALOGUE_QUERY = re.compile(r"#?\$(?:q|d)[^#|]*#?", re.IGNORECASE)
_DIALOGUE_EXPRESSION = re.compile(r"\$\{([^{}]*)\}")
_DIALOGUE_TOKEN = re.compile(r"\{\{[^{}]*\}\}")
_DIALOGUE_DIRECTIVE = re.compile(r"%[A-Za-z0-9_]+")
_DIALOGUE_INPUT_SEPARATOR = re.compile(r"\binputSeparator\s*=.*$", re.IGNORECASE)
_DIALOGUE_ACTION = re.compile(r"\*[^*\r\n]*\*")
_DIALOGUE_NARRATION = re.compile(r"^\s*%")
_DIALOGUE_LONE_DOLLAR = re.compile(r"(?<![A-Za-z0-9])\$(?![A-Za-z0-9])")
_SINGLE_LETTER_RESIDUE = re.compile(
    r"(?<=[。！？；：，、…])\s*[A-Za-z]\s*(?=[\u4e00-\u9fff])"
)
_STARDEW_BRANCH_HEADER = re.compile(
    r"(?<![A-Za-z0-9_])\d+\s+-?\d+\s+[A-Za-z][A-Za-z0-9_]*\b"
)
_STARDEW_BRANCH_SEPARATOR = "\x00"
_EVENT_TARGET_PREFIX = "data/events/"
_EVENT_COMMAND = re.compile(
    r'(?:^|/)(?P<command>speak|end\s+dialogue|textAboveHead)\s+'
    r'(?P<speaker>[A-Za-z][A-Za-z0-9_]*)\s+"(?P<text>(?:\\.|[^"\\])*)"',
    re.IGNORECASE,
)
_EVENT_ID_PREFIX = re.compile(r"^\s*(?P<event_id>\d+)(?:_|/|$)")
_EVENT_PARTICIPANT_CONDITION = re.compile(
    r"/(?P<condition>[fo])\s+(?P<npc>[A-Za-z][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_NON_PLAYER_EVENT_SPEAKERS = {"farmer", "player", "host"}


def _normalise_source_path(source_path: str | Path) -> str:
    """把来源路径变成可提交的相对路径，避免泄露本机绝对路径。"""

    value = str(source_path).replace("\\", "/").strip()
    if not value:
        return "unknown.json"
    if value.startswith("/") or (len(value) >= 3 and value[1] == ":"):
        value = value.rsplit("/", 1)[-1]
    return value.lstrip("./") or "unknown.json"


def _locale_candidates(locale: str) -> list[str]:
    value = str(locale).strip().replace("_", "-")
    candidates: list[str] = []
    for candidate in (value, value.split("-", 1)[0], "default"):
        if candidate and candidate.casefold() not in {
            existing.casefold() for existing in candidates
        }:
            candidates.append(candidate)
    return candidates


def _ordered_i18n_catalogs(
    catalogs: Mapping[str, Mapping[str, Any]],
    locale: str,
) -> list[Mapping[str, Any]]:
    ordered_catalogs: list[Mapping[str, Any]] = []
    for candidate in _locale_candidates(locale):
        for catalog_name, catalog in catalogs.items():
            if str(catalog_name).casefold() == candidate.casefold():
                ordered_catalogs.append(catalog)
                break
    return ordered_catalogs


def _lookup_i18n_value(
    key: str,
    catalogs: Iterable[Mapping[str, Any]],
) -> str | None:
    folded_key = key.casefold()
    for catalog in catalogs:
        value = catalog.get(key)
        if isinstance(value, str):
            return value
        for raw_key, raw_value in catalog.items():
            if str(raw_key).casefold() == folded_key and isinstance(raw_value, str):
                return raw_value
    return None


def resolve_i18n_text(
    text: str,
    catalogs: Mapping[str, Mapping[str, Any]],
    *,
    locale: str = "zh-CN",
) -> str:
    """解析 Content Patcher 的 i18n 引用，未找到时保留原占位符。"""

    if not isinstance(text, str) or not text:
        return text
    ordered_catalogs = _ordered_i18n_catalogs(catalogs, locale)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = _lookup_i18n_value(key, ordered_catalogs)
        if value is not None:
            return value
        return match.group(0)

    return _I18N_TOKEN.sub(replace, text)


def resolve_i18n_candidates(
    text: str,
    catalogs: Mapping[str, Mapping[str, Any]],
    *,
    locale: str = "zh-CN",
    max_candidates: int = _DEFAULT_I18N_CANDIDATE_LIMIT,
) -> list[dict[str, str]]:
    """为依赖运行时表达式的 i18n 引用收集可审计候选，不猜测唯一结果。

    Content Patcher 会在游戏运行时展开 ``Random``、季节、日期和条件表达式，
    因此静态导出不能把其中一句伪装成最终台词。这里仅按动态键前缀枚举目录中
    已存在的键，并按键名稳定排序、限制数量；没有匹配项时返回空数组。
    """

    if not isinstance(text, str) or not text or max_candidates <= 0:
        return []
    ordered_catalogs = _ordered_i18n_catalogs(catalogs, locale)
    if not ordered_catalogs:
        return []

    prefixes: dict[str, str] = {}
    for match in _I18N_DYNAMIC_PREFIX.finditer(text):
        if match.group("delimiter") != "{{":
            continue
        prefix = match.group(1).strip()
        if not prefix:
            continue
        prefixes.setdefault(prefix.casefold(), prefix)

    candidates: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    # 每个动态键族单独限量，避免一条同时包含多个分支的对白只留下第一个族。
    for folded_prefix in sorted(prefixes):
        prefix = prefixes[folded_prefix]
        family: dict[tuple[str, str], str] = {}
        for catalog in ordered_catalogs:
            for raw_key in catalog:
                key = str(raw_key).strip()
                if not key or not key.casefold().startswith(folded_prefix):
                    continue
                value = _lookup_i18n_value(key, ordered_catalogs)
                if value is not None and not _I18N_REFERENCE.search(value):
                    family[(key.casefold(), key)] = value
        family_count = 0
        for (_, key), value in sorted(family.items(), key=lambda item: item[0]):
            folded_key = key.casefold()
            if folded_key in seen_keys:
                continue
            candidates.append({"key": key, "text": value})
            seen_keys.add(folded_key)
            family_count += 1
            if family_count >= max_candidates:
                break
    return candidates


def _split_dialogue_control_flow(text: str) -> list[str]:
    """在不拆开 ``${男^女}`` 和 ``{{...}}`` 表达式的前提下拆分分支。"""

    # 部分导出的 Stardew 原版对白把条件分支头直接串在同一个值里，
    # 例如 ``6 0 Wed_01_02``。它不是 NPC 台词，但必须作为边界处理，
    # 否则整个控制脚本会被当成一条可模仿的长句。
    text = _STARDEW_BRANCH_HEADER.sub(_STARDEW_BRANCH_SEPARATOR, text)
    branches: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("${", index):
            end = text.find("}", index + 2)
            if end >= 0:
                current.append(text[index : end + 1])
                index = end + 1
                continue
        if text.startswith("{{", index):
            end = text.find("}}", index + 2)
            if end >= 0:
                current.append(text[index : end + 2])
                index = end + 2
                continue
        if text[index] == _STARDEW_BRANCH_SEPARATOR:
            branches.append("".join(current))
            current = []
            index += 1
            continue
        if text.startswith("||", index):
            branches.append("".join(current))
            current = []
            index += 2
            continue
        if text[index] in {"^", "|"}:
            branches.append("".join(current))
            current = []
            index += 1
            continue
        current.append(text[index])
        index += 1
    branches.append("".join(current))
    return branches


def _clean_dialogue_branch(text: str) -> str:
    # 某些 Content Patcher 的随机表达式在静态展开时会留下
    # ``inputSeparator=...}}`` 控制残渣；这不是 NPC 台词，不能进入模仿样本。
    if _DIALOGUE_NARRATION.match(text):
        # ``%……`` 是“NPC 没有理你”或事件旁白分支，不是 NPC 的说话内容。
        return ""
    text = _DIALOGUE_INPUT_SEPARATOR.sub("", text)
    value = _DIALOGUE_EXPRESSION.sub(
        lambda match: match.group(1).split("^", 1)[0], text
    )
    value = _DIALOGUE_TOKEN.sub(" ", value)
    value = _DIALOGUE_QUERY.sub(" ", value)
    value = _DIALOGUE_MARKER.sub(" ", value)
    value = _DIALOGUE_DIRECTIVE.sub(" ", value)
    value = _DIALOGUE_ACTION.sub(" ", value)
    value = value.replace("*", " ")
    value = _DIALOGUE_LONE_DOLLAR.sub(" ", value)
    value = value.replace("@", "你")
    # 个别中文导出会在中文句间混入 OCR/编码残片（例如“…… e 你”）。
    # 只清理夹在中文标点与中文之间的单个拉丁字母，避免误删真正的英文术语。
    value = clean_dialogue_noise(value)
    value = re.sub(r"#+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_dialogue_noise(text: str) -> str:
    """清理已生成索引中夹在中文句间的单字母残片。"""

    if not isinstance(text, str):
        return text
    return _SINGLE_LETTER_RESIDUE.sub("", text)


def clean_dialogue_variants(text: str) -> list[str]:
    """提取可供模型模仿的对白变体，同时保留语料原文供审计。"""

    if not isinstance(text, str) or not text.strip():
        return []
    variants: list[str] = []
    seen: set[str] = set()
    for branch in _split_dialogue_control_flow(text):
        cleaned = _clean_dialogue_branch(branch)
        if cleaned and cleaned.casefold() not in seen:
            variants.append(cleaned)
            seen.add(cleaned.casefold())
    return variants


def classify_dialogue_target(target: str) -> tuple[str, str]:
    """从 Content Patcher target 得到 NPC ID 和证据类型。

    这里**刻意**只认 `Characters/Dialogue`（以及按文件名恢复的
    `MarriageDialogue` / `RoommateDialogue`），不认 `Data/ExtraDialogue`。
    SVE 往 `Data/ExtraDialogue` 写的那 18 条（Summit 事件、Gunther 卧室台词等）
    因此被 `continue` 跳过 —— 那是**已知缺口**，但补它属于"让事件场景台词
    进入语气证据池"，语义上要不要收需要用户拍板，本轮不动。详见
    `_read_payload` 上方的方案 A／B／C 说明。
    """

    normalised = str(target).replace("\\", "/").strip("/")
    if normalised.casefold().startswith(_DIALOGUE_PREFIX):
        dialogue_target = normalised[len(_DIALOGUE_PREFIX):]
    else:
        # 派生索引的 sourcePath 通常只保留文件名，例如
        # ``MarriageDialogueElliott.zh-CN.json``。旧索引没有保存
        # evidenceKind 时仍应能从这个路径恢复婚后来源，而不是把它当
        # 成普通日常对白。
        dialogue_target = normalised.rsplit("/", 1)[-1]
        if not dialogue_target.casefold().startswith(
            ("marriagedialogue", "roommatedialogue")
        ):
            return "", ""
    lowered = dialogue_target.casefold()
    if lowered.startswith("marriagedialogue"):
        return dialogue_target[len("MarriageDialogue"):], "marriage_dialogue"
    if lowered.startswith("roommatedialogue"):
        return dialogue_target[len("RoommateDialogue"):], "roommate_dialogue"
    return dialogue_target, "dialogue"


def _is_event_target(target: str) -> bool:
    normalised = str(target).replace("\\", "/").strip("/").casefold()
    return normalised.startswith(_EVENT_TARGET_PREFIX)


def _event_id_from_source_key(source_key: str) -> str:
    match = _EVENT_ID_PREFIX.match(str(source_key))
    return match.group("event_id") if match else ""


def _unescape_event_text(text: str) -> str:
    # 事件脚本中的引号通常已经由 JSON 解码还原；这里只处理命令参数中
    # 仍残留的转义引号和反斜杠，不对中文做 unicode_escape 二次解码。
    return str(text).replace(r"\"", '"').replace(r"\\", "\\")


def _event_participants(source_key: str, raw_script: str) -> list[str]:
    """提取事件涉及的 NPC，而不把玩家或旁白误算成角色。"""

    participants: list[str] = []
    seen: set[str] = set()

    def append(value: str) -> None:
        npc_id = str(value).strip()
        if not npc_id or npc_id.casefold() in _NON_PLAYER_EVENT_SPEAKERS:
            return
        folded = npc_id.casefold()
        if folded in seen:
            return
        seen.add(folded)
        participants.append(npc_id)

    # /f 和 /o 是事件键中最常见的角色条件；即使角色没有发言，
    # 也必须保留为事件参与者，避免用“实际发言者”冒充完整事件阵容。
    for match in _EVENT_PARTICIPANT_CONDITION.finditer(str(source_key)):
        append(match.group("npc"))
    for match in _EVENT_COMMAND.finditer(str(raw_script)):
        append(match.group("speaker"))
    return participants


def _event_conditions(source_key: str) -> dict[str, str]:
    """保留原始事件键，供审计触发条件，不猜测游戏内部语义。"""

    value = str(source_key).strip()
    return {"raw": value} if value else {}


def _extract_event_dialogue_records(
    entries: Mapping[Any, Any],
    *,
    source_mod: str,
    source_path: str | Path,
    i18n_catalogs: Mapping[str, Mapping[str, Any]] | None = None,
    locale: str = "zh-CN",
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    safe_source_mod = str(source_mod).strip() or "unknown"
    safe_source_path = _normalise_source_path(source_path)
    for raw_key, raw_script in entries.items():
        source_key = str(raw_key).strip()
        if not source_key or not isinstance(raw_script, str) or not raw_script.strip():
            continue
        event_id = _event_id_from_source_key(source_key)
        participants = _event_participants(source_key, raw_script)
        for line_index, match in enumerate(_EVENT_COMMAND.finditer(raw_script), start=1):
            speaker = match.group("speaker").strip()
            if speaker.casefold() in _NON_PLAYER_EVENT_SPEAKERS:
                continue
            raw_text = _unescape_event_text(match.group("text")).strip()
            if not raw_text:
                continue
            record: dict[str, Any] = {
                "sampleId": (
                    f"{safe_source_mod}:{safe_source_path}:{source_key}:"
                    f"event-line-{line_index}"
                ),
                "npcId": speaker,
                "sourceMod": safe_source_mod,
                "sourcePath": safe_source_path,
                "sourceKey": source_key,
                "text": raw_text,
                "evidenceKind": "event_dialogue",
                "eventLineIndex": line_index,
                "conditions": {"eventId": event_id} if event_id else {},
                "eventConditions": _event_conditions(source_key),
                "participants": participants,
            }
            if event_id:
                record["eventId"] = event_id
            variants = clean_dialogue_variants(raw_text)
            if variants and (len(variants) > 1 or variants[0] != raw_text.strip()):
                record["dialogueVariants"] = variants
            if i18n_catalogs:
                resolved_text = resolve_i18n_text(
                    raw_text,
                    i18n_catalogs,
                    locale=locale,
                )
                if resolved_text != raw_text and not _I18N_REFERENCE.search(
                    resolved_text
                ):
                    resolved_variants = clean_dialogue_variants(resolved_text)
                    if resolved_variants:
                        record["resolvedText"] = resolved_variants[0]
                    if len(resolved_variants) > 1:
                        record["dialogueVariants"] = resolved_variants
                else:
                    dynamic_candidates = resolve_i18n_candidates(
                        raw_text,
                        i18n_catalogs,
                        locale=locale,
                    )
                    if dynamic_candidates:
                        record["dynamicCandidates"] = dynamic_candidates
            records.append(record)
    return records


def _iter_dialogue_targets(raw_target: object) -> Iterable[str]:
    if isinstance(raw_target, str):
        for target in raw_target.split(","):
            if target.strip():
                yield target.strip()
        return
    if isinstance(raw_target, (bytes, bytearray, Mapping)):
        return
    if isinstance(raw_target, Iterable):
        for target in raw_target:
            if isinstance(target, str):
                yield target


def infer_dialogue_conditions(target: str, source_key: str) -> dict[str, str]:
    """推断不会改变原文的最小条件标签。"""

    _, evidence_kind = classify_dialogue_target(target)
    if evidence_kind in {"marriage_dialogue", "roommate_dialogue"}:
        # Stardew 中 RoommateDialogue 仅用于婚后同居，因此仍属于 married 阶段。
        return {"relationshipStage": "married"}
    match = _WEEKDAY_DIALOGUE_KEY.fullmatch(str(source_key).strip())
    if match:
        hearts = int(match.group("hearts") or 0)
        if hearts >= 8:
            stage = "close"
        elif hearts >= 6:
            stage = "friend"
        elif hearts >= 2:
            stage = "acquaintance"
        else:
            stage = "stranger"
        return {"relationshipStage": stage}
    return {}


def extract_content_patcher_dialogue(
    payload: Mapping[str, Any],
    *,
    source_mod: str,
    source_path: str | Path,
    i18n_catalogs: Mapping[str, Mapping[str, Any]] | None = None,
    locale: str = "zh-CN",
) -> tuple[list[dict[str, Any]], list[str]]:
    """提取一个 Content Patcher JSON 中的 EditData 对白。"""

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    changes = payload.get("Changes", [])
    if not isinstance(changes, list):
        return [], [f"Changes 不是数组：{_normalise_source_path(source_path)}"]

    safe_source_mod = str(source_mod).strip() or "unknown"
    safe_source_path = _normalise_source_path(source_path)
    for change in changes:
        if not isinstance(change, Mapping):
            continue
        if str(change.get("Action", "")).casefold() != "editdata":
            continue
        entries = change.get("Entries", {})
        if not isinstance(entries, Mapping):
            warnings.append(f"对白 Entries 不是对象：{safe_source_path}")
            continue
        for target in _iter_dialogue_targets(change.get("Target", "")):
            if _is_event_target(target):
                records.extend(
                    _extract_event_dialogue_records(
                        entries,
                        source_mod=safe_source_mod,
                        source_path=safe_source_path,
                        i18n_catalogs=i18n_catalogs,
                        locale=locale,
                    )
                )
                continue
            npc_id, evidence_kind = classify_dialogue_target(target)
            if not npc_id:
                continue
            for raw_key, raw_text in entries.items():
                source_key = str(raw_key).strip()
                if not source_key or not isinstance(raw_text, str) or not raw_text.strip():
                    continue
                record: dict[str, Any] = {
                    "sampleId": f"{safe_source_mod}:{safe_source_path}:{source_key}",
                    "npcId": npc_id,
                    "sourceMod": safe_source_mod,
                    "sourcePath": safe_source_path,
                    "sourceKey": source_key,
                    "text": raw_text,
                    "evidenceKind": evidence_kind,
                    "conditions": infer_dialogue_conditions(target, source_key),
                }
                variants = clean_dialogue_variants(raw_text)
                if variants and (len(variants) > 1 or variants[0] != raw_text.strip()):
                    record["dialogueVariants"] = variants
                if i18n_catalogs:
                    resolved_text = resolve_i18n_text(
                        raw_text,
                        i18n_catalogs,
                        locale=locale,
                    )
                    if resolved_text != raw_text and not _I18N_REFERENCE.search(
                        resolved_text
                    ):
                        resolved_variants = clean_dialogue_variants(resolved_text)
                        if resolved_variants:
                            record["resolvedText"] = resolved_variants[0]
                        if len(resolved_variants) > 1:
                            record["dialogueVariants"] = resolved_variants
                    else:
                        dynamic_candidates = resolve_i18n_candidates(
                            raw_text,
                            i18n_catalogs,
                            locale=locale,
                        )
                        if dynamic_candidates:
                            record["dynamicCandidates"] = dynamic_candidates
                records.append(record)
    return _dedupe_records(records), warnings


def _extract_plain_dialogue(
    payload: Mapping[str, Any],
    *,
    npc_id: str,
    source_mod: str,
    source_path: str | Path,
) -> list[dict[str, Any]]:
    entries: Mapping[Any, Any]
    raw_entries = payload.get("Entries")
    if isinstance(raw_entries, Mapping):
        entries = raw_entries
    else:
        entries = payload

    safe_source_mod = str(source_mod).strip() or "unknown"
    raw_npc_id = _LOCALE_SUFFIX.sub("", str(npc_id).strip()) or "unknown"
    dialogue_target = f"Characters/Dialogue/{raw_npc_id}"
    canonical_id, evidence_kind = classify_dialogue_target(dialogue_target)
    if not canonical_id:
        canonical_id = raw_npc_id
        evidence_kind = "dialogue"
    safe_source_path = _normalise_source_path(source_path)
    records: list[dict[str, Any]] = []
    for raw_key, raw_text in entries.items():
        source_key = str(raw_key).strip()
        if not source_key or not isinstance(raw_text, str) or not raw_text.strip():
            continue
        records.append(
            {
                "sampleId": f"{safe_source_mod}:{safe_source_path}:{source_key}",
                "npcId": canonical_id,
                "sourceMod": safe_source_mod,
                "sourcePath": safe_source_path,
                "sourceKey": source_key,
                "text": raw_text,
                "evidenceKind": evidence_kind,
                "conditions": infer_dialogue_conditions(dialogue_target, source_key),
            }
        )
        variants = clean_dialogue_variants(raw_text)
        if variants and (len(variants) > 1 or variants[0] != raw_text.strip()):
            records[-1]["dialogueVariants"] = variants
    return records


def _extract_plain_events(
    payload: Mapping[str, Any],
    *,
    source_mod: str,
    source_path: str | Path,
) -> list[dict[str, Any]]:
    """提取已解包的 vanilla ``Data/Events/*.json``。"""

    if not isinstance(payload, Mapping):
        return []
    return _extract_event_dialogue_records(
        payload,
        source_mod=source_mod,
        source_path=source_path,
    )


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _select_vanilla_dialogue_paths(
    paths: Iterable[Path],
    root: Path,
    locale: str | None,
) -> list[Path]:
    """按语言选择原版对白；没有目标语言时回退到无后缀文件。"""

    candidates = sorted(paths)
    if locale is None or not str(locale).strip():
        return candidates
    requested = str(locale).strip().replace("_", "-").casefold()
    groups: dict[str, list[Path]] = {}
    for path in candidates:
        relative = path.relative_to(root)
        base_name = _LOCALE_SUFFIX.sub("", path.stem) + path.suffix
        group_key = relative.with_name(base_name).as_posix().casefold()
        groups.setdefault(group_key, []).append(path)

    selected: list[Path] = []
    for group in groups.values():
        exact = [
            path
            for path in group
            if (
                (match := _LOCALE_SUFFIX.search(path.stem)) is not None
                and match.group(0)[1:].replace("_", "-").casefold() == requested
            )
        ]
        if exact:
            selected.extend(exact)
            continue
        selected.extend(path for path in group if not _LOCALE_SUFFIX.search(path.stem))
    return sorted(selected)


def _warn_for_unpacked_sources(root: Path, warnings: list[str]) -> None:
    """报告根下未解包的 ``.xnb`` 来源，**按目录合并成一条**。

    判据是「根下存在 ``.xnb``」，**与有没有同名 JSON 无关**——所以「把 xnb 解包」
    并不能消除这条警告（2026-09-20 核实时纠正过这个误解，它曾写在待办里）。

    像 SVE 的 ``assets/XNBs/`` 有 55 个室内地图 xnb，它们对**对话**索引没有用处，
    逐条报告只会把 55 行噪音灌进 warnings、**让真正的警告被淹没**（与审计工具的
    误报是同一类问题）。因此按目录合并，并保留目录名与数量，信息不丢。
    """
    by_directory: dict[Path, list[Path]] = {}
    for path in sorted(root.rglob("*.xnb")):
        by_directory.setdefault(path.parent, []).append(path)

    for directory, paths in sorted(by_directory.items()):
        relative = _relative_path(directory, root)
        where = "" if relative == "." else f"{relative}/"
        names = "、".join(path.name for path in paths[:3])
        suffix = f" 等 {len(paths)} 个" if len(paths) > 3 else ""
        warnings.append(f"xnb source requires unpacked JSON: {where}{names}{suffix}")


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按来源键去重，保留 Content Patcher 最后一次覆盖的文本。"""

    by_sample_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        sample_id = str(record.get("sampleId", "")).strip()
        if not sample_id:
            continue
        if sample_id not in by_sample_id:
            order.append(sample_id)
        by_sample_id[sample_id] = record
    return [by_sample_id[sample_id] for sample_id in order]


# --- 解析失败时"丢的到底是什么"（2026-09-22 第 6 批） -------------------------
#
# 起因：查 Birdie 为什么 0 条语料时发现，这个导出器的 warnings 只有一句
# `无法解析 JSON：xxx`，与"一个配方表读不出来"完全同级。而真正的情况是
# **`Data/ExtraDialogue` 谁都不扫**——她的 15 条台词一声不响地没了，
# 10 条失败警告混在一起，看不出哪条真的要命。
#
# 同一个缺口有三个修法（第 5 批报告 §1.4 的三选一）：
#
# * **A. 加第三个 vanilla 入口** —— `build_dialogue_corpus` 增
#   `vanilla_extra_dialogue_root` 之类的参数、按 `<NPC><数字>` / `<NPC>_<后缀>`
#   两种键名形状归 npcId。**本轮不做**：它会改变全库语料 records，必须重建
#   14.9 MB 的真机索引；而且"要不要把 `Data/ExtraDialogue` 里那些无主键
#   （`PurchasedItem_*` / `NewChild_*`）也收进来"要先拍板。
# * **B. 让 Content Patcher 的 `Data/ExtraDialogue` Target 可用** —— 在
#   `classify_dialogue_target` 里加一个 `Data/ExtraDialogue` 分支，用 Entries
#   键名归 NPC（能复活 SVE 写进那里的 18 条）。**本轮也不做**，两个理由：
#   同样要重建索引；而且那条路上的文本是**事件场景台词**，收进来会混进
#   `styleSamples`（语气证据），与"日常对白"的语义不同 —— 这一条要用户拍板。
# * **C. 让解析失败看得见**（**本轮做了**）—— 失败时附一句"这文件里本来
#   有多少对白 Target"。零重建、零语义变更，只把已有的静默丢弃变成可读。
#
# 下面两个判据只做**粗筛**：目的是把"丢台词"和"丢别的东西"分开，不复刻
# `classify_dialogue_target` 的精确规则（此刻 JSON 已经解析不了了）。两条口径：
#
# * **对白 Target** = 值里含 `dialogue`（`Characters/Dialogue/*`、`Data/ExtraDialogue`）。
#   **刻意不收 `Data/Events`**：CP 往 `Data/Events` 写的 patch 走事件路径，而
#   `classify_dialogue_target` 不认它 —— 这类 Target 解析成功也不会进索引，
#   把它们算成"这次解析失败丢掉的台词"会把警告夸大（实测 SVE 的
#   `code/Other/Monsters.json` 会因此从 0 跳到 52）。真要把事件台词收进来，
#   那是与方案 B 同一类决策，得先拍板。
# * 计数按**去重后的不同 Target 值**，与第 5 批 `.tmp/facet-coverage/b5_json_scan.py`
#   的口径一致 —— 按出现次数数会把 Krobus.json 的 3 个对白 Target 报成 14 个，
#   而这条警告的全部意义就是让人一眼判断"要不要紧"，夸大比漏报更坏。
_DIALOGUE_FILE_MARKERS: tuple[str, ...] = (
    "characters/dialogue",
    "data/extradialogue",
    "data/events",
    "marriagedialogue",
    "roommatedialogue",
)
_DIALOGUE_TARGET_MARKERS: tuple[str, ...] = ("dialogue",)
_TARGET_VALUE_PATTERN = re.compile(r'"Target"\s*:\s*"([^"]*)"')


def _dialogue_loss_note(path: Path, relative: str) -> str:
    """解析失败时，从**原始文本**里估一句"这文件本来带多少台词"。

    任何异常都退化成空串：这里是在解释失败原因，不能反过来把导出器弄崩。
    """

    normalised = relative.replace("\\", "/").casefold()
    if any(marker in normalised for marker in _DIALOGUE_FILE_MARKERS):
        return "该文件本身就是对白/事件文件，里面的台词全部丢失"
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    targets = sorted(set(_TARGET_VALUE_PATTERN.findall(raw)))
    if not targets:
        return "该文件里没有对白 Target"
    hits = sum(
        1
        for target in targets
        if any(
            marker in target.replace("\\", "/").casefold()
            for marker in _DIALOGUE_TARGET_MARKERS
        )
    )
    return f"该文件里有 {hits} 个对白 Target（全文共 {len(targets)} 个不同 Target）"


def _read_payload(path: Path, root: Path, warnings: list[str]) -> Mapping[str, Any] | None:
    relative = _relative_path(path, root)
    try:
        return _load_json(path)
    except Exception as exc:  # noqa: BLE001 - exporter must continue past one bad asset
        note = _dialogue_loss_note(path, relative)
        suffix = f"—— {note}" if note else ""
        warnings.append(f"无法解析 JSON：{relative}（{type(exc).__name__}）{suffix}")
        return None


def _load_i18n_catalogs(
    root: Path,
    *,
    locale: str,
    warnings: list[str],
) -> dict[str, Mapping[str, Any]]:
    """读取 Content Patcher 根目录下的 default/语言覆盖字典。"""

    i18n_root = root / "i18n"
    if not i18n_root.is_dir():
        return {}
    catalogs: dict[str, Mapping[str, Any]] = {}
    for candidate in _locale_candidates(locale):
        path = i18n_root / f"{candidate}.json"
        if not path.is_file():
            continue
        payload = _read_payload(path, root, warnings)
        if isinstance(payload, Mapping):
            catalogs[candidate] = payload
    return catalogs


def _manifest_source_mod(root: Path, warnings: list[str]) -> str:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        warnings.append(f"缺少 manifest.json：{root.name}")
        return root.name
    payload = _read_payload(manifest_path, root, warnings)
    unique_id = payload.get("UniqueID") if payload else None
    if isinstance(unique_id, str) and unique_id.strip():
        return unique_id.strip()
    warnings.append(f"manifest.json 缺少 UniqueID：{root.name}")
    return root.name


def build_dialogue_corpus(
    *,
    vanilla_root: str | Path | None = None,
    vanilla_events_root: str | Path | None = None,
    mod_roots: Iterable[str | Path] = (),
    locale: str = "zh-CN",
    vanilla_locale: str | None = None,
) -> dict[str, Any]:
    """从已解包 vanilla 对白、事件和 Content Patcher 根目录构建语料。

    vanilla 侧只有**两个入口**：解包的 `Characters/Dialogue/*.json`（用文件名
    stem 当 npcId）与解包的 `Data/Events/*.json`（从事件脚本提参与者）。
    `Data/ExtraDialogue` **谁都不扫** —— Birdie 这类 `CanSocialize: FALSE`
    的 NPC 台词全放在那里，于是表现为"她没有台词"。补第三个入口是方案 A，
    会改变全库语料、需要重建索引，本轮不做（详见 `_read_payload` 上方的说明）。
    """

    corpus: dict[str, Any] = {
        "schemaVersion": 1,
        "records": [],
        "sources": [],
        "warnings": [],
    }
    records: list[dict[str, Any]] = corpus["records"]
    warnings: list[str] = corpus["warnings"]
    sources: list[dict[str, str]] = corpus["sources"]

    if vanilla_root is not None:
        root = Path(vanilla_root)
        if not root.is_dir():
            warnings.append(f"vanilla 根目录不存在：{root.name}")
        else:
            sources.append({"sourceMod": "vanilla", "root": root.name})
            _warn_for_unpacked_sources(root, warnings)
            vanilla_paths = _select_vanilla_dialogue_paths(
                root.rglob("*.json"),
                root,
                vanilla_locale,
            )
            for path in vanilla_paths:
                relative = _relative_path(path, root)
                payload = _read_payload(path, root, warnings)
                if payload is None:
                    continue
                records.extend(
                    _extract_plain_dialogue(
                        payload,
                        npc_id=path.stem,
                        source_mod="vanilla",
                        source_path=relative,
                    )
                )

    if vanilla_events_root is not None:
        root = Path(vanilla_events_root)
        if not root.is_dir():
            warnings.append(f"vanilla 事件根目录不存在：{root.name}")
        else:
            sources.append({"sourceMod": "vanilla", "root": root.name})
            _warn_for_unpacked_sources(root, warnings)
            event_paths = _select_vanilla_dialogue_paths(
                root.rglob("*.json"),
                root,
                vanilla_locale,
            )
            for path in event_paths:
                relative = _relative_path(path, root)
                payload = _read_payload(path, root, warnings)
                if payload is None or not isinstance(payload, Mapping):
                    continue
                records.extend(
                    _extract_plain_events(
                        payload,
                        source_mod="vanilla",
                        source_path=Path("Data") / "Events" / relative,
                    )
                )

    for raw_root in mod_roots:
        root = Path(raw_root)
        if not root.is_dir():
            warnings.append(f"mod 根目录不存在：{root.name}")
            continue
        source_mod = _manifest_source_mod(root, warnings)
        sources.append({"sourceMod": source_mod, "root": root.name})
        _warn_for_unpacked_sources(root, warnings)
        i18n_catalogs = _load_i18n_catalogs(
            root,
            locale=locale,
            warnings=warnings,
        )
        for path in sorted(root.rglob("*.json")):
            relative = _relative_path(path, root)
            if path.name.casefold() in {"manifest.json", "config.json"}:
                continue
            if "i18n" in {part.casefold() for part in path.parts}:
                continue
            payload = _read_payload(path, root, warnings)
            if payload is None:
                continue
            if isinstance(payload.get("Changes"), list):
                extracted, extracted_warnings = extract_content_patcher_dialogue(
                    payload,
                    source_mod=source_mod,
                    source_path=relative,
                    i18n_catalogs=i18n_catalogs,
                    locale=locale,
                )
                records.extend(extracted)
                warnings.extend(extracted_warnings)

    records[:] = _dedupe_records(records)
    return corpus


def write_dialogue_corpus(corpus: Mapping[str, Any], output_path: str | Path) -> None:
    """原子写入导出文件。"""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)
