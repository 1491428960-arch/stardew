"""运行时已解析对白的可追溯 JSONL 记录。

Content Patcher 的动态键只能在游戏实际求值后确认具体台词。本模块提供一个
小而严格的边界：只接受已经解析完成的文本，记录它对应的离线 corpus 证据，
并用内容哈希保证重复采样不会无限膨胀。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


RUNTIME_SAMPLE_SCHEMA_VERSION = 1
# 花括号数宽松：CP 用 `{{i18n:...}}`，别的 mod 会留单花括号 `{i18n:...}`。
_UNRESOLVED_I18N = re.compile(r"\{\{?\s*i18n\s*:", re.IGNORECASE)
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{2})")
_MAX_TEXT_LENGTH = 2000
_MAX_CONTEXT_ITEMS = 32


def _required_text(raw: Mapping[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"运行时样本缺少 {field}")
    return value.strip()


def _relative_path(value: str) -> str:
    path = value.strip().replace("\\", "/")
    if not path or _ABSOLUTE_PATH.match(path):
        raise ValueError("sourcePath 必须是相对路径")
    return path.lstrip("./") or "unknown.json"


def _safe_mapping(value: object, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} 必须是对象")
    if len(value) > _MAX_CONTEXT_ITEMS:
        raise ValueError(f"{field} 条目过多")
    result: dict[str, Any] = {}
    for key, item in value.items():
        name = str(key).strip()
        if not name or len(name) > 80:
            raise ValueError(f"{field} 包含无效键")
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[name] = item
        elif isinstance(item, list) and all(
            isinstance(entry, (str, int, float, bool)) or entry is None
            for entry in item
        ):
            result[name] = list(item)
        else:
            raise ValueError(f"{field}.{name} 必须是简单值")
    return result


def attribute_runtime_sample(
    raw: Mapping[str, Any],
    corpus_records: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """对唯一的 NPC+sourceKey+已解析文本命中补回静态来源。

    运行时采样器故意不猜测来源；只有 corpus 中恰好一条记录同时满足三项
    条件时才归属。重复键、文本不一致或缺少字段都会保持
    ``runtime.unattributed``，避免把动态分支误挂到错误 Mod。
    """

    result = dict(raw)
    npc_id = raw.get("npcId")
    source_key = raw.get("candidateKey", raw.get("sourceKey"))
    text = raw.get("text")
    if not all(isinstance(value, str) and value.strip() for value in (npc_id, source_key, text)):
        return result
    matches: list[Mapping[str, Any]] = []
    for record in corpus_records:
        if not isinstance(record, Mapping):
            continue
        if str(record.get("npcId", "")).casefold() != npc_id.casefold():
            continue
        if str(record.get("sourceKey", "")).strip() != source_key.strip():
            continue
        resolved_text = record.get("resolvedText", record.get("text"))
        if not isinstance(resolved_text, str) or resolved_text.strip() != text.strip():
            continue
        if not str(record.get("sourceMod", "")).strip():
            continue
        matches.append(record)
    if len(matches) != 1:
        return result
    match = matches[0]
    source_mod = str(match["sourceMod"]).strip()
    source_path = match.get("sourcePath")
    canonical_key = str(match.get("sourceKey", source_key)).strip()
    if isinstance(source_path, str) and source_path.strip():
        result["sourcePath"] = source_path.strip()
    result["sourceMod"] = source_mod
    result["sourceKey"] = canonical_key
    result["attribution"] = {
        "match": "npc+sourceKey+text",
        "sourceMod": source_mod,
        "sourcePath": result.get("sourcePath", ""),
        "sourceKey": canonical_key,
    }
    return result


def normalise_runtime_sample(raw: Mapping[str, Any]) -> dict[str, Any]:
    """校验并规范一条运行时样本；不会保留本机绝对路径或未解析模板。"""

    if not isinstance(raw, Mapping):
        raise ValueError("运行时样本必须是对象")
    source_sample_id = _required_text(raw, "sourceSampleId")
    npc_id = _required_text(raw, "npcId")
    source_mod = _required_text(raw, "sourceMod")
    source_path = _relative_path(_required_text(raw, "sourcePath"))
    source_key = _required_text(raw, "sourceKey")
    text = _required_text(raw, "text")
    if len(text) > _MAX_TEXT_LENGTH:
        raise ValueError("运行时对白过长")
    if _UNRESOLVED_I18N.search(text):
        raise ValueError("运行时样本文本仍含未解析 i18n")

    conditions = _safe_mapping(raw.get("conditions"), "conditions")
    game_state = _safe_mapping(raw.get("gameState"), "gameState")
    attribution = _safe_mapping(raw.get("attribution"), "attribution")
    candidate_key = raw.get("candidateKey")
    if candidate_key is not None and (
        not isinstance(candidate_key, str) or not candidate_key.strip()
    ):
        raise ValueError("candidateKey 必须是非空字符串")
    captured_at = raw.get("capturedAt")
    if captured_at is not None and (
        not isinstance(captured_at, str) or not captured_at.strip()
    ):
        raise ValueError("capturedAt 必须是字符串")

    fingerprint = json.dumps(
        {
            "sourceSampleId": source_sample_id,
            "text": text,
            "candidateKey": candidate_key.strip() if isinstance(candidate_key, str) else None,
            "conditions": conditions,
            "gameState": game_state,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    sample_id = f"runtime:{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:24]}"
    result: dict[str, Any] = {
        "schemaVersion": RUNTIME_SAMPLE_SCHEMA_VERSION,
        "sampleId": sample_id,
        "sourceSampleId": source_sample_id,
        "npcId": npc_id,
        "sourceMod": source_mod,
        "sourcePath": source_path,
        "sourceKey": source_key,
        "text": text,
        "evidenceKind": "runtime_dialogue",
    }
    if isinstance(candidate_key, str) and candidate_key.strip():
        result["candidateKey"] = candidate_key.strip()
    if conditions:
        result["conditions"] = conditions
    if game_state:
        result["gameState"] = game_state
    if attribution:
        result["attribution"] = attribution
    if isinstance(captured_at, str) and captured_at.strip():
        result["capturedAt"] = captured_at.strip()
    return result


def load_runtime_samples(path: str | Path) -> list[dict[str, Any]]:
    """读取 JSONL；空行忽略，错误包含行号，便于定位采样器问题。"""

    source = Path(path)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"无法读取运行时样本：{source.name}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            sample = normalise_runtime_sample(raw)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"运行时样本第 {line_number} 行无效：{exc}") from exc
        if sample["sampleId"] not in seen:
            rows.append(sample)
            seen.add(sample["sampleId"])
    return rows


def append_runtime_sample(path: str | Path, raw: Mapping[str, Any]) -> dict[str, Any]:
    """校验后追加一条样本；同一内容哈希已存在时不重复写入。"""

    destination = Path(path)
    sample = normalise_runtime_sample(raw)
    existing = load_runtime_samples(destination) if destination.exists() else []
    if any(item["sampleId"] == sample["sampleId"] for item in existing):
        return sample
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(sample, ensure_ascii=False, separators=(",", ":")) + "\n")
    return sample
