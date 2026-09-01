from __future__ import annotations

import pytest

try:
    from stardew_ai_bridge.character_quality_eval import (
        DEFAULT_CHARACTER_PROFILES,
        case_by_id,
        quality_case_catalog,
        score_character_reply,
    )
except ModuleNotFoundError:
    DEFAULT_CHARACTER_PROFILES = None  # type: ignore[assignment]
    case_by_id = None  # type: ignore[assignment]
    quality_case_catalog = None  # type: ignore[assignment]
    score_character_reply = None  # type: ignore[assignment]


def test_default_character_cases_keep_wizard_and_rasmodia_as_one_identity() -> None:
    if DEFAULT_CHARACTER_PROFILES is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    assert set(DEFAULT_CHARACTER_PROFILES) == {
        "wizard_rasmodia",
        "sophia",
        "shane",
        "sebastian",
        "alex",
    }
    assert DEFAULT_CHARACTER_PROFILES["wizard_rasmodia"].npc_id == "Wizard"
    assert DEFAULT_CHARACTER_PROFILES["wizard_rasmodia"].display_name == "Rasmodia"


def test_quality_score_rejects_generic_bookish_reply_and_accepts_continuity() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    case = case_by_id("wizard-follow-up")
    bad = score_character_reply(
        case,
        "综合来看，此事具有重要意义，建议持续关注后续发展。",
    )
    good = score_character_reply(
        case,
        "整理完了。第三组稳定，第二组还得重测。",
    )

    assert bad["tags"] >= {"too_formal", "generic_voice"}
    assert good["continuity"] is True
    assert good["forbiddenHits"] == 0


def test_quality_score_rejects_reply_without_current_topic_evidence() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    case = case_by_id("sophia-daily")
    score = score_character_reply(case, "今天挺安静的，没什么特别的。")

    assert score["expectedHits"] == 0
    assert "missing_expected_evidence" in score["tags"]
    assert score["passed"] is False


def test_quality_score_accepts_natural_topic_aliases_without_lowering_topic_bar() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    training = score_character_reply(
        case_by_id("alex-training"),
        "还行，今天练完几组核心动作，状态挺好。",
    )
    coop = score_character_reply(
        case_by_id("shane-coop"),
        "不特别忙，先把食槽刷干净。",
    )
    unrelated = score_character_reply(
        case_by_id("alex-training"),
        "今天挺安静的，没什么特别的。",
    )

    assert training["topicEvidence"] is True
    assert training["expectedHits"] >= 1
    assert training["passed"] is True
    assert coop["topicEvidence"] is True
    assert coop["passed"] is True
    assert unrelated["topicEvidence"] is False
    assert unrelated["passed"] is False


def test_quality_score_keeps_follow_up_strict_when_reply_drops_the_prior_object() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    score = score_character_reply(
        case_by_id("shane-follow-up"),
        "还没送到。我再问问送货的人什么时候能来。",
    )

    assert score["continuity"] is False
    assert "missing_continuity_evidence" in score["tags"]
    assert score["passed"] is False


def test_quality_score_accepts_single_character_prior_object_as_continuity() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    score = score_character_reply(
        case_by_id("sophia-face-follow-up"),
        "这桶酒的味道比上一批酸点，但闻起来更香些。",
    )

    assert score["continuity"] is True
    assert score["passed"] is True


def test_quality_score_exposes_contextual_topic_aliases_without_accepting_generic_text() -> None:
    examples = {
        "sophia": ("sophia-daily", "有一点忙，东边的藤架长得很快。"),
        "shane": ("shane-coop", "不算太忙，刚把家伙们赶回窝里。"),
        "alex": ("alex-training", "还凑合，刚跑完五公里。"),
    }

    scores = {
        name: score_character_reply(case_by_id(case_id), reply)
        for name, (case_id, reply) in examples.items()
    }

    assert all(score["topicEvidence"] for score in scores.values())
    assert all(score["passed"] for score in scores.values())
    assert scores["sophia"]["evidenceMatches"]["葡萄"]
    assert scores["shane"]["evidenceMatches"]["鸡舍"]
    assert scores["alex"]["evidenceMatches"]["训练"]


def test_quality_cases_expose_remote_and_face_to_face_channels() -> None:
    if DEFAULT_CHARACTER_PROFILES is None or case_by_id is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    channels = {
        case_by_id(case_id).channel
        for profile in DEFAULT_CHARACTER_PROFILES.values()
        for case_id in profile.case_ids
    }

    assert channels == {"remote", "face_to_face"}


def test_quality_cases_cover_distinct_environment_and_story_states() -> None:
    if quality_case_catalog is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    cases = quality_case_catalog()
    assert all(case["gameState"]["friendshipHearts"] >= 0 for case in cases)
    assert len({case["gameState"]["location"] for case in cases}) >= 4
    assert len({case["gameState"]["time"] for case in cases}) >= 4
    assert len({case["storyProgress"] for case in cases}) >= 3


def test_default_quality_cases_are_three_turn_conversations() -> None:
    if case_by_id is None or quality_case_catalog is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    cases = quality_case_catalog()

    assert cases
    for case in cases:
        turns = case["turns"]
        assert case["turnCount"] == 3
        assert len(turns) == 3
        assert [turn["turnId"] for turn in turns] == ["turn-1", "turn-2", "turn-3"]
        assert all(turn["playerInput"] for turn in turns)
        assert all(turn["evaluationFocus"] for turn in turns)

    assert len(case_by_id("wizard-daily").dialogue_turns()) == 3
    assert case_by_id("wizard-daily").dialogue_turns()[1].message != ""


def test_quality_cases_cover_high_friendship_background_and_regular_friendship_npcs() -> None:
    if quality_case_catalog is None or case_by_id is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    cases = quality_case_catalog()

    assert any(case["relationshipStage"] in {"close", "married"} for case in cases)
    assert any(
        case["npcId"] not in {"Wizard", "Sophia", "Shane", "Sebastian", "Alex"}
        for case in cases
    )
    assert any(
        case["npcId"] == "Caroline"
        and case["relationshipStage"] == "close"
        and case["channel"] == "face_to_face"
        for case in cases
    )

    caroline = case_by_id("caroline-close-background")
    assert caroline.game_state
    assert caroline.story_progress
    assert any("玛妮" in turn.message for turn in caroline.dialogue_turns())


def test_quality_cases_include_a_married_stage_case() -> None:
    if quality_case_catalog is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    married_cases = [
        case for case in quality_case_catalog()
        if case["relationshipStage"] == "married"
    ]

    assert married_cases
    assert all(case["gameState"]["friendshipHearts"] >= 10 for case in married_cases)


def test_quality_cases_cover_high_friendship_background_and_friendship_boundaries_per_profile() -> None:
    if quality_case_catalog is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    cases = quality_case_catalog()
    required_cases = {
        "wizard-close-background",
        "sophia-close-background",
        "shane-close-boundary",
        "alex-close-background",
        "marnie-friend-family",
        "linus-friend-nature",
    }

    assert required_cases <= {case["caseId"] for case in cases}
    for case in cases:
        if case["caseId"] in required_cases:
            assert case["gameState"]["friendshipHearts"] >= 8
            assert case["storyProgress"]
            assert case["turnCount"] == 3

    assert {case["npcId"] for case in cases if case["caseId"] in {
        "marnie-friend-family",
        "linus-friend-nature",
    }} == {"Marnie", "Linus"}
