"""`runtime_samples` 的校验边界：运行时采样器与索引之间的那道闸门。

2026-09-20 用覆盖率数据定位到它只有 **86%**，未覆盖的行**几乎全是坏输入分支**——
而它恰好是“游戏写出来的东西”进入索引前的最后一道校验。这里逐条补上：

- **`sourcePath` 必须相对**：`C:\\...`／`D:/...`／`\\\\server`／`//server` 一律拒绝，
  防止把本机布局写进要提交的索引。
- **文本必须已解析**：含 `{{i18n:...}}` 的未解析模板一律拒绝。
- **可选字段是“空则不写”**：`conditions`／`gameState`／`attribution`／`capturedAt` 为空时
  **不出现在结果里**，而不是留一个空对象。
- **`sampleId` 是内容哈希**：同样内容得到同样 id——这是“重复采样不会无限膨胀”的基础。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.runtime_samples import (
    append_runtime_sample,
    attribute_runtime_sample,
    load_runtime_samples,
    normalise_runtime_sample,
)


def _raw(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sourceSampleId": "s-1",
        "npcId": "Shane",
        "sourceMod": "Vanilla",
        "sourcePath": "characters.json",
        "sourceKey": "Mon1",
        "text": "今天鸡舍那边挺忙的。",
    }
    base.update(overrides)
    return base


# --- 必填字段 ---------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["sourceSampleId", "npcId", "sourceMod", "sourcePath", "sourceKey", "text"],
)
def test_every_required_field_is_enforced(field: str) -> None:
    payload = _raw()
    payload.pop(field)

    with pytest.raises(ValueError):
        normalise_runtime_sample(payload)


@pytest.mark.parametrize("value", ["", "   ", None, 42])
def test_blank_required_fields_are_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(npcId=value))


def test_non_mapping_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        normalise_runtime_sample(["not", "a", "mapping"])  # type: ignore[arg-type]


# --- sourcePath 必须是相对路径（安全相关）-----------------------------------


@pytest.mark.parametrize(
    "value",
    ["C:\\Users\\someone\\Mods\\x.json", "D:/sbeam/mod.json", "\\\\server\\share\\x.json", "//server/share"],
)
def test_absolute_source_paths_are_rejected(value: str) -> None:
    # 绝对路径会把本机目录结构写进要提交的索引。
    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(sourcePath=value))


def test_leading_dot_slash_is_stripped_from_source_path() -> None:
    assert normalise_runtime_sample(_raw(sourcePath="./characters.json"))["sourcePath"] == (
        "characters.json"
    )


def test_backslashes_become_forward_slashes() -> None:
    assert normalise_runtime_sample(_raw(sourcePath="i18n\\zh.json"))["sourcePath"] == (
        "i18n/zh.json"
    )


# --- 文本 -------------------------------------------------------------------


def test_overlong_text_is_rejected() -> None:
    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(text="字" * 2001))


def test_unresolved_i18n_template_is_rejected() -> None:
    # 动态键必须已由游戏求值；模板占位符说明它还没有。
    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(text="你好 {{i18n: Shane.Mon1}}"))


# --- 可选映射字段 -----------------------------------------------------------


def test_optional_mappings_are_omitted_when_absent() -> None:
    result = normalise_runtime_sample(_raw())

    assert "conditions" not in result
    assert "gameState" not in result
    assert "attribution" not in result
    assert "capturedAt" not in result


def test_optional_mappings_are_kept_when_present() -> None:
    result = normalise_runtime_sample(
        _raw(conditions={"relationshipStage": "close"}, attribution={"match": "x"})
    )

    assert result["conditions"] == {"relationshipStage": "close"}
    assert result["attribution"] == {"match": "x"}


def test_non_mapping_optional_field_is_rejected() -> None:
    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(conditions="不是对象"))


def test_too_many_mapping_entries_are_rejected() -> None:
    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(conditions={f"k{i}": 1 for i in range(33)}))


def test_mapping_with_a_blank_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(conditions={"  ": 1}))


def test_mapping_accepts_scalars_and_flat_lists_only() -> None:
    result = normalise_runtime_sample(
        _raw(conditions={"a": 1, "b": None, "c": ["x", 2, True]})
    )
    assert result["conditions"] == {"a": 1, "b": None, "c": ["x", 2, True]}

    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(conditions={"nested": {"x": 1}}))
    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(conditions={"list": [{"x": 1}]}))


# --- candidateKey / capturedAt ----------------------------------------------


@pytest.mark.parametrize("value", ["", "   ", 42])
def test_candidate_key_must_be_a_non_empty_string(value: object) -> None:
    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(candidateKey=value))


@pytest.mark.parametrize("value", ["", "   ", 42])
def test_captured_at_must_be_a_string(value: object) -> None:
    with pytest.raises(ValueError):
        normalise_runtime_sample(_raw(capturedAt=value))


# --- sampleId 是内容哈希 ----------------------------------------------------


def test_sample_id_is_a_content_hash() -> None:
    first = normalise_runtime_sample(_raw())
    second = normalise_runtime_sample(_raw())

    assert first["sampleId"] == second["sampleId"]
    assert first["sampleId"].startswith("runtime:")


def test_different_text_gets_a_different_sample_id() -> None:
    first = normalise_runtime_sample(_raw())
    second = normalise_runtime_sample(_raw(text="换一句话试试看。"))

    assert first["sampleId"] != second["sampleId"]


def test_evidence_kind_marks_it_as_runtime_dialogue() -> None:
    assert normalise_runtime_sample(_raw())["evidenceKind"] == "runtime_dialogue"


# --- attribute_runtime_sample -----------------------------------------------


def _corpus(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "npcId": "Shane",
        "sourceKey": "Mon1",
        "text": "今天鸡舍那边挺忙的。",
        "sourceMod": "Vanilla",
        "sourcePath": "characters.json",
    }
    record.update(overrides)
    return record


def test_unique_match_is_attributed() -> None:
    result = attribute_runtime_sample(_raw(), [_corpus()])

    assert result["sourceMod"] == "Vanilla"
    assert result["attribution"]["match"] == "npc+sourceKey+text"


def test_no_match_keeps_the_sample_unattributed() -> None:
    result = attribute_runtime_sample(_raw(), [])

    assert "attribution" not in result


def test_multiple_matches_keep_the_sample_unattributed() -> None:
    # 有歧义宁可不归属，免得把动态分支挂到错误的 Mod 上。
    result = attribute_runtime_sample(_raw(), [_corpus(), _corpus(sourceMod="SVE")])

    assert "attribution" not in result


def test_records_missing_source_mod_do_not_count_as_matches() -> None:
    result = attribute_runtime_sample(_raw(), [_corpus(sourceMod="")])

    assert "attribution" not in result


def test_attribution_is_skipped_when_required_fields_are_absent() -> None:
    result = attribute_runtime_sample({"npcId": "Shane"}, [_corpus()])

    assert "attribution" not in result


# --- load / append ----------------------------------------------------------


def test_load_ignores_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    path.write_text(
        json.dumps(_raw(), ensure_ascii=False) + "\n\n   \n",
        encoding="utf-8",
    )

    assert len(load_runtime_samples(path)) == 1


def test_load_reports_the_line_number_of_a_bad_row(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    path.write_text(
        json.dumps(_raw(), ensure_ascii=False) + "\n{bad json}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        load_runtime_samples(path)

    assert "第 2 行" in str(excinfo.value)


def test_load_missing_file_raises_with_the_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as excinfo:
        load_runtime_samples(tmp_path / "nope.jsonl")

    assert "nope.jsonl" in str(excinfo.value)


def test_load_deduplicates_by_sample_id(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    line = json.dumps(_raw(), ensure_ascii=False)
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")

    assert len(load_runtime_samples(path)) == 1


def test_append_writes_once_and_deduplicates(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "samples.jsonl"

    first = append_runtime_sample(path, _raw())
    append_runtime_sample(path, _raw())  # 同内容 → 不再写

    assert path.read_text(encoding="utf-8").count("\n") == 1
    assert load_runtime_samples(path) == [first]
