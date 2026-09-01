from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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
        item.get("sourceType") == "handcrafted_example"
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
