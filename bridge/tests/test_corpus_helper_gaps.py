"""`corpus` 里四个边角函数：噪声清理、事件提取入口、容错读 JSON、manifest 归属。

用**函数级覆盖率排序**挑出来的——它们各缺 1/3 到 1/2，而缺的**全是错误分支**：
非字符串输入、非 Mapping 载荷、JSON 解析失败、manifest 缺失或没有 UniqueID。

这些分支不测的后果很具体：导出器（`build_dialogue_corpus`）会**因为一个坏资产整批中断**，
而它们存在的意义恰恰是“**跳过坏的、继续导出好的**”。

顺带一提：`_read_payload` 的警告文案就是索引文件里那 9 条“无法解析 JSON：…（JSONDecodeError）”
的来源（见 `scripts/audit_profile_index.py` 的体检输出）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.corpus import (
    _extract_plain_events,
    _manifest_source_mod,
    _read_payload,
    clean_dialogue_noise,
)


# --- clean_dialogue_noise ---------------------------------------------------


@pytest.mark.parametrize("value", [None, 42, ["a"], b"x"])
def test_non_strings_are_returned_unchanged(value: object) -> None:
    # 注意是**原样返回**，不是返回空字符串——调用方可能靠这个区分“没给”与“洗成空”。
    assert clean_dialogue_noise(value) is value  # type: ignore[arg-type]


def test_strings_are_cleaned() -> None:
    assert clean_dialogue_noise("你好。 e 世界") == "你好。世界"


# --- _extract_plain_events --------------------------------------------------


@pytest.mark.parametrize("payload", ["x", None, 42, ["a"]])
def test_non_mapping_event_payloads_yield_nothing(payload: object) -> None:
    assert (
        _extract_plain_events(payload, source_mod="Vanilla", source_path="events/x.json")  # type: ignore[arg-type]
        == []
    )


def test_an_empty_event_payload_yields_nothing() -> None:
    assert _extract_plain_events({}, source_mod="Vanilla", source_path="events/x.json") == []


# --- _read_payload ----------------------------------------------------------


def test_a_good_json_file_is_read(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    warnings: list[str] = []

    assert _read_payload(path, tmp_path, warnings) == {"a": 1}
    assert warnings == []


def test_broken_json_is_reported_and_skipped(tmp_path: Path) -> None:
    # 这是导出器“跳过坏的、继续好的”的关键一步。
    path = tmp_path / "broken.json"
    path.write_text("{不是 JSON", encoding="utf-8")
    warnings: list[str] = []

    assert _read_payload(path, tmp_path, warnings) is None
    assert len(warnings) == 1
    assert "无法解析 JSON" in warnings[0]
    # 警告里带相对路径与异常类型名，便于定位是哪个资产
    assert "broken.json" in warnings[0]
    assert "JSONDecodeError" in warnings[0]


def test_a_missing_file_is_also_tolerated(tmp_path: Path) -> None:
    warnings: list[str] = []

    assert _read_payload(tmp_path / "nope.json", tmp_path, warnings) is None
    assert len(warnings) == 1
    assert "无法解析 JSON" in warnings[0]


# --- _manifest_source_mod ---------------------------------------------------


def test_a_missing_manifest_warns_and_falls_back_to_the_directory_name(tmp_path: Path) -> None:
    mod_root = tmp_path / "SomeMod"
    mod_root.mkdir()
    warnings: list[str] = []

    assert _manifest_source_mod(mod_root, warnings) == "SomeMod"
    assert warnings and "缺少 manifest.json" in warnings[0]


def test_a_unique_id_is_used_when_present(tmp_path: Path) -> None:
    mod_root = tmp_path / "SomeMod"
    mod_root.mkdir()
    (mod_root / "manifest.json").write_text(
        json.dumps({"UniqueID": "FlashShifter.SVE"}), encoding="utf-8"
    )
    warnings: list[str] = []

    assert _manifest_source_mod(mod_root, warnings) == "FlashShifter.SVE"
    assert warnings == []


@pytest.mark.parametrize("unique_id", [None, "", "   ", 42])
def test_a_missing_or_blank_unique_id_warns_and_falls_back(
    tmp_path: Path, unique_id: object
) -> None:
    mod_root = tmp_path / "SomeMod"
    mod_root.mkdir()
    payload = {} if unique_id is None else {"UniqueID": unique_id}
    (mod_root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    warnings: list[str] = []

    assert _manifest_source_mod(mod_root, warnings) == "SomeMod"
    assert warnings and "缺少 UniqueID" in warnings[-1]


def test_a_broken_manifest_also_falls_back(tmp_path: Path) -> None:
    mod_root = tmp_path / "SomeMod"
    mod_root.mkdir()
    (mod_root / "manifest.json").write_text("{坏的", encoding="utf-8")
    warnings: list[str] = []

    # 解析失败会先记一条“无法解析 JSON”，再记一条“缺少 UniqueID”，最后回落目录名
    assert _manifest_source_mod(mod_root, warnings) == "SomeMod"
    assert any("无法解析 JSON" in warning for warning in warnings)
    assert any("缺少 UniqueID" in warning for warning in warnings)
