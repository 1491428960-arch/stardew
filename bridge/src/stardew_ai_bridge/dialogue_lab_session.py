from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


log = logging.getLogger(__name__)

SESSION_VERSION = 1
MAX_MESSAGES = 400
MAX_HISTORY = 50
MAX_TEXT_LENGTH = 4000
MAX_NPC_ID_LENGTH = 100
MAX_DISPLAY_NAME_LENGTH = 100
MAX_PROVIDER_LENGTH = 50
MAX_WARNING_LENGTH = 500


def empty_session() -> dict[str, object]:
    return {
        "version": SESSION_VERSION,
        "messages": [],
        "history": [],
        "lastDiagnostics": None,
    }


def _bounded_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    return value[:limit]


def _finite_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _normalize_usage(value: Any) -> dict[str, int] | None:
    if not isinstance(value, Mapping):
        return None
    usage: dict[str, int] = {}
    for key in ("inputTokens", "outputTokens", "totalTokens"):
        number = value.get(key)
        if isinstance(number, int) and not isinstance(number, bool) and number >= 0:
            usage[key] = number
    return usage or None


def _normalize_message(value: Any) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    role = value.get("role")
    text = _bounded_text(value.get("text"), limit=MAX_TEXT_LENGTH)
    if role not in {"user", "npc"} or text is None:
        return None

    message: dict[str, object] = {"role": role, "text": text}
    npc_id = _bounded_text(value.get("npcId"), limit=MAX_NPC_ID_LENGTH)
    if npc_id:
        message["npcId"] = npc_id
    display_name = _bounded_text(
        value.get("displayName"), limit=MAX_DISPLAY_NAME_LENGTH
    )
    if display_name is not None:
        message["displayName"] = display_name
    created_at = _finite_number(value.get("createdAt"))
    if created_at is not None:
        message["createdAt"] = created_at
    return message


def _normalize_history_item(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    role = value.get("role")
    content = _bounded_text(value.get("content"), limit=MAX_TEXT_LENGTH)
    if role not in {"user", "assistant"} or content is None:
        return None
    return {"role": role, "content": content}


def _normalize_diagnostics(value: Any) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None

    diagnostics: dict[str, object] = {}
    provider = _bounded_text(value.get("provider"), limit=MAX_PROVIDER_LENGTH)
    if provider is not None:
        diagnostics["provider"] = provider
    latency_ms = _finite_number(value.get("latencyMs"))
    if latency_ms is not None and latency_ms >= 0:
        diagnostics["latencyMs"] = latency_ms
    fallback = value.get("fallback")
    if isinstance(fallback, bool):
        diagnostics["fallback"] = fallback
    warnings = value.get("warnings")
    if isinstance(warnings, list):
        diagnostics["warnings"] = [
            item[:MAX_WARNING_LENGTH]
            for item in warnings[:20]
            if isinstance(item, str)
        ]
    reply = _bounded_text(value.get("reply"), limit=MAX_TEXT_LENGTH)
    if reply is not None:
        diagnostics["reply"] = reply
    usage = _normalize_usage(value.get("usage"))
    if usage is not None:
        diagnostics["usage"] = usage
    return diagnostics


def normalize_session(value: Any) -> dict[str, object]:
    """只保留实验室恢复所需字段，不让请求字段进入本地会话文件。"""
    if not isinstance(value, Mapping):
        return empty_session()

    raw_messages = value.get("messages")
    messages = (
        [item for item in (_normalize_message(raw) for raw in raw_messages) if item]
        if isinstance(raw_messages, list)
        else []
    )[-MAX_MESSAGES:]
    raw_history = value.get("history")
    history = (
        [
            item
            for item in (
                _normalize_history_item(raw) for raw in raw_history
            )
            if item
        ][-MAX_HISTORY:]
        if isinstance(raw_history, list)
        else []
    )
    return {
        "version": SESSION_VERSION,
        "messages": messages,
        "history": history,
        "lastDiagnostics": _normalize_diagnostics(value.get("lastDiagnostics")),
    }


class DialogueLabSessionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, object]:
        if not self.path.exists():
            return empty_session()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping) or value.get("version") != SESSION_VERSION:
                raise ValueError("不支持的会话版本")
            return normalize_session(value)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            log.warning("对话实验室会话文件损坏，将恢复空会话: %s", exc)
            self._backup_corrupt_file()
            return empty_session()

    def save(self, value: Any) -> dict[str, object]:
        session = normalize_session(value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(session, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
        return session

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _backup_corrupt_file(self) -> None:
        if not self.path.exists():
            return
        candidate = self.path.with_name(f"{self.path.name}.corrupt")
        suffix = 1
        while candidate.exists():
            candidate = self.path.with_name(f"{self.path.name}.corrupt.{suffix}")
            suffix += 1
        try:
            os.replace(self.path, candidate)
        except OSError:
            log.warning("无法备份损坏的会话文件: %s", self.path)
