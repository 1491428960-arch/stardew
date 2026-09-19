"""`ProfileIndexStore.dialogue_reference` 的筛选与去重。

按**缺失行数**排序挑出来的（缺 9/35）。它服务“原文浏览／参照”页，docstring 说
“返回网页参照用的完整已解析对白及一组稳定置顶样本”。

筛选规则里最要紧的一条写在校验代码的注释里：

    原文浏览页是给人复核语气用的；**控制脚本、旁白和动作残渣不能混进可见对白**，
    否则用户会把它误判成角色语言风格。

所以下面专门钉住“含控制残留的**被排除**”，而不只是钉住“正常文本被保留”。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.profile_index import ProfileIndexStore


def _sample(
    sample_id: str = "s1",
    npc_id: str = "Shane",
    text: str = "今天鸡舍那边挺忙的。",
    **extra: object,
) -> dict[str, object]:
    return {
        "sampleId": sample_id,
        "npcId": npc_id,
        "text": text,
        "sourceMod": "Vanilla",
        "sourceKey": "Mon1",
        "sourcePath": "characters.json",
        "evidenceKind": "dialogue",
        **extra,
    }


def _store(tmp_path: Path, *, samples: list[object], schema_version: int = 2, field: str = "speechEvidence") -> ProfileIndexStore:
    index = {"schemaVersion": schema_version, "profiles": {}, "voiceCards": {}, field: samples}
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return ProfileIndexStore(path)


# --- 空 ID 的形状 -----------------------------------------------------------


@pytest.mark.parametrize("npc_id", ["", "   ", None, 42])
def test_a_blank_npc_id_returns_an_empty_structure(tmp_path: Path, npc_id: object) -> None:
    reference = _store(tmp_path, samples=[]).dialogue_reference(npc_id)  # type: ignore[arg-type]

    assert reference == {
        "npcId": "",
        "total": 0,
        "representatives": [],
        "dialogues": [],
    }


# --- 正常形态 ---------------------------------------------------------------


def test_a_matching_sample_is_returned_with_the_canonical_id(tmp_path: Path) -> None:
    store = _store(tmp_path, samples=[_sample()])

    reference = store.dialogue_reference("  Shane  ")

    assert reference["npcId"] == "Shane"  # 去掉了首尾空白，并经 canonical 表
    assert reference["total"] == 1
    assert reference["dialogues"][0]["text"] == "今天鸡舍那边挺忙的。"


def test_the_canonical_table_is_case_sensitive_but_matching_is_not(tmp_path: Path) -> None:
    # 实测细节：`canonical_npc_id` 是**查表 + 去空白**，不做大小写纠正。
    # 所以小写输入会原样回显，但**匹配**用的是 casefold 比较，样本照样取得到。
    store = _store(tmp_path, samples=[_sample()])

    lowercase = store.dialogue_reference("  shane  ")

    assert lowercase["npcId"] == "shane"  # 回显保留输入的大小写
    assert lowercase["total"] == 1  # 但确实命中了 Shane 的样本


def test_only_the_whitelisted_fields_survive(tmp_path: Path) -> None:
    store = _store(tmp_path, samples=[_sample(secretField="不该出现")])

    dialogue = store.dialogue_reference("Shane")["dialogues"][0]

    assert "secretField" not in dialogue


# --- 筛选规则 ---------------------------------------------------------------


def test_samples_of_other_npcs_are_excluded(tmp_path: Path) -> None:
    store = _store(tmp_path, samples=[_sample(), _sample(sample_id="s2", npc_id="Emily")])

    assert store.dialogue_reference("Shane")["total"] == 1


@pytest.mark.parametrize("text", ["", "   ", None, 42])
def test_samples_without_usable_text_are_excluded(tmp_path: Path, text: object) -> None:
    store = _store(tmp_path, samples=[_sample(text=text)])  # type: ignore[arg-type]

    assert store.dialogue_reference("Shane")["total"] == 0


def test_unresolved_i18n_is_excluded(tmp_path: Path) -> None:
    # 还没解析出具体台词的模板不能进可见对白。
    store = _store(tmp_path, samples=[_sample(text="你好 {{i18n: Shane.Mon1}}")])

    assert store.dialogue_reference("Shane")["total"] == 0


@pytest.mark.parametrize("text", ["她笑了笑 *微笑*", "%旁白一句", "（笑了笑）说"])
def test_control_residue_is_excluded(tmp_path: Path, text: str) -> None:
    # 这是本函数最重要的一条：控制脚本/旁白/动作残渣会让人误判角色语气。
    store = _store(tmp_path, samples=[_sample(text=text)])

    assert store.dialogue_reference("Shane")["total"] == 0


def test_non_mapping_records_are_skipped(tmp_path: Path) -> None:
    store = _store(tmp_path, samples=["not-a-mapping", _sample()])

    assert store.dialogue_reference("Shane")["total"] == 1


# --- sampleId 的去重与生成 --------------------------------------------------


def test_duplicate_sample_ids_are_deduplicated(tmp_path: Path) -> None:
    store = _store(tmp_path, samples=[_sample(), _sample(text="另一句不一样的台词。")])

    assert store.dialogue_reference("Shane")["total"] == 1


def test_a_missing_sample_id_is_generated(tmp_path: Path) -> None:
    # 没有 sampleId 的旧记录会被补成 `<canonical>:<序号>`，保证代表样本可稳定排序。
    store = _store(tmp_path, samples=[_sample(sample_id="")])

    dialogue = store.dialogue_reference("Shane")["dialogues"][0]

    assert dialogue["sampleId"] == "Shane:0"


# --- 代表样本上限 -----------------------------------------------------------


@pytest.mark.parametrize(("limit", "expected"), [(100, 3), (-5, 0)])
def test_the_representative_limit_is_clamped(tmp_path: Path, limit: int, expected: int) -> None:
    samples = [_sample(sample_id=f"s{i}", text=f"第 {i} 句台词内容。") for i in range(3)]
    store = _store(tmp_path, samples=samples)

    reference = store.dialogue_reference("Shane", representative_limit=limit)

    assert reference["total"] == 3  # total 不受上限影响
    assert len(reference["representatives"]) == expected


# --- schema v1 兼容 ---------------------------------------------------------


def test_schema_v1_falls_back_to_style_samples(tmp_path: Path) -> None:
    # 老索引没有 speechEvidence，要从 styleSamples 取。
    store = _store(tmp_path, samples=[_sample()], schema_version=1, field="styleSamples")

    assert store.dialogue_reference("Shane")["total"] == 1
