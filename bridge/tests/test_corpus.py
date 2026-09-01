from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.corpus import (
    build_dialogue_corpus,
    classify_dialogue_target,
    clean_dialogue_variants,
    extract_content_patcher_dialogue,
    infer_dialogue_conditions,
    resolve_i18n_candidates,
    resolve_i18n_text,
)


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_classify_dialogue_target_preserves_npc_and_dialogue_kind() -> None:
    assert classify_dialogue_target(
        "Characters/Dialogue/MarriageDialogueRasmodia"
    ) == ("Rasmodia", "marriage_dialogue")
    assert classify_dialogue_target(
        "Characters/Dialogue/RoommateDialogueRasmodia"
    ) == ("Rasmodia", "roommate_dialogue")
    assert classify_dialogue_target("Maps/Town") == ("", "")


def test_infer_dialogue_conditions_marks_marriage_dialogue() -> None:
    assert infer_dialogue_conditions(
        "Characters/Dialogue/MarriageDialogueRasmodia", "Rain"
    ) == {"relationshipStage": "married"}
    assert infer_dialogue_conditions(
        "Characters/Dialogue/RoommateDialogueRasmodia", "Rain"
    ) == {"relationshipStage": "married"}


def test_extract_dialogue_keeps_provenance_and_stage() -> None:
    payload = {
        "Changes": [
            {
                "Action": "EditData",
                "Target": "Characters/Dialogue/MarriageDialogueRasmodia",
                "Entries": {"Rain": "雨天适合留在塔里。"},
            }
        ]
    }

    records, warnings = extract_content_patcher_dialogue(
        payload,
        source_mod="Dacar.SeasRomRasmodia",
        source_path="assets/Dialogue.json",
    )

    assert warnings == []
    assert records == [
        {
            "sampleId": "Dacar.SeasRomRasmodia:assets/Dialogue.json:Rain",
            "npcId": "Rasmodia",
            "sourceMod": "Dacar.SeasRomRasmodia",
            "sourcePath": "assets/Dialogue.json",
            "sourceKey": "Rain",
            "text": "雨天适合留在塔里。",
            "evidenceKind": "marriage_dialogue",
            "conditions": {"relationshipStage": "married"},
        }
    ]


def test_extract_dialogue_preserves_i18n_reference_and_skips_invalid_changes() -> None:
    payload = {
        "Changes": [
            {
                "Action": "EditData",
                "Target": "Characters/Dialogue/Wizard",
                "Entries": {"Rain": "{{i18n:Wizard.Rain}}", "Empty": ""},
            },
            {"Action": "EditImage", "Target": "Characters/Wizard"},
            {"Action": "EditData", "Target": "Maps/Town", "Entries": {}},
        ]
    }

    records, warnings = extract_content_patcher_dialogue(
        payload,
        source_mod="vanilla",
        source_path="Characters/Dialogue/Wizard.json",
    )

    assert warnings == []
    assert records == [
        {
            "sampleId": "vanilla:Characters/Dialogue/Wizard.json:Rain",
            "npcId": "Wizard",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Wizard.json",
            "sourceKey": "Rain",
            "text": "{{i18n:Wizard.Rain}}",
            "evidenceKind": "dialogue",
            "conditions": {},
        }
    ]


def test_resolve_i18n_text_prefers_locale_override_and_falls_back_to_default() -> None:
    catalogs = {
        "default": {
            "Sophia.CharacterDialogue.001": "English line",
            "Sophia.CharacterDialogue.002": "English fallback",
            "Andy.GiftBDPos": "大小写也应该能命中",
            "WizardDialogue.Forest West": "带空格的键",
        },
        "zh": {"Sophia.CharacterDialogue.001": "中文台词"},
    }

    assert resolve_i18n_text(
        "{{i18n:Sophia.CharacterDialogue.001}}", catalogs, locale="zh-CN"
    ) == "中文台词"
    assert resolve_i18n_text(
        "{{i18n:Sophia.CharacterDialogue.002}}", catalogs, locale="zh-CN"
    ) == "English fallback"
    assert resolve_i18n_text(
        "{{i18n:Sophia.CharacterDialogue.999}}", catalogs, locale="zh-CN"
    ) == "{{i18n:Sophia.CharacterDialogue.999}}"
    assert resolve_i18n_text(
        "{{i18n:Andy.GiftBDpos}}", catalogs, locale="zh-CN"
    ) == "大小写也应该能命中"
    assert resolve_i18n_text(
        "{{i18n:Sophia.CharacterDialogue.001 {{expressionList}} }}",
        catalogs,
        locale="zh-CN",
    ) == "中文台词"
    assert resolve_i18n_text(
        "{{i18n:WizardDialogue.Forest West}}", catalogs, locale="zh-CN"
    ) == "带空格的键"


def test_resolve_i18n_candidates_enumerates_dynamic_key_family_deterministically() -> None:
    catalogs = {
        "default": {
            "Wizard.funLeave.1": "第一句",
            "Wizard.funLeave.2": "第二句",
            "Wizard.funLeave.10": "第十句",
            "Other.1": "不应混入",
        }
    }

    assert resolve_i18n_candidates(
        "{{i18n:Wizard.funLeave.{{Random:{{Range:1,10}}}}}}",
        catalogs,
    ) == [
        {"key": "Wizard.funLeave.1", "text": "第一句"},
        {"key": "Wizard.funLeave.10", "text": "第十句"},
        {"key": "Wizard.funLeave.2", "text": "第二句"},
    ]


def test_resolve_i18n_candidates_prefers_locale_and_respects_cap() -> None:
    catalogs = {
        "default": {
            "Npc.Line.1": "默认一",
            "Npc.Line.2": "默认二",
            "Npc.Line.3": "默认三",
        },
        "zh": {
            "Npc.Line.1": "中文一",
            "Npc.Line.2": "中文二",
        },
    }

    assert resolve_i18n_candidates(
        "{{i18n:Npc.Line.{{Random:{{Range:1,3}}}}}}",
        catalogs,
        locale="zh-CN",
        max_candidates=2,
    ) == [
        {"key": "Npc.Line.1", "text": "中文一"},
        {"key": "Npc.Line.2", "text": "中文二"},
    ]


def test_resolve_i18n_candidates_keeps_multiple_dynamic_branches() -> None:
    catalogs = {
        "default": {
            "LanceKrobus.1": "会见科罗布斯",
            "LanceKrobus.2": "会见马龙",
            "Lance.MarriageDialogue.035": "婚后句一",
            "Lance.MarriageDialogue.036": "婚后句二",
        }
    }

    candidates = resolve_i18n_candidates(
        "$query FLAG#{{i18n:LanceKrobus.{{Random:{{Range:1,2}}}}}}"
        "|{{i18n:Lance.MarriageDialogue.0{{Random:{{Range:35,36}}}}}}",
        catalogs,
    )

    assert {candidate["key"] for candidate in candidates} == {
        "LanceKrobus.1",
        "LanceKrobus.2",
        "Lance.MarriageDialogue.035",
        "Lance.MarriageDialogue.036",
    }


def test_resolve_i18n_candidates_skips_alias_values_with_unresolved_i18n() -> None:
    assert resolve_i18n_candidates(
        "{{i18n:Wizard.SpouseStardrop {{expressionList}}}}",
        {"default": {"Wizard.SpouseStardrop": "{{i18n:Wizard.Stardrop}}"}},
    ) == []


def test_extract_dialogue_records_dynamic_i18n_candidates_without_faking_resolution() -> None:
    payload = {
        "Changes": [
            {
                "Action": "EditData",
                "Target": "Characters/Dialogue/Wizard",
                "Entries": {
                    "funLeave": "{{i18n:Wizard.funLeave.{{Random:{{Range:1,2}}}}}}"
                },
            }
        ]
    }

    records, warnings = extract_content_patcher_dialogue(
        payload,
        source_mod="Example.Mod",
        source_path="assets/Dialogue.json",
        i18n_catalogs={
            "default": {
                "Wizard.funLeave.1": "候选一",
                "Wizard.funLeave.2": "候选二",
            }
        },
    )

    assert warnings == []
    assert "resolvedText" not in records[0]
    assert records[0]["dynamicCandidates"] == [
        {"key": "Wizard.funLeave.1", "text": "候选一"},
        {"key": "Wizard.funLeave.2", "text": "候选二"},
    ]


def test_extract_dialogue_does_not_mark_partially_resolved_text_as_final() -> None:
    payload = {
        "Changes": [
            {
                "Action": "EditData",
                "Target": "Characters/Dialogue/Wizard",
                "Entries": {
                    "Mixed": (
                        "{{i18n:Wizard.Static}}|"
                        "{{i18n:Wizard.Dynamic.{{Random:{{Range:1,2}}}}}}"
                    )
                },
            }
        ]
    }

    records, warnings = extract_content_patcher_dialogue(
        payload,
        source_mod="Example.Mod",
        source_path="assets/Dialogue.json",
        i18n_catalogs={
            "default": {
                "Wizard.Static": "静态分支",
                "Wizard.Dynamic.1": "动态一",
                "Wizard.Dynamic.2": "动态二",
            }
        },
    )

    assert warnings == []
    assert "resolvedText" not in records[0]
    assert records[0]["dynamicCandidates"] == [
        {"key": "Wizard.Dynamic.1", "text": "动态一"},
        {"key": "Wizard.Dynamic.2", "text": "动态二"},
    ]


def test_build_corpus_adds_resolved_i18n_text_without_losing_raw_reference(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mod"
    _write_json(root / "manifest.json", {"UniqueID": "Example.Mod"})
    _write_json(
        root / "i18n" / "default.json",
        {"Sophia.CharacterDialogue.001": "English line"},
    )
    _write_json(
        root / "i18n" / "zh.json",
        {"Sophia.CharacterDialogue.001": "中文台词"},
    )
    _write_json(
        root / "Dialogue.json",
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/Sophia",
                    "Entries": {
                        "Introduction": "{{i18n:Sophia.CharacterDialogue.001}}"
                    },
                }
            ]
        },
    )

    corpus = build_dialogue_corpus(mod_roots=[root], locale="zh-CN")

    assert corpus["warnings"] == []
    assert corpus["records"][0]["text"] == "{{i18n:Sophia.CharacterDialogue.001}}"
    assert corpus["records"][0]["resolvedText"] == "中文台词"


def test_build_corpus_warns_when_vanilla_xnb_is_not_unpacked(tmp_path: Path) -> None:
    vanilla_root = tmp_path / "vanilla-dialogue"
    vanilla_root.mkdir()
    (vanilla_root / "Wizard.xnb").write_bytes(b"binary placeholder")

    from stardew_ai_bridge.corpus import build_dialogue_corpus

    corpus = build_dialogue_corpus(vanilla_root=vanilla_root)

    assert any(
        "xnb source requires unpacked JSON" in warning
        for warning in corpus["warnings"]
    )


def test_build_corpus_uses_last_content_patcher_edit_for_duplicate_key(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mod"
    _write_json(
        root / "manifest.json",
        {"UniqueID": "Example.Mod"},
    )
    _write_json(
        root / "Dialogue.json",
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/Rasmodia",
                    "Entries": {"Rain": "旧文本"},
                },
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/Rasmodia",
                    "Entries": {"Rain": "最终文本"},
                },
            ]
        },
    )

    corpus = build_dialogue_corpus(mod_roots=[root])

    assert len(corpus["records"]) == 1
    assert corpus["records"][0]["text"] == "最终文本"


def test_extract_dialogue_accepts_target_array_without_comma_in_npc_id() -> None:
    records, warnings = extract_content_patcher_dialogue(
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": [
                        "Characters/Dialogue/MarriageDialogueJuna",
                        "Characters/Dialogue/RoommateDialogueJuna",
                    ],
                    "Entries": {"Rain": "婚后也要先确认风险。"},
                }
            ]
        },
        source_mod="Example.Mod",
        source_path="Dialogue.json",
    )

    assert warnings == []
    assert len(records) == 1
    assert records[0]["npcId"] == "Juna"
    assert records[0]["evidenceKind"] == "roommate_dialogue"
    assert records[0]["conditions"] == {"relationshipStage": "married"}


def test_extract_dialogue_accepts_content_patcher_comma_target() -> None:
    records, warnings = extract_content_patcher_dialogue(
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/MarriageDialogueJuna, Characters/Dialogue/MarriageDialogueJunaRoommate",
                    "Entries": {"Rain": "婚后也要先确认风险。"},
                }
            ]
        },
        source_mod="Example.Mod",
        source_path="Dialogue.json",
    )

    assert warnings == []
    assert len(records) == 1
    assert records[0]["npcId"] == "JunaRoommate"


def test_build_corpus_strips_locale_suffix_from_vanilla_npc_id(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vanilla"
    _write_json(root / "Wizard.json", {"Rain": "English"})
    _write_json(root / "Wizard.zh-CN.json", {"Rain": "中文"})

    corpus = build_dialogue_corpus(vanilla_root=root)

    assert {record["npcId"] for record in corpus["records"]} == {"Wizard"}
    assert {record["text"] for record in corpus["records"]} == {"English", "中文"}


def test_extract_dialogue_keeps_raw_control_script_and_clean_variants() -> None:
    raw_text = (
        "第一段#$b#第二段^性别分支||另一条$q问题#$r回答一#$r回答二$h"
    )
    records, warnings = extract_content_patcher_dialogue(
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Characters/Dialogue/Shane",
                    "Entries": {"Mon6": raw_text},
                }
            ]
        },
        source_mod="vanilla",
        source_path="Characters/Dialogue/Shane.json",
    )

    assert warnings == []
    assert records[0]["text"] == raw_text
    variants = records[0]["dialogueVariants"]
    assert len(variants) >= 3
    assert any("第一段" in variant and "第二段" in variant for variant in variants)
    assert any("性别分支" in variant for variant in variants)
    assert any("另一条" in variant for variant in variants)
    assert all(
        marker not in variant
        for variant in variants
        for marker in ("^", "||", "#$b#", "$q", "#$r", "$h")
    )


def test_clean_dialogue_variants_drops_input_separator_control_residue() -> None:
    assert clean_dialogue_variants("今天还好。 inputSeparator=@@}}") == ["今天还好。"]
    assert clean_dialogue_variants("{{Random:今天还好。}}inputSeparator=@@}}") == []


def test_clean_dialogue_variants_removes_single_letter_residue_between_chinese_text() -> None:
    assert clean_dialogue_variants("海滩真的是个很酷的地方…… e 你得多晒晒太阳……") == [
        "海滩真的是个很酷的地方……你得多晒晒太阳……"
    ]


def test_clean_dialogue_variants_keeps_real_english_when_not_a_chinese_boundary_residue() -> None:
    assert clean_dialogue_variants("我会用 C++ 写工具，也会看英文文档。") == [
        "我会用 C++ 写工具，也会看英文文档。"
    ]


def test_clean_dialogue_variants_removes_actions_and_drops_narration_or_lone_dollar() -> None:
    assert clean_dialogue_variants("*唉*……我还在这里做什么？") == [
        "……我还在这里做什么？"
    ]
    assert clean_dialogue_variants("%海莉没有理你。") == []
    assert clean_dialogue_variants("$") == []


def test_clean_dialogue_variants_splits_numeric_stardew_branch_headers() -> None:
    raw_text = (
        "如果你不是女孩子，我就约你打球了。 6 0 Wed_01_02 "
        "我站在旁边看就好了。 5 15 Wed_01_01 我想和你打球！ "
        "5 0 Wed_01_03 （愤怒）你到底是什么意思？"
    )

    variants = clean_dialogue_variants(raw_text)

    assert variants == [
        "如果你不是女孩子，我就约你打球了。",
        "我站在旁边看就好了。",
        "我想和你打球！",
        "（愤怒）你到底是什么意思？",
    ]
    assert all(
        marker not in variant
        for variant in variants
        for marker in ("Wed_01_02", "Wed_01_01", "Wed_01_03")
    )
