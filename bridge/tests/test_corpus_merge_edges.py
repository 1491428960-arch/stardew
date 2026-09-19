"""`ProfileIndexBuilder._merge_corpus_payload` 的早退与跳过分支。

按**缺失行数**排序挑出来的（缺 8 行）。它是“把已导出的语料合并进索引”的入口，
缺的这段是三类跳过 + **一处提前 return**：

- `sources` 里的条目**不是映射**、或 **`sourceMod`/`root` 为空** → 跳过；
- **`records` 不是列表 → 整个函数提前返回**；
- `records` 条目**不是映射** → 跳过；
- **`npcId`/`sourceKey`/正文任一缺失** → 跳过。

“提前返回”这条尤其值得钉住：**`sources` 与 `warnings` 已经合并完了，之后的部分却不会**——
测出来是为了让将来改这里的人知道这条边界，而不是猜。
"""

from __future__ import annotations

from pathlib import Path

from stardew_ai_bridge.profile_index import ProfileIndexBuilder


def _index() -> dict[str, object]:
    index: dict[str, object] = {
        key: [] for key in ("styleSamples", "speechEvidence", "sources", "warnings")
    }
    index["profiles"] = {}
    return index


def _merge(tmp_path: Path, payload: object) -> dict[str, object]:
    index = _index()
    ProfileIndexBuilder(tmp_path)._merge_corpus_payload(index, payload)
    return index


def _record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "npcId": "Shane",
        "sourceMod": "SVE",
        "sourceKey": "Mon1",
        "sourcePath": "characters/Shane.json",
        "text": "今天鸡舍那边挺忙的。",
    }
    base.update(overrides)
    return base


# --- 提前返回 ---------------------------------------------------------------


def test_a_non_list_records_field_returns_early(tmp_path: Path) -> None:
    # `sources` 在它之前、已经合并；`records` 之后的部分则不会。
    index = _merge(
        tmp_path,
        {"sources": [{"sourceMod": "SVE", "root": "/x/Mod"}], "records": "不是列表"},
    )

    assert index["sources"] == [{"sourceMod": "SVE", "root": "Mod"}]
    assert index["styleSamples"] == []
    assert index["warnings"] == []


# --- sources 的两条跳过 -----------------------------------------------------


def test_non_mapping_sources_are_skipped(tmp_path: Path) -> None:
    index = _merge(tmp_path, {"sources": ["不是映射", 42, None]})

    assert index["sources"] == []


def test_sources_missing_either_field_are_skipped(tmp_path: Path) -> None:
    index = _merge(
        tmp_path,
        {"sources": [{"sourceMod": "", "root": "/x"}, {"sourceMod": "SVE", "root": "  "}]},
    )

    assert index["sources"] == []


def test_a_source_keeps_only_the_directory_name(tmp_path: Path) -> None:
    index = _merge(tmp_path, {"sources": [{"sourceMod": "SVE", "root": "/deep/path/MyMod"}]})

    assert index["sources"] == [{"sourceMod": "SVE", "root": "MyMod"}]


def test_duplicate_sources_are_collapsed(tmp_path: Path) -> None:
    entry = {"sourceMod": "SVE", "root": "/x/Mod"}
    index = _merge(tmp_path, {"sources": [entry, dict(entry)]})

    assert len(index["sources"]) == 1


# --- records 的跳过 ---------------------------------------------------------


def test_non_mapping_records_are_skipped(tmp_path: Path) -> None:
    index = _merge(tmp_path, {"records": ["不是映射", 42]})

    assert index["styleSamples"] == []


def test_records_missing_required_fields_are_skipped(tmp_path: Path) -> None:
    assert _merge(tmp_path, {"records": [_record(npcId="")]})["styleSamples"] == []
    assert _merge(tmp_path, {"records": [_record(sourceKey="")]})["styleSamples"] == []
    assert _merge(tmp_path, {"records": [_record(text="")]})["styleSamples"] == []
    assert _merge(tmp_path, {"records": [_record(text=None)]})["styleSamples"] == []


def test_a_bad_record_does_not_hide_a_good_one(tmp_path: Path) -> None:
    index = _merge(tmp_path, {"records": [_record(npcId=""), _record()]})

    assert len(index["styleSamples"]) == 1


# --- 语义补充 ---------------------------------------------------------------


def test_resolved_text_wins_over_raw_text(tmp_path: Path) -> None:
    # `resolvedText` 是解析过 i18n 之后的正文，优先于原始 `text`。
    index = _merge(
        tmp_path,
        {"records": [_record(text="{{i18n: Shane.Mon1}}", resolvedText="今天鸡舍那边挺忙的。")]},
    )

    assert "鸡舍" in str(index["styleSamples"])


def test_warnings_are_merged_and_blank_ones_dropped(tmp_path: Path) -> None:
    index = _merge(tmp_path, {"warnings": ["真的警告", "  ", 42, ""]})

    assert index["warnings"] == ["真的警告"]
