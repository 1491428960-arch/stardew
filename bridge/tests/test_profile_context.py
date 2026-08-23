from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.personas import PersonaStore
from stardew_ai_bridge.profile_index import ProfileIndexStore
from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder


def _write_index(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "profiles": {},
                "styleSamples": [
                    {
                        "sampleId": f"sophia-{index}",
                        "npcId": "Sophia",
                        "sourceMod": "FlashShifter.SVECode",
                        "sourcePath": "C:/Users/private/dialogue.json",
                        "sourceKey": f"line-{index}",
                        "text": f"样本 {index}",
                        "evidenceKind": "dialogue",
                    }
                    for index in range(10)
                ]
                + [
                    {
                        "sampleId": "alex-1",
                        "npcId": "Alex",
                        "sourceMod": "vanilla",
                        "sourcePath": "vanilla.json",
                        "sourceKey": "summer_1",
                        "text": "另一位 NPC 的样本",
                        "evidenceKind": "dialogue",
                    }
                ],
                "storyEvents": [
                    {
                        "eventId": "sve:event-1",
                        "sourceMod": "SVE",
                        "sourceKey": "event-1",
                        "participants": ["Sophia", "player"],
                        "summary": "玩家参加了葡萄园活动。",
                        "canonical": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_style_samples_match_npc_and_source_and_are_capped(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    _write_index(index_path)

    samples = ProfileIndexStore(index_path).style_samples(
        "sophia",
        ["SVE"],
        limit=8,
    )

    assert len(samples) == 8
    assert {sample["npcId"] for sample in samples} == {"Sophia"}
    assert {sample["sourceMod"] for sample in samples} == {"FlashShifter.SVECode"}
    assert all("sourcePath" not in sample for sample in samples)


def test_zero_limit_returns_no_evidence(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    _write_index(index_path)

    store = ProfileIndexStore(index_path)

    assert store.style_samples("Sophia", ["SVE"], limit=0) == []
    assert store.story_events("Sophia", ["SVE"], limit=0) == []


def test_story_events_match_participant_and_source(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    _write_index(index_path)

    events = ProfileIndexStore(index_path).story_events(
        "Sophia",
        ["SVE"],
    )

    assert len(events) == 1
    assert events[0]["eventId"] == "sve:event-1"
    assert events[0]["participants"] == ["Sophia", "player"]


def test_invalid_index_degrades_to_empty_results(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text("{not-json", encoding="utf-8")

    store = ProfileIndexStore(index_path)

    assert store.style_samples("Sophia", ["SVE"]) == []
    assert store.story_events("Sophia", ["SVE"]) == []


def test_missing_index_is_safe(tmp_path: Path) -> None:
    store = ProfileIndexStore(tmp_path / "missing.json")

    assert store.style_samples("Sophia", []) == []
    assert store.story_events("Sophia", []) == []


def test_context_builder_adds_only_current_npc_index_evidence(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    _write_index(index_path)
    store = ProfileIndexStore(index_path)
    builder = ContextBuilder(PersonaStore(Path(__file__).parents[2] / "data" / "personas"), store)

    context = builder.build(
        npc_id="Sophia",
        source_mods=["SVE"],
        recentFacts=[],
    )

    assert len(context["styleSamples"]) == 8
    assert len(context["storyEvents"]) == 1
    assert all(sample["npcId"] == "Sophia" for sample in context["styleSamples"])
    assert "sourcePath" not in json.dumps(context, ensure_ascii=False)


def test_context_without_index_keeps_legacy_shape() -> None:
    builder = ContextBuilder(PersonaStore(Path(__file__).parents[2] / "data" / "personas"))

    context = builder.build("Wizard", source_mods=[])

    assert set(context) == {
        "npcIdentity",
        "modSources",
        "gameState",
        "recentFacts",
        "history",
    }


def test_prompt_separates_optional_style_and_story_messages(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    _write_index(index_path)
    context = ContextBuilder(
        PersonaStore(Path(__file__).parents[2] / "data" / "personas"),
        ProfileIndexStore(index_path),
    ).build("Sophia", source_mods=["SVE"])

    messages = PromptBuilder().build(context, "最近怎么样？")
    names = [message.get("name") for message in messages]
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "style_evidence" in names
    assert "story_facts" in names
    assert '\\"canonical\\": true' in rendered
    assert "sourcePath" not in rendered
    assert "C:/Users/private" not in rendered
