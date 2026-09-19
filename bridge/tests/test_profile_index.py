from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from stardew_ai_bridge.personas import canonical_npc_id
from stardew_ai_bridge.profile_index import ProfileIndexBuilder, ProfileIndexStore


def _write_json(path: Path, value: str | dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_persona_layers_preserve_sources_and_overlay_boundaries(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {
            "mod": "vanilla",
            "personas": {
                "Wizard": {
                    "npcId": "Wizard",
                    "displayName": "Wizard",
                    "coreTraits": ["谨慎"],
                },
                "Sophia": {
                    "npcId": "Sophia",
                    "displayName": "Sophia",
                    "coreTraits": ["温和"],
                },
            },
        },
    )
    _write_json(
        persona_dir / "sve.json",
        {
            "mod": "SVE",
            "sourceMods": ["FlashShifter.SVECode"],
            "personas": {
                "Wizard": {"displayName": "Magnus"},
                "Sophia": {"displayName": "Sophia", "source": "SVE"},
            },
        },
    )

    index = ProfileIndexBuilder(persona_dir).build()

    assert index["schemaVersion"] == 2
    profiles = index["profiles"]
    assert isinstance(profiles, dict)
    assert profiles["Sophia"]["sourceMods"] == ["vanilla", "SVE"]
    assert profiles["Sophia"]["sourceFiles"] == ["vanilla.json", "sve.json"]
    assert profiles["Wizard"]["overlays"]["SVE"]["displayName"] == "Magnus"
    assert profiles["Wizard"]["displayName"] == "Wizard"


def test_feminine_overlay_stays_profile_metadata_and_never_becomes_dialogue_source(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {
            "mod": "vanilla",
            "personas": {
                "Shane": {
                    "npcId": "Shane",
                    "displayName": "Shane",
                    "coreTraits": ["直白", "疲惫"],
                }
            },
        },
    )
    _write_json(
        persona_dir / "female-bachelors.json",
        {
            "mod": "female-bachelors",
            "personas": {
                "Shane": {
                    "genderPresentation": {
                        "layer": "expression_only",
                        "basePersonaPriority": "higher",
                        "toneAdjustments": ["亲密时更容易露出尴尬"],
                    }
                }
            },
        },
    )
    corpus_path = tmp_path / "resolved.json"
    _write_json(
        corpus_path,
        {
            "schemaVersion": 1,
            "records": [
                {
                    "sampleId": "vanilla:Shane:Rain",
                    "npcId": "Shane",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Shane",
                    "sourceKey": "Rain",
                    "text": "下雨天，鸡舍里也得有人照看。",
                    "evidenceKind": "dialogue",
                }
            ],
        },
    )

    index = ProfileIndexBuilder(persona_dir).build(corpus_paths=[corpus_path])

    profiles = index["profiles"]
    assert isinstance(profiles, dict)
    overlay = profiles["Shane"]["overlays"]["female-bachelors"]
    assert overlay["genderPresentation"]["layer"] == "expression_only"
    assert overlay["genderPresentation"]["basePersonaPriority"] == "higher"

    samples = index["styleSamples"]
    assert samples == [
        {
            "sampleId": "vanilla:Shane:Rain",
            "npcId": "Shane",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Shane",
            "sourceKey": "Rain",
            "text": "下雨天，鸡舍里也得有人照看。",
            "evidenceKind": "dialogue",
        }
    ]
    assert all("genderPresentation" not in sample for sample in samples)


def test_ineligible_female_overlay_does_not_suppress_vanilla_evidence(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {
            "mod": "vanilla",
            "personas": {
                "Caroline": {
                    "npcId": "Caroline",
                    "displayName": "Caroline",
                }
            },
        },
    )
    _write_json(
        persona_dir / "female-bachelors.json",
        {
            "mod": "female-bachelors",
            "personas": {
                "Caroline": {"displayName": "错误名字"},
            },
        },
    )
    corpus_path = tmp_path / "resolved.json"
    _write_json(
        corpus_path,
        {
            "schemaVersion": 1,
            "records": [
                {
                    "sampleId": "caroline-vanilla",
                    "npcId": "Caroline",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Caroline",
                    "sourceKey": "Mon",
                    "text": "今天牧场很安静。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "caroline-female",
                    "npcId": "Caroline",
                    "sourceMod": "female-bachelors",
                    "sourcePath": "Mod/Dialogue/Caroline",
                    "sourceKey": "Mon",
                    "text": "这条错误覆盖不应该压掉原版。",
                    "evidenceKind": "dialogue",
                },
            ],
        },
    )

    index = ProfileIndexBuilder(persona_dir).build(corpus_paths=[corpus_path])
    index_path = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, index_path)
    samples = ProfileIndexStore(index_path).style_samples(
        "Caroline", ["vanilla", "female-bachelors"], limit=8
    )

    assert {sample["sourceMod"] for sample in samples} == {
        "vanilla",
        "female-bachelors",
    }


def test_content_patcher_dialogue_keeps_i18n_reference_and_source_key(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "sve"
    _write_json(
        mod_root / "manifest.json",
        {"Name": "Stardew Valley Expanded", "UniqueID": "FlashShifter.SVECode"},
    )
    _write_json(
        mod_root / "assets" / "Sophia" / "Dialogue.json",
        """
        {
          // Content Patcher allows comments and trailing commas.
          "Changes": [
            {
              "Action": "EditData",
              "Target": "Characters/Dialogue/Sophia",
              "Entries": {
                "Introduction": "{{i18n:Sophia.CharacterDialogue.001}}",
                "Rain": "今天适合待在家里。",
              },
            },
          ],
        }
        """,
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    samples = index["styleSamples"]
    assert isinstance(samples, list)
    assert {sample["sourceKey"] for sample in samples} == {"Introduction", "Rain"}
    introduction = next(sample for sample in samples if sample["sourceKey"] == "Introduction")
    assert introduction["npcId"] == "Sophia"
    assert introduction["sourceMod"] == "FlashShifter.SVECode"
    assert introduction["text"] == "{{i18n:Sophia.CharacterDialogue.001}}"
    assert introduction["sourcePath"] == "assets/Sophia/Dialogue.json"
    assert index["storyEvents"] == []


def test_profile_index_uses_resolved_text_but_does_not_feed_dynamic_candidates(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    corpus_path = tmp_path / "sve-dialogue-corpus.json"
    _write_json(
        corpus_path,
        {
            "schemaVersion": 1,
            "records": [
                {
                    "sampleId": "Example.Mod:Dialogue.json:Rain",
                    "npcId": "Wizard",
                    "sourceMod": "Example.Mod",
                    "sourcePath": "Dialogue.json",
                    "sourceKey": "Rain",
                    "text": "{{i18n:Wizard.Rain}}",
                    "resolvedText": "中文原文",
                    "dynamicCandidates": [
                        {"key": "Wizard.Rain.1", "text": "不应直接喂给模型"}
                    ],
                    "evidenceKind": "dialogue",
                    "conditions": {},
                }
            ],
            "sources": [],
            "warnings": [],
        },
    )

    index = ProfileIndexBuilder(persona_dir).build(corpus_paths=[corpus_path])

    assert index["styleSamples"][0]["text"] == "中文原文"
    assert index["speechEvidence"][0]["text"] == "中文原文"
    assert "dynamicCandidates" not in index["styleSamples"][0]


def test_profile_index_excludes_source_artifacts_from_style_speech_and_voice(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    corpus_path = tmp_path / "corpus.json"
    _write_json(
        corpus_path,
        {
            "schemaVersion": 1,
            "records": [
                {
                    "sampleId": "old-key",
                    "npcId": "Alex",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Alex.json",
                    "sourceKey": "Wed_01_old",
                    "text": "今天过得还好。",
                },
                {
                    "sampleId": "number-prefix",
                    "npcId": "Alex",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Alex.json",
                    "sourceKey": "Thu",
                    "text": "5 长途奔袭！……开个玩笑而已。",
                },
                {
                    "sampleId": "npc-prefix",
                    "npcId": "Alex",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Alex.json",
                    "sourceKey": "Fri",
                    "text": "Sebastian1 我昨晚跑进山洞里……",
                },
                {
                    "sampleId": "clean",
                    "npcId": "Alex",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Alex.json",
                    "sourceKey": "Mon",
                    "text": "嘿！今天感觉不错。",
                },
            ],
        },
    )

    index = ProfileIndexBuilder(persona_dir).build(corpus_paths=[corpus_path])

    assert [item["sampleId"] for item in index["styleSamples"]] == ["clean"]
    assert [item["sampleId"] for item in index["speechEvidence"]] == ["clean"]
    assert [item["sampleId"] for item in index["voiceCards"]["Alex"]["voiceAnchors"]] == [
        "clean"
    ]


def test_resolved_corpus_replaces_matching_unresolved_mod_sample(
    tmp_path: Path,
) -> None:
    """合并已解析语料时，不能让同 ID 的 i18n 占位符挡住中文原文。"""

    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "sve"
    _write_json(
        mod_root / "manifest.json",
        {"UniqueID": "Example.Mod"},
    )
    _write_json(
        mod_root / "Dialogue.json",
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/Sophia",
                    "Entries": {
                        "Introduction": "{{i18n:Sophia.Introduction}}",
                    },
                }
            ]
        },
    )
    corpus_path = tmp_path / "resolved.json"
    _write_json(
        corpus_path,
        {
            "schemaVersion": 1,
            "records": [
                {
                    "sampleId": "Example.Mod:Dialogue.json:Introduction",
                    "npcId": "Sophia",
                    "sourceMod": "Example.Mod",
                    "sourcePath": "Dialogue.json",
                    "sourceKey": "Introduction",
                    "text": "{{i18n:Sophia.Introduction}}",
                    "resolvedText": "呀！有陌生人！",
                    "evidenceKind": "dialogue",
                }
            ],
        },
    )

    index = ProfileIndexBuilder(persona_dir).build(
        [mod_root],
        corpus_paths=[corpus_path],
    )

    samples = [
        sample
        for sample in index["styleSamples"]
        if sample["sampleId"] == "Example.Mod:Dialogue.json:Introduction"
    ]
    assert len(samples) == 1
    assert samples[0]["text"] == "呀！有陌生人！"


def test_profile_builder_prefers_resolved_text_over_stale_dynamic_variants(
    tmp_path: Path,
) -> None:
    """旧语料中的动态切片不能盖过可用的 resolvedText。"""

    persona_dir = tmp_path / "personas"
    _write_json(persona_dir / "vanilla.json", {"mod": "vanilla", "personas": {}})
    corpus_path = tmp_path / "resolved.json"
    _write_json(
        corpus_path,
        {
            "schemaVersion": 1,
            "records": [
                {
                    "sampleId": "Example.Mod:Dialogue.json:Mon",
                    "npcId": "Sophia",
                    "sourceMod": "Example.Mod",
                    "sourcePath": "Dialogue.json",
                    "sourceKey": "Mon",
                    "text": "{{i18n:Sophia.CharacterDialogue.001}}",
                    "resolvedText": "早上好。葡萄园今天还算安静。",
                    "dialogueVariants": [
                        "{{i18n:Sophia.CharacterDialogue.001",
                        "default={{i18n:Sophia.CharacterDialogue.001",
                    ],
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "Example.Mod:Dialogue.json:Tue",
                    "npcId": "Sophia",
                    "sourceMod": "Example.Mod",
                    "sourcePath": "Dialogue.json",
                    "sourceKey": "Tue",
                    "text": "{{i18n:Sophia.Dynamic.{{Random:{{Range:1,3}}}}}}",
                    "dialogueVariants": [
                        "{{i18n:Sophia.Dynamic.{{Random: }}",
                    ],
                    "evidenceKind": "dialogue",
                },
            ],
        },
    )

    index = ProfileIndexBuilder(persona_dir).build(corpus_paths=[corpus_path])

    assert [item["text"] for item in index["styleSamples"]] == [
        "早上好。葡萄园今天还算安静。"
    ]
    assert [item["text"] for item in index["speechEvidence"]] == [
        "早上好。葡萄园今天还算安静。"
    ]


def test_index_v2_keeps_fact_provenance_and_excludes_unverified_by_default(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {
            "mod": "vanilla",
            "personas": {
                "Wizard": {
                    "knowledgeFacts": [
                        {
                            "factId": "tower-residence",
                            "summary": "居住并工作的地点是法师塔。",
                            "knowledgeScope": "canon_confirmed",
                            "confidence": "high",
                            "sourceRefs": ["vanilla:Wizard:Tower"],
                        },
                        {
                            "factId": "unverified-rumor",
                            "summary": "没有来源的传闻。",
                            "knowledgeScope": "unverified",
                            "confidence": "low",
                            "sourceRefs": [],
                        },
                    ]
                }
            },
        },
    )

    index = ProfileIndexBuilder(persona_dir).build()

    assert index["schemaVersion"] == 2
    assert index["knowledgeFacts"] == [
        {
            "factId": "tower-residence",
            "npcId": "Wizard",
            "sourceMod": "vanilla",
            "summary": "居住并工作的地点是法师塔。",
            "knowledgeScope": "canon_confirmed",
            "confidence": "high",
            "sourceRefs": ["vanilla:Wizard:Tower"],
        }
    ]


def test_content_patcher_dialogue_projects_stage_aware_speech_evidence(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "rasmodia"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Rasmodia"})
    _write_json(
        mod_root / "MarriageDialogue.json",
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/MarriageDialogueRasmodia",
                    "Entries": {"Rain": "雨天留在塔里。"},
                }
            ]
        },
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    evidence = index["speechEvidence"]
    assert evidence == [
        {
            "sampleId": "Example.Rasmodia:MarriageDialogue.json:Rain",
                "npcId": "Wizard",
            "sourceMod": "Example.Rasmodia",
            "sourcePath": "MarriageDialogue.json",
            "sourceKey": "Rain",
            "text": "雨天留在塔里。",
            "evidenceKind": "marriage_dialogue",
            "conditions": {"relationshipStage": "married"},
        }
    ]


def test_profile_index_derives_voice_card_from_speech_evidence(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "rasmodia"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Rasmodia"})
    _write_json(
        mod_root / "Dialogue.json",
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/Rasmodia",
                    "Entries": {
                        "Rain": "也许魔法需要边界。",
                        "Night": "当然，风险并不等于命运。",
                    },
                }
            ]
        },
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    card = index["voiceCards"]["Wizard"]
    assert card["features"]["uncertaintyMarkers"] == 1
    assert card["features"]["magicMarkers"] == 1
    assert card["features"]["boundaryMarkers"] == 2
    assert card["evidenceRefs"] == [
        "Example.Rasmodia:Dialogue.json:Rain",
        "Example.Rasmodia:Dialogue.json:Night",
    ]


def test_sophia_voice_card_reselects_stage_energy_anchors(tmp_path: Path) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "voiceCards": {
                    "Sophia": {
                        "npcId": "Sophia",
                        "voiceAnchors": [
                            {
                                "sampleId": "static",
                                "sourceMod": "SVE",
                                "sourceKey": "Mon",
                                "text": "静态卡不应覆盖阶段重选。",
                            }
                        ],
                    }
                },
                "speechEvidence": [
                    {
                        "sampleId": "calm",
                        "npcId": "Sophia",
                        "sourceMod": "SVE",
                        "sourceKey": "Rain",
                        "conditions": {"relationshipStage": "married"},
                        "text": "今天酒窖里很安静。",
                    },
                    {
                        "sampleId": "hot",
                        "npcId": "Sophia",
                        "sourceMod": "SVE",
                        "sourceKey": "Good_0",
                        "evidenceKind": "marriage_dialogue",
                        "conditions": {"relationshipStage": "married"},
                        "text": "嘿，小傻瓜！再靠近一点……！！！爱你哟！",
                    },
                    {
                        "sampleId": "stranger",
                        "npcId": "Sophia",
                        "sourceMod": "SVE",
                        "sourceKey": "Mon",
                        "conditions": {"relationshipStage": "stranger"},
                        "text": "嗯……你好。",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    card = ProfileIndexStore(index_path).voice_card(
        "Sophia", ["SVE"], relationship_stage="married"
    )

    assert [item["sourceKey"] for item in card["voiceAnchors"][:2]] == [
        "Good_0",
        "Rain",
    ]


def test_sophia_voice_card_uses_compatible_stage_when_dating_has_no_exact_samples(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    records = [
        {
            "sampleId": "stranger-calm",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourceKey": "Mon",
            "conditions": {"relationshipStage": "stranger"},
            "text": "嗯……你好。",
        },
        {
            "sampleId": "friend-bright",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourceKey": "Good_4",
            "conditions": {"relationshipStage": "friend"},
            "text": "耶，葡萄终于变甜了呀！我刚才还在等这一刻。",
        },
        {
            "sampleId": "close-bright",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourceKey": "Outdoor_4",
            "conditions": {"relationshipStage": "close"},
            "text": "嘿！你也闻到了吗？这股甜味今天特别明显。",
        },
    ]
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "voiceCards": {
                    "Sophia": {
                        "npcId": "Sophia",
                        "voiceAnchors": [
                            {"sourceMod": "SVE", "sourceKey": "Mon", "text": "旧卡。"}
                        ],
                    }
                },
                "speechEvidence": records,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    card = ProfileIndexStore(index_path).voice_card(
        "Sophia", ["SVE"], relationship_stage="dating"
    )

    selected = card["voiceAnchors"]
    assert {item["sampleId"] for item in selected} >= {
        "friend-bright",
        "close-bright",
    }
    assert all(item["sampleId"] != "stranger-calm" for item in selected)


def test_non_sophia_voice_card_reselects_stage_anchors_from_original_evidence(
    tmp_path: Path,
) -> None:
    """其他角色也应从当前关系阶段的原文证据重选声线锚点。"""

    index_path = tmp_path / "profile-index.json"
    records = [
        {
            "sampleId": "stranger-shane",
            "npcId": "Shane",
            "sourceMod": "vanilla",
            "sourceKey": "Mon",
            "conditions": {"relationshipStage": "stranger"},
            "text": "我不认识你。你为什么要和我说话？",
            "evidenceKind": "dialogue",
        },
        {
            "sampleId": "close-shane",
            "npcId": "Shane",
            "sourceMod": "vanilla",
            "sourceKey": "Mon10",
            "conditions": {"relationshipStage": "close"},
            "text": "我只是想确认你没把自己累垮。就这样。",
            "evidenceKind": "dialogue",
        },
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "voiceCards": {
                "Shane": {
                    "npcId": "Shane",
                    "voiceAnchors": [
                        {
                            "sampleId": "static",
                            "sourceMod": "vanilla",
                            "sourceKey": "Introduction",
                            "text": "静态卡不应覆盖当前阶段原文。",
                        }
                    ],
                }
            },
            "speechEvidence": records,
        },
    )

    card = ProfileIndexStore(index_path).voice_card(
        "Shane", ["vanilla"], relationship_stage="close"
    )

    assert [item["sampleId"] for item in card["voiceAnchors"]] == [
        "close-shane"
    ]


def test_profile_index_aliases_rasmodia_to_wizard_for_shared_evidence(
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
                        "sampleId": "wizard-daily",
                        "npcId": "Wizard",
                        "sourceMod": "vanilla",
                        "sourceKey": "Rain",
                        "text": "今天只是普通的一天。",
                        "evidenceKind": "dialogue",
                    },
                    {
                        "sampleId": "rasmodia-overlay",
                        "npcId": "Rasmodia",
                        "sourceMod": "Parrot.RomRas",
                        "sourceKey": "Rain",
                        "text": "今天的研究还算安静。",
                        "evidenceKind": "dialogue",
                    },
                ],
                "voiceCards": {
                    "Wizard": {
                        "npcId": "Wizard",
                        "features": {"magicMarkers": 1},
                        "topicHints": [],
                        "evidenceRefs": ["wizard-daily"],
                    }
                },
                "storyEvents": [],
                "knowledgeFacts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = ProfileIndexStore(index_path)
    wizard_ids = {
        item["sampleId"]
        for item in store.speech_evidence("Wizard", ["Parrot.RomRas"])
    }
    rasmodia_ids = {
        item["sampleId"]
        for item in store.speech_evidence("Rasmodia", ["Parrot.RomRas"])
    }

    assert wizard_ids == rasmodia_ids == {"wizard-daily", "rasmodia-overlay"}
    assert all(
        item["npcId"] == "Wizard"
        for item in store.speech_evidence("Rasmodia", ["Parrot.RomRas"])
    )
    assert store.voice_card("Rasmodia")["npcId"] == "Wizard"


def test_profile_index_merges_case_only_npc_ids_without_duplicate_json_keys(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {"Wizard": {"displayName": "法师"}}},
    )
    mod_root = tmp_path / "mod"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    _write_json(
        mod_root / "Dialogue.json",
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/wizard",
                    "Entries": {"Rain": "也许魔法需要边界。"},
                }
            ]
        },
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    assert list(index["profiles"]) == ["Wizard"]
    assert list(index["voiceCards"]) == ["Wizard"]
    assert index["speechEvidence"][0]["npcId"] == "Wizard"


def test_content_json_dialogue_target_adds_profile_skeleton(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "mod"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    _write_json(
        mod_root / "content.json",
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/CustomNpc",
                    "Entries": {
                        "Introduction": "{{i18n:CustomNpc.Introduction}}",
                    },
                },
            ],
        },
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    profiles = index["profiles"]
    assert isinstance(profiles, dict)
    assert profiles["CustomNpc"]["sourceMods"] == ["Example.Mod"]
    assert profiles["CustomNpc"]["sourceFiles"] == ["content.json"]
    assert index["styleSamples"][0]["npcId"] == "CustomNpc"


def test_content_patcher_single_quoted_string_is_accepted(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "mod"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    (mod_root / "content.json").write_text(
        """
        {
          "Changes": [
            {
              "Action": "EditData",
              "Target": "Characters/Dialogue/CustomNpc",
              "Entries": {
                "Note": '她说：\\"别忘了回家。\\"',
              },
            },
          ],
        }
        """,
        encoding="utf-8",
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    assert index["warnings"] == []
    assert index["styleSamples"][0]["text"] == '她说："别忘了回家。"'


def test_invalid_json_becomes_warning_and_never_leaks_absolute_paths(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {"Alex": {"displayName": "Alex"}}},
    )
    mod_root = tmp_path / "mod"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    (mod_root / "broken-dialogue.json").write_text("{ not-json", encoding="utf-8")

    index = ProfileIndexBuilder(persona_dir).build([mod_root])
    rendered = json.dumps(index, ensure_ascii=False)

    assert any("invalid JSON" in warning for warning in index["warnings"])
    assert "broken-dialogue.json" in rendered
    assert str(tmp_path) not in rendered


def test_content_patcher_utf8_bom_is_accepted(tmp_path: Path) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "sve"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    dialogue = mod_root / "Dialogue.json"
    dialogue.write_text(
        '\ufeff{"Changes":[{"Action":"EditData","Target":"Characters/Dialogue/Alex",'
        '"Entries":{"Rain":"{{i18n:Alex.Rain}}"}}]}',
        encoding="utf-8",
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    assert len(index["styleSamples"]) == 1
    assert index["warnings"] == []


def test_content_patcher_multiline_dialogue_is_accepted(tmp_path: Path) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "sve"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    dialogue = mod_root / "MarriageDialogue.json"
    dialogue.write_text(
        '{"Changes":[{"Action":"EditData","Target":"Characters/Dialogue/MarriageDialogueAlex",'
        '"Entries":{"funLeave_Alex":"第一行\n{{i18n:Alex.funLeave}}\n第二行"}}]}',
        encoding="utf-8",
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    assert len(index["styleSamples"]) == 1
    assert index["styleSamples"][0]["npcId"] == "Alex"
    assert "\n" in index["styleSamples"][0]["text"]
    assert index["warnings"] == []


def test_non_dialogue_content_patcher_files_without_dialogue_targets_are_ignored(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "sve"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    (mod_root / "code" / "NPCs").mkdir(parents=True)
    (mod_root / "code" / "NPCs" / "Krobus.json").write_text(
        '{"Changes":[{"Fields":{"Krobus":{0:99999}}}]}',
        encoding="utf-8",
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    assert index["styleSamples"] == []
    assert index["warnings"] == []


def test_content_patcher_dialogue_in_arbitrary_json_filename_is_indexed(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "mod"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    _write_json(
        mod_root / "patches.json",
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/CustomNpc",
                    "Entries": {"Rain": "任意文件名也应保留。"},
                }
            ]
        },
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    assert index["styleSamples"][0]["sourcePath"] == "patches.json"


def test_profile_builder_expands_clean_variants_for_direct_mod_root(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "example-mod"
    _write_json(
        mod_root / "manifest.json",
        {"Name": "Example Mod", "UniqueID": "Example.Mod"},
    )
    _write_json(
        mod_root / "dialogue.json",
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/Alex",
                    "Entries": {
                        "Wed": (
                            "我去海滩投球。 6 0 Wed_01_02 "
                            "我今天只想在旁边看。"
                        )
                    },
                }
            ]
        },
    )

    index = ProfileIndexBuilder(persona_dir).build(mod_roots=[mod_root])
    samples = [
        item for item in index["styleSamples"] if item["npcId"] == "Alex"
    ]

    assert [item["text"] for item in samples] == [
        "我去海滩投球。",
        "我今天只想在旁边看。",
    ]
    assert all("Wed_01_02" not in item["text"] for item in samples)


def test_write_rejects_output_directory_that_is_a_file(tmp_path: Path) -> None:
    output = tmp_path / "output.json"
    output.write_text("not a directory", encoding="utf-8")

    with pytest.raises(OSError):
        ProfileIndexBuilder.write({"schemaVersion": 1}, output / "nested.json")


def test_cli_writes_index_to_explicit_output_path(tmp_path: Path) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {"Alex": {"displayName": "Alex"}}},
    )
    output = tmp_path / "generated" / "profile-index.json"
    script = Path(__file__).parents[2] / "scripts" / "build_profile_index.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--persona-dir",
            str(persona_dir),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["schemaVersion"] == 2


def test_cli_rejects_missing_persona_directory_without_creating_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "generated" / "profile-index.json"
    script = Path(__file__).parents[2] / "scripts" / "build_profile_index.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--persona-dir",
            str(tmp_path / "does-not-exist"),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not output.exists()


def test_profile_index_merges_runtime_dialogue_samples(tmp_path: Path) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(persona_dir / "vanilla.json", {"mod": "vanilla", "personas": {}})
    runtime_path = tmp_path / "runtime-dialogue-samples.jsonl"
    runtime_path.write_text(
        json.dumps(
            {
                "sourceSampleId": "Example.Mod:dialogue.json:rain",
                "npcId": "Claire",
                "sourceMod": "Example.Mod",
                "sourcePath": "dialogue.json",
                "sourceKey": "rain",
                "text": "今天的雨声很适合工作。",
                "candidateKey": "Claire.rain.1",
                "conditions": {"season": "Spring"},
                "gameState": {"season": "Spring", "day": 3},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    index = ProfileIndexBuilder(persona_dir).build(runtime_sample_paths=[runtime_path])

    sample = index["styleSamples"][0]
    assert sample["evidenceKind"] == "runtime_dialogue"
    assert sample["sourceSampleId"] == "Example.Mod:dialogue.json:rain"
    assert sample["candidateKey"] == "Claire.rain.1"
    assert sample["gameState"] == {"season": "Spring", "day": 3}


def test_profile_index_prioritizes_daily_dialogue_over_event_evidence(
    tmp_path: Path,
) -> None:
    """模型证据窗口不应把事件文案当作日常角色口吻。"""

    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": [
                {
                    "sampleId": "ras:event",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Data/Events/SVE_Events.json",
                    "sourceKey": "eventLine",
                    "text": "事件里的长篇说明。",
                },
                {
                    "sampleId": "ras:festival",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/FestivalDialogue.json",
                    "sourceKey": "festivalLine",
                    "text": "节庆时才会说的话。",
                },
                {
                    "sampleId": "ras:daily",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "Mon",
                    "text": "如果没有重要的事，请不要打搅我。",
                },
                {
                    "sampleId": "ras:integrated",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Integrated/IntegratedDialogueWizard.json",
                    "sourceKey": "Tue",
                    "text": "我还有好多活要干呢。",
                },
            ],
            "speechEvidence": [],
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)
    samples = store.style_samples("Wizard", ["Parrot.RomRas"], limit=4)

    assert [item["sampleId"] for item in samples] == [
        "ras:daily",
        "ras:integrated",
    ]


def test_profile_index_prioritizes_stable_daily_keys_within_dialogue_files(
    tmp_path: Path,
) -> None:
    """同一对白文件内也应先取平日短句，而不是季节/事件长句。"""

    index_path = tmp_path / "index.json"
    samples = [
        ("seasonal", "spring_Mon"),
        ("event", "event_speakof2"),
        ("introduction", "Introduction"),
        ("neutral", "Neutral_7"),
        ("weekday", "Tue"),
        ("good", "Good_7"),
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": [
                {
                    "sampleId": f"ras:{sample_id}",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": source_key,
                    "text": f"{source_key} 的示例台词。",
                }
                for sample_id, source_key in samples
            ],
            "speechEvidence": [],
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)
    selected = store.style_samples("Wizard", ["Parrot.RomRas"], limit=6)

    assert [item["sourceKey"] for item in selected] == [
        "Tue",
        "Introduction",
    ]


def test_profile_index_filters_special_lines_from_style_and_speech_windows(
    tmp_path: Path,
) -> None:
    records = [
        {
            "sampleId": "daily",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/Standard/StandardDialogueSophia.json",
            "sourceKey": "Mon2",
            "text": "今天的葡萄园还算安静。",
        },
        {
            "sampleId": "festival",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/FestivalDialogue.json",
            "sourceKey": "wonEggHunt",
            "text": "今天的节日真热闹！",
        },
        {
            "sampleId": "triggered",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "code/Festivals/jojaday.json",
            "sourceKey": "sale",
            "text": "特卖活动开始了。",
        },
    ]
    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)

    assert [item["sampleId"] for item in store.style_samples("Sophia", ["SVE"])] == [
        "daily"
    ]
    assert [
        item["sampleId"]
        for item in store.speech_evidence(
            "Sophia", ["SVE"], relationship_stage="acquaintance"
        )
    ] == ["daily"]


def test_profile_index_filters_real_conditional_keys_from_model_windows(
    tmp_path: Path,
) -> None:
    records = [
        {
            "sampleId": f"sample:{source_key}",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "assets/CharacterFiles/Dialogue/Sophia/Dialogue.json",
            "sourceKey": source_key,
            "text": f"不应进入模型窗口：{source_key}",
            "evidenceKind": "dialogue",
        }
        for source_key in (
            "pamHouseUpgradeAnonymous",
            "Hospital_5_17",
            "BlueMoonVineyard2_21_47",
            "sophia_event1",
            "Indoor_Day_0",
            "funLeave_Shane",
        )
    ]
    records.append(
        {
            "sampleId": "daily",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "assets/CharacterFiles/Dialogue/Sophia/Dialogue.json",
            "sourceKey": "Mon",
            "text": "今天还好。",
            "evidenceKind": "dialogue",
        }
    )
    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)

    assert [item["sampleId"] for item in store.style_samples("Sophia", ["SVE"])] == [
        "daily"
    ]
    assert [
        item["sampleId"]
        for item in store.speech_evidence("Sophia", ["SVE"], relationship_stage="stranger")
    ] == ["daily"]


def test_profile_index_filters_relationship_specific_style_samples(
    tmp_path: Path,
) -> None:
    """陌生人不应把婚后对白当作当前口吻，婚后阶段仍可取到它。"""

    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": [
                {
                    "sampleId": "ras:marriage",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Integrated/IntegratedMarriageDialogueWizard.json",
                    "sourceKey": "Good_0",
                    "text": "你给了我新生，我的甜心。",
                    "evidenceKind": "marriage_dialogue",
                    "conditions": {"relationshipStage": "married"},
                },
                {
                    "sampleId": "ras:daily",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "Tue",
                    "text": "如果没有重要的事，请不要打搅我。",
                    "evidenceKind": "dialogue",
                },
            ],
            "speechEvidence": [],
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)

    stranger = store.style_samples(
        "Wizard",
        ["Parrot.RomRas"],
        relationship_stage="stranger",
    )
    married = store.style_samples(
        "Wizard",
        ["Parrot.RomRas"],
        relationship_stage="married",
    )

    assert [item["sampleId"] for item in stranger] == ["ras:daily"]
    assert [item["sampleId"] for item in married] == ["ras:marriage"]


def test_profile_index_prioritizes_topic_related_original_evidence(
    tmp_path: Path,
) -> None:
    """当前问题命中摩托车时，原文证据应先取摩托车而不是音乐对白。"""

    index_path = tmp_path / "profile-index.json"
    samples = [
        {
            "sampleId": "sebastian:music",
            "npcId": "Sebastian",
            "sourceMod": "vanilla",
            "sourceKey": "Mon6",
            "text": "我最近在调试一段音乐，没空参加聚会。",
        },
        {
            "sampleId": "sebastian:motorcycle",
            "npcId": "Sebastian",
            "sourceMod": "vanilla",
            "sourceKey": "Tue6",
            "text": "我的摩托车还没修好，发动机又出了点问题。",
        },
        {
            "sampleId": "sebastian:generic",
            "npcId": "Sebastian",
            "sourceMod": "vanilla",
            "sourceKey": "Wed6",
            "text": "今天没什么特别的。",
        },
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": samples,
            "speechEvidence": samples,
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)
    style = store.style_samples(
        "Sebastian",
        ["vanilla"],
        relationship_stage="friend",
        player_input="你的摩托车修好了吗？",
        limit=2,
    )
    speech = store.speech_evidence(
        "Sebastian",
        ["vanilla"],
        relationship_stage="friend",
        player_input="你的摩托车修好了吗？",
        limit=2,
    )

    assert style[0]["sampleId"] == "sebastian:motorcycle"
    assert speech[0]["sampleId"] == "sebastian:motorcycle"


def test_profile_index_demotes_unrelated_magic_evidence_for_plain_input(
    tmp_path: Path,
) -> None:
    """日常输入时，魔法主题样本不能压过同来源的普通日常样本。"""

    index_path = tmp_path / "profile-index.json"
    samples = [
        {
            "sampleId": "wizard:magic",
            "npcId": "Wizard",
            "sourceMod": "Parrot.RomRas",
            "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
            "sourceKey": "Mon",
            "text": "星界的潮汐今天很平静，魔法也没有异常。",
            "conditions": {"relationshipStage": "friend"},
        },
        {
            "sampleId": "wizard:daily",
            "npcId": "Wizard",
            "sourceMod": "Parrot.RomRas",
            "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
            "sourceKey": "Tue",
            "text": "今天有些累。我会先把手边的书整理好。",
            "conditions": {"relationshipStage": "friend"},
        },
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": samples,
            "speechEvidence": samples,
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)
    for selected in (
        store.style_samples(
            "Wizard",
            ["Romanceable Rasmodius"],
            relationship_stage="friend",
            player_input="你今天看起来有点累。",
            limit=2,
        ),
        store.speech_evidence(
            "Wizard",
            ["Romanceable Rasmodius"],
            relationship_stage="friend",
            player_input="你今天看起来有点累。",
            limit=2,
        ),
    ):
        assert selected[0]["sampleId"] == "wizard:daily"


def test_profile_index_allows_lower_friendship_stage_without_stranger_fallback(
    tmp_path: Path,
) -> None:
    """朋友阶段可复用相识阶段对白，但不能退回无心级初识对白。"""

    index_path = tmp_path / "profile-index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": [
                {
                    "sampleId": "sebastian:stranger",
                    "npcId": "Sebastian",
                    "sourceMod": "vanilla",
                    "sourceKey": "Mon",
                    "text": "初次见面时的寒暄。",
                },
                {
                    "sampleId": "sebastian:acquaintance",
                    "npcId": "Sebastian",
                    "sourceMod": "vanilla",
                    "sourceKey": "Fri2",
                    "text": "我的摩托车还没修好。",
                },
                {
                    "sampleId": "sebastian:friend",
                    "npcId": "Sebastian",
                    "sourceMod": "vanilla",
                    "sourceKey": "Tue6",
                    "text": "今天在听音乐。",
                },
            ],
            "speechEvidence": [],
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).style_samples(
        "Sebastian",
        ["vanilla"],
        relationship_stage="friend",
        player_input="你的摩托车修好了吗？",
        limit=8,
    )

    assert [item["sampleId"] for item in selected] == [
        "sebastian:acquaintance",
        "sebastian:friend",
    ]


def test_profile_index_speech_topic_can_reach_lower_stage_daily_evidence(
    tmp_path: Path,
) -> None:
    """明确话题没有当前阶段原文时，可补充更早阶段的日常话题证据。"""

    index_path = tmp_path / "profile-index.json"
    records = [
        {
            "sampleId": "alex:friend:generic",
            "npcId": "Alex",
            "sourceMod": "vanilla",
            "sourceKey": "Tue6",
            "text": "今天过得不错。",
            "conditions": {"relationshipStage": "friend"},
        },
        {
            "sampleId": "alex:stranger:training",
            "npcId": "Alex",
            "sourceMod": "vanilla",
            "sourceKey": "Mon",
            "text": "我刚做完一组俯卧撑。",
            "conditions": {"relationshipStage": "stranger"},
        },
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).speech_evidence(
        "Alex",
        ["vanilla"],
        relationship_stage="friend",
        player_input="今天训练得怎么样？",
        limit=2,
    )

    assert [item["sampleId"] for item in selected] == [
        "alex:stranger:training",
        "alex:friend:generic",
    ]


def test_profile_index_does_not_relax_stage_for_generic_small_talk(
    tmp_path: Path,
) -> None:
    """没有明确话题时，朋友阶段不能因回退逻辑带入陌生期对白。"""

    index_path = tmp_path / "profile-index.json"
    records = [
        {
            "sampleId": "shane:friend",
            "npcId": "Shane",
            "sourceMod": "vanilla",
            "sourceKey": "Tue6",
            "text": "今天还行。",
            "conditions": {"relationshipStage": "friend"},
        },
        {
            "sampleId": "shane:stranger",
            "npcId": "Shane",
            "sourceMod": "vanilla",
            "sourceKey": "Mon",
            "text": "我不认识你。",
            "conditions": {"relationshipStage": "stranger"},
        },
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).speech_evidence(
        "Shane",
        ["vanilla"],
        relationship_stage="friend",
        player_input="最近怎么样？",
        limit=2,
    )

    assert [item["sampleId"] for item in selected] == ["shane:friend"]


def test_profile_index_topic_match_precedes_unrelated_overlay_introduction(
    tmp_path: Path,
) -> None:
    """明确话题命中时，来源配额不能把无关覆盖层介绍对白顶到前面。"""

    index_path = tmp_path / "profile-index.json"
    records = [
        {
            "sampleId": "ras:introduction",
            "npcId": "Wizard",
            "sourceMod": "Parrot.RomRas",
            "sourcePath": "Dialogue/Standard/Wizard.json",
            "sourceKey": "Introduction",
            "text": "你好，年轻的你。前方还有许多冒险等着你。",
        },
        {
            "sampleId": "vanilla:research",
            "npcId": "Wizard",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Wizard.zh-CN.json",
            "sourceKey": "Wed",
            "text": "研究一门学问需要很多年才能理解它的语言。",
            "conditions": {"relationshipStage": "stranger"},
        },
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).speech_evidence(
        "Wizard",
        ["vanilla", "Romanceable Rasmodius"],
        relationship_stage="friend",
        player_input="早上好，最近研究得怎么样？",
        limit=2,
    )

    assert [item["sampleId"] for item in selected] == [
        "vanilla:research",
        "ras:introduction",
    ]


def test_profile_index_matches_training_example_for_short_synonym(
    tmp_path: Path,
) -> None:
    """玩家说“练哪一项”时，不能因没写出“训练”二字而丢失 Alex 示例。"""

    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)
    store = ProfileIndexStore(output)
    selected = store.behavior_examples(
        "Alex",
        ["vanilla", "female-bachelors"],
        relationship_stage="friend",
        channel="remote",
        player_input="今天练哪一项？",
        limit=4,
    )

    assert selected
    assert selected[0]["topic"] in {"training", "running", "sports"}


@pytest.mark.parametrize(
    ("npc_id", "source_mods", "player_input", "expected_topic"),
    [
        (
            "Sophia",
            ["Stardew Valley Expanded"],
            "今天葡萄园忙不忙？",
            "vineyard",
        ),
        (
            "Shane",
            ["vanilla", "female-bachelors"],
            "鸡舍今天忙吗？",
            "chicken_coop",
        ),
        (
            "Sebastian",
            ["vanilla", "female-bachelors"],
            "最近还骑摩托车出去吗？",
            "motorcycle",
        ),
        (
            "Alex",
            ["vanilla", "female-bachelors"],
            "今天训练得怎么样？",
            "training",
        ),
    ],
)
def test_bundled_behavior_examples_cover_acquaintance_topic(
    tmp_path: Path,
    npc_id: str,
    source_mods: list[str],
    player_input: str,
    expected_topic: str,
) -> None:
    """初识阶段也必须有当前话题示例，不能退回通用问候。"""

    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)

    selected = ProfileIndexStore(output).behavior_examples(
        npc_id,
        source_mods,
        relationship_stage="acquaintance",
        channel="remote",
        player_input=player_input,
        limit=2,
    )

    assert selected
    assert selected[0]["topic"] == expected_topic


@pytest.mark.parametrize(
    ("npc_id", "player_input"),
    [
        ("Abigail", "最近在矿洞里发现什么了吗？"),
        ("Emily", "最近还在做新的衣服吗？"),
        ("Haley", "最近有没有拍到有意思的照片？"),
        ("Leah", "最近还在做雕塑吗？"),
    ],
)
def test_first_normal_vanilla_batch_is_retrievable_by_topic(
    tmp_path: Path,
    npc_id: str,
    player_input: str,
) -> None:
    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)

    selected = ProfileIndexStore(output).behavior_examples(
        npc_id,
        ["vanilla"],
        relationship_stage="friend",
        channel="remote",
        player_input=player_input,
        limit=2,
    )

    assert selected
    assert all(item["npcId"] == npc_id for item in selected)


@pytest.mark.parametrize(
    ("npc_id", "player_input"),
    [
        ("Penny", "最近还在教孩子们读书吗？"),
        ("Maru", "最近有没有做新的发明或实验？"),
        ("Jodi", "最近家里做饭和家务忙不忙？"),
        ("Robin", "最近木工店还有新的建筑工作吗？"),
    ],
)
def test_second_normal_vanilla_batch_is_retrievable_by_topic(
    tmp_path: Path,
    npc_id: str,
    player_input: str,
) -> None:
    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)

    selected = ProfileIndexStore(output).behavior_examples(
        npc_id,
        ["vanilla"],
        relationship_stage="friend",
        channel="remote",
        player_input=player_input,
        limit=2,
    )

    assert selected
    assert all(item["npcId"] == npc_id for item in selected)


@pytest.mark.parametrize(
    ("npc_id", "player_input"),
    [
        ("Clint", "最近铁匠铺的矿石和工具忙不忙？"),
        ("Demetrius", "最近的科学研究有新发现吗？"),
        ("Evelyn", "最近花园和烘焙怎么样？"),
        ("George", "最近生活还习惯吗？"),
        ("Caroline", "最近家里的植物长得怎么样？"),
        ("Marnie", "最近牧场的动物还好吗？"),
        ("Linus", "最近在野外过得怎么样？"),
        ("Gus", "最近酒馆的食物和生意怎么样？"),
        ("Kent", "最近回家以后和家人相处得怎么样？"),
        ("Lewis", "最近小镇的事务和责任忙不忙？"),
        ("Pam", "最近公交和路上的生活还顺利吗？"),
        ("Pierre", "最近商店的经营和生意怎么样？"),
        ("Sandy", "最近沙漠商店和进货怎么样？"),
        ("Willy", "最近钓鱼和海边的生活怎么样？"),
        ("Dwarf", "最近矿洞和矿石交易怎么样？"),
        ("Krobus", "最近下水道的生活和孤独感怎么样？"),
        ("Jas", "最近童年和跳绳玩得怎么样？"),
        ("Vincent", "最近童年和昆虫观察怎么样？"),
    ],
)
def test_normal_vanilla_roles_are_retrievable_by_topic(
    tmp_path: Path,
    npc_id: str,
    player_input: str,
) -> None:
    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)

    selected = ProfileIndexStore(output).behavior_examples(
        npc_id,
        ["vanilla"],
        relationship_stage="friend",
        channel="remote",
        player_input=player_input,
        limit=2,
    )

    assert selected
    assert all(item["npcId"] == npc_id for item in selected)


@pytest.mark.parametrize(
    ("npc_id", "player_input"),
    [
        ("Leo", "最近岛上的生活和鹦鹉怎么样？"),
        ("Gunther", "最近博物馆和文物研究怎么样？"),
        ("Marlon", "最近冒险者公会和矿洞安全吗？"),
        ("Birdie", "最近岛屿生活和手作怎么样？"),
    ],
)
def test_special_vanilla_roles_are_retrievable_by_topic(
    tmp_path: Path,
    npc_id: str,
    player_input: str,
) -> None:
    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)

    selected = ProfileIndexStore(output).behavior_examples(
        npc_id,
        ["vanilla"],
        relationship_stage="friend",
        channel="remote",
        player_input=player_input,
        limit=2,
    )

    assert selected
    assert all(item["npcId"] == npc_id for item in selected)


def test_behavior_examples_ignore_generic_keywords_when_semantic_topic_is_present(
    tmp_path: Path,
) -> None:
    """输入含明确话题时，不应把“今天”命中的问候当成同等候选。"""

    index_path = tmp_path / "profile-index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "behaviorExamples": [
                {
                    "exampleId": "generic-today",
                    "npcId": "Shane",
                    "sourceMods": ["vanilla"],
                    "channels": ["face_to_face"],
                    "relationshipStages": ["acquaintance"],
                    "topic": "daily_status",
                    "topicKeywords": ["今天", "最近"],
                    "playerInput": "今天过得怎么样？",
                    "npcReply": "还行。",
                },
                {
                    "exampleId": "specific-chicken",
                    "npcId": "Shane",
                    "sourceMods": ["vanilla"],
                    "channels": ["face_to_face"],
                    "relationshipStages": ["acquaintance"],
                    "topic": "chicken_coop",
                    "topicKeywords": ["鸡舍", "鸡"],
                    "playerInput": "鸡舍今天忙吗？",
                    "npcReply": "还行。没着火，就算顺利。",
                },
            ],
        },
    )

    selected = ProfileIndexStore(index_path).behavior_examples(
        "Shane",
        ["vanilla"],
        relationship_stage="acquaintance",
        channel="face_to_face",
        player_input="鸡舍今天忙吗？",
        limit=4,
    )

    assert [item["exampleId"] for item in selected] == ["specific-chicken"]


def test_profile_index_prefers_exact_topic_word_over_related_topic_word(
    tmp_path: Path,
) -> None:
    """输入说“葡萄”时，含葡萄的原文应排在只有酒吧的相邻话题之前。"""

    samples = [
        {
            "sampleId": "sophia:bar",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourceKey": "Sat6",
            "text": "要找个时间去酒吧吃点东西吗？",
        },
        {
            "sampleId": "sophia:grape",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourceKey": "Fri2",
            "text": "葡萄园最近有点忙，葡萄藤长得特别快。",
        },
    ]
    index_path = tmp_path / "profile-index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": samples,
            "speechEvidence": samples,
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)
    for selected in (
        store.style_samples(
            "Sophia",
            ["SVE"],
            player_input="新摘的葡萄怎么样？",
            limit=2,
        ),
        store.speech_evidence(
            "Sophia",
            ["SVE"],
            player_input="新摘的葡萄怎么样？",
            limit=2,
        ),
    ):
        assert selected[0]["sampleId"] == "sophia:grape"


def test_profile_index_selects_behavior_examples_by_topic_stage_and_source(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    (persona_dir / "vanilla.json").write_text(
        json.dumps({"mod": "vanilla", "personas": {"Shane": {"npcId": "Shane"}}}),
        encoding="utf-8",
    )
    (persona_dir / "behavior-examples.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "examples": [
                    {
                        "exampleId": "shane:work:friend",
                        "npcId": "Shane",
                        "sourceMods": ["female-bachelors"],
                        "channels": ["face_to_face"],
                        "relationshipStages": ["friend"],
                        "speechFunction": "answer_directly",
                        "topic": "work_pressure",
                        "topicKeywords": ["鸡舍", "工作"],
                        "emotion": "tired_dry_humor",
                        "playerInput": "鸡舍今天忙吗？",
                        "npcReply": "还行。没着火，就算顺利。",
                        "sourceType": "handcrafted_example",
                    },
                    {
                        "exampleId": "shane:weather:stranger",
                        "npcId": "Shane",
                        "sourceMods": ["female-bachelors"],
                        "channels": ["face_to_face"],
                        "relationshipStages": ["stranger"],
                        "speechFunction": "small_talk",
                        "topic": "weather",
                        "topicKeywords": ["天气"],
                        "emotion": "flat",
                        "playerInput": "今天天气怎么样？",
                        "npcReply": "下雨。至少不用浇水。",
                        "sourceType": "handcrafted_example",
                    },
                    {
                        "exampleId": "alex:training:friend",
                        "npcId": "Alex",
                        "sourceMods": ["vanilla"],
                        "channels": ["face_to_face"],
                        "relationshipStages": ["friend"],
                        "speechFunction": "offer_action",
                        "topic": "training",
                        "topicKeywords": ["训练", "跑步"],
                        "emotion": "confident",
                        "playerInput": "今天训练吗？",
                        "npcReply": "当然。跑完这组我再陪你聊。",
                        "sourceType": "handcrafted_example",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)
    store = ProfileIndexStore(output)

    selected = store.behavior_examples(
        "Shane",
        ["female-bachelors"],
        relationship_stage="friend",
        channel="face_to_face",
        player_input="鸡舍今天忙吗？",
        limit=2,
    )

    assert [item["exampleId"] for item in selected] == ["shane:work:friend"]
    assert store.behavior_examples(
        "Shane",
        ["female-bachelors"],
        relationship_stage="friend",
        channel="remote",
        player_input="鸡舍今天忙吗？",
    ) == []
    assert store.behavior_examples(
        "Shane",
        ["female-bachelors"],
        relationship_stage="friend",
        channel="face_to_face",
        player_input="今天训练吗？",
    ) == []


def test_behavior_loader_skips_invalid_and_unapproved_candidates(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    (persona_dir / "vanilla.json").write_text(
        json.dumps({"mod": "vanilla", "personas": {"Shane": {"npcId": "Shane"}}}),
        encoding="utf-8",
    )
    approved = {
        "exampleId": "shane-approved",
        "npcId": "Shane",
        "sourceMods": ["vanilla"],
        "channels": ["face_to_face"],
        "relationshipStages": ["acquaintance"],
        "playerInput": "鸡舍今天忙吗？",
        "npcReply": "还行。没着火，就算顺利。",
        "sourceType": "handcrafted_example",
    }
    approved_generated = {
        **approved,
        "exampleId": "shane-human-approved",
        "sourceType": "human_approved",
    }
    invalid = {**approved, "exampleId": "missing-reply", "npcReply": ""}
    draft = {**approved, "exampleId": "draft-only", "sourceType": "model_draft"}
    unknown = {**approved, "exampleId": "unknown-state", "sourceType": "model_review"}
    (persona_dir / "behavior-examples.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "examples": [approved, approved_generated, invalid, draft, unknown],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    index = ProfileIndexBuilder(persona_dir).build()

    assert [item["exampleId"] for item in index["behaviorExamples"]] == [
        "shane-approved",
        "shane-human-approved",
    ]
    assert any("unapproved behavior example" in warning for warning in index["warnings"])


def test_bundled_behavior_examples_cover_five_evaluation_characters() -> None:
    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    examples = index["behaviorExamples"]
    assert isinstance(examples, list)

    expected_npcs = {"Wizard", "Sophia", "Shane", "Sebastian", "Alex"}
    grouped = {
        npc_id: [item for item in examples if item.get("npcId") == npc_id]
        for npc_id in expected_npcs
    }
    assert set(grouped) == expected_npcs
    assert all(len(items) >= 30 for items in grouped.values())
    assert all(len({item["topic"] for item in items}) >= 10 for items in grouped.values())
    assert all(
        len({item["speechFunction"] for item in items}) >= 6
        for items in grouped.values()
    )
    assert all(
        item.get("sourceType") in {"handcrafted_example", "human_approved"}
        and item.get("playerInput")
        and item.get("npcReply")
        and item.get("topicKeywords")
        and item.get("speechFunction")
        for items in grouped.values()
        for item in items
    )
    assert len({item["npcReply"] for item in examples}) >= len(expected_npcs)
    rendered = json.dumps(examples, ensure_ascii=False).casefold()
    assert "apikey" not in rendered
    assert "token" not in rendered
    assert "cookie" not in rendered
    assert "prompt" not in rendered
    assert not any(item.get("npcId") == "Rasmodia" for item in examples)


@pytest.mark.parametrize(
    ("npc_id", "source_mods", "stage", "channel", "player_input", "example_id", "kind"),
    [
        (
            "Wizard",
            ["Romanceable Rasmodius"],
            "dating",
            "remote",
            "今天没什么要核对的，我只是想你了。你现在方便跟我聊一会儿吗？",
            "wizard:dating:remote-invite:01",
            "specific_plan",
        ),
        (
            "Wizard",
            ["Romanceable Rasmodius"],
            "married",
            "face_to_face",
            "今晚别把时间都给那些记录，留一点给我，好吗？",
            "wizard:married:evening:02",
            "shared_evening",
        ),
        (
            "Sophia",
            ["Stardew Valley Expanded"],
            "dating",
            "face_to_face",
            "你真的给我留了一杯？还是只想让我陪你尝一口呀？",
            "sophia:dating:wine:01",
            "playful_tease",
        ),
        (
            "Sophia",
            ["Stardew Valley Expanded"],
            "married",
            "face_to_face",
            "今天那幅画画完了吗？晚饭后要不要给我看看？",
            "sophia:married:painting:02",
            "creative_share",
        ),
        (
            "Shane",
            ["female-bachelors"],
            "dating",
            "remote",
            "你今天还好吗？要不要我过来陪你吃点东西？",
            "shane:dating:care:01",
            "guarded_care",
        ),
        (
            "Shane",
            ["female-bachelors"],
            "married",
            "face_to_face",
            "今天谁去照看鸡舍？",
            "shane:married:coop:02",
            "guarded_care",
        ),
        (
            "Sebastian",
            ["female-bachelors"],
            "dating",
            "face_to_face",
            "今晚一起听歌吗？",
            "sebastian:dating:music:01",
            "shared_evening",
        ),
        (
            "Sebastian",
            ["female-bachelors"],
            "married",
            "face_to_face",
            "音乐停了，过来靠我近点？",
            "sebastian:married:closeness:02",
            "affection_signal",
        ),
        (
            "Alex",
            ["female-bachelors"],
            "dating",
            "face_to_face",
            "我今天看起来怎么样？",
            "alex:dating:compliment:01",
            "playful_tease",
        ),
        (
            "Alex",
            ["female-bachelors"],
            "married",
            "face_to_face",
            "比赛和晚饭都结束了，陪我出去走走？",
            "alex:married:beach:02",
            "specific_plan",
        ),
    ],
)
def test_bundled_approved_high_stage_examples_preserve_initiative_metadata(
    tmp_path: Path,
    npc_id: str,
    source_mods: list[str],
    stage: str,
    channel: str,
    player_input: str,
    example_id: str,
    kind: str,
) -> None:
    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(ProfileIndexBuilder(persona_dir).build(), output)

    selected = ProfileIndexStore(output).behavior_examples(
        npc_id,
        source_mods,
        relationship_stage=stage,
        channel=channel,
        player_input=player_input,
        limit=4,
    )

    matching = next(item for item in selected if item["exampleId"] == example_id)
    assert matching["sourceType"] == "human_approved"
    assert matching["initiativeExpectation"] == ("guarded" if npc_id == "Shane" else "proactive")
    assert matching["initiativeKind"] == kind


@pytest.mark.parametrize(
    ("npc_id", "player_input", "expected_topic"),
    [
        ("Shane", "鸡舍今天忙吗？", "chicken_coop"),
        ("Sebastian", "最近还骑摩托车出去吗？", "motorcycle"),
    ],
)
def test_generic_bundled_behavior_examples_are_available_in_vanilla_scenarios(
    tmp_path: Path,
    npc_id: str,
    player_input: str,
    expected_topic: str,
) -> None:
    """娘化包中的通用措辞示范也应服务于未启用娘化包的原版场景。"""

    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)

    selected = ProfileIndexStore(output).behavior_examples(
        npc_id,
        ["vanilla"],
        relationship_stage="acquaintance",
        channel="face_to_face" if npc_id == "Shane" else "remote",
        player_input=player_input,
        limit=4,
    )

    assert selected
    assert selected[0]["topic"] == expected_topic


@pytest.mark.parametrize(
    ("npc_id", "source_mods", "player_input"),
    [
        ("Wizard", ["vanilla", "Stardew Valley Expanded", "Parrot.RomRas"], "最近过得怎么样？"),
        ("Sophia", ["Stardew Valley Expanded"], "最近过得怎么样？"),
        ("Shane", ["female-bachelors"], "最近过得怎么样？"),
        ("Sebastian", ["female-bachelors"], "最近过得怎么样？"),
        ("Alex", ["vanilla", "female-bachelors"], "最近过得怎么样？"),
    ],
)
def test_bundled_behavior_examples_have_multiple_matches_for_common_input(
    tmp_path: Path,
    npc_id: str,
    source_mods: list[str],
    player_input: str,
) -> None:
    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)
    store = ProfileIndexStore(output)

    selected = store.behavior_examples(
        npc_id,
        source_mods,
        relationship_stage="friend",
        channel="remote",
        player_input=player_input,
        limit=4,
    )

    assert len(selected) >= 2
    assert all(item["npcId"] == "Wizard" if npc_id == "Rasmodia" else item["npcId"] == npc_id for item in selected)


@pytest.mark.parametrize(
    ("npc_id", "source_mods", "player_input", "expected_topic"),
    [
        (
            "Wizard",
            ["Romanceable Rasmodius"],
            "那第三组现在稳定了吗？",
            "research_result",
        ),
        (
            "Sebastian",
            ["vanilla", "female-bachelors"],
            "那段代码后来修好了吗？",
            "debugging",
        ),
        (
            "Alex",
            ["vanilla", "female-bachelors"],
            "下次一起练练？",
            "remote_invitation",
        ),
    ],
)
def test_bundled_behavior_examples_prioritize_concrete_follow_up_phrases(
    tmp_path: Path,
    npc_id: str,
    source_mods: list[str],
    player_input: str,
    expected_topic: str,
) -> None:
    """连续追问或邀约中的具体短语应压过相邻的泛话题示例。"""

    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)

    selected = ProfileIndexStore(output).behavior_examples(
        npc_id,
        source_mods,
        relationship_stage="friend",
        channel="face_to_face" if npc_id != "Alex" else "remote",
        player_input=player_input,
        limit=4,
    )

    assert selected
    assert selected[0]["topic"] == expected_topic


def test_bundled_behavior_examples_prioritize_invitation_phrase_over_shared_object(
    tmp_path: Path,
) -> None:
    """邀约中的共同短语应压过因“记录”命中的整理工作示例。"""

    persona_dir = Path(__file__).resolve().parents[2] / "data" / "personas"
    index = ProfileIndexBuilder(persona_dir).build()
    output = tmp_path / "profile-index.json"
    ProfileIndexBuilder.write(index, output)

    selected = ProfileIndexStore(output).behavior_examples(
        "Wizard",
        ["Romanceable Rasmodius"],
        relationship_stage="friend",
        channel="remote",
        player_input="改天一起核对一下记录？",
        limit=4,
    )

    assert selected
    assert selected[0]["topic"] == "invitation"


def test_profile_index_uses_vanilla_daily_rhythm_when_overlay_only_has_seasonal_lines(
    tmp_path: Path,
) -> None:
    """覆盖层缺少平日键时，原版 Mon/Tue 应压过覆盖层季节独白。"""

    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": [
                {
                    "sampleId": "ras:seasonal-overlay",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "spring_Mon",
                    "text": "星界的潮汐在春日变得格外清晰。",
                },
                {
                    "sampleId": "vanilla:weekday",
                    "npcId": "Wizard",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Wizard.zh-CN.json",
                    "sourceKey": "Mon",
                    "text": "如果没有重要的事，请不要打搅我。",
                },
            ],
            "speechEvidence": [],
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).style_samples(
        "Wizard",
        ["Parrot.RomRas"],
        relationship_stage="stranger",
        limit=2,
    )

    # 季节覆盖层不应进入稳定语气窗口；这里的目标是保留原版日常节奏，
    # 而不是在没有对应季节状态时把季节台词当成普通说话方式。
    assert [item["sampleId"] for item in selected] == ["vanilla:weekday"]


def test_profile_index_filters_high_friendship_variants_for_strangers(
    tmp_path: Path,
) -> None:
    """陌生人阶段只使用无心级后缀的 Mon/Tue，不喂高好感对白。"""

    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": [
                {
                    "sampleId": "vanilla:mon8",
                    "npcId": "Wizard",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Wizard.zh-CN.json",
                    "sourceKey": "Mon8",
                    "text": "魔法在那里欣欣向荣……",
                },
                {
                    "sampleId": "vanilla:tue",
                    "npcId": "Wizard",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Wizard.zh-CN.json",
                    "sourceKey": "Tue",
                    "text": "如果没有重要的事，请不要打搅我。",
                },
                {
                    "sampleId": "vanilla:mon",
                    "npcId": "Wizard",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Wizard.zh-CN.json",
                    "sourceKey": "Mon",
                    "text": "关于你的未来，我看到了很多事啊。",
                },
                {
                    "sampleId": "vanilla:tue10",
                    "npcId": "Wizard",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Wizard.zh-CN.json",
                    "sourceKey": "Tue10",
                    "text": "假如现实是由意识产生的……",
                },
            ],
            "speechEvidence": [],
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).style_samples(
        "Wizard",
        ["Parrot.RomRas"],
        relationship_stage="stranger",
        limit=4,
    )

    assert [item["sourceKey"] for item in selected] == ["Tue", "Mon"]


def test_profile_store_uses_dialogue_key_heart_stage_when_conditions_are_missing(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": [
                    {
                        "sampleId": f"shane-{key}",
                        "npcId": "Shane",
                        "sourceMod": "vanilla",
                        "sourcePath": "Characters/Dialogue/Shane.zh-CN.json",
                        "sourceKey": key,
                        "text": f"{key} 台词",
                    }
                    for key in ("Mon", "Mon2", "Mon4", "Mon6", "Mon8", "Mon10")
                ],
                "speechEvidence": [],
                "voiceCards": {},
                "storyEvents": [],
                "knowledgeFacts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = ProfileIndexStore(index_path)
    friend_keys = {
        item["sourceKey"]
        for item in store.style_samples(
            "Shane", ["vanilla"], relationship_stage="friend", limit=8
        )
    }
    stranger_keys = {
        item["sourceKey"]
        for item in store.style_samples(
            "Shane", ["vanilla"], relationship_stage="stranger", limit=8
        )
    }

    assert "Mon" not in friend_keys
    assert friend_keys & {"Mon6", "Mon8", "Mon10"}
    assert stranger_keys == {"Mon"}


def test_profile_index_prefers_stage_specific_daily_samples_over_generic_special_lines(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "styleSamples": [
                    {
                        "sampleId": "gift",
                        "npcId": "Shane",
                        "sourceMod": "vanilla",
                        "sourceKey": "AcceptBirthdayGift_Loved",
                        "text": "谢谢你的生日礼物。",
                    },
                    {
                        "sampleId": "friend-mon",
                        "npcId": "Shane",
                        "sourceMod": "vanilla",
                        "sourceKey": "Mon6",
                        "text": "说实话，我还是不太理解为什么你要和我交朋友。",
                        "conditions": {"relationshipStage": "friend"},
                    },
                    {
                        "sampleId": "friend-tue",
                        "npcId": "Shane",
                        "sourceMod": "vanilla",
                        "sourceKey": "Tue6",
                        "text": "生活也没那么糟嘛……至少还有冷披萨和鸡蛋可吃。",
                        "conditions": {"relationshipStage": "friend"},
                    },
                ],
                "speechEvidence": [],
                "profiles": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    samples = ProfileIndexStore(index_path).style_samples(
        "Shane",
        ["vanilla"],
        relationship_stage="friend",
        limit=2,
    )

    assert [item["sourceKey"] for item in samples] == ["Mon6", "Tue6"]


def test_profile_builder_excludes_special_static_lines_from_model_evidence(
    tmp_path: Path,
) -> None:
    corpus_path = tmp_path / "corpus.json"
    _write_json(
        corpus_path,
        {
            "schemaVersion": 1,
            "records": [
                {
                    "sampleId": "daily",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "Mon",
                    "text": "今天还好。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "separator",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "Tue",
                    "text": "{{Random:今天还好。}}inputSeparator=@@}}",
                    "dialogueVariants": ["inputSeparator=@@}}"],
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "seasonal",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "spring_Mon",
                    "text": "春天的特殊独白。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "gift",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/UCR.json",
                    "sourceKey": "AcceptBirthdayGift_Loved",
                    "text": "谢谢你的生日礼物。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "event",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/FestivalDialogue.json",
                    "sourceKey": "event_speakof2",
                    "text": "节日里的特殊发言。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "event-capitalized",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "Event_Mine_1",
                    "text": "矿洞事件里的特殊发言。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "relationship-scene",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "MovieInvitation",
                    "text": "邀请看电影的特殊发言。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "spouse-scene",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "SpouseFarmhouseClutter",
                    "text": "配偶场景里的特殊发言。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "relation-response",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "Good_2",
                    "text": "这是一句礼物关系响应。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "married",
                    "npcId": "Wizard",
                    "sourceMod": "Parrot.RomRas",
                    "sourcePath": "assets/Dialogue/Standard/StandardMarriageDialogueWizard.json",
                    "sourceKey": "Rain",
                    "text": "婚后下雨时的一句对白。",
                    "evidenceKind": "marriage_dialogue",
                    "conditions": {"relationshipStage": "married"},
                },
            ],
        },
    )

    index = ProfileIndexBuilder(tmp_path / "personas").build(
        corpus_paths=[corpus_path]
    )

    assert [item["sourceKey"] for item in index["styleSamples"]] == [
        "Mon",
        "Rain",
    ]
    assert [item["sourceKey"] for item in index["speechEvidence"]] == [
        "Mon",
        "Rain",
    ]


def test_profile_builder_never_falls_back_to_control_only_dialogue(
    tmp_path: Path,
) -> None:
    corpus_path = tmp_path / "corpus.json"
    _write_json(
        corpus_path,
        {
            "schemaVersion": 1,
            "records": [
                {
                    "sampleId": "narration",
                    "npcId": "Haley",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Haley.zh-CN.json",
                    "sourceKey": "Fri",
                    "text": "%海莉没有理你。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "dollar",
                    "npcId": "Wizard",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Wizard.zh-CN.json",
                    "sourceKey": "Tue",
                    "text": "$",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "action",
                    "npcId": "Shane",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Shane.zh-CN.json",
                    "sourceKey": "Wed",
                    "text": "*唉*……今天还得上班。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "inline-narration",
                    "npcId": "Sophia",
                    "sourceMod": "SVE",
                    "sourcePath": "assets/CharacterFiles/Dialogue/Sophia/Dialogue.json",
                    "sourceKey": "Mon2",
                    "text": "…… %索菲娅没有理你。她看起来很伤心。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "parenthetical-action",
                    "npcId": "Alex",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Alex.zh-CN.json",
                    "sourceKey": "Wed",
                    "text": "（愤怒）你到底是什么意思？",
                    "evidenceKind": "dialogue",
                },
            ],
        },
    )

    index = ProfileIndexBuilder(tmp_path / "personas").build(
        corpus_paths=[corpus_path]
    )

    assert [item["npcId"] for item in index["styleSamples"]] == ["Shane"]
    assert index["styleSamples"][0]["text"] == "……今天还得上班。"
    assert [item["npcId"] for item in index["speechEvidence"]] == ["Shane"]


def test_profile_index_drops_inline_narration_and_parenthetical_actions_from_old_indexes(
    tmp_path: Path,
) -> None:
    records = [
        {
            "sampleId": "good",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "Dialogue/Standard/Sophia.json",
            "sourceKey": "Mon",
            "text": "呃……你好。",
        },
        {
            "sampleId": "inline-narration",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "Dialogue/Standard/Sophia.json",
            "sourceKey": "Mon2",
            "text": "…… %索菲娅没有理你。她看起来很伤心。",
        },
        {
            "sampleId": "parenthetical-action",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "Dialogue/Standard/Sophia.json",
            "sourceKey": "Tue",
            "text": "（愤怒）你到底是什么意思？",
        },
    ]
    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)

    assert [item["sampleId"] for item in store.style_samples("Sophia", ["SVE"])] == [
        "good"
    ]
    assert [
        item["sampleId"] for item in store.speech_evidence("Sophia", ["SVE"])
    ] == ["good"]


def test_dialogue_reference_drops_control_residue_from_browser_review_data(
    tmp_path: Path,
) -> None:
    """原文参照页也不能把旧索引中的旁白和动作残渣展示给用户。"""

    index_path = tmp_path / "index.json"
    records = [
        {
            "sampleId": "good",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "Dialogue/Standard/Sophia.json",
            "sourceKey": "Mon",
            "text": "呃……你好。",
        },
        {
            "sampleId": "inline-narration",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "Dialogue/Standard/Sophia.json",
            "sourceKey": "Mon2",
            "text": "…… %索菲娅没有理你。她看起来很伤心。",
        },
        {
            "sampleId": "parenthetical-action",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "Dialogue/Standard/Sophia.json",
            "sourceKey": "Tue",
            "text": "（愤怒）你到底是什么意思？",
        },
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    reference = ProfileIndexStore(index_path).dialogue_reference("Sophia")

    assert reference["total"] == 1
    assert [item["sampleId"] for item in reference["dialogues"]] == ["good"]
    assert [item["sampleId"] for item in reference["representatives"]] == ["good"]


def test_profile_index_deduplicates_same_text_before_source_reservation(
    tmp_path: Path,
) -> None:
    records = [
        {
            "sampleId": "ras:introduction:integrated",
            "npcId": "Wizard",
            "sourceMod": "Parrot.RomRas",
            "sourcePath": "Dialogue/Integrated/Wizard.json",
            "sourceKey": "Introduction",
            "text": "你好，年轻的你。",
        },
        {
            "sampleId": "ras:introduction:standard",
            "npcId": "Wizard",
            "sourceMod": "Parrot.RomRas",
            "sourcePath": "Dialogue/Standard/Wizard.json",
            "sourceKey": "Introduction",
            "text": "你好，年轻的你。",
        },
        {
            "sampleId": "vanilla:daily",
            "npcId": "Wizard",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Wizard.zh-CN.json",
            "sourceKey": "Tue6",
            "text": "今天塔里还算安静。",
            "conditions": {"relationshipStage": "friend"},
        },
    ]
    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).style_samples(
        "Wizard",
        ["Romanceable Rasmodius"],
        relationship_stage="friend",
        player_input="最近怎么样？",
        limit=3,
    )

    texts = [item["text"] for item in selected]
    assert len(texts) == len(set(texts))


def test_profile_index_does_not_put_overlay_introduction_before_stage_daily_for_small_talk(
    tmp_path: Path,
) -> None:
    records = [
        {
            "sampleId": "ras:introduction",
            "npcId": "Wizard",
            "sourceMod": "Parrot.RomRas",
            "sourcePath": "Dialogue/Standard/Wizard.json",
            "sourceKey": "Introduction",
            "text": "你好，年轻的你。前方还有许多冒险等着你。",
        },
        {
            "sampleId": "vanilla:daily",
            "npcId": "Wizard",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Wizard.zh-CN.json",
            "sourceKey": "Tue6",
            "text": "今天塔里还算安静。",
            "conditions": {"relationshipStage": "friend"},
        },
    ]
    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).style_samples(
        "Wizard",
        ["Romanceable Rasmodius"],
        relationship_stage="friend",
        player_input="最近怎么样？",
        limit=2,
    )

    assert selected[0]["sampleId"] == "vanilla:daily"


def test_profile_index_matches_alex_specific_sports_terms_and_sophia_vineyard(
    tmp_path: Path,
) -> None:
    samples = [
        {
            "sampleId": "alex:generic",
            "npcId": "Alex",
            "sourceMod": "vanilla",
            "sourceKey": "Mon",
            "text": "今天过得不错。",
        },
        {
            "sampleId": "alex:pushups",
            "npcId": "Alex",
            "sourceMod": "vanilla",
            "sourceKey": "Tue",
            "text": "我刚做完一组俯卧撑。",
        },
        {
            "sampleId": "sophia:greeting",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourceKey": "Mon",
            "text": "今天还好吗？",
        },
        {
            "sampleId": "sophia:vineyard",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourceKey": "Tue",
            "text": "葡萄园今天很忙，葡萄藤需要重新固定。",
        },
    ]
    index_path = tmp_path / "profile-index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": samples,
            "speechEvidence": samples,
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)
    alex = store.style_samples(
        "Alex", ["vanilla"], player_input="今天做了几组俯卧撑？", limit=2
    )
    sophia = store.speech_evidence(
        "Sophia", ["SVE"], player_input="葡萄园最近忙不忙？", limit=2
    )

    assert alex[0]["sampleId"] == "alex:pushups"
    assert sophia[0]["sampleId"] == "sophia:vineyard"


def test_profile_builder_excludes_progress_and_location_triggered_lines_from_model_evidence(
    tmp_path: Path,
) -> None:
    """未满足游戏触发条件的进度/地点对白不能充当通用角色语气。"""

    corpus_path = tmp_path / "corpus.json"
    triggered_keys = (
        "GreenRain",
        "Resort",
        "cc_Bridge",
        "cropMatured_398",
        "firstVisit_Railroad",
        "fishCaught_159",
        "purchasedAnimal_Chicken_memory_oneday",
        "achievement_15",
        "AnimalShop_30_16",
        "Custom_SophiaHouse_10_25",
    )
    _write_json(
        corpus_path,
        {
            "schemaVersion": 1,
            "records": [
                {
                    "sampleId": "daily",
                    "npcId": "Wizard",
                    "sourceMod": "vanilla",
                    "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                    "sourceKey": "Tue",
                    "text": "今天还好。",
                    "evidenceKind": "dialogue",
                },
                *[
                    {
                        "sampleId": f"triggered-{key}",
                        "npcId": "Wizard",
                        "sourceMod": "vanilla",
                        "sourcePath": "assets/Dialogue/Standard/StandardDialogueWizard.json",
                        "sourceKey": key,
                        "text": f"{key} 触发时才会说。",
                        "evidenceKind": "dialogue",
                    }
                    for key in triggered_keys
                ],
            ],
        },
    )

    index = ProfileIndexBuilder(tmp_path / "personas").build(
        corpus_paths=[corpus_path]
    )

    for field in ("styleSamples", "speechEvidence"):
        assert [item["sourceKey"] for item in index[field]] == ["Tue"]


def test_profile_index_dialogue_reference_keeps_all_provenance_and_curates_daily_examples(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": [],
            "speechEvidence": [
                {
                    "sampleId": "event",
                    "npcId": "Wizard",
                    "sourceMod": "SVE",
                    "sourcePath": "Events/Wizard.json",
                    "sourceKey": "event_1",
                    "text": "事件中的原始对白。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "daily-vanilla",
                    "npcId": "Wizard",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Wizard.json",
                    "sourceKey": "Mon",
                    "text": "原版日常对白。",
                    "evidenceKind": "dialogue",
                    "conditions": {"relationshipStage": "friend"},
                },
                {
                    "sampleId": "daily-sve",
                    "npcId": "Wizard",
                    "sourceMod": "SVE",
                    "sourcePath": "Dialogue/Standard/Wizard.json",
                    "sourceKey": "Tue",
                    "text": "覆盖层日常对白。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "triggered",
                    "npcId": "Wizard",
                    "sourceMod": "SVE",
                    "sourcePath": "Dialogue/Standard/Wizard.json",
                    "sourceKey": "pamHouseUpgrade",
                    "text": "特殊触发对白。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "introduction",
                    "npcId": "Wizard",
                    "sourceMod": "vanilla",
                    "sourcePath": "Characters/Dialogue/Wizard.json",
                    "sourceKey": "Introduction",
                    "text": "初次介绍对白。",
                    "evidenceKind": "dialogue",
                },
                {
                    "sampleId": "other-npc",
                    "npcId": "Sophia",
                    "sourceMod": "SVE",
                    "sourcePath": "Dialogue/Standard/Sophia.json",
                    "sourceKey": "Mon",
                    "text": "不应混入。",
                    "evidenceKind": "dialogue",
                },
            ],
            "voiceCards": {},
            "storyEvents": [],
            "knowledgeFacts": [],
            "behaviorExamples": [],
            "warnings": [],
        },
    )

    reference = ProfileIndexStore(index_path).dialogue_reference(
        "Rasmodia", representative_limit=3
    )

    assert reference["npcId"] == "Wizard"
    assert reference["total"] == 5
    assert [item["sampleId"] for item in reference["dialogues"]] == [
        "event",
        "daily-vanilla",
        "daily-sve",
        "triggered",
        "introduction",
    ]
    assert [item["sampleId"] for item in reference["representatives"]] == [
        "daily-vanilla",
        "introduction",
        "daily-sve",
    ]
    assert reference["dialogues"][1]["conditions"] == {
        "relationshipStage": "friend"
    }


def test_profile_index_dialogue_reference_does_not_pin_special_lines_over_daily_lines(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "index.json"
    daily_records = [
        {
            "sampleId": f"daily-{key}",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "Dialogue/Standard/Sophia.json",
            "sourceKey": key,
            "text": f"日常对白 {key}。",
            "evidenceKind": "dialogue",
        }
        for key in ("Mon", "Mon2", "Tue", "Tue4", "Wed", "Thu", "Fri", "Sat", "Sun")
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": [],
            "speechEvidence": [
                {
                    "sampleId": "special",
                    "npcId": "Sophia",
                    "sourceMod": "SVE",
                    "sourcePath": "Dialogue/Standard/Sophia.json",
                    "sourceKey": "pamHouseUpgrade",
                    "text": "特殊触发对白。",
                    "evidenceKind": "dialogue",
                },
                *daily_records,
            ],
            "voiceCards": {},
            "storyEvents": [],
            "knowledgeFacts": [],
            "behaviorExamples": [],
            "warnings": [],
        },
    )

    reference = ProfileIndexStore(index_path).dialogue_reference(
        "Sophia", representative_limit=8
    )

    representative_ids = {
        item["sampleId"] for item in reference["representatives"]
    }
    assert "special" not in representative_ids
    assert len(representative_ids) == 8


def test_profile_index_store_cleans_single_letter_residue_from_existing_index(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": [],
            "speechEvidence": [
                {
                    "sampleId": "alex-noise",
                    "npcId": "Alex",
                    "sourceMod": "vanilla",
                    "sourceKey": "Mon",
                    "text": "海滩真的是个很酷的地方。 e 你得多晒晒太阳。",
                    "evidenceKind": "dialogue",
                    "conditions": {"relationshipStage": "acquaintance"},
                }
            ],
            "voiceCards": {},
            "storyEvents": [],
            "knowledgeFacts": [],
            "behaviorExamples": [],
            "warnings": [],
        },
    )

    evidence = ProfileIndexStore(index_path).speech_evidence(
        "Alex",
        ["vanilla"],
        relationship_stage="acquaintance",
        player_input="海滩怎么样？",
    )

    assert evidence[0]["text"] == "海滩真的是个很酷的地方。你得多晒晒太阳。"


def test_profile_index_dialogue_reference_pins_more_broadly_across_categories_sources_and_stages(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "index.json"
    source_paths = {
        "vanilla": "Characters/Dialogue/Wizard.json",
        "SVE": "Dialogue/Standard/Wizard.json",
        "RomRas": "Dialogue/Integrated/Wizard.json",
    }
    stage_by_key = {
        "Mon": "stranger",
        "Tue": "acquaintance",
        "Mon2": "acquaintance",
        "Tue4": "friend",
        "Wed6": "close",
        "Thu8": "close",
        "Fri10": "friend",
    }
    keys = (
        "Introduction",
        "Mon",
        "Tue",
        "Mon2",
        "Tue4",
        "Wed6",
        "Thu8",
        "Fri10",
        "Thu",
        "Fri",
        "Sat",
        "Sun",
    )
    records = []
    for source_mod, source_path in source_paths.items():
        for key in keys:
            record = {
                "sampleId": f"{source_mod}-{key}",
                "npcId": "Wizard",
                "sourceMod": source_mod,
                "sourcePath": source_path,
                "sourceKey": key,
                "text": f"{source_mod} 的 {key} 代表对白。",
                "evidenceKind": "dialogue",
            }
            if key in stage_by_key:
                record["conditions"] = {
                    "relationshipStage": stage_by_key[key]
                }
            records.append(record)
    records.append(
        {
            "sampleId": "special",
            "npcId": "Wizard",
            "sourceMod": "SVE",
            "sourcePath": "Dialogue/Standard/Wizard.json",
            "sourceKey": "pamHouseUpgrade",
            "text": "特殊触发对白。",
            "evidenceKind": "dialogue",
        }
    )
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": [],
            "speechEvidence": records,
            "voiceCards": {},
            "storyEvents": [],
            "knowledgeFacts": [],
            "behaviorExamples": [],
            "warnings": [],
        },
    )

    reference = ProfileIndexStore(index_path).dialogue_reference("Rasmodia")

    representatives = reference["representatives"]
    assert len(representatives) == 16
    assert "special" not in {item["sampleId"] for item in representatives}
    assert {item["sourceMod"] for item in representatives} >= {
        "vanilla",
        "SVE",
        "RomRas",
    }
    assert {
        item["conditions"]["relationshipStage"]
        for item in representatives
        if "conditions" in item
    } >= {"stranger", "acquaintance", "friend", "close"}
    assert {item["sourceKey"] for item in representatives} >= {
        "Introduction",
        "Mon",
        "Mon2",
    }


def test_profile_index_npc_catalog_merges_profiles_and_evidence_without_alias_duplicate(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {
                "Caroline": {
                    "npcId": "Caroline",
                    "displayName": "Caroline",
                    "sourceMods": ["vanilla"],
                },
                "Rasmodia": {
                    "npcId": "Rasmodia",
                    "displayName": "Rasmodia",
                    "sourceMods": ["Romanceable Rasmodius"],
                },
            },
            "styleSamples": [
                {
                    "sampleId": "caroline-daily",
                    "npcId": "Caroline",
                    "sourceMod": "vanilla",
                    "text": "花园今天很安静。",
                },
                {
                    "sampleId": "wizard-daily",
                    "npcId": "Wizard",
                    "sourceMod": "vanilla",
                    "text": "嗯。",
                },
            ],
            "speechEvidence": [],
            "voiceCards": {},
        },
    )

    catalog = ProfileIndexStore(index_path).npc_catalog()

    by_id = {item["npcId"]: item for item in catalog}
    assert "Caroline" in by_id
    assert "Wizard" in by_id
    assert "Rasmodia" not in by_id
    assert by_id["Caroline"]["hasDialogueEvidence"] is True
    assert by_id["Caroline"]["sourceMods"] == ["vanilla"]


def test_profile_index_builder_loads_biography_known_characters_and_story_events(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {
            "mod": "vanilla",
            "personas": {
                "Caroline": {
                    "displayName": "Caroline",
                    "biography": [
                        {
                            "factId": "caroline-garden",
                            "summary": "她照料温室和花园。",
                            "knowledgeScope": "canon_confirmed",
                            "sourceRefs": ["Characters/Dialogue/Caroline"],
                        }
                    ],
                    "knownCharacters": [
                        {
                            "knownNpcId": "Marnie",
                            "relation": "镇上的熟人",
                            "summary": "她知道 Marnie 经营牧场。",
                            "knowledgeScope": "canon_confirmed",
                            "sourceRefs": ["Characters/Dialogue/Caroline"],
                        }
                    ],
                    "storyEvents": [
                        {
                            "eventId": "vanilla:caroline-garden",
                            "sourceKey": "caroline-garden",
                            "participants": ["Caroline", "player"],
                            "summary": "玩家帮助 Caroline 整理花园。",
                            "canonical": True,
                            "requiredEventId": "vanilla:caroline-garden",
                        }
                    ],
                }
            },
        },
    )

    index = ProfileIndexBuilder(persona_dir).build()

    assert index["knowledgeFacts"][0]["factId"] == "caroline-garden"
    assert index["knowledgeFacts"][0]["npcId"] == "Caroline"
    assert index["knownCharacters"][0]["npcId"] == "Caroline"
    assert index["knownCharacters"][0]["knownNpcId"] == "Marnie"
    assert index["storyEvents"][0]["eventId"] == "vanilla:caroline-garden"


def test_profile_index_builder_merges_vanilla_event_provenance(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {"Sebastian": {"displayName": "Sebastian"}}},
    )
    events_root = tmp_path / "Data" / "Events"
    _write_json(
        events_root / "Mountain.zh-CN.json",
        {
            "384882/f Sebastian 2500/t 2000 2400": (
                "speak Sebastian \"上来，我带你去山上。\""
            )
        },
    )

    index = ProfileIndexBuilder(persona_dir).build(
        vanilla_events_root=events_root,
        vanilla_locale="zh-CN",
    )

    event = next(
        item
        for item in index["speechEvidence"]
        if item.get("eventId") == "384882"
    )
    assert event["evidenceKind"] == "event_dialogue"
    assert event["eventConditions"]["raw"].startswith("384882/")
    assert event["participants"] == ["Sebastian"]
    assert event["eventLineIndex"] == 1


def test_repository_personas_include_structured_facts_for_friendship_npcs() -> None:
    persona_dir = Path(__file__).parents[2] / "data" / "personas"

    index = ProfileIndexBuilder(persona_dir).build()

    fact_npcs = {
        item["npcId"]
        for item in index["knowledgeFacts"]
        if isinstance(item, dict) and item.get("npcId")
    }
    relation_owners = {
        item["npcId"]
        for item in index["knownCharacters"]
        if isinstance(item, dict) and item.get("npcId")
    }

    assert {
        "Wizard",
        "Shane",
        "Sophia",
        "Sebastian",
        "Alex",
        "Caroline",
        "Marnie",
        "Linus",
    } <= fact_npcs
    assert {"Shane", "Sebastian", "Alex", "Caroline", "Marnie"} <= relation_owners


def test_elliott_overlay_keeps_vanilla_daily_voice_and_source_provenance(
    tmp_path: Path,
) -> None:
    """female-bachelors 婚后对白不能吞掉 Elliott 的原版日常语气证据。"""

    index_path = tmp_path / "profile-index.json"
    vanilla_daily = {
        "sampleId": "vanilla:elliott:Mon",
        "npcId": "Elliott",
        "sourceMod": "vanilla",
        "sourcePath": "Characters/Dialogue/Elliott.json",
        "sourceKey": "Mon",
        "text": "我今天还在改那份未完成的稿子。",
        "evidenceKind": "dialogue",
    }
    vanilla_beach = {
        "sampleId": "vanilla:elliott:Tue",
        "npcId": "Elliott",
        "sourceMod": "vanilla",
        "sourcePath": "Characters/Dialogue/Elliott.json",
        "sourceKey": "Tue",
        "text": "海风很适合让人暂时放下手里的稿子。",
        "evidenceKind": "dialogue",
    }
    unrelated_overlay = {
        "sampleId": "female-bachelors:elliott:OneKid_3",
        "npcId": "Elliott",
        "sourceMod": "female-bachelors",
        "sourcePath": "Characters/Dialogue/Elliott.json",
        "sourceKey": "OneKid_3",
        "text": "孩子今天睡得很早，屋里终于安静了。",
        "evidenceKind": "marriage_dialogue",
        "conditions": {"relationshipStage": "married"},
    }
    unrelated_overlay_2 = {
        "sampleId": "female-bachelors:elliott:TwoKids_1",
        "npcId": "Elliott",
        "sourceMod": "female-bachelors",
        "sourcePath": "Characters/Dialogue/Elliott.json",
        "sourceKey": "TwoKids_1",
        "text": "我得先把孩子们安顿好，晚点再说。",
        "evidenceKind": "marriage_dialogue",
        "conditions": {"relationshipStage": "married"},
    }
    records = [vanilla_daily, vanilla_beach, unrelated_overlay, unrelated_overlay_2]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {
                "Elliott": {
                    "npcId": "Elliott",
                    "sourceMods": ["vanilla", "female-bachelors"],
                    "overlays": {"female-bachelors": {"layer": "expression_only"}},
                }
            },
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    store = ProfileIndexStore(index_path)
    for selected in (
        store.style_samples(
            "Elliott",
            ["vanilla", "female-bachelors"],
            relationship_stage="married",
            player_input="未完成的稿子",
            limit=4,
        ),
        store.speech_evidence(
            "Elliott",
            ["vanilla", "female-bachelors"],
            relationship_stage="married",
            player_input="未完成的稿子",
            limit=4,
        ),
    ):
        selected_ids = {item["sampleId"] for item in selected}
        selected_sources = {item["sourceMod"] for item in selected}
        assert "vanilla:elliott:Mon" in selected_ids
        assert "vanilla:elliott:Tue" in selected_ids
        assert selected_sources == {"vanilla", "female-bachelors"}
        assert all(
            item.get("sampleId")
            and item.get("sourceMod")
            and item.get("sourceKey")
            for item in selected
        )


def test_vanilla_marriage_dialogue_is_canonicalized_as_married_evidence(
    tmp_path: Path,
) -> None:
    vanilla_root = tmp_path / "vanilla"
    dialogue_path = vanilla_root / "Characters" / "Dialogue" / "MarriageDialogueElliott.zh-CN.json"
    _write_json(
        dialogue_path,
        {
            "Rainy_Day_1": "雨声让我想起海边的小屋。今天没有灵感。",
            "Good_2": "我本来是来寻找象牙塔的，却找到了你。",
        },
    )

    index = ProfileIndexBuilder(tmp_path / "personas").build(
        vanilla_root=vanilla_root,
        vanilla_locale="zh-CN",
    )

    records = [
        item
        for item in index["speechEvidence"]
        if isinstance(item, dict) and item.get("sourcePath") == "Characters/Dialogue/MarriageDialogueElliott.zh-CN.json"
    ]

    assert canonical_npc_id("MarriageDialogueElliott") == "Elliott"
    assert records
    assert {item["npcId"] for item in records} == {"Elliott"}
    assert {item["evidenceKind"] for item in records} == {"marriage_dialogue"}
    assert {
        item["conditions"]["relationshipStage"]
        for item in records
        if isinstance(item.get("conditions"), dict)
    } == {"married"}


def test_married_elliott_speech_evidence_prefers_vanilla_marriage_samples(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    marriage = {
        "sampleId": "vanilla:marriage:Rainy_Day_1",
        "npcId": "MarriageDialogueElliott",
        "sourceMod": "vanilla",
        "sourcePath": "Characters/Dialogue/MarriageDialogueElliott.zh-CN.json",
        "sourceKey": "Rainy_Day_1",
        "text": "雨声让我想起海边的小屋。",
        "evidenceKind": "marriage_dialogue",
        "conditions": {"relationshipStage": "married"},
    }
    daily = {
        "sampleId": "vanilla:daily:Mon",
        "npcId": "Elliott",
        "sourceMod": "vanilla",
        "sourcePath": "Characters/Dialogue/Elliott.zh-CN.json",
        "sourceKey": "Mon",
        "text": "纸与笔的声音让我安静下来。",
        "evidenceKind": "dialogue",
    }
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": [marriage, daily],
            "speechEvidence": [marriage, daily],
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).speech_evidence(
        "Elliott",
        ["vanilla"],
        relationship_stage="married",
        limit=2,
    )

    assert selected
    assert selected[0]["npcId"] == "Elliott"
    assert selected[0]["evidenceKind"] == "marriage_dialogue"
    assert selected[0]["conditions"] == {"relationshipStage": "married"}


def test_vanilla_plain_marriage_dialogue_is_canonicalized_with_married_provenance(
    tmp_path: Path,
) -> None:
    """MarriageDialogueElliott 文件不能作为一个伪 NPC 或普通日常语料进入索引。"""

    vanilla_root = tmp_path / "vanilla"
    dialogue_path = vanilla_root / "Characters" / "Dialogue" / (
        "MarriageDialogueElliott.zh-CN.json"
    )
    _write_json(
        dialogue_path,
        {
            "Rainy_Day_1": "雨声让我想起海边的小屋。",
            "Good_2": "我想把这首诗给你看。",
        },
    )

    index = ProfileIndexBuilder(tmp_path / "personas").build(
        vanilla_root=vanilla_root,
        vanilla_locale="zh-CN",
    )

    records = [
        item
        for item in index["speechEvidence"]
        if isinstance(item, dict)
        and item.get("sourcePath")
        == "Characters/Dialogue/MarriageDialogueElliott.zh-CN.json"
    ]
    assert records
    assert {item["npcId"] for item in records} == {"Elliott"}
    assert {item["evidenceKind"] for item in records} == {"marriage_dialogue"}
    assert {
        item["conditions"]["relationshipStage"]
        for item in records
        if isinstance(item.get("conditions"), dict)
    } == {"married"}


def test_legacy_marriage_path_gets_married_provenance_when_index_lacks_metadata(
    tmp_path: Path,
) -> None:
    """旧的派生索引也不能把 MarriageDialogue 当成普通日常语料。"""

    index_path = tmp_path / "legacy-profile-index.json"
    legacy_record = {
        "sampleId": "vanilla:MarriageDialogueElliott:Rainy_Day_1",
        "npcId": "MarriageDialogueElliott",
        "sourceMod": "vanilla",
        "sourcePath": "MarriageDialogueElliott.zh-CN.json",
        "sourceKey": "Rainy_Day_1",
        "text": "雨声让我想起海边的小屋。",
        # 旧索引曾把婚后文件默认为 dialogue，也没有 conditions。
        "evidenceKind": "dialogue",
    }
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": [legacy_record],
            "speechEvidence": [legacy_record],
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).speech_evidence(
        "Elliott",
        ["vanilla"],
        relationship_stage="married",
        limit=2,
    )

    assert selected
    assert selected[0]["npcId"] == "Elliott"
    assert selected[0]["evidenceKind"] == "marriage_dialogue"
    assert selected[0]["conditions"] == {"relationshipStage": "married"}


def test_married_elliott_speech_uses_marriage_voice_and_daily_vanilla_fallback(
    tmp_path: Path,
) -> None:
    """婚后专属对白优先，明确话题无婚后命中时仍可补普通日常节奏。"""

    index_path = tmp_path / "profile-index.json"
    records = [
        {
            "sampleId": "vanilla:MarriageDialogueElliott:Good_2",
            "npcId": "Elliott",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/MarriageDialogueElliott.zh-CN.json",
            "sourceKey": "Good_2",
            "text": "我想把这首诗给你看。",
            "evidenceKind": "marriage_dialogue",
            "conditions": {"relationshipStage": "married"},
        },
        {
            "sampleId": "vanilla:Elliott:Mon",
            "npcId": "Elliott",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Elliott.zh-CN.json",
            "sourceKey": "Mon",
            "text": "海风一起来，我就想起还没写完的稿子。",
            "evidenceKind": "dialogue",
            "conditions": {"relationshipStage": "friend"},
        },
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {"Elliott": {"npcId": "Elliott"}},
            "styleSamples": records,
            "speechEvidence": records,
        },
    )

    store = ProfileIndexStore(index_path)
    marriage_evidence = store.speech_evidence(
        "Elliott",
        ["vanilla"],
        relationship_stage="married",
        player_input="你今天读诗了吗？",
        limit=6,
    )

    assert marriage_evidence[0]["sampleId"] == (
        "vanilla:MarriageDialogueElliott:Good_2"
    )
    assert marriage_evidence[0]["evidenceKind"] == "marriage_dialogue"
    assert marriage_evidence[0]["conditions"] == {"relationshipStage": "married"}

    daily_fallback = store.speech_evidence(
        "Elliott",
        ["vanilla"],
        relationship_stage="married",
        player_input="今天海风怎么样？",
        limit=6,
    )
    assert [item["sampleId"] for item in daily_fallback] == [
        "vanilla:Elliott:Mon",
        "vanilla:MarriageDialogueElliott:Good_2",
    ]
    assert daily_fallback[1]["evidenceKind"] == "marriage_dialogue"
    assert daily_fallback[1]["conditions"] == {"relationshipStage": "married"}


def test_event_dialogue_requires_completion_and_has_bounded_priority(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "profile-index.json"
    daily = [
        {
            "sampleId": f"daily-{index}",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "Characters/Dialogue/Sophia",
            "sourceKey": "Mon",
            "text": f"日常样本 {index}。",
            "evidenceKind": "dialogue",
        }
        for index in range(5)
    ]
    events = [
        {
            "sampleId": f"event-{index}",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "code/NPCs/SophiaEvents.json",
            "sourceKey": f"900{index}/f Sophia 1200",
            "eventId": f"900{index}",
            "eventLineIndex": 1,
            "text": f"事件样本 {index}。",
            "evidenceKind": "event_dialogue",
        }
        for index in range(4)
    ]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": [*daily, *events],
            "speechEvidence": [*daily, *events],
        },
    )
    store = ProfileIndexStore(index_path)

    before_completion = store.speech_evidence("Sophia", ["SVE"], limit=6)
    after_completion = store.speech_evidence(
        "Sophia",
        ["SVE"],
        completed_event_ids=["SVE:9000", "9001", "9002", "9003"],
        limit=6,
    )

    assert not any(
        item.get("evidenceKind") == "event_dialogue" for item in before_completion
    )
    completed_event_samples = [
        item
        for item in after_completion
        if item.get("evidenceKind") == "event_dialogue"
    ]
    assert 1 <= len(completed_event_samples) <= 2
    assert after_completion[0]["evidenceKind"] == "event_dialogue"
    assert len(after_completion) == 6


def test_completed_event_dialogue_survives_source_quota_with_vanilla_fallback(
    tmp_path: Path,
) -> None:
    """事件素材不能被 Mod/vanilla 双来源配额在最后一步丢掉。"""

    index_path = tmp_path / "profile-index.json"
    event = {
        "sampleId": "sve:event-9000",
        "npcId": "Sophia",
        "sourceMod": "SVE",
        "sourcePath": "code/NPCs/SophiaEvents.json",
        "sourceKey": "9000/f Sophia 1200",
        "eventId": "9000",
        "eventLineIndex": 1,
        "text": "我还记得那天的葡萄藤。",
        "evidenceKind": "event_dialogue",
    }
    sve_daily = [
        {
            "sampleId": f"sve:daily-{index}",
            "npcId": "Sophia",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/Standard/Sophia.json",
            "sourceKey": f"Mon{index}",
            "text": f"SVE 日常样本 {index}。",
            "evidenceKind": "dialogue",
        }
        for index in range(4)
    ]
    vanilla_daily = [
        {
            "sampleId": f"vanilla:daily-{index}",
            "npcId": "Sophia",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Sophia.json",
            "sourceKey": f"Tue{index}",
            "text": f"vanilla 日常样本 {index}。",
            "evidenceKind": "dialogue",
        }
        for index in range(4)
    ]
    records = [event, *sve_daily, *vanilla_daily]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).speech_evidence(
        "Sophia",
        ["SVE", "vanilla"],
        completed_event_ids=["SVE:9000"],
        limit=6,
    )

    event_samples = [
        item for item in selected if item.get("evidenceKind") == "event_dialogue"
    ]
    assert selected[0]["sampleId"] == "sve:event-9000"
    assert 1 <= len(event_samples) <= 2
    assert len(selected) == 6


def test_completed_event_dialogue_outranks_stage_specific_marriage_evidence(
    tmp_path: Path,
) -> None:
    """已完成事件在婚后阶段也应先于普通婚后语气锚点。"""

    index_path = tmp_path / "profile-index.json"
    event = {
        "sampleId": "sve:event-9000",
        "npcId": "Wizard",
        "sourceMod": "SVE",
        "sourcePath": "code/NPCs/WizardEvents.json",
        "sourceKey": "9000/f Wizard 1200",
        "eventId": "9000",
        "eventLineIndex": 1,
        "text": "我还记得那次你闯进塔里的时候。",
        "evidenceKind": "event_dialogue",
    }
    marriage = [
        {
            "sampleId": f"sve:marriage-{index}",
            "npcId": "Wizard",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/MarriageDialogueWizard.json",
            "sourceKey": f"Good_{index}",
            "text": f"婚后语气样本 {index}。",
            "evidenceKind": "marriage_dialogue",
            "conditions": {"relationshipStage": "married"},
        }
        for index in range(4)
    ]
    daily = [
        {
            "sampleId": f"vanilla:daily-{index}",
            "npcId": "Wizard",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Wizard.json",
            "sourceKey": f"Tue{index}",
            "text": f"vanilla 日常样本 {index}。",
            "evidenceKind": "dialogue",
        }
        for index in range(4)
    ]
    records = [event, *marriage, *daily]
    _write_json(
        index_path,
        {
            "schemaVersion": 2,
            "profiles": {},
            "styleSamples": records,
            "speechEvidence": records,
            "voiceCards": {},
        },
    )

    selected = ProfileIndexStore(index_path).speech_evidence(
        "Wizard",
        ["SVE", "vanilla"],
        relationship_stage="married",
        completed_event_ids=["SVE:9000"],
        limit=6,
    )

    event_samples = [
        item for item in selected if item.get("evidenceKind") == "event_dialogue"
    ]
    assert selected[0]["sampleId"] == "sve:event-9000"
    assert 1 <= len(event_samples) <= 2
