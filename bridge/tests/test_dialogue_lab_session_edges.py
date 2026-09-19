"""`dialogue_lab_session` 的校验与健壮性边界。

2026-09-20 用覆盖率定位到它只有 **85%**，未覆盖的全是**异常与恢复路径**——
而“会话文件损坏时还能不能起来”恰恰是这个模块存在的理由。补上：

- **写入是原子的**：先写临时文件再 `os.replace`；失败时清掉临时文件再抛。
- **损坏文件会被备份而不是覆盖**：`.corrupt` → `.corrupt.1` → `.corrupt.2` 递增，
  这样反复损坏也不会把上一份现场冲掉。
- **恢复是静默的**：任何损坏都返回空会话并记一条 warning，不让实验室打不开。
- **`bool` 不是数字**：`createdAt=True`、usage 里的 `True`、非布尔的 `fallback`
  都不该被当成 1（同一手法在 `providers`／`evaluation_budget` 里也出现过）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from stardew_ai_bridge.dialogue_lab_session import (
    DialogueLabSessionStore,
    empty_session,
    normalize_session,
    _bounded_text,
    _finite_number,
    _normalize_diagnostics,
    _normalize_history_item,
    _normalize_message,
    _normalize_usage,
)


def _store(tmp_path: Path) -> DialogueLabSessionStore:
    return DialogueLabSessionStore(tmp_path / "session.json")


# --- 基础归一化辅助 ---------------------------------------------------------


def test_bounded_text_truncates_but_does_not_trim() -> None:
    assert _bounded_text("  x  ", limit=10) == "  x  "
    assert _bounded_text("abcdef", limit=3) == "abc"
    assert _bounded_text(42, limit=10) is None
    assert _bounded_text(None, limit=10) is None


@pytest.mark.parametrize("value", [True, False, "3", None, [], {}])
def test_finite_number_rejects_non_numbers_and_booleans(value: object) -> None:
    # bool 是 int 的子类；不排除的话 True 会被当成 1。
    assert _finite_number(value) is None


def test_finite_number_accepts_int_and_float() -> None:
    assert _finite_number(3) == 3
    assert _finite_number(1.5) == 1.5


def test_usage_keeps_only_non_negative_ints() -> None:
    assert _normalize_usage(
        {"inputTokens": 5, "outputTokens": True, "totalTokens": -1}
    ) == {"inputTokens": 5}


def test_usage_returns_none_when_nothing_usable() -> None:
    assert _normalize_usage({"x": 1}) is None
    assert _normalize_usage("not a mapping") is None


# --- 消息与历史 -------------------------------------------------------------


@pytest.mark.parametrize("role", ["system", "assistant", "", None, 1])
def test_message_role_must_be_user_or_npc(role: object) -> None:
    assert _normalize_message({"role": role, "text": "x"}) is None


def test_message_rejects_non_mapping_and_missing_text() -> None:
    assert _normalize_message("nope") is None
    assert _normalize_message({"role": "user"}) is None
    assert _normalize_message({"role": "user", "text": 42}) is None


def test_message_keeps_optional_fields_when_present() -> None:
    message = _normalize_message(
        {"role": "npc", "text": "hi", "npcId": "Shane", "displayName": "谢恩", "createdAt": 12}
    )

    assert message == {
        "role": "npc",
        "text": "hi",
        "npcId": "Shane",
        "displayName": "谢恩",
        "createdAt": 12,
    }


def test_message_drops_a_boolean_timestamp() -> None:
    assert "createdAt" not in _normalize_message(
        {"role": "user", "text": "x", "createdAt": True}
    )


@pytest.mark.parametrize("role", ["npc", "system", "", None])
def test_history_role_must_be_user_or_assistant(role: object) -> None:
    # 注意历史里是 assistant，不是 npc——两处的角色名不一样。
    assert _normalize_history_item({"role": role, "content": "x"}) is None


def test_history_item_accepts_both_valid_roles() -> None:
    assert _normalize_history_item({"role": "user", "content": "a"}) == {
        "role": "user",
        "content": "a",
    }
    assert _normalize_history_item({"role": "assistant", "content": "b"}) == {
        "role": "assistant",
        "content": "b",
    }


# --- 诊断 -------------------------------------------------------------------


def test_diagnostics_none_and_non_mapping() -> None:
    assert _normalize_diagnostics(None) is None
    assert _normalize_diagnostics("x") is None


def test_diagnostics_keeps_only_well_formed_fields() -> None:
    diagnostics = _normalize_diagnostics(
        {
            "provider": "cloud",
            "latencyMs": -5,  # 负数不保留
            "fallback": "no",  # 非布尔不保留
            "warnings": ["ok", 1, "z" * 600],
        }
    )

    assert diagnostics is not None
    assert diagnostics["provider"] == "cloud"
    assert "latencyMs" not in diagnostics
    assert "fallback" not in diagnostics
    # 只有字符串留下，且每条被截到 500
    assert diagnostics["warnings"] == ["ok", "z" * 500]


def test_diagnostics_caps_the_warning_list() -> None:
    diagnostics = _normalize_diagnostics({"warnings": [f"w{i}" for i in range(30)]})

    assert diagnostics is not None
    assert len(diagnostics["warnings"]) == 20


def test_diagnostics_keeps_a_valid_usage_block() -> None:
    diagnostics = _normalize_diagnostics({"usage": {"inputTokens": 1, "totalTokens": 2}})

    assert diagnostics == {"usage": {"inputTokens": 1, "totalTokens": 2}}


# --- normalize_session ------------------------------------------------------


def test_non_mapping_session_becomes_empty() -> None:
    assert normalize_session("x") == empty_session()
    assert normalize_session(None) == empty_session()


def test_session_caps_messages_and_history_keeping_the_latest() -> None:
    session = normalize_session(
        {
            "messages": [{"role": "user", "text": str(i)} for i in range(405)],
            "history": [{"role": "user", "content": str(i)} for i in range(55)],
        }
    )

    assert len(session["messages"]) == 400
    assert len(session["history"]) == 50
    # 保留的是**最后**若干条
    assert session["messages"][0]["text"] == "5"
    assert session["history"][0]["content"] == "5"


def test_invalid_items_are_dropped_silently() -> None:
    session = normalize_session(
        {
            "messages": [{"role": "user", "text": "ok"}, {"role": "bad", "text": "x"}, 7],
            "history": [{"role": "assistant", "content": "ok"}, {"role": "npc", "content": "x"}],
        }
    )

    assert len(session["messages"]) == 1
    assert len(session["history"]) == 1


def test_version_is_always_rewritten_to_current() -> None:
    assert normalize_session({"version": 99})["version"] == 1


# --- Store.load -------------------------------------------------------------


def test_load_returns_empty_session_when_the_file_is_missing(tmp_path: Path) -> None:
    assert _store(tmp_path).load() == empty_session()


def test_load_backs_up_a_file_with_an_unsupported_version(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"version": 99}), encoding="utf-8")

    assert store.load() == empty_session()
    assert (tmp_path / "session.json.corrupt").exists()


def test_repeated_corruption_uses_incrementing_backup_names(tmp_path: Path) -> None:
    # 反复损坏不能把上一份现场冲掉。
    store = _store(tmp_path)
    for _ in range(3):
        store.path.write_text("{bad", encoding="utf-8")
        assert store.load() == empty_session()

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "session.json.corrupt",
        "session.json.corrupt.1",
        "session.json.corrupt.2",
    ]


def test_load_recovers_from_broken_json(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("not json at all", encoding="utf-8")

    assert store.load() == empty_session()


# --- Store.save / clear -----------------------------------------------------


def test_save_round_trips_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save({"messages": [{"role": "user", "text": "hi"}], "history": []})

    assert store.load()["messages"] == [{"role": "user", "text": "hi"}]
    # 目录里只应有正式文件，没有 .tmp 残留
    assert sorted(p.name for p in tmp_path.iterdir()) == ["session.json"]


def test_save_cleans_up_the_temporary_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(RuntimeError):
        store.save({"messages": []})

    # 临时文件必须被清掉，正式文件不该出现
    assert list(tmp_path.glob("*.tmp")) == []
    assert not store.path.exists()


def test_clear_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save({"messages": []})

    store.clear()
    store.clear()  # 第二次不该抛 FileNotFoundError

    assert not store.path.exists()
