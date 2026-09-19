"""`build_dialogue_corpus` 的根目录容错与 payload 跳过分支。

按**缺失行数**排序挑出来的——缺的 7 行**全是容错分支**，没有一行在主路径上。

它在三处各有一个“**根目录不存在就警告、但不中断**”的分支（vanilla 对白根、vanilla
事件根、mod 根），以及四个“**读不出 payload 就跳过**”的分支。这类分支不测的后果很具体：
**一个路径写错就整批构建静默少数据**——而导出器的设计意图正是“**跳过坏的、继续好的**”。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.corpus import build_dialogue_corpus


def _bad_json(path: Path) -> Path:
    path.write_text("{坏的", encoding="utf-8")
    return path


# --- 三个根目录不存在 -------------------------------------------------------


def test_a_missing_vanilla_root_warns_once(tmp_path: Path) -> None:
    corpus = build_dialogue_corpus(vanilla_root=tmp_path / "nope")

    assert corpus["records"] == []
    assert corpus["sources"] == []
    assert corpus["warnings"] == ["vanilla 根目录不存在：nope"]


def test_a_missing_vanilla_events_root_warns_once(tmp_path: Path) -> None:
    corpus = build_dialogue_corpus(vanilla_events_root=tmp_path / "no-events")

    assert corpus["warnings"] == ["vanilla 事件根目录不存在：no-events"]


def test_a_missing_mod_root_warns_and_is_skipped(tmp_path: Path) -> None:
    corpus = build_dialogue_corpus(mod_roots=[tmp_path / "no-mod"])

    assert corpus["warnings"] == ["mod 根目录不存在：no-mod"]


def test_no_roots_at_all_yields_an_empty_but_valid_corpus(tmp_path: Path) -> None:
    corpus = build_dialogue_corpus()

    assert corpus["records"] == []
    assert corpus["warnings"] == []
    assert corpus["schemaVersion"] == 1


def test_a_missing_mod_root_does_not_stop_the_others(tmp_path: Path) -> None:
    # 一个路径写错不该让整批构建少掉其他根的内容。
    good = tmp_path / "GoodMod"
    good.mkdir()

    corpus = build_dialogue_corpus(mod_roots=[tmp_path / "no-mod", good])

    assert "mod 根目录不存在：no-mod" in corpus["warnings"]
    # 好的那个根仍然被登记进 sources（即使它里面没有可提取的对白）
    assert any(source["root"] == "GoodMod" for source in corpus["sources"])


# --- payload 读不出就跳过 ---------------------------------------------------


def test_a_broken_json_file_is_skipped_but_reported(tmp_path: Path) -> None:
    root = tmp_path / "Vanilla"
    root.mkdir()
    _bad_json(root / "Shane.json")

    corpus = build_dialogue_corpus(vanilla_root=root)

    assert corpus["records"] == []
    assert any("无法解析 JSON" in warning for warning in corpus["warnings"])


def test_one_broken_file_does_not_hide_the_others(tmp_path: Path) -> None:
    root = tmp_path / "Vanilla"
    root.mkdir()
    _bad_json(root / "Broken.json")
    (root / "Shane.json").write_text(
        json.dumps({"Mon1": "今天鸡舍那边挺忙的。"}, ensure_ascii=False), encoding="utf-8"
    )

    corpus = build_dialogue_corpus(vanilla_root=root)

    assert any("鸡舍" in json.dumps(record, ensure_ascii=False) for record in corpus["records"])


def test_a_broken_event_file_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "Events"
    root.mkdir()
    _bad_json(root / "spring13.json")

    corpus = build_dialogue_corpus(vanilla_events_root=root)

    assert corpus["records"] == []
    assert any("无法解析 JSON" in warning for warning in corpus["warnings"])


def test_a_non_mapping_event_payload_is_skipped(tmp_path: Path) -> None:
    # 事件根那一支多一个 `isinstance(payload, Mapping)` 条件（普通对白根没有）。
    root = tmp_path / "Events"
    root.mkdir()
    (root / "spring13.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    corpus = build_dialogue_corpus(vanilla_events_root=root)

    assert corpus["records"] == []


def test_manifest_and_config_files_are_not_read_as_dialogue(tmp_path: Path) -> None:
    root = tmp_path / "Mod"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps({"UniqueID": "Some.Mod"}), encoding="utf-8"
    )
    (root / "config.json").write_text("{坏的", encoding="utf-8")

    corpus = build_dialogue_corpus(mod_roots=[root])

    # config.json 被按文件名跳过，所以不该产生“无法解析 JSON”警告
    assert not any("无法解析 JSON" in warning for warning in corpus["warnings"])


def test_the_manifest_provides_the_source_mod_name(tmp_path: Path) -> None:
    root = tmp_path / "Mod"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps({"UniqueID": "FlashShifter.SVE"}), encoding="utf-8"
    )

    corpus = build_dialogue_corpus(mod_roots=[root])

    assert any(source["sourceMod"] == "FlashShifter.SVE" for source in corpus["sources"])
