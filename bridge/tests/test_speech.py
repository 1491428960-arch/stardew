from __future__ import annotations

import pytest

from stardew_ai_bridge.evidence import (
    is_model_evidence_record,
    is_stable_voice_evidence_record,
)
from stardew_ai_bridge.speech import derive_speech_profile, select_stage_voice_anchors


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


def test_sophia_voice_energy_selects_stage_fit_calm_and_expressive_anchors() -> None:
    samples = [
        {
            "sampleId": "stranger",
            "sourceMod": "SVE",
            "sourceKey": "Mon",
            "conditions": {"relationshipStage": "stranger"},
            "text": "嗯……你好。",
        },
        {
            "sampleId": "married-calm",
            "sourceMod": "SVE",
            "sourceKey": "Rain",
            "conditions": {"relationshipStage": "married"},
            "text": "今天酒窖里很安静。",
        },
        {
            "sampleId": "married-hot",
            "sourceMod": "SVE",
            "sourceKey": "Good_0",
            "conditions": {"relationshipStage": "married"},
            "text": "嘿，小傻瓜！再靠近一点……！！！爱你哟！",
        },
    ]

    selected = select_stage_voice_anchors(
        samples, npc_id="Sophia", relationship_stage="married", max_count=2
    )

    assert [item["sampleId"] for item in selected] == [
        "married-hot",
        "married-calm",
    ]
    assert selected[0]["voiceEnergy"] == "high"
    assert selected[1]["voiceEnergy"] == "low"
    assert selected[0]["energySignals"]["excitementMarkers"] >= 1
    assert selected[0]["energySignals"]["exclamationMarkers"] >= 2


def test_sophia_stage_anchors_put_multiple_high_energy_samples_first_when_available() -> None:
    """自然 Sophia 不能让低能量样本占住前面的原文示例窗口。"""

    samples = [
        {
            "sampleId": "married-calm",
            "sourceMod": "SVE",
            "sourceKey": "Outdoor_0",
            "conditions": {"relationshipStage": "married"},
            "text": "我喜欢这里的新鲜空气。",
        },
        {
            "sampleId": "married-hot-1",
            "sourceMod": "SVE",
            "sourceKey": "Outdoor_4",
            "conditions": {"relationshipStage": "married"},
            "text": "嘿，小傻瓜！今天有什么有趣的事吗？哦哦哦，听起来很重要！",
        },
        {
            "sampleId": "married-hot-2",
            "sourceMod": "SVE",
            "sourceKey": "Good_8",
            "conditions": {"relationshipStage": "married"},
            "text": "耶！你终于起来了！早餐想吃点什么吗？",
        },
    ]

    selected = select_stage_voice_anchors(
        samples, npc_id="Sophia", relationship_stage="married", max_count=2
    )

    assert [item["sampleId"] for item in selected] == [
        "married-hot-1",
        "married-hot-2",
    ]
    assert all(item["voiceEnergy"] == "high" for item in selected)


def test_sophia_dating_anchors_fall_back_to_nearby_stage_without_global_low_energy() -> None:
    """没有 dating 原文时，dating 应借用 close/friend 的活泼日常，而不是全局陌生期对白。"""

    samples = [
        {
            "sampleId": "stranger-calm",
            "sourceMod": "SVE",
            "sourceKey": "Mon",
            "conditions": {"relationshipStage": "stranger"},
            "text": "嗯……你好。",
        },
        {
            "sampleId": "friend-bright",
            "sourceMod": "SVE",
            "sourceKey": "Good_4",
            "conditions": {"relationshipStage": "friend"},
            "text": "耶，葡萄终于变甜了呀！我刚才还在等这一刻。",
        },
        {
            "sampleId": "close-bright",
            "sourceMod": "SVE",
            "sourceKey": "Outdoor_4",
            "conditions": {"relationshipStage": "close"},
            "text": "嘿！你也闻到了吗？这股甜味今天特别明显。",
        },
    ]

    selected = select_stage_voice_anchors(
        samples, npc_id="Sophia", relationship_stage="dating", max_count=3
    )

    assert selected
    assert {item["sampleId"] for item in selected} >= {
        "friend-bright",
        "close-bright",
    }
    assert all(item["sampleId"] != "stranger-calm" for item in selected)
    assert any(item["voiceEnergy"] == "high" for item in selected)


def test_sophia_dating_anchors_prefer_stage_samples_over_unconditional_intro() -> None:
    """dating 有阶段原文时，不能被无阶段的介绍句抢走锚点窗口。"""

    samples = [
        {
            "sampleId": "unconditional-intro",
            "sourceMod": "SVE",
            "sourceKey": "Introduction",
            "text": "呀！有陌生人！等、等一下。",
        },
        {
            "sampleId": "close-lively",
            "sourceMod": "SVE",
            "sourceKey": "Mon10",
            "conditions": {"relationshipStage": "close"},
            "text": "我想找个时间去爬山！我们也可以去野餐！",
        },
    ]

    selected = select_stage_voice_anchors(
        samples, npc_id="Sophia", relationship_stage="dating", max_count=2
    )

    assert selected
    assert selected[0]["sampleId"] == "close-lively"
    assert all(item["sampleId"] != "unconditional-intro" for item in selected)


def test_non_sophia_stage_anchors_prefer_current_relationship_voice() -> None:
    """原文贴合不能只对 Sophia 生效，其他角色也要按当前阶段取样。"""

    samples = [
        {
            "sampleId": "stranger-intro",
            "sourceMod": "vanilla",
            "sourceKey": "Mon",
            "conditions": {"relationshipStage": "stranger"},
            "text": "我不认识你。你为什么要和我说话？",
        },
        {
            "sampleId": "close-shane",
            "sourceMod": "vanilla",
            "sourceKey": "Mon10",
            "conditions": {"relationshipStage": "close"},
            "text": "我只是想确认你没把自己累垮。就这样。",
        },
    ]

    selected = select_stage_voice_anchors(
        samples, npc_id="Shane", relationship_stage="close", max_count=2
    )

    assert [item["sampleId"] for item in selected] == ["close-shane"]


def test_voice_anchor_window_does_not_over_represent_speech_particles() -> None:
    """锚点窗口的语气词密度不能明显高于该角色原文全库。

    2026-09-24（`docs/report-kimi-filler-diagnosis-2026-09-24.md`）：
    原窗口的语气词密度是该角色全库的 1.80x（中位）、最高 3.59x。原因在
    排序键把 `introduction` 排在前面，而介绍句恰好是语气词最密集的一类
    （「呃……你好。」「噢。你是刚搬进来的，对吧？」）。模型把这个被放大的
    窗口当模板复现，Kimi 输出又在其上放大到 2.48x。

    **同一份诊断里已实测：改 prompt 措辞拉不住**——每角色 100 轮、共 600 轮、
    0/3 角色显著变化。所以只能从选样这一侧修。
    """

    clean_texts = [
        "今天在农场干活，天气还不错。",
        "早上喂完鸡，又去修了围栏。",
        "镇上的集市昨天挺热闹。",
        "今年春天的雨水比往年多。",
        "刚把地翻完，打算种点土豆。",
        "下午去河边坐了一会儿。",
        "晚上早点睡，明天还得早起。",
    ]
    dense_texts = [
        "呃……啊，哦！你好。嗯，我是这个人。",
        "哦，唔……你也在这儿啊。唉，算了。",
        "嘿！嗯……今天天气啊，还不错吧？",
        "呃，那个……我、我该走了。",
    ]
    samples = [
        {
            "sampleId": f"day-{key}",
            "sourceKey": key,
            "sourceMod": "vanilla",
            "text": text,
        }
        for key, text in zip(
            ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), clean_texts
        )
    ]
    samples += [
        {
            "sampleId": f"intro-{index}",
            "sourceKey": "Introduction",
            "sourceMod": "vanilla",
            "text": text,
        }
        for index, text in enumerate(dense_texts)
    ]

    anchors = derive_speech_profile("Shane", samples, max_evidence=8)["voiceAnchors"]
    assert len(anchors) == 8, "窗口应当被填满，否则测不到筛选行为"

    def particles(text: str) -> int:
        return sum(1 for char in text if char in "嗯呃哦啊唉呀哎诶嘿哈唔嘛呢吧")

    def chinese(text: str) -> int:
        return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")

    window = sum(particles(item["text"]) for item in anchors)
    window_chars = sum(chinese(item["text"]) for item in anchors)
    corpus = sum(particles(item["text"]) for item in samples)
    corpus_chars = sum(chinese(item["text"]) for item in samples)

    assert window / window_chars <= corpus / corpus_chars * 1.25 + 1e-9, (
        f"锚点窗口语气词密度 {window / window_chars:.3f} 超过全库 "
        f"{corpus / corpus_chars:.3f} 的 1.25 倍"
    )
