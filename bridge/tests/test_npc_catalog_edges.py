"""`ProfileIndexStore.npc_catalog` 的三来源合并。

按“缺失行数”排序挑出来的（缺 14 行）。它把三个来源汇成一份完整 NPC 目录：

- `profiles`（角色资料）
- `styleSamples` / `speechEvidence`（对白样本——能反推出“这个 NPC 有对白证据”）
- `voiceCards`（语气卡）

docstring 特别强调“**不按恋爱资格裁剪**”，所以它比 `RelationshipWorldContext` 那类
按关系过滤的接口更宽。

下面几条断言记的是**实测行为**，其中几处与直觉不同——照实写下来，而不是照直觉写：

- `_is_catalog_npc_id(None)` 是 **True**（它只拒绝空字符串）；
- **非 Mapping 的 profile 也会进目录**，此时用它的 key 当 `npcId`；
- `sourceMods` 给字符串时被当成**单项列表**。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.profile_index import ProfileIndexStore, _is_catalog_npc_id


def _store(tmp_path: Path, index: dict[str, object]) -> ProfileIndexStore:
    payload = {"schemaVersion": 2, **index}
    path = tmp_path / "index.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return ProfileIndexStore(path)


def _by_id(catalog: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(item["npcId"]): item for item in catalog}


# --- 目录 ID 的过滤 ---------------------------------------------------------


def test_the_catalog_id_filter_only_rejects_blank_strings() -> None:
    assert _is_catalog_npc_id("Shane") is True
    assert _is_catalog_npc_id("  shane  ") is True
    assert _is_catalog_npc_id("Unknown_Npc") is True
    assert _is_catalog_npc_id("") is False
    assert _is_catalog_npc_id("   ") is False
    # 实测：None 也会通过（函数只拒空字符串）
    assert _is_catalog_npc_id(None) is True


def test_an_empty_index_yields_an_empty_catalog(tmp_path: Path) -> None:
    assert _store(tmp_path, {}).npc_catalog() == []


# --- profiles 来源 ----------------------------------------------------------


def test_profiles_contribute_the_display_name(tmp_path: Path) -> None:
    catalog = _by_id(
        _store(tmp_path, {"profiles": {"Shane": {"npcId": "Shane", "displayName": "谢恩"}}}).npc_catalog()
    )

    assert catalog["Shane"]["displayName"] == "谢恩"


def test_a_blank_display_name_falls_back_to_the_npc_id(tmp_path: Path) -> None:
    catalog = _by_id(
        _store(tmp_path, {"profiles": {"Abigail": {"npcId": "Abigail", "displayName": "   "}}}).npc_catalog()
    )

    assert catalog["Abigail"]["displayName"] == "Abigail"


def test_a_string_source_mods_becomes_a_single_item_list(tmp_path: Path) -> None:
    catalog = _by_id(
        _store(tmp_path, {"profiles": {"Abigail": {"npcId": "Abigail", "sourceMods": "SVE"}}}).npc_catalog()
    )

    assert catalog["Abigail"]["sourceMods"] == ["SVE"]


def test_profiles_can_declare_dialogue_evidence(tmp_path: Path) -> None:
    catalog = _by_id(
        _store(
            tmp_path,
            {"profiles": {"Shane": {"npcId": "Shane", "hasDialogueEvidence": True}}},
        ).npc_catalog()
    )

    assert catalog["Shane"]["hasDialogueEvidence"] is True


def test_a_non_mapping_profile_falls_back_to_its_key(tmp_path: Path) -> None:
    # 实测行为：profile 值不是 Mapping 时不会崩，而是拿 key 当 npcId 建一个空条目。
    catalog = _by_id(_store(tmp_path, {"profiles": {"Broken": "not-a-mapping"}}).npc_catalog())

    assert catalog["Broken"] == {
        "npcId": "Broken",
        "displayName": "Broken",
        "sourceMods": [],
        "hasDialogueEvidence": False,
    }


def test_the_key_is_only_used_when_the_profile_has_no_npc_id(tmp_path: Path) -> None:
    catalog = _by_id(
        _store(tmp_path, {"profiles": {"lower-key": {"npcId": "Canonical"}}}).npc_catalog()
    )

    assert "Canonical" in catalog
    assert "lower-key" not in catalog


# --- 样本来源 ---------------------------------------------------------------


def test_a_sample_with_text_marks_dialogue_evidence(tmp_path: Path) -> None:
    catalog = _by_id(
        _store(
            tmp_path,
            {"styleSamples": [{"npcId": "Emily", "sourceMod": "Vanilla", "text": "你好呀。"}]},
        ).npc_catalog()
    )

    assert catalog["Emily"]["hasDialogueEvidence"] is True
    assert catalog["Emily"]["sourceMods"] == ["Vanilla"]


def test_a_sample_with_blank_text_does_not_mark_dialogue_evidence(tmp_path: Path) -> None:
    # 只有空白文本的样本不算“有对白证据”。
    catalog = _by_id(
        _store(
            tmp_path,
            {"styleSamples": [{"npcId": "Emily", "sourceMod": "Vanilla", "text": "   "}]},
        ).npc_catalog()
    )

    assert catalog["Emily"]["hasDialogueEvidence"] is False


def test_non_mapping_sample_records_are_skipped(tmp_path: Path) -> None:
    catalog = _by_id(
        _store(
            tmp_path,
            {
                "styleSamples": [
                    "not-a-mapping",
                    {"npcId": "Emily", "sourceMod": "Vanilla", "text": "你好。"},
                ]
            },
        ).npc_catalog()
    )

    assert list(catalog) == ["Emily"]


def test_a_non_list_evidence_field_is_skipped(tmp_path: Path) -> None:
    # speechEvidence 不是列表时整体跳过，而不是报错。
    catalog = _by_id(
        _store(
            tmp_path,
            {
                "styleSamples": [{"npcId": "Emily", "sourceMod": "Vanilla", "text": "你好。"}],
                "speechEvidence": "not-a-list",
            },
        ).npc_catalog()
    )

    assert list(catalog) == ["Emily"]


# --- 语气卡来源 -------------------------------------------------------------


def test_voice_cards_contribute_source_mods_only(tmp_path: Path) -> None:
    catalog = _by_id(
        _store(tmp_path, {"voiceCards": {"Wizard": {"npcId": "Wizard", "sourceMod": "Vanilla"}}}).npc_catalog()
    )

    assert catalog["Wizard"]["sourceMods"] == ["Vanilla"]
    # 语气卡不代表对白证据
    assert catalog["Wizard"]["hasDialogueEvidence"] is False


def test_a_non_mapping_voice_card_falls_back_to_its_key(tmp_path: Path) -> None:
    catalog = _by_id(_store(tmp_path, {"voiceCards": {"Broken": "x"}}).npc_catalog())

    assert "Broken" in catalog


# --- 合并与排序 -------------------------------------------------------------


def test_all_three_sources_merge_into_one_entry(tmp_path: Path) -> None:
    catalog = _by_id(
        _store(
            tmp_path,
            {
                "profiles": {"Shane": {"sourceMods": ["Vanilla"], "displayName": "谢恩"}},
                "styleSamples": [{"npcId": "Shane", "sourceMod": "SVE", "text": "今天挺忙的。"}],
                "voiceCards": {"Shane": {"npcId": "Shane", "sourceMod": "Other"}},
            },
        ).npc_catalog()
    )

    shane = catalog["Shane"]
    assert shane["displayName"] == "谢恩"
    assert set(shane["sourceMods"]) == {"Vanilla", "SVE", "Other"}  # type: ignore[arg-type]
    assert shane["hasDialogueEvidence"] is True


def test_duplicate_source_mods_are_collapsed(tmp_path: Path) -> None:
    catalog = _by_id(
        _store(
            tmp_path,
            {
                "profiles": {"Shane": {"sourceMods": ["Vanilla"]}},
                "styleSamples": [{"npcId": "Shane", "sourceMod": "Vanilla", "text": "你好。"}],
            },
        ).npc_catalog()
    )

    assert catalog["Shane"]["sourceMods"] == ["Vanilla"]


def test_the_catalog_is_sorted_by_display_name_then_id(tmp_path: Path) -> None:
    catalog = _store(
        tmp_path,
        {
            "profiles": {
                "Zoe": {"npcId": "Zoe", "displayName": "zoe"},
                "Abigail": {"npcId": "Abigail", "displayName": "Abigail"},
                "Shane": {"npcId": "Shane", "displayName": "shane"},
            }
        },
    ).npc_catalog()

    assert [item["npcId"] for item in catalog] == ["Abigail", "Shane", "Zoe"]


@pytest.mark.parametrize("field", ["profiles", "voiceCards"])
def test_a_non_mapping_container_is_ignored(tmp_path: Path, field: str) -> None:
    assert _store(tmp_path, {field: "not-a-mapping"}).npc_catalog() == []
