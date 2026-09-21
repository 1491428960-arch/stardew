from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.dialogue_lab_session import (
    SESSION_VERSION,
    DialogueLabSessionStore,
    empty_session,
)


def _session() -> dict[str, object]:
    return {
        "version": SESSION_VERSION,
        "messages": [
            {
                "role": "user",
                "text": "你好",
                "npcId": "Rasmodia",
                "displayName": "Rasmodia",
                "createdAt": 123,
            }
        ],
        "history": [{"role": "user", "content": "你好"}],
        # 请求路径开关是会话状态的一部分（决定下一次请求发哪套 prompt），
        # 因此会话文件与它的契约测试一起带上这个字段。
        "compactPrompt": True,
        "lastDiagnostics": {
            "provider": "local",
            "latencyMs": 42,
            "fallback": False,
            "warnings": [],
            "reply": "你好。",
            "usage": {
                "inputTokens": 123,
                "outputTokens": 17,
                "totalTokens": 140,
            },
        },
    }


def test_session_store_saves_and_loads_versioned_session(tmp_path: Path) -> None:
    path = tmp_path / "artifacts" / "dialogue-lab-session.json"
    store = DialogueLabSessionStore(path)

    store.save(_session())

    assert store.load() == _session()
    assert json.loads(path.read_text(encoding="utf-8")) == _session()


def test_session_store_returns_empty_session_for_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "dialogue-lab-session.json"
    path.write_text("{not-json", encoding="utf-8")
    store = DialogueLabSessionStore(path)

    assert store.load() == empty_session()
    assert not path.exists()
    assert list(tmp_path.glob("dialogue-lab-session.json.corrupt*"))


def test_session_store_filters_sensitive_and_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "dialogue-lab-session.json"
    store = DialogueLabSessionStore(path)
    payload = {
        **_session(),
        "apiKey": "secret",
        "token": "secret",
        "prompt": "private prompt",
        "lastPayload": {"message": "private request"},
        "messages": [
            {
                **_session()["messages"][0],
                "request": "private request",
                "token": "secret",
            }
        ],
        "lastDiagnostics": {
            **_session()["lastDiagnostics"],
            "request": "private request",
            "apiKey": "secret",
        },
    }

    saved = store.save(payload)

    assert saved == _session()
    assert store.load() == _session()
    assert "secret" not in path.read_text(encoding="utf-8")
    assert "private request" not in path.read_text(encoding="utf-8")


def test_session_store_clear_removes_local_file(tmp_path: Path) -> None:
    path = tmp_path / "dialogue-lab-session.json"
    store = DialogueLabSessionStore(path)
    store.save(_session())

    store.clear()

    assert not path.exists()
    assert store.load() == empty_session()


def test_session_store_writes_atomically_without_leftover_temp_files(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "dialogue-lab-session.json"
    store = DialogueLabSessionStore(path)

    store.save(_session())

    assert path.exists()
    assert not list(path.parent.glob("*.tmp"))
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == SESSION_VERSION


def test_session_store_keeps_safe_usage_but_discards_sensitive_usage_neighbors(
    tmp_path: Path,
) -> None:
    path = tmp_path / "dialogue-lab-session.json"
    store = DialogueLabSessionStore(path)

    payload = {
        **_session(),
        "lastDiagnostics": {
            **_session()["lastDiagnostics"],
            "usage": {
                "inputTokens": 123,
                "outputTokens": 17,
                "totalTokens": 140,
                "prompt": "private prompt",
                "apiKey": "secret key",
            },
            "request": "private request",
        },
    }

    store.save(payload)

    loaded = store.load()
    assert loaded["lastDiagnostics"]["usage"] == {
        "inputTokens": 123,
        "outputTokens": 17,
        "totalTokens": 140,
    }
    saved_text = path.read_text(encoding="utf-8")
    assert "private prompt" not in saved_text
    assert "secret key" not in saved_text
    assert "private request" not in saved_text
