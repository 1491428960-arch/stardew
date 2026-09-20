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


def test_many_xnb_in_one_directory_collapse_into_a_single_warning(
    tmp_path: Path,
) -> None:
    """同一目录下的多个 xnb 合并成一条。

    SVE 的 `assets/XNBs/` 有 55 个室内地图 xnb，它们对**对话**索引没有用处
    （而判据本来就是“根下存在 .xnb”，与有没有同名 JSON 无关，所以解包也消不掉）。
    逐条报告只会把 55 行噪音灌进 warnings，**让真正的警告被淹没**——
    与审计工具的误报是同一类问题，所以这里按目录合并。
    """
    vanilla_root = tmp_path / "vanilla-dialogue"
    maps = vanilla_root / "assets" / "XNBs"
    maps.mkdir(parents=True)
    for name in ("AdventureGuild", "AdventurerSummit", "AndyHouse", "ApplesRoom"):
        (maps / f"{name}.xnb").write_bytes(b"binary placeholder")

    from stardew_ai_bridge.corpus import build_dialogue_corpus

    corpus = build_dialogue_corpus(vanilla_root=vanilla_root)

    xnb_warnings = [
        warning
        for warning in corpus["warnings"]
        if warning.startswith("xnb source requires unpacked JSON")
    ]
    assert len(xnb_warnings) == 1, xnb_warnings
    # 信息不能丢：目录与数量都要写清楚。
    assert "assets/XNBs" in xnb_warnings[0]
    assert "4" in xnb_warnings[0]


def test_xnb_in_different_directories_each_get_their_own_warning(
    tmp_path: Path,
) -> None:
    vanilla_root = tmp_path / "vanilla-dialogue"
    (vanilla_root / "a").mkdir(parents=True)
    (vanilla_root / "b").mkdir(parents=True)
    (vanilla_root / "a" / "One.xnb").write_bytes(b"x")
    (vanilla_root / "b" / "Two.xnb").write_bytes(b"x")

    from stardew_ai_bridge.corpus import build_dialogue_corpus

    corpus = build_dialogue_corpus(vanilla_root=vanilla_root)

    xnb_warnings = [
        warning
        for warning in corpus["warnings"]
        if warning.startswith("xnb source requires unpacked JSON")
    ]
    assert len(xnb_warnings) == 2, xnb_warnings


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


def test_extract_event_dialogue_keeps_speaker_lines_and_event_provenance() -> None:
    records, warnings = extract_content_patcher_dialogue(
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "Data/Events/town",
                    "Entries": {
                        "8185290_Medicine/f Sophia 1200": (
                            "none/-500 -500/farmer 1 1 0 Sophia 2 2 0/"
                            "speak farmer \"玩家不应进入。\"/"
                            "speak Sophia \"{{i18n:Sophia.Event.01}}\"/"
                            "textAboveHead Sophia \"{{i18n:Sophia.Event.02}}\"/"
                            "end dialogue Sophia \"{{i18n:Sophia.Event.03}}\"/"
                            "message \"{{i18n:Sophia.Event.04}}\"/emote Sophia 16"
                        )
                    },
                }
            ]
        },
        source_mod="FlashShifter.StardewValleyExpandedCP",
        source_path="code/NPCs/SophiaEvents.json",
        i18n_catalogs={
            "default": {
                "Sophia.Event.01": "我记得那天的风。",
                "Sophia.Event.02": "别走神啦。",
                "Sophia.Event.03": "现在想起来还是有点不好意思。",
                "Sophia.Event.04": "不应当被提取。",
            }
        },
    )

    assert warnings == []
    assert [record["npcId"] for record in records] == ["Sophia", "Sophia", "Sophia"]
    assert [record["eventLineIndex"] for record in records] == [2, 3, 4]
    assert all(record["evidenceKind"] == "event_dialogue" for record in records)
    assert all(record["eventId"] == "8185290" for record in records)
    assert all(record["sourceKey"] == "8185290_Medicine/f Sophia 1200" for record in records)
    assert records[0]["resolvedText"] == "我记得那天的风。"
    assert records[1]["resolvedText"] == "别走神啦。"
    assert records[2]["resolvedText"] == "现在想起来还是有点不好意思。"
    assert all("玩家不应进入" not in record["text"] for record in records)


def test_build_corpus_extracts_event_dialogue_from_content_patcher_data_events(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mod"
    _write_json(root / "manifest.json", {"UniqueID": "Example.Mod"})
    _write_json(
        root / "i18n" / "default.json",
        {"Alex.Event.01": "我不会忘记那场比赛。"},
    )
    _write_json(
        root / "Events.json",
        {
            "Changes": [
                {
                    "Action": "EditData",
                    "Target": "data/events/sport",
                    "Entries": {
                        "7000001/f Alex 1800": (
                            "none/speak Alex \"{{i18n:Alex.Event.01}}\"/"
                            "end dialogue Alex \"比赛结束了。\""
                        )
                    },
                }
            ]
        },
    )

    corpus = build_dialogue_corpus(mod_roots=[root])

    assert corpus["warnings"] == []
    assert len(corpus["records"]) == 2
    assert {record["evidenceKind"] for record in corpus["records"]} == {
        "event_dialogue"
    }
    assert {record["eventId"] for record in corpus["records"]} == {"7000001"}
    assert {record.get("resolvedText") for record in corpus["records"]} == {
        "我不会忘记那场比赛。",
        None,
    }


def test_build_corpus_extracts_vanilla_events_with_participants_and_conditions(
    tmp_path: Path,
) -> None:
    events_root = tmp_path / "Content" / "Data" / "Events"
    _write_json(
        events_root / "Mountain.zh-CN.json",
        {
            "384882/f Sebastian 2500/o Abigail/t 2000 2400": (
                "nightTime/-1000 -1000/farmer 18 35 0 Sebastian -100 -100 0/"
                "speak Sebastian \"嘿，@。上来……我想给你看样东西。\"/"
                "speak farmer \"玩家不应进入语料。\"/"
                "end dialogue Sebastian \"你是唯一一个被我带到这里的人。\""
            )
        },
    )

    corpus = build_dialogue_corpus(
        vanilla_events_root=events_root,
        vanilla_locale="zh-CN",
    )

    assert corpus["warnings"] == []
    records = corpus["records"]
    assert len(records) == 2
    assert {record["npcId"] for record in records} == {"Sebastian"}
    assert {record["eventId"] for record in records} == {"384882"}
    assert all(record["evidenceKind"] == "event_dialogue" for record in records)
    assert all(
        record["participants"] == ["Sebastian", "Abigail"] for record in records
    )
    assert all(record["conditions"] == {"eventId": "384882"} for record in records)
    assert all(
        record["eventConditions"]["raw"]
        == "384882/f Sebastian 2500/o Abigail/t 2000 2400"
        for record in records
    )
    assert all(
        record["sourcePath"] == "Data/Events/Mountain.zh-CN.json"
        for record in records
    )
    assert all("玩家不应进入" not in record["text"] for record in records)


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
