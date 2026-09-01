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


def test_source_alias_matches_runtime_unique_id(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": [],
                "speechEvidence": [
                    {
                        "sampleId": "romras-intro",
                        "npcId": "Wizard",
                        "sourceMod": "Parrot.RomRas",
                        "sourceKey": "Introduction",
                        "text": "你好，年轻的你。",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    evidence = ProfileIndexStore(index_path).speech_evidence(
        "Wizard", ["Romanceable Rasmodius"]
    )

    assert [item["sampleId"] for item in evidence] == ["romras-intro"]


def test_persona_and_index_share_rasmodia_source_aliases_and_prioritize_overlay(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": [
                    {
                        "sampleId": "vanilla-daily",
                        "npcId": "Wizard",
                        "sourceMod": "vanilla",
                        "sourceKey": "Mon",
                        "text": "原版的日常对白。",
                    },
                    {
                        "sampleId": "romras-daily",
                        "npcId": "Wizard",
                        "sourceMod": "Parrot.RomRas",
                        "sourceKey": "Introduction",
                        "text": "RomRas 的日常对白。",
                    },
                ],
                "speechEvidence": [
                    {
                        "sampleId": "vanilla-daily",
                        "npcId": "Wizard",
                        "sourceMod": "vanilla",
                        "sourceKey": "Mon",
                        "text": "原版的日常对白。",
                    },
                    {
                        "sampleId": "romras-daily",
                        "npcId": "Wizard",
                        "sourceMod": "Parrot.RomRas",
                        "sourceKey": "Introduction",
                        "text": "RomRas 的日常对白。",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    evidence = ProfileIndexStore(index_path).speech_evidence(
        "Wizard", ["Romanceable Rasmodia"], limit=2
    )

    assert [item["sampleId"] for item in evidence] == ["romras-daily", "vanilla-daily"]


def test_rasmodia_original_evidence_reaches_final_prompt_with_display_alias(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": [],
                "speechEvidence": [
                    {
                        "sampleId": "vanilla-daily",
                        "npcId": "Wizard",
                        "sourceMod": "vanilla",
                        "sourceKey": "Mon",
                        "text": "原版的日常对白。",
                    },
                    {
                        "sampleId": "romras-daily",
                        "npcId": "Wizard",
                        "sourceMod": "Parrot.RomRas",
                        "sourceKey": "Introduction",
                        "text": "这几天塔里很安静。",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    context = ContextBuilder(
        PersonaStore(Path(__file__).parents[2] / "data" / "personas"),
        ProfileIndexStore(index_path),
    ).build(
        "Wizard",
        source_mods=["Romanceable Rasmodia"],
        friendshipHearts=0,
        message="最近怎么样？",
    )
    messages = PromptBuilder().build(context, "最近怎么样？")
    speech = next(message for message in messages if message["name"] == "speech_evidence")

    assert "这几天塔里很安静。" in speech["content"]


def test_source_specific_evidence_is_reserved_when_vanilla_fills_window(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    vanilla = [
        {
            "sampleId": f"vanilla-{day}",
            "npcId": "Wizard",
            "sourceMod": "vanilla",
            "sourceKey": day,
            "text": f"原版 {day}。",
        }
        for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    ]
    overlay = [
        {
            "sampleId": "romras-intro",
            "npcId": "Wizard",
            "sourceMod": "Parrot.RomRas",
            "sourceKey": "Introduction",
            "text": "你好，年轻的你。",
        },
        {
            "sampleId": "romras-rain",
            "npcId": "Wizard",
            "sourceMod": "Parrot.RomRas",
            "sourceKey": "Rain",
            "text": "雨天也不妨碍我工作。",
        },
    ]
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": vanilla + overlay,
                "speechEvidence": vanilla + overlay,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = ProfileIndexStore(index_path)
    style = store.style_samples("Wizard", ["Parrot.RomRas"], limit=6)
    speech = store.speech_evidence("Wizard", ["Parrot.RomRas"], limit=6)

    assert any(item["sourceMod"] == "Parrot.RomRas" for item in style)
    assert any(item["sourceMod"] == "Parrot.RomRas" for item in speech)


def test_seasonal_overlay_does_not_displace_vanilla_daily_samples(
    tmp_path: Path,
) -> None:
    """覆盖层样本即使排序分数较低，也不能被 vanilla 日常样本挤到后面。"""
    index_path = tmp_path / "profile-index.json"
    vanilla = [
        {
            "sampleId": f"vanilla-{day}",
            "npcId": "Wizard",
            "sourceMod": "vanilla",
            "sourceKey": day,
            "text": f"原版 {day}。",
        }
        for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
    ]
    overlay = [
        {
            "sampleId": f"romras-season-{index}",
            "npcId": "Wizard",
            "sourceMod": "Parrot.RomRas",
            "sourceKey": f"Summer_{index}",
            "text": f"RomRas 夏日样本 {index}。",
        }
        for index in range(3)
    ]
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": vanilla + overlay,
                "speechEvidence": vanilla + overlay,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = ProfileIndexStore(index_path)

    for selected in (
        store.style_samples("Wizard", ["Parrot.RomRas"], limit=6),
        store.speech_evidence("Wizard", ["Parrot.RomRas"], limit=6),
    ):
        assert [item["sourceMod"] for item in selected[:3]] == [
            "vanilla",
            "vanilla",
            "vanilla",
        ]
        assert all(item["sourceMod"] == "vanilla" for item in selected)


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

    assert len(context["speechEvidence"]) == 6
    assert len(context["styleSamples"]) == 2
    assert len(context["speechEvidence"]) + len(context["styleSamples"]) == 8
    assert len(context["storyEvents"]) == 1
    assert all(sample["npcId"] == "Sophia" for sample in context["styleSamples"])
    assert "sourcePath" not in json.dumps(context, ensure_ascii=False)


def test_context_builder_keeps_speech_and_style_evidence_distinct(
    tmp_path: Path,
) -> None:
    """原文证据与语气补充样本不能把同一句对白重复送进上下文。"""

    index_path = tmp_path / "profile-index.json"
    records = [
        {
            "sampleId": f"sophia-{index}",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourceKey": f"Mon{index + 2}",
            "text": f"葡萄园样本 {index}。",
            "evidenceKind": "dialogue",
            "conditions": {"relationshipStage": "acquaintance"},
        }
        for index in range(10)
    ]
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": records,
                "speechEvidence": records,
                "voiceCards": {},
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    context = ContextBuilder(
        PersonaStore(Path(__file__).parents[2] / "data" / "personas"),
        ProfileIndexStore(index_path),
    ).build(
        "Sophia",
        source_mods=["SVE"],
        relationshipStage="acquaintance",
        message="最近葡萄园怎么样？",
    )

    speech_texts = {item["text"] for item in context["speechEvidence"]}
    style_texts = {item["text"] for item in context["styleSamples"]}
    assert speech_texts
    assert style_texts
    assert speech_texts.isdisjoint(style_texts)


def test_context_stage_policy_is_not_the_descriptive_stage_profile() -> None:
    builder = ContextBuilder(PersonaStore(Path(__file__).parents[2] / "data" / "personas"))

    context = builder.build(
        "Shane",
        source_mods=["female-bachelors"],
        friendshipHearts=0,
    )
    identity = context["npcIdentity"]

    assert identity["stageProfile"]["stage"] == "stranger"
    assert identity["stagePolicy"]["stage"] == "stranger"
    assert identity["stagePolicy"]["initiative"]
    assert identity["stagePolicy"]["boundaryMode"]


def test_context_marks_index_event_completed_when_runtime_flag_matches(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    _write_index(index_path)
    builder = ContextBuilder(
        PersonaStore(Path(__file__).parents[2] / "data" / "personas"),
        ProfileIndexStore(index_path),
    )

    context = builder.build(
        {
            "npcId": "Sophia",
            "sourceMods": ["SVE"],
            "gameState": {
                "completedEventIds": ["sve:event-1"],
            },
        }
    )

    assert context["storyEvents"][0]["status"] == "completed"


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


def test_speech_evidence_hard_filters_npc_source_and_relationship_stage(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "speechEvidence": [
                    {
                        "sampleId": "ras-vanilla-stranger",
                        "npcId": "Rasmodia",
                        "sourceMod": "vanilla",
                        "text": "原版初识样本",
                        "conditions": {"relationshipStage": "stranger"},
                    },
                    {
                        "sampleId": "ras-sve-friend",
                        "npcId": "Rasmodia",
                        "sourceMod": "FlashShifter.SVECode",
                        "text": "SVE 朋友阶段样本",
                        "conditions": {"relationshipStage": "friend"},
                    },
                    {
                        "sampleId": "ras-sve-dating",
                        "npcId": "Rasmodia",
                        "sourceMod": "FlashShifter.SVECode",
                        "text": "SVE 恋爱阶段样本",
                        "conditions": {"relationshipStage": "dating"},
                    },
                    {
                        "sampleId": "wizard-sve-friend",
                        "npcId": "Alex",
                        "sourceMod": "FlashShifter.SVECode",
                        "text": "另一个 NPC 的样本",
                        "conditions": {"relationshipStage": "friend"},
                    },
                ],
                "knowledgeFacts": [],
                "voiceCards": {},
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    evidence = ProfileIndexStore(index_path).speech_evidence(
        "Rasmodia",
        ["SVE"],
        relationship_stage="friend",
    )

    assert [item["sampleId"] for item in evidence] == ["ras-sve-friend"]


def test_speech_evidence_falls_back_to_legacy_style_samples(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "styleSamples": [
                    {
                        "sampleId": "legacy-ras",
                "npcId": "Wizard",
                        "sourceMod": "Nom0ri.RomRas",
                        "sourceKey": "Rain",
                        "text": "旧索引里的对白。",
                        "evidenceKind": "dialogue",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    evidence = ProfileIndexStore(index_path).speech_evidence(
        "Rasmodia", ["Nom0ri.RomRas"], relationship_stage="friend"
    )

    assert [item["sampleId"] for item in evidence] == ["legacy-ras"]


def test_voice_card_returns_a_copy_for_known_npc(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "voiceCards": {
                    "Wizard": {
                        "npcId": "Wizard",
                        "features": {"magicMarkers": 3},
                        "topicHints": ["魔法与星界"],
                        "evidenceRefs": ["vanilla:Wizard:Rain"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = ProfileIndexStore(index_path)
    card = store.voice_card("wizard")
    card["features"]["magicMarkers"] = 0

    assert store.voice_card("Wizard")["features"]["magicMarkers"] == 3
    assert store.voice_card("Unknown") == {}


def test_voice_card_prefers_active_mod_voice_anchors_over_vanilla(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "voiceCards": {
                    "Wizard": {
                        "npcId": "Wizard",
                        "voiceAnchors": [
                            {
                                "sampleId": "vanilla-voice",
                                "sourceMod": "vanilla",
                                "text": "原版语气。",
                            },
                            {
                                "sampleId": "rasmodia-voice",
                                "sourceMod": "Nom0ri.RomRas",
                                "text": "娘化内容包语气。",
                            },
                        ],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    card = ProfileIndexStore(index_path).voice_card(
        "Rasmodia", ["Romanceable Rasmodius"]
    )

    assert [item["sampleId"] for item in card["voiceAnchors"]] == [
        "rasmodia-voice",
        "vanilla-voice",
    ]


def test_schema_two_empty_speech_evidence_does_not_fallback_to_style_samples(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "styleSamples": [
                    {
                        "sampleId": "legacy",
                        "npcId": "Wizard",
                        "sourceMod": "vanilla",
                        "text": "不应被 schema 2 空证据重新启用。",
                    }
                ],
                "speechEvidence": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    evidence = ProfileIndexStore(index_path).speech_evidence(
        "Wizard", ["vanilla"], relationship_stage="friend"
    )

    assert evidence == []


def test_context_projects_voice_card_without_exposing_stage_profiles(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "voiceCards": {
                    "Wizard": {
                        "npcId": "Wizard",
                        "features": {"magicMarkers": 3},
                        "topicHints": ["魔法与星界"],
                        "evidenceRefs": ["vanilla:Wizard:Rain"],
                    }
                },
                "speechEvidence": [
                    {
                        "sampleId": "wizard-1",
                        "npcId": "Wizard",
                        "sourceMod": "vanilla",
                        "text": "魔法需要边界。",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    persona_dir = Path(__file__).parents[2] / "data" / "personas"

    context = ContextBuilder(
        PersonaStore(persona_dir), ProfileIndexStore(index_path)
    ).build("Wizard", ["vanilla"], relationshipStage="friend")

    assert context["voiceCard"]["features"]["magicMarkers"] == 3
    assert len(context["speechEvidence"]) == 1
    assert "stageProfiles" not in context["npcIdentity"]


def test_knowledge_facts_hard_filters_scope_source_and_completed_event(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "speechEvidence": [],
                "knowledgeFacts": [
                    {
                        "factId": "canon",
                        "npcId": "Rasmodia",
                        "sourceMod": "vanilla",
                        "summary": "确定事实",
                        "knowledgeScope": "canon_confirmed",
                    },
                    {
                        "factId": "rumor",
                        "npcId": "Rasmodia",
                        "sourceMod": "SVE",
                        "summary": "未确认传闻",
                        "knowledgeScope": "unverified",
                    },
                    {
                        "factId": "event-done",
                        "npcId": "Rasmodia",
                        "sourceMod": "SVE",
                        "summary": "已完成事件",
                        "knowledgeScope": "runtime_confirmed",
                        "requiredEventId": "sve:rasmodia:1",
                    },
                    {
                        "factId": "event-pending",
                        "npcId": "Rasmodia",
                        "sourceMod": "SVE",
                        "summary": "未完成事件",
                        "knowledgeScope": "runtime_confirmed",
                        "requiredEventId": "sve:rasmodia:2",
                    },
                    {
                        "factId": "low-confidence",
                        "npcId": "Rasmodia",
                        "sourceMod": "SVE",
                        "summary": "低可信度的推断",
                        "knowledgeScope": "runtime_confirmed",
                        "confidence": "low",
                    },
                ],
                "voiceCards": {},
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    facts = ProfileIndexStore(index_path).knowledge_facts(
        "Rasmodia",
        ["SVE"],
        completed_event_ids=["sve:rasmodia:1"],
    )

    assert [item["factId"] for item in facts] == ["event-done", "canon"]


def test_context_projects_only_hard_filtered_speech_and_facts(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "speechEvidence": [
                    {
                        "sampleId": "wizard-friend",
                        "npcId": "Wizard",
                        "sourceMod": "SVE",
                        "text": "朋友阶段的研究样本",
                        "conditions": {"relationshipStage": "friend"},
                    },
                    {
                        "sampleId": "wizard-dating",
                        "npcId": "Wizard",
                        "sourceMod": "SVE",
                        "text": "恋爱阶段的研究样本",
                        "conditions": {"relationshipStage": "dating"},
                    },
                ],
                "knowledgeFacts": [
                    {
                        "factId": "completed",
                        "npcId": "Wizard",
                        "sourceMod": "SVE",
                        "summary": "已完成的事实",
                        "knowledgeScope": "runtime_confirmed",
                        "requiredEventId": "sve:1",
                    },
                    {
                        "factId": "pending",
                        "npcId": "Wizard",
                        "summary": "不应进入上下文",
                        "sourceMod": "SVE",
                        "knowledgeScope": "runtime_confirmed",
                        "requiredEventId": "sve:2",
                    },
                ],
                "voiceCards": {},
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    builder = ContextBuilder(
        PersonaStore(Path(__file__).parents[2] / "data" / "personas"),
        ProfileIndexStore(index_path),
    )

    context = builder.build(
        "Wizard",
        source_mods=["SVE"],
        relationshipStage="friend",
        completedEventIds=["sve:1"],
    )

    assert [item["sampleId"] for item in context["speechEvidence"]] == [
        "wizard-friend",
    ]
    assert [item["factId"] for item in context["knowledgeFacts"]] == [
        "completed",
    ]


def test_known_characters_are_filtered_by_owner_source_scope_and_event(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "speechEvidence": [],
                "knowledgeFacts": [],
                "knownCharacters": [
                    {
                        "npcId": "Caroline",
                        "knownNpcId": "Marnie",
                        "relation": "熟人",
                        "summary": "Caroline 知道 Marnie 经营牧场。",
                        "sourceMod": "vanilla",
                        "knowledgeScope": "canon_confirmed",
                    },
                    {
                        "npcId": "Caroline",
                        "knownNpcId": "Wizard",
                        "relation": "传闻",
                        "summary": "未确认的传闻。",
                        "sourceMod": "vanilla",
                        "knowledgeScope": "unverified",
                    },
                    {
                        "npcId": "Caroline",
                        "knownNpcId": "Abigail",
                        "relation": "母女",
                        "summary": "未完成剧情后的信息。",
                        "sourceMod": "vanilla",
                        "knowledgeScope": "runtime_confirmed",
                        "requiredEventId": "vanilla:family",
                    },
                    {
                        "npcId": "Shane",
                        "knownNpcId": "Marnie",
                        "relation": "亲戚",
                        "summary": "不属于 Caroline 的关系。",
                        "sourceMod": "vanilla",
                        "knowledgeScope": "canon_confirmed",
                    },
                ],
                "voiceCards": {},
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    known = ProfileIndexStore(index_path).known_characters(
        "Caroline",
        ["vanilla"],
        completed_event_ids=["vanilla:family"],
    )

    assert [item["knownNpcId"] for item in known] == ["Marnie", "Abigail"]
    assert all(item["npcId"] == "Caroline" for item in known)


def test_context_projects_known_characters_separately_from_facts(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "speechEvidence": [],
                "knowledgeFacts": [],
                "knownCharacters": [
                    {
                        "npcId": "Caroline",
                        "knownNpcId": "Marnie",
                        "relation": "熟人",
                        "summary": "她知道 Marnie 经营牧场。",
                        "sourceMod": "vanilla",
                        "knowledgeScope": "canon_confirmed",
                    }
                ],
                "voiceCards": {},
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    context = ContextBuilder(
        PersonaStore(Path(__file__).parents[2] / "data" / "personas"),
        ProfileIndexStore(index_path),
    ).build("Caroline", source_mods=["vanilla"], message="Marnie 最近怎么样？")

    assert context["knownCharacters"][0]["knownNpcId"] == "Marnie"


def test_prompt_renders_hard_filtered_evidence_as_separate_messages(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "speechEvidence": [
                    {
                        "sampleId": "wizard-friend",
                        "npcId": "Wizard",
                        "sourceMod": "SVE",
                        "text": "朋友阶段的研究样本",
                        "conditions": {"relationshipStage": "friend"},
                    },
                ],
                "knowledgeFacts": [
                    {
                        "factId": "completed",
                        "npcId": "Wizard",
                        "sourceMod": "SVE",
                        "summary": "已完成的事实",
                        "knowledgeScope": "runtime_confirmed",
                    },
                ],
                "voiceCards": {},
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    context = ContextBuilder(
        PersonaStore(Path(__file__).parents[2] / "data" / "personas"),
        ProfileIndexStore(index_path),
    ).build("Wizard", source_mods=["SVE"], relationshipStage="friend")

    messages = PromptBuilder().build(context, "你还记得那件事吗？")
    names = [message["name"] for message in messages]
    rendered = json.dumps(messages, ensure_ascii=False)

    assert "speech_evidence" in names
    assert "knowledge_facts" in names
    assert "wizard-friend" in rendered
    assert "runtime_confirmed" in rendered


def test_rasmodia_context_filters_unresolved_i18n_but_keeps_runtime_evidence(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": [
                    {
                        "sampleId": "raw-template",
                        "npcId": "Wizard",
                        "sourceMod": "Parrot.RomRas",
                        "sourceKey": "funReturn",
                        "text": "{{i18n:Wizard.funReturn.{{Random:1,2}}}}",
                        "evidenceKind": "dialogue",
                    },
                    {
                        "sampleId": "runtime:rasmodia-1",
                        "npcId": "Wizard",
                        "sourceMod": "Parrot.RomRas",
                        "sourceKey": "funReturn",
                        "text": "星界的潮汐今天很平静。",
                        "evidenceKind": "runtime_dialogue",
                    },
                ],
                "speechEvidence": [
                    {
                        "sampleId": "raw-template",
                        "npcId": "Wizard",
                        "sourceMod": "Parrot.RomRas",
                        "sourceKey": "funReturn",
                        "text": "{{i18n:Wizard.funReturn.{{Random:1,2}}}}",
                        "evidenceKind": "dialogue",
                    },
                    {
                        "sampleId": "runtime:rasmodia-1",
                        "npcId": "Wizard",
                        "sourceMod": "Parrot.RomRas",
                        "sourceKey": "funReturn",
                        "text": "星界的潮汐今天很平静。",
                        "evidenceKind": "runtime_dialogue",
                        "conditions": {"relationshipStage": "friend"},
                    },
                ],
                "voiceCards": {},
                "storyEvents": [],
                "knowledgeFacts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    builder = ContextBuilder(
        PersonaStore(Path(__file__).parents[2] / "data" / "personas"),
        ProfileIndexStore(index_path),
    )
    context = builder.build(
        "Wizard",
        source_mods=["Parrot.RomRas"],
        relationshipStage="friend",
    )
    rendered = json.dumps(context, ensure_ascii=False)

    assert "{{i18n:" not in rendered
    assert "星界的潮汐今天很平静。" in rendered
    assert context["npcIdentity"]["displayName"] == "Rasmodia"


def test_runtime_dialogue_evidence_is_prioritised_for_style_context(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    samples = [
        {
            "sampleId": f"static-{index}",
            "npcId": "Claire",
            "sourceMod": "FlashShifter.StardewValleyExpandedCP",
            "sourceKey": f"static-{index}",
            "text": f"静态候选 {index}",
            "evidenceKind": "dialogue",
        }
        for index in range(8)
    ]
    runtime = {
        "sampleId": "runtime:claire-1",
        "npcId": "Claire",
        "sourceMod": "FlashShifter.StardewValleyExpandedCP",
        "sourceKey": "funReturn_Claire",
        "text": "实际运行时分支",
        "evidenceKind": "runtime_dialogue",
    }
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": [*samples, runtime],
                "speechEvidence": [*samples, runtime],
                "voiceCards": {},
                "storyEvents": [],
                "knowledgeFacts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = ProfileIndexStore(index_path)

    assert store.style_samples(
        "Claire", ["FlashShifter.StardewValleyExpandedCP"], limit=1
    )[0]["evidenceKind"] == "runtime_dialogue"
    assert store.speech_evidence(
        "Claire", ["FlashShifter.StardewValleyExpandedCP"], limit=1
    )[0]["evidenceKind"] == "runtime_dialogue"


def test_mod_specific_evidence_precedes_vanilla_when_both_match(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    vanilla = [
        {
            "sampleId": f"vanilla-{index}",
            "npcId": "Wizard",
            "sourceMod": "vanilla",
            "text": f"原版样本 {index}",
            "evidenceKind": "dialogue",
        }
        for index in range(6)
    ]
    rasmodia = {
        "sampleId": "rasmodia-voice",
        "npcId": "Wizard",
        "sourceMod": "Parrot.RomRas",
        "text": "星界的回声需要谨慎记录。",
        "evidenceKind": "dialogue",
        "conditions": {"relationshipStage": "friend"},
    }
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": [*vanilla, rasmodia],
                "speechEvidence": [*vanilla, rasmodia],
                "voiceCards": {},
                "storyEvents": [],
                "knowledgeFacts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = ProfileIndexStore(index_path)

    assert store.style_samples("Wizard", ["Parrot.RomRas"], limit=1)[0]["sampleId"] == (
        "rasmodia-voice"
    )
    assert store.speech_evidence(
        "Wizard",
        ["Parrot.RomRas"],
        relationship_stage="friend",
        limit=1,
    )[0]["sampleId"] == "rasmodia-voice"
