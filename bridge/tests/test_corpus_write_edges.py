"""`corpus.write_dialogue_corpus` 的原子写入。

2026-09-20 用覆盖率定位到 `corpus.py` 90%，其中 **L828–835 是整个 `write_dialogue_corpus`
函数体**（8 行）从未被执行——导出语料的最后一步此前没有测试。

它与 `dialogue_lab_session.save` 属于同一类“原子写”（先写临时文件再 `os.replace`），
但**少了失败清理**：写失败时 `.tmp` 会留在原地。下面有一条测试把这个差异如实记录下来，
以免将来误以为两处的健壮性一样。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from stardew_ai_bridge.corpus import write_dialogue_corpus

_CORPUS = {
    "records": [
        {"sourceKey": "Mon1", "text": "今天鸡舍那边挺忙的。"},
        {"sourceKey": "Mon2", "text": "有空来坐坐。"},
    ],
    "warnings": [],
}


def test_writes_the_corpus_as_readable_json(tmp_path: Path) -> None:
    destination = tmp_path / "corpus.json"

    write_dialogue_corpus(_CORPUS, destination)

    assert json.loads(destination.read_text(encoding="utf-8")) == _CORPUS


def test_creates_missing_parent_directories(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "deeper" / "corpus.json"

    write_dialogue_corpus(_CORPUS, destination)

    assert destination.is_file()


def test_chinese_is_not_escaped(tmp_path: Path) -> None:
    # 导出文件是要提交、要被人工阅读的，中文必须原样保留。
    destination = tmp_path / "corpus.json"

    write_dialogue_corpus(_CORPUS, destination)

    raw = destination.read_text(encoding="utf-8")
    assert "今天鸡舍那边挺忙的。" in raw
    assert "\\u" not in raw


def test_output_is_indented_and_newline_terminated(tmp_path: Path) -> None:
    destination = tmp_path / "corpus.json"

    write_dialogue_corpus(_CORPUS, destination)

    raw = destination.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert '\n  "records"' in raw  # indent=2


def test_existing_file_is_replaced(tmp_path: Path) -> None:
    destination = tmp_path / "corpus.json"
    destination.write_text('{"old": true}\n', encoding="utf-8")

    write_dialogue_corpus(_CORPUS, destination)

    assert json.loads(destination.read_text(encoding="utf-8")) == _CORPUS


def test_successful_write_leaves_no_temporary_file(tmp_path: Path) -> None:
    destination = tmp_path / "corpus.json"

    write_dialogue_corpus(_CORPUS, destination)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["corpus.json"]


def test_a_failed_replace_leaves_the_temporary_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 与 `dialogue_lab_session.save` 的差异：那边会在失败时清掉临时文件，这边不会。
    # 如实记录，而不是假装两处一样健壮。
    destination = tmp_path / "corpus.json"

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError):
        write_dialogue_corpus(_CORPUS, destination)

    # 目标文件没被写成，但临时文件留了下来
    assert not destination.exists()
    assert [p.name for p in tmp_path.iterdir()] == ["corpus.json.tmp"]


def test_accepts_a_string_path(tmp_path: Path) -> None:
    destination = tmp_path / "corpus.json"

    write_dialogue_corpus(_CORPUS, str(destination))

    assert destination.is_file()
