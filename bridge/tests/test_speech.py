from __future__ import annotations

import pytest

from stardew_ai_bridge.evidence import (
    is_model_evidence_record,
    is_stable_voice_evidence_record,
)
from stardew_ai_bridge.speech import derive_speech_profile


def test_derive_speech_profile_reports_markers_and_capped_evidence() -> None:
    samples = [
        {"sampleId": "a", "text": "也许这只是星界能量的回响。", "sourceMod": "vanilla"},
        {"sampleId": "b", "text": "魔法需要边界，旅行者。", "sourceMod": "SVE"},
        {
            "sampleId": "c",
            "text": "当然，我并不打算把猜测称作预言。",
            "sourceMod": "Rasmodia",
        },
    ]

    card = derive_speech_profile("Rasmodia", samples, max_evidence=2)

    assert card["npcId"] == "Rasmodia"
    assert card["features"]["uncertaintyMarkers"] >= 1
    assert card["features"]["magicMarkers"] >= 1
    assert card["features"]["boundaryMarkers"] >= 1
    assert card["features"]["dryHumorMarkers"] >= 1
    assert card["evidenceRefs"] == ["a", "b"]
    assert all("text" not in value for value in [card])


def test_derive_speech_profile_is_deterministic_and_ignores_invalid_samples() -> None:
    samples = [
        {"sampleId": "a", "text": "魔法与风险。"},
        {"sampleId": "", "text": "秘密。"},
        {"sampleId": "missing-text"},
        "not-a-record",
    ]

    first = derive_speech_profile("Rasmodia", samples, max_evidence=6)
    second = derive_speech_profile("Rasmodia", samples, max_evidence=6)

    assert first == second
    assert first["evidenceRefs"] == ["a"]
    assert first["features"]["magicMarkers"] == 1
    assert first["features"]["boundaryMarkers"] == 2


def test_derive_speech_profile_ignores_control_residue_in_voice_evidence() -> None:
    samples = [
        {
            "sampleId": "narration",
            "sourceKey": "Mon",
            "text": "%海莉没有理你。",
        },
        {
            "sampleId": "action",
            "sourceKey": "Tue",
            "text": "*唉*……今天还得上班。",
        },
        {"sampleId": "dollar", "sourceKey": "Wed", "text": "$"},
        {"sampleId": "clean", "sourceKey": "Thu", "text": "今天过得还好。"},
    ]

    card = derive_speech_profile("Shane", samples, max_evidence=6)

    assert card["evidenceRefs"] == ["clean"]
    assert [item["sampleId"] for item in card["voiceAnchors"]] == ["clean"]


@pytest.mark.parametrize(
    "record",
    [
        {
            "sourceKey": "Wed_01_old",
            "text": "今天过得还好。",
        },
        {
            "sourceKey": "Thu",
            "text": "5 长途奔袭！……开个玩笑而已。",
        },
        {
            "sourceKey": "Thu",
            "text": "Sebastian1 我昨晚跑进山洞里……",
        },
    ],
)
def test_source_artifacts_never_become_model_or_voice_evidence(
    record: dict[str, str],
) -> None:
    assert not is_model_evidence_record(record)
    assert not is_stable_voice_evidence_record(record)


def test_derive_speech_profile_prefers_chinese_localized_evidence_refs() -> None:
    samples = [
        {
            "sampleId": "vanilla:Wizard.de-DE.json:Rain",
            "sourcePath": "Wizard.de-DE.json",
            "text": "Magie.",
        },
        {
            "sampleId": "vanilla:Wizard.zh-CN.json:Rain",
            "sourcePath": "Wizard.zh-CN.json",
            "text": "魔法需要边界。",
        },
        {
            "sampleId": "vanilla:Wizard.json:Rain",
            "sourcePath": "Wizard.json",
            "text": "Magic.",
        },
    ]

    card = derive_speech_profile("Wizard", samples, max_evidence=2)

    assert card["evidenceRefs"] == [
        "vanilla:Wizard.zh-CN.json:Rain",
        "vanilla:Wizard.json:Rain",
    ]
    assert card["features"]["magicMarkers"] == 1


def test_derive_speech_profile_extracts_diverse_positive_voice_anchors() -> None:
    samples = [
        {
            "sampleId": "vanilla:Alex:Introduction",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Alex.zh-CN.json",
            "sourceKey": "Introduction",
            "text": "嘿！你就是新来的农场主吧？",
        },
        {
            "sampleId": "vanilla:Alex:Mon",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Alex.zh-CN.json",
            "sourceKey": "Mon",
            "text": "我今天感觉棒极了。",
        },
        {
            "sampleId": "vanilla:Alex:Tue",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Alex.zh-CN.json",
            "sourceKey": "Tue",
            "text": "我得去海滩练习投球了。",
        },
        {
            "sampleId": "vanilla:Alex:long",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Alex.zh-CN.json",
            "sourceKey": "long",
            "text": "这是一段过长的说明文字，应该被语气锚点选择器跳过，因为它更像资料摘要而不是游戏里角色会说的一小句对白。" * 2,
        },
    ]

    card = derive_speech_profile("Alex", samples, max_anchors=3)

    assert [item["sampleId"] for item in card["voiceAnchors"]] == [
        "vanilla:Alex:Introduction",
        "vanilla:Alex:Mon",
        "vanilla:Alex:Tue",
    ]
    assert all(set(item) >= {"sampleId", "sourceMod", "text"} for item in card["voiceAnchors"])


def test_derive_speech_profile_keeps_dialogue_structure_metadata_on_voice_anchors() -> None:
    """Prompt 采样需要 sourceKey 判断日常、关系和介绍句的结构。"""

    samples = [
        {
            "sampleId": "weekday",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Alex.zh-CN.json",
            "sourceKey": "Mon",
            "text": "今天挺适合打球的。",
        },
        {
            "sampleId": "weekday-two",
            "sourceMod": "vanilla",
            "sourcePath": "Characters/Dialogue/Alex.zh-CN.json",
            "sourceKey": "Tue",
            "text": "海滩那边今天应该不错。",
        },
    ]

    card = derive_speech_profile("Alex", samples, max_anchors=2)

    assert {item["sourceKey"] for item in card["voiceAnchors"]} == {
        "Mon",
        "Tue",
    }


def test_derive_speech_profile_excludes_special_lines_from_voice_anchors() -> None:
    samples = [
        {
            "sampleId": "daily-introduction",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/Standard/StandardDialogueSophia.json",
            "sourceKey": "Introduction",
            "text": "嗯……你好。今天还好吗？",
        },
        {
            "sampleId": "daily-mon",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/Standard/StandardDialogueSophia.json",
            "sourceKey": "Mon",
            "text": "今天的葡萄园还算安静。",
        },
        {
            "sampleId": "daily-tue",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/Standard/StandardDialogueSophia.json",
            "sourceKey": "Tue",
            "text": "我下午想画一会儿。",
        },
        {
            "sampleId": "daily-mon-duplicate",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/Standard/StandardDialogueSophia.json",
            "sourceKey": "Mon4",
            "text": "今天的葡萄园还算安静。",
        },
        {
            "sampleId": "event",
            "sourceMod": "SVE",
            "sourcePath": "assets/Data/Events/Sophia.json",
            "sourceKey": "event4",
            "text": "我把这件事藏了很久，现在终于要告诉你。",
        },
        {
            "sampleId": "festival",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/FestivalDialogue.json",
            "sourceKey": "wonEggHunt",
            "text": "今天的节日真热闹！",
        },
        {
            "sampleId": "special",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/Standard/StandardDialogueSophia.json",
            "sourceKey": "pamHouseUpgrade",
            "text": "这里终于成了一个真正的家。",
        },
        {
            "sampleId": "married",
            "sourceMod": "SVE",
            "sourcePath": "assets/Dialogue/MarriageDialogueSophia.json",
            "sourceKey": "Good_0",
            "evidenceKind": "marriage_dialogue",
            "conditions": {"relationshipStage": "married"},
            "text": "再靠近一点……*亲吻*",
        },
    ]

    card = derive_speech_profile("Sophia", samples, max_anchors=8)

    assert [item["sampleId"] for item in card["voiceAnchors"]] == [
        "daily-introduction",
        "daily-mon",
        "daily-tue",
    ]


@pytest.mark.parametrize(
    "source_key",
    [
        "pamHouseUpgradeAnonymous",
        "Hospital_5_17",
        "BlueMoonVineyard2_21_47",
        "sophia_event1",
        "Indoor_Day_0",
        "funLeave_Shane",
        "Wed2_inlaw_Abigail",
        "makeup_yes",
    ],
)
def test_real_conditional_dialogue_keys_never_become_stable_voice_anchors(
    source_key: str,
) -> None:
    record = {
        "sampleId": f"SVE:{source_key}",
        "sourceMod": "SVE",
        "sourcePath": "assets/CharacterFiles/Dialogue/Sophia/Dialogue.json",
        "sourceKey": source_key,
        "text": "这是一条只在特定地点、时间或事件中出现的对白。",
        "evidenceKind": "dialogue",
    }

    assert not is_stable_voice_evidence_record(record)


@pytest.mark.parametrize("source_key", ["Mon2", "Mon4", "Mon6", "Mon8", "Tue10"])
def test_friendship_gated_weekday_dialogue_is_not_a_stage_neutral_voice_anchor(
    source_key: str,
) -> None:
    record = {
        "sampleId": f"vanilla:Wizard:{source_key}",
        "sourceMod": "vanilla",
        "sourcePath": "Characters/Dialogue/Wizard.zh-CN.json",
        "sourceKey": source_key,
        "text": "这是一条只有关系变近后才会出现的日常对白。",
        "evidenceKind": "dialogue",
    }

    assert not is_stable_voice_evidence_record(record)
