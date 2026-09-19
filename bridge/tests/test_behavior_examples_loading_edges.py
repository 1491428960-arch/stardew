"""`ProfileIndexBuilder._load_behavior_examples` 的加载与拒绝分支。

按**缺失行数**排序挑出来的（缺 11 行，**全是错误分支**）。docstring 点明了它的定位：

    加载**人工审核的**成对示例，**不把它们伪装成原版对白证据**。

也就是说：这些样例进的是 `behaviorExamples`（few-shot 参考卡），**不是** `speechEvidence`
（语气锚点的原文证据）——两者混起来会让“角色的说话风格”被人工样例污染。

缺的 11 行是四道拒绝闸门 + 两道条目级过滤：坏 JSON、`schemaVersion` 不是 1、
`examples` 不是列表、条目不是映射、`exampleId` 重复。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.profile_index import ProfileIndexBuilder

_FILE = "behavior-examples.json"


def _example(
    example_id: str = "e1",
    *,
    source_type: str = "handcrafted_example",
    **overrides: object,
) -> dict[str, object]:
    base: dict[str, object] = {
        "exampleId": example_id,
        "npcId": "Shane",
        "playerInput": "鸡舍那边怎么样",
        "npcReply": "今天鸡舍那边挺忙的，不过还行。",
        "sourceType": source_type,
    }
    base.update(overrides)
    return base


def _load(tmp_path: Path, payload: object = None, *, raw: str | None = None):
    """把 payload 写成 behavior-examples.json，跑一次加载并返回 index。"""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / _FILE
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
    elif payload is not None:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    index: dict[str, object] = {"warnings": [], "behaviorExamples": [], "speechEvidence": []}
    ProfileIndexBuilder(tmp_path)._load_behavior_examples(index)
    return index


def _file_payload(examples: object, *, schema: object = 1) -> dict[str, object]:
    return {"schemaVersion": schema, "examples": examples}


# --- 正常路径 ---------------------------------------------------------------


def test_a_reviewed_example_is_loaded(tmp_path: Path) -> None:
    index = _load(tmp_path, _file_payload([_example()]))

    assert index["warnings"] == []
    examples = index["behaviorExamples"]
    assert len(examples) == 1
    assert examples[0]["exampleId"] == "e1"  # type: ignore[index]


def test_the_documented_position_is_honoured(tmp_path: Path) -> None:
    # “不把它们伪装成原版对白证据”：behaviorExamples 有内容，speechEvidence 仍是空的。
    index = _load(tmp_path, _file_payload([_example()]))

    assert index["behaviorExamples"] != []
    assert index["speechEvidence"] == []


def test_a_missing_file_is_silently_skipped(tmp_path: Path) -> None:
    index = _load(tmp_path)  # 不写文件

    assert index["warnings"] == []
    assert index["behaviorExamples"] == []


# --- 四道拒绝闸门 -----------------------------------------------------------


def test_broken_json_is_reported(tmp_path: Path) -> None:
    index = _load(tmp_path, raw="{坏的")

    assert index["warnings"] == [f"invalid behavior examples JSON: {_FILE}"]
    assert index["behaviorExamples"] == []


@pytest.mark.parametrize("schema", [2, 0, None, "1"])
def test_an_unsupported_schema_is_reported(tmp_path: Path, schema: object) -> None:
    index = _load(tmp_path, _file_payload([_example()], schema=schema))

    assert index["warnings"] == [f"unsupported behavior examples schema: {_FILE}"]
    assert index["behaviorExamples"] == []


@pytest.mark.parametrize("examples", ["不是列表", {"k": 1}, 42, None])
def test_a_non_list_examples_field_is_reported(tmp_path: Path, examples: object) -> None:
    index = _load(tmp_path, _file_payload(examples))

    assert index["warnings"] == [f"invalid behavior examples list: {_FILE}"]
    assert index["behaviorExamples"] == []


# --- 条目级过滤 -------------------------------------------------------------


@pytest.mark.parametrize("bad", ["不是映射", 42, None, ["a"]])
def test_non_mapping_entries_are_reported_with_their_position(
    tmp_path: Path, bad: object
) -> None:
    index = _load(tmp_path, _file_payload([_example(), bad]))

    assert index["warnings"] == [f"invalid behavior example: {_FILE}:1"]
    assert len(index["behaviorExamples"]) == 1


def test_duplicate_example_ids_are_reported(tmp_path: Path) -> None:
    index = _load(tmp_path, _file_payload([_example(), _example()]))

    assert index["warnings"] == ["duplicate behavior example: e1"]
    assert len(index["behaviorExamples"]) == 1


def test_an_unapproved_source_type_is_reported(tmp_path: Path) -> None:
    index = _load(tmp_path, _file_payload([_example(source_type="model_draft")]))

    assert index["warnings"] == [f"unapproved behavior example: {_FILE}:0"]
    assert index["behaviorExamples"] == []


def test_an_invalid_example_is_reported_with_the_first_error(tmp_path: Path) -> None:
    # 校验失败时把第一条错误拼进警告，便于定位。
    index = _load(tmp_path, _file_payload([{"exampleId": "e1", "npcId": "Shane"}]))

    assert len(index["warnings"]) == 1
    assert index["warnings"][0].startswith(f"invalid behavior example: {_FILE}:0:")
    assert index["behaviorExamples"] == []


def test_a_bad_entry_does_not_hide_a_good_one(tmp_path: Path) -> None:
    index = _load(
        tmp_path,
        _file_payload(["不是映射", _example("good"), _example(source_type="model_draft")]),
    )

    assert len(index["behaviorExamples"]) == 1
    assert index["behaviorExamples"][0]["exampleId"] == "good"  # type: ignore[index]
    # 两条坏条目各留一条警告
    assert len(index["warnings"]) == 2
