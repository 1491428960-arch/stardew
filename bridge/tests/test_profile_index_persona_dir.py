"""索引器按**结构**区分 persona 文件与数据文件（B13 的索引侧）。

`data/personas/` 里混放了非 persona 文件（`behavior-quality-scenarios.json`、
`behavior-examples.json`），它们的顶层键是 `schemaVersion`／`description`／`scenarios`
——都不是映射，却被逐条当成 persona 报成 `invalid persona`。索引体检里那 **3 条噪音
警告**就是这么来的：

    invalid persona: behavior-quality-scenarios.json:schemaVersion
    invalid persona: behavior-quality-scenarios.json:description
    invalid persona: behavior-quality-scenarios.json:scenarios

B13 给了两个选项（搬走文件／让索引器按结构跳过），这里选**后者**：零文件移动、零风险，
也不依赖文件名清单。判据是**结构**——persona 条目必然是映射。

同时**保留真正的坏信号**：坏 JSON 仍报 `invalid JSON`；只有"条目不是映射"与"整份文件
没有一个 persona 条目"不再刷警告（后者就是数据文件本身）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.profile_index import ProfileIndexBuilder


def _run(persona_dir: Path) -> tuple[dict[str, object], list[str]]:
    builder = ProfileIndexBuilder(persona_dir)
    profiles: dict[str, object] = {}
    warnings: list[str] = []
    builder._load_personas(profiles, warnings, [], [], [])
    return profiles, warnings


def _write(path: Path, payload: object, *, raw: str | None = None) -> None:
    text = raw if raw is not None else json.dumps(payload, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")


# --- 数据文件不再刷警告 -----------------------------------------------------


def test_a_data_file_produces_no_warnings(tmp_path: Path) -> None:
    _write(
        tmp_path / "behavior-quality-scenarios.json",
        {"schemaVersion": 2, "description": "行为样例", "scenarios": [{"a": 1}]},
    )

    profiles, warnings = _run(tmp_path)

    assert warnings == []
    assert profiles == {}


def test_a_data_file_is_accompanied_by_real_personas_fine(tmp_path: Path) -> None:
    _write(tmp_path / "vanilla.json", {"personas": {"Shane": {"displayName": "谢恩"}}})
    _write(
        tmp_path / "behavior-quality-scenarios.json",
        {"schemaVersion": 2, "description": "行为样例", "scenarios": []},
    )

    profiles, warnings = _run(tmp_path)

    assert warnings == []
    assert "Shane" in profiles


# --- 真正的信号仍在 ---------------------------------------------------------


def test_broken_json_is_still_reported(tmp_path: Path) -> None:
    _write(tmp_path / "broken.json", None, raw="{坏的")

    _, warnings = _run(tmp_path)

    assert warnings == ["invalid JSON: broken.json"]


def test_a_non_mapping_personas_key_is_still_reported(tmp_path: Path) -> None:
    # `personas` 键存在但值不是映射——这是真问题，不能静默。
    _write(tmp_path / "weird.json", {"personas": ["not", "a", "mapping"]})

    _, warnings = _run(tmp_path)

    assert warnings == ["invalid personas mapping: weird.json"]


def test_an_empty_npc_id_is_still_reported(tmp_path: Path) -> None:
    _write(tmp_path / "vanilla.json", {"personas": {"  ": {"displayName": "无名"}}})

    _, warnings = _run(tmp_path)

    assert warnings == ["empty npcId: vanilla.json"]


def test_a_missing_directory_is_still_reported(tmp_path: Path) -> None:
    _, warnings = _run(tmp_path / "nope")

    assert warnings == ["persona directory not found: nope"]


# --- 条目级的静默过滤 -------------------------------------------------------


def test_non_mapping_entries_are_silently_dropped(tmp_path: Path) -> None:
    # 同一个文件里混了一个非映射条目：它不进 profiles，但也不再单条报警。
    _write(
        tmp_path / "vanilla.json",
        {"personas": {"Shane": {"displayName": "谢恩"}, "notAMapping": 42}},
    )

    profiles, warnings = _run(tmp_path)

    assert warnings == []
    assert set(profiles) == {"Shane"}


def test_a_file_whose_entries_are_all_non_mappings_is_skipped(tmp_path: Path) -> None:
    # 全是非映射 → 整份文件按数据文件跳过，连 markers 都不用解析。
    _write(tmp_path / "all-data.json", {"a": 1, "b": "x", "c": [1]})

    profiles, warnings = _run(tmp_path)

    assert warnings == []
    assert profiles == {}


def test_the_filename_based_skip_still_works(tmp_path: Path) -> None:
    # behavior-examples.json 早就按文件名跳过；新的结构判据与它并存，不该互相干扰。
    _write(tmp_path / "behavior-examples.json", {"personas": {"X": {"a": 1}}})

    assert _run(tmp_path) == ({}, [])


@pytest.mark.parametrize("npc_id", ["Shane", "Emily"])
def test_real_personas_are_still_loaded(tmp_path: Path, npc_id: str) -> None:
    _write(tmp_path / "vanilla.json", {"personas": {npc_id: {"displayName": npc_id}}})

    profiles, warnings = _run(tmp_path)

    assert npc_id in profiles
    assert warnings == []
