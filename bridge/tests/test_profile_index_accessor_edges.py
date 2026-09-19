"""`ProfileIndexStore` 各访问器在“空索引 / 非法参数”下的行为。

用覆盖率看，`profile_index.py` 未覆盖的行**分散在六个访问器里**（`story_events`、
`known_characters`、`speech_evidence`、`dialogue_reference`、`behavior_examples`、
`knowledge_facts`），而且**都落在每个方法开头几行的参数校验上**。这里集中补上。

核心契约：所有访问器都必须对**空索引与非法 `npc_id`** 安全返回空，而不是抛异常——
它们服务于 Prompt 构造，一个越界输入不该让整轮对话失败。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.profile_index import ProfileIndexStore


def _store(tmp_path: Path, index: dict[str, object] | None = None) -> ProfileIndexStore:
    payload = index or {
        "schemaVersion": 2,
        "profiles": {},
        "voiceCards": {},
        "speechEvidence": [],
        "styleSamples": [],
        "storyEvents": [],
        "knownCharacters": [],
        "behaviorExamples": [],
        "knowledgeFacts": [],
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return ProfileIndexStore(path)


# --- 空索引：每个访问器都安全返回空 -----------------------------------------


def test_npc_catalog_is_empty_for_an_empty_index(tmp_path: Path) -> None:
    assert _store(tmp_path).npc_catalog() == []


def test_voice_card_returns_an_empty_mapping(tmp_path: Path) -> None:
    assert _store(tmp_path).voice_card("Shane") == {}


def test_dialogue_reference_keeps_its_shape(tmp_path: Path) -> None:
    # 即使没有数据也要给出结构，调用方才能直接取字段。
    reference = _store(tmp_path).dialogue_reference("Shane")

    assert reference["npcId"] == "Shane"
    assert reference["total"] == 0
    assert reference["representatives"] == []


@pytest.mark.parametrize(
    "call",
    [
        lambda store: store.style_samples("Shane", ()),
        lambda store: store.story_events("Shane", ()),
        lambda store: store.known_characters("Shane", ()),
        lambda store: store.speech_evidence("Shane", ()),
        lambda store: store.behavior_examples("Shane", ()),
        lambda store: store.knowledge_facts("Shane", ()),
    ],
    ids=[
        "style_samples",
        "story_events",
        "known_characters",
        "speech_evidence",
        "behavior_examples",
        "knowledge_facts",
    ],
)
def test_every_list_accessor_returns_empty(tmp_path: Path, call) -> None:  # type: ignore[no-untyped-def]
    assert call(_store(tmp_path)) == []


# --- 非法 npc_id：一律安全返回空，而不是抛异常 ------------------------------


@pytest.mark.parametrize("npc_id", ["", "   ", None, 42])
def test_blank_or_non_string_npc_id_is_safe(tmp_path: Path, npc_id: object) -> None:
    store = _store(tmp_path)

    assert store.style_samples(npc_id, ()) == []  # type: ignore[arg-type]
    assert store.story_events(npc_id, ()) == []  # type: ignore[arg-type]
    assert store.known_characters(npc_id, ()) == []  # type: ignore[arg-type]
    assert store.speech_evidence(npc_id, ()) == []  # type: ignore[arg-type]
    assert store.behavior_examples(npc_id, ()) == []  # type: ignore[arg-type]
    assert store.knowledge_facts(npc_id, ()) == []  # type: ignore[arg-type]
    assert store.voice_card(npc_id) == {}  # type: ignore[arg-type]


# --- 上限与范围参数 ---------------------------------------------------------


def test_zero_limit_yields_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert store.style_samples("Shane", (), limit=0) == []
    assert store.speech_evidence("Shane", (), limit=0) == []
    assert store.behavior_examples("Shane", (), limit=0) == []
    assert store.knowledge_facts("Shane", (), limit=0) == []


def test_empty_allowed_scopes_yields_nothing(tmp_path: Path) -> None:
    assert _store(tmp_path).known_characters("Shane", (), allowed_scopes=()) == []
    assert _store(tmp_path).knowledge_facts("Shane", (), allowed_scopes=()) == []


def test_dialogue_reference_respects_a_zero_representative_limit(tmp_path: Path) -> None:
    reference = _store(tmp_path).dialogue_reference("Shane", representative_limit=0)

    assert reference["representatives"] == []


# --- 来源过滤（需要非空索引）------------------------------------------------


def _with_style_sample(tmp_path: Path, source_mod: str) -> ProfileIndexStore:
    return _store(
        tmp_path,
        {
            "schemaVersion": 2,
            "profiles": {"Shane": {"npcId": "Shane"}},
            "voiceCards": {},
            "speechEvidence": [],
            "styleSamples": [
                {
                    "sampleId": "s1",
                    "npcId": "Shane",
                    "text": "今天鸡舍那边挺忙的。",
                    "sourceMod": source_mod,
                    "sourceKey": "Mon1",
                    "sourcePath": "characters.json",
                    "evidenceKind": "dialogue",
                }
            ],
            "storyEvents": [],
            "knownCharacters": [],
            "behaviorExamples": [],
            "knowledgeFacts": [],
        },
    )


def test_style_samples_are_returned_for_a_matching_source(tmp_path: Path) -> None:
    store = _with_style_sample(tmp_path, "Vanilla")

    assert len(store.style_samples("Shane", ("Vanilla",))) == 1


def test_style_samples_are_filtered_out_for_an_unrelated_source(tmp_path: Path) -> None:
    # 样本来自别的包，而请求只启用了 SVE → 不该返回。
    store = _with_style_sample(tmp_path, "SomeOtherMod")

    assert store.style_samples("Shane", ("SVE",)) == []


def test_style_samples_are_not_capped_below_the_available_count(tmp_path: Path) -> None:
    # limit 是上限而不是固定值：只有一条样本时给 8 也只返回一条。
    store = _with_style_sample(tmp_path, "Vanilla")

    assert len(store.style_samples("Shane", (), limit=8)) == 1
