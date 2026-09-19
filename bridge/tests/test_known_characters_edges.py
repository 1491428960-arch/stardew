"""`ProfileIndexStore.known_characters` 的条件过滤与门控。

按**缺失行数**排序挑出来的（缺 8/39），是剩余缺口里最值得补的**公开访问器**。

它回答“这个 NPC 知道哪些其他角色”，而过滤链条比同类访问器长，中间有两条尤其要紧：

- **低置信度不返回**：`confidence == "low"` 的条目被丢掉（缺字段时默认 `"medium"`，会返回）。
- **事件门控**：带 `requiredEventId` 的条目，只有在玩家**已完成该事件**时才返回——
  这就是“没走到那段剧情之前，NPC 不该知道这件事”。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.profile_index import ProfileIndexStore


def _relation(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "npcId": "Shane",
        "knownNpcId": "Emily",
        "sourceMod": "Vanilla",
        "knowledgeScope": "canon_confirmed",
        "confidence": "medium",
        "summary": "谢恩知道艾米丽在酒吧上班。",
    }
    base.update(overrides)
    return base


def _store(tmp_path: Path, *, relations: object) -> ProfileIndexStore:
    index = {
        "schemaVersion": 2,
        "profiles": {},
        "voiceCards": {},
        "knownCharacters": relations,
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return ProfileIndexStore(path)


# --- 入口与上限 -------------------------------------------------------------


@pytest.mark.parametrize("npc_id", ["", "   ", None, 42])
def test_a_blank_npc_id_yields_nothing(tmp_path: Path, npc_id: object) -> None:
    assert _store(tmp_path, relations=[_relation()]).known_characters(npc_id, ()) == []  # type: ignore[arg-type]


def test_a_zero_limit_yields_nothing(tmp_path: Path) -> None:
    assert _store(tmp_path, relations=[_relation()]).known_characters("Shane", (), limit=0) == []


def test_the_limit_is_capped_at_eight(tmp_path: Path) -> None:
    relations = [_relation(knownNpcId=f"Char{i}") for i in range(12)]
    store = _store(tmp_path, relations=relations)

    assert len(store.known_characters("Shane", (), limit=100)) == 8


def test_a_non_list_container_yields_nothing(tmp_path: Path) -> None:
    assert _store(tmp_path, relations="not-a-list").known_characters("Shane", ()) == []


# --- 过滤链条 ---------------------------------------------------------------


def test_a_relation_owned_by_another_npc_is_skipped(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation(npcId="Emily")])

    assert store.known_characters("Shane", ()) == []


def test_an_unrelated_source_mod_is_skipped(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation(sourceMod="SomeOtherMod")])

    assert store.known_characters("Shane", ("SVE",)) == []


def test_a_disallowed_scope_is_skipped(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation(knowledgeScope="rumour")])

    assert store.known_characters("Shane", ()) == []


def test_scopes_are_matched_case_insensitively(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation(knowledgeScope="  CANON_CONFIRMED  ")])

    assert len(store.known_characters("Shane", ())) == 1


def test_an_empty_scope_allowlist_yields_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation()])

    assert store.known_characters("Shane", (), allowed_scopes=()) == []


def test_low_confidence_relations_are_skipped(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation(confidence="LOW")])

    assert store.known_characters("Shane", ()) == []


@pytest.mark.parametrize("confidence", ["medium", "high", None])
def test_other_confidence_levels_are_kept(tmp_path: Path, confidence: object) -> None:
    # 缺 confidence 时默认 medium——不能因为“没写”就把条目丢掉。
    relation = _relation() if confidence is None else _relation(confidence=confidence)
    store = _store(tmp_path, relations=[relation])

    assert len(store.known_characters("Shane", ())) == 1


# --- 事件门控 ---------------------------------------------------------------


def test_a_gated_relation_is_hidden_until_the_event_is_completed(tmp_path: Path) -> None:
    # 没走到那段剧情之前，NPC 不该知道这件事。
    store = _store(tmp_path, relations=[_relation(requiredEventId="14")])

    assert store.known_characters("Shane", ()) == []
    assert store.known_characters("Shane", (), completed_event_ids=["14"]) != []


def test_event_ids_are_matched_case_insensitively_and_trimmed(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation(requiredEventId="Fall_14")])

    assert store.known_characters("Shane", (), completed_event_ids=["  fall_14  "]) != []


def test_a_relation_without_a_gate_is_always_visible(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation(requiredEventId="   ")])

    assert len(store.known_characters("Shane", ())) == 1


# --- 目标角色字段 -----------------------------------------------------------


def test_a_blank_known_npc_id_is_skipped(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation(knownNpcId="   ")])

    assert store.known_characters("Shane", ()) == []


def test_subject_npc_id_is_used_as_a_fallback(tmp_path: Path) -> None:
    relation = _relation()
    relation.pop("knownNpcId")
    relation["subjectNpcId"] = "Emily"
    store = _store(tmp_path, relations=[relation])

    result = store.known_characters("Shane", ())

    assert result and result[0]["knownNpcId"] == "Emily"


def test_the_owner_and_target_are_canonicalised(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation(npcId="  Shane  ")])

    result = store.known_characters("Shane", ())

    assert result[0]["npcId"] == "Shane"
    assert result[0]["knownNpcId"] == "Emily"


def test_only_whitelisted_fields_survive(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=[_relation(secretField="不该出现")])

    assert "secretField" not in store.known_characters("Shane", ())[0]


def test_non_mapping_records_are_skipped(tmp_path: Path) -> None:
    store = _store(tmp_path, relations=["not-a-mapping", _relation()])

    assert len(store.known_characters("Shane", ())) == 1
