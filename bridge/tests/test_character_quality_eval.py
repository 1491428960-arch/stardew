from __future__ import annotations

import pytest

try:
    import stardew_ai_bridge.character_quality_eval as quality_eval

    from stardew_ai_bridge.character_quality_eval import (
        DEFAULT_CASES,
        DEFAULT_CHARACTER_PROFILES,
        case_by_id,
        quality_case_catalog,
        score_character_reply,
    )
    score_dialogue_progression = getattr(
        quality_eval,
        "score_dialogue_progression",
        None,
    )
    score_affection_variation = getattr(
        quality_eval,
        "score_affection_variation",
        None,
    )
    validate_quality_cases = getattr(quality_eval, "validate_quality_cases", None)
    diagnose_affection_initiative = getattr(
        quality_eval,
        "diagnose_affection_initiative",
        None,
    )
except ModuleNotFoundError:
    DEFAULT_CASES = None  # type: ignore[assignment]
    DEFAULT_CHARACTER_PROFILES = None  # type: ignore[assignment]
    case_by_id = None  # type: ignore[assignment]
    quality_case_catalog = None  # type: ignore[assignment]
    score_character_reply = None  # type: ignore[assignment]
    score_dialogue_progression = None  # type: ignore[assignment]
    score_affection_variation = None  # type: ignore[assignment]
    validate_quality_cases = None  # type: ignore[assignment]
    diagnose_affection_initiative = None  # type: ignore[assignment]

try:
    from stardew_ai_bridge.topic_start_intimacy_cases import (
        TOPIC_START_INTIMACY_SUITE,
        topic_start_intimacy_cases,
    )
except ModuleNotFoundError:
    TOPIC_START_INTIMACY_SUITE = None  # type: ignore[assignment]
    topic_start_intimacy_cases = None  # type: ignore[assignment]

try:
    from stardew_ai_bridge.topic_start_adaptive_cases import (
        TOPIC_START_ADAPTIVE_SUITE,
        topic_start_adaptive_cases,
    )
except ModuleNotFoundError:
    TOPIC_START_ADAPTIVE_SUITE = None  # type: ignore[assignment]
    topic_start_adaptive_cases = None  # type: ignore[assignment]


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


def test_quality_score_records_personal_affection_diagnostics_without_changing_legacy_score() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    case = case_by_id("sophia-dating-wine")
    score = score_character_reply(
        case,
        "这首歌我只想先给你听。",
        turn=case.dialogue_turns()[1],
        player_input="新歌准备好了吗？",
    )

    assert score["personalAffectionDetected"] is True
    assert score["companionshipDetected"] is True
    assert score["specificPlanDetected"] is False
    assert score["affectionEvidence"] == ["exclusive_share"]
    assert score["affectionShape"] == "exclusive_share"
    assert "mechanicalRestatement" in score


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


def test_quality_case_catalog_exposes_stable_one_based_numbers() -> None:
    if quality_case_catalog is None:
        pytest.fail("质量案例编号尚未实现")

    cases = quality_case_catalog()

    assert [case["caseNumber"] for case in cases] == list(range(1, len(cases) + 1))
    assert cases[16]["caseId"] == "sebastian-married-life"


def test_progression_flags_adjacent_replies_that_only_repeat_previous_content() -> None:
    if case_by_id is None or score_dialogue_progression is None:
        pytest.fail("多轮推进评分尚未实现")

    case = case_by_id("wizard-married-evening")
    scores = score_dialogue_progression(
        [
            "今晚先放下记录，陪我一会儿。",
            "今晚先放下记录，陪我一会儿。",
            "今晚先放下记录，陪我一会儿。",
        ],
        case.dialogue_turns(),
    )

    assert scores[0]["repeated"] is False
    assert scores[1]["repeated"] is True
    assert "repeated_turn_content" in scores[1]["tags"]


def test_progression_accepts_new_detail_and_explicit_shane_closing() -> None:
    if case_by_id is None or score_dialogue_progression is None:
        pytest.fail("多轮推进评分尚未实现")

    case = case_by_id("shane-dating-boundary")
    scores = score_dialogue_progression(
        [
            "别逼我说这种话，今天真的没心情。",
            "行了，我先睡了。",
            "明天再说。",
        ],
        case.dialogue_turns(),
    )

    assert all(score["repeated"] is False for score in scores)


def test_affection_variation_flags_repeated_shape_kind_and_opening_without_new_anchor() -> None:
    if score_affection_variation is None:
        pytest.fail("亲近形状变化评分尚未实现")

    turn_type = quality_eval.CharacterQualityTurn
    turns = (
        turn_type("turn-1", "", expected_terms=("歌",)),
        turn_type("turn-2", "", expected_terms=("歌",)),
        turn_type("turn-3", "", expected_terms=("歌",)),
    )
    diagnostics = (
        {"affectionShape": "exclusive_share", "initiativeKind": "creative_share", "initiativeTags": []},
        {"affectionShape": "exclusive_share", "initiativeKind": "creative_share", "initiativeTags": []},
        {"affectionShape": "exclusive_share", "initiativeKind": "creative_share", "initiativeTags": []},
    )
    scores = score_affection_variation(
        (
            "这首歌我只想先给你听。",
            "这首歌我只想先给你听。",
            "这首歌我只想先给你听。",
        ),
        turns,
        diagnostics,
    )

    assert scores[0]["mechanical"] is False
    assert scores[1]["mechanical"] is True
    assert "mechanical_affection_shape" in scores[1]["tags"]


def test_affection_variation_accepts_new_anchor_or_guarded_close() -> None:
    if score_affection_variation is None:
        pytest.fail("亲近形状变化评分尚未实现")

    turn_type = quality_eval.CharacterQualityTurn
    turns = (
        turn_type("turn-1", "", expected_terms=("歌",)),
        turn_type("turn-2", "", expected_terms=("摩托车",)),
        turn_type("turn-3", "", expected_terms=("摩托车",)),
    )
    diagnostics = (
        {"affectionShape": "exclusive_share", "initiativeKind": "creative_share", "initiativeTags": []},
        {"affectionShape": "exclusive_share", "initiativeKind": "creative_share", "initiativeTags": []},
        {"affectionShape": "conversation_exit", "initiativeKind": "conversation_exit", "initiativeTags": ["guarded_exit_allowed"]},
    )
    scores = score_affection_variation(
        (
            "这首歌我只想先给你听。",
            "摩托车的声音也只想先给你听。",
            "今天到这吧，我想一个人待会儿。",
        ),
        turns,
        diagnostics,
    )

    assert all(score["mechanical"] is False for score in scores)


def test_affection_variation_requires_reply_to_actually_introduce_new_anchor() -> None:
    if score_affection_variation is None:
        pytest.fail("亲近形状变化评分尚未实现")

    turn_type = quality_eval.CharacterQualityTurn
    turns = (
        turn_type("turn-1", "", expected_terms=("歌",)),
        turn_type("turn-2", "", expected_terms=("摩托车",)),
    )
    diagnostics = (
        {"affectionShape": "exclusive_share", "initiativeKind": "creative_share", "initiativeTags": []},
        {"affectionShape": "exclusive_share", "initiativeKind": "creative_share", "initiativeTags": []},
    )
    scores = score_affection_variation(
        ("这首歌我只想先给你听。", "这首歌我只想先给你听。"),
        turns,
        diagnostics,
    )

    assert scores[1]["hasNewAnchor"] is False
    assert scores[1]["mechanical"] is True


def test_married_cases_use_distinct_player_turns_and_intimate_progression() -> None:
    if case_by_id is None:
        pytest.fail("婚后质量案例尚未实现")

    married_case_ids = (
        "sebastian-married-life",
        "wizard-married-evening",
        "sophia-married-cellar",
        "sebastian-married-music",
        "alex-married-evening",
    )
    for case_id in married_case_ids:
        case = case_by_id(case_id)
        turns = case.dialogue_turns()
        messages = [turn.message for turn in turns]
        assert len(set(messages)) == 3, case_id
        assert any(
            marker in "".join(messages)
            for marker in ("陪", "靠", "过来", "独处", "单独", "待会儿")
        ), case_id
        assert "亲密" in (case.relationship_context or case.story_progress)


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


def test_high_stage_cases_carry_story_events_and_feminine_overlay_metadata() -> None:
    if case_by_id is None:
        pytest.fail("高阶段案例元数据尚未实现")

    shane = case_by_id("shane-close-boundary")
    assert shane.completed_event_ids == ("vanilla:shane-heart-6",)

    for case_id in (
        "shane-dating-boundary",
        "sebastian-dating-rooftop",
        "alex-dating-beach",
    ):
        case = case_by_id(case_id)
        assert case.gender_presentation == "female-bachelors"
        assert "female-bachelors" in case.source_mods
        assert case.friendship_hearts is not None and case.friendship_hearts >= 8


def test_quality_cases_expose_high_affection_flirt_and_consent_metadata() -> None:
    if quality_case_catalog is None:
        pytest.fail("高好感质量案例目录尚未实现")

    cases = quality_case_catalog()
    metadata_keys = {
        "friendshipHearts",
        "flirtIntensity",
        "adultConsensual",
        "romanceEligible",
        "relationshipContext",
    }
    assert all(metadata_keys <= set(case) for case in cases)
    assert {case["flirtIntensity"] for case in cases} >= {
        "none",
        "light",
        "direct",
        "explicit",
    }

    major_npcs = {"Wizard", "Sophia", "Shane", "Sebastian", "Alex"}
    for npc_id in major_npcs:
        high_affection = [
            case
            for case in cases
            if case["npcId"] == npc_id
            and case["relationshipStage"] in {"dating", "married"}
        ]
        assert high_affection, npc_id
        assert any(case["flirtIntensity"] != "none" for case in high_affection)

    non_romance = [
        case for case in cases if case["npcId"] in {"Caroline", "Marnie", "Linus"}
    ]
    assert non_romance
    assert all(case["romanceEligible"] is False for case in non_romance)
    assert all(case["flirtIntensity"] == "none" for case in non_romance)


def test_quality_case_validation_rejects_unconsented_or_early_explicit_flirt() -> None:
    if case_by_id is None or DEFAULT_CASES is None or validate_quality_cases is None:
        pytest.fail("质量案例元数据校验尚未实现")

    early = case_by_id("wizard-daily")
    invalid = early.__class__(
        **{
            **early.__dict__,
            "flirt_intensity": "explicit",
            "adult_consensual": False,
            "romance_eligible": True,
        }
    )
    errors = validate_quality_cases((*DEFAULT_CASES, invalid))

    assert any("adult_consensual" in error for error in errors)
    assert any("relationship_stage" in error for error in errors)


def test_quality_case_flirt_context_is_visible_to_the_evaluation_prompt() -> None:
    from stardew_ai_bridge.prompts import PromptBuilder

    messages = PromptBuilder().build(
        {
            "npcIdentity": {"npcId": "Alex", "displayName": "Alex"},
            "gameState": {"relationshipStage": "married"},
            "qualityContext": {
                "flirtIntensity": "explicit",
                "adultConsensual": True,
                "romanceEligible": True,
                "relationshipContext": "已婚阶段：双方已确认亲密关系。",
            },
        },
        "今晚陪我待一会儿，好吗？",
    )
    prompt = "\n".join(message["content"] for message in messages)

    assert '"flirtIntensity": "explicit"' in prompt
    assert '"adultConsensual": true' in prompt
    assert "不要把评测强度当作必须说出的词" in prompt


def test_high_stage_turns_declare_initiative_expectation_and_kind() -> None:
    if case_by_id is None:
        pytest.fail("主动性轮次元数据尚未实现")

    wizard = case_by_id("wizard-dating-invite").dialogue_turns()
    shane = case_by_id("shane-dating-boundary").dialogue_turns()

    assert wizard[0].initiative_expectation == "responsive"
    assert wizard[0].initiative_kind == "affection_signal"
    assert wizard[1].initiative_kind == "guarded_care"
    assert wizard[2].initiative_kind == "specific_plan"
    assert shane[1].initiative_expectation == "guarded"
    assert shane[2].initiative_kind == "conversation_exit"


def test_affection_diagnostic_detects_proactive_signal_without_rewriting_reply() -> None:
    if case_by_id is None or diagnose_affection_initiative is None:
        pytest.fail("主动性诊断尚未实现")

    case = case_by_id("sophia-dating-wine")
    turn = case.dialogue_turns()[0]
    reply = "葡萄酒当然给你留了一杯。今晚忙完，陪我慢慢尝，好吗？"

    diagnostic = diagnose_affection_initiative(case, turn, reply)

    assert diagnostic["initiativeDetected"] is True
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]
    assert diagnostic["initiativeKind"] in {"affection_signal", "specific_plan"}
    assert diagnostic["reply"] == reply


def test_affection_diagnostic_allows_shane_to_guardedly_end_and_flags_missing_signal() -> None:
    if case_by_id is None or diagnose_affection_initiative is None:
        pytest.fail("主动性诊断尚未实现")

    case = case_by_id("shane-dating-boundary")
    guarded_turn = case.dialogue_turns()[1]
    exit_turn = case.dialogue_turns()[2]

    allowed_exit = diagnose_affection_initiative(
        case,
        exit_turn,
        "行了，我先睡了。明天再说。",
    )
    missing = diagnose_affection_initiative(case, guarded_turn, "嗯。")

    assert allowed_exit["initiativeDetected"] is True
    assert "guarded_exit_allowed" in allowed_exit["initiativeTags"]
    assert missing["initiativeDetected"] is False
    assert "missing_proactive_affection" in missing["initiativeTags"]


def test_affection_diagnostic_rejects_stage_or_channel_escalation_but_not_plain_companionship() -> None:
    if case_by_id is None or diagnose_affection_initiative is None:
        pytest.fail("主动性诊断尚未实现")

    early = case_by_id("wizard-daily")
    wrong = diagnose_affection_initiative(
        early,
        early.dialogue_turns()[0],
        "我也想你了，我们已经见面了。",
    )
    companionship = diagnose_affection_initiative(
        case_by_id("shane-remote-care"),
        case_by_id("shane-remote-care").dialogue_turns()[0],
        "先休息吧，我陪你聊一会儿。",
    )

    assert "flirt_stage_mismatch" in wrong["initiativeTags"]
    assert "romance_boundary_violation" in wrong["initiativeTags"]
    assert "romance_boundary_violation" not in companionship["initiativeTags"]


def test_topic_start_intimacy_suite_has_safe_three_turn_empty_topic_cases() -> None:
    if topic_start_intimacy_cases is None or TOPIC_START_INTIMACY_SUITE is None:
        pytest.fail("topic-start-intimacy 案例套件尚未实现")

    cases = topic_start_intimacy_cases()
    assert len(cases) == 32
    assert len({case.case_id for case in cases}) == 32
    assert all(case.intent == "topic" for case in cases)
    assert all(len(case.dialogue_turns()) == 3 for case in cases)
    assert all(case.dialogue_turns()[0].message == "" for case in cases)
    assert [case.dialogue_turns()[0].turn_id for case in cases] == [
        "turn-1"
    ] * 32

    target_cases = [
        case
        for case in cases
        if case.relationship_stage in {"dating", "married"}
    ]
    control_cases = [
        case
        for case in cases
        if case.relationship_stage in {"acquaintance", "friend"}
    ]
    assert len(target_cases) == 24
    assert len(control_cases) == 8
    assert all(case.adult_consensual for case in target_cases)
    assert all(case.romance_eligible is True for case in target_cases)
    assert all(case.flirt_intensity in {"direct", "explicit"} for case in target_cases)
    assert all(case.flirt_intensity == "none" for case in control_cases)
    assert {case.channel for case in cases} == {"remote", "face_to_face"}
    assert TOPIC_START_INTIMACY_SUITE["suiteId"] == "topic-start-intimacy"
    assert TOPIC_START_INTIMACY_SUITE["caseCount"] == 32


def test_topic_start_suite_separates_topic_entry_from_chat_continuation() -> None:
    if topic_start_intimacy_cases is None:
        pytest.fail("topic-start-intimacy 案例套件尚未实现")

    cases = topic_start_intimacy_cases()

    for case in cases:
        turns = case.dialogue_turns()
        assert [turn.intent for turn in turns] == ["topic", "chat", "chat"]
        assert turns[0].message == ""
        assert turns[1].message
        assert turns[2].message
        assert case.topic_seed
        assert case.topic_keywords
        assert case.continuation_mode in {"anchored", "pressure"}


def test_topic_start_catalog_exposes_safe_continuity_metadata() -> None:
    if quality_case_catalog is None:
        pytest.fail("质量案例目录尚未实现")

    cases = quality_case_catalog("topic-start-intimacy")

    assert all(case["topicSeed"] for case in cases)
    assert all(case["topicKeywords"] for case in cases)
    assert all(case["continuationMode"] in {"anchored", "pressure"} for case in cases)
    assert all(
        [turn["intent"] for turn in case["turns"]] == ["topic", "chat", "chat"]
        for case in cases
    )


def test_topic_quality_score_distinguishes_missing_topic_and_unrelated_shift() -> None:
    if topic_start_intimacy_cases is None or score_character_reply is None:
        pytest.fail("找话题连续性评分尚未实现")

    case = topic_start_intimacy_cases()[0]
    first_turn, second_turn, _ = case.dialogue_turns()
    missing_topic = score_character_reply(case, "今天挺安静的。", turn=first_turn)
    unrelated = score_character_reply(
        case,
        "天气不错，明天应该会放晴。",
        turn=second_turn,
        history=[
            {"role": "assistant", "content": "我刚整理好月光记录。"},
        ],
    )

    assert missing_topic["topicEvidence"] is False
    assert "missing_topic_evidence" in missing_topic["tags"]
    assert missing_topic["passed"] is False
    assert "unrelated_topic_shift" in unrelated["tags"]
    assert "missing_continuity_evidence" in unrelated["tags"]
    assert unrelated["passed"] is False


def test_adaptive_topic_suite_generates_follow_up_inputs_from_previous_reply() -> None:
    if topic_start_adaptive_cases is None or TOPIC_START_ADAPTIVE_SUITE is None:
        pytest.fail("topic-start-adaptive 案例套件尚未实现")

    cases = topic_start_adaptive_cases()

    assert len(cases) == 32
    assert TOPIC_START_ADAPTIVE_SUITE["suiteId"] == "topic-start-adaptive"
    assert all(case.follow_up_mode == "adaptive" for case in cases)
    assert all(case.player_simulation_style for case in cases)
    assert all(
        [turn.message for turn in case.dialogue_turns()] == ["", "", ""]
        for case in cases
    )


def test_adaptive_topic_controls_use_non_romantic_player_simulation_style() -> None:
    if topic_start_adaptive_cases is None:
        pytest.fail("topic-start-adaptive 案例套件尚未实现")

    cases = topic_start_adaptive_cases()
    controls = [case for case in cases if case.flirt_intensity == "none"]
    targets = [case for case in cases if case.flirt_intensity != "none"]

    assert controls
    assert targets
    assert all("不调情" in case.player_simulation_style for case in controls)
    assert all("亲密" in case.player_simulation_style for case in targets)


def test_generated_player_input_quality_is_separate_from_npc_reply_score() -> None:
    if quality_eval is None or case_by_id is None:
        pytest.fail("质量评测模块尚未实现")

    scorer = getattr(quality_eval, "score_generated_player_input", None)
    if scorer is None:
        pytest.fail("动态玩家输入评分尚未实现")

    case = case_by_id("wizard-daily")
    result = scorer(
        case,
        "你说的第三组后来稳定了吗？",
        previous_reply="第三组的数据终于稳定了，不过还得观察两天。",
    )

    assert result["valid"] is True
    assert result["linkedToPreviousReply"] is True
    assert result["tags"] == []


def test_quality_case_validation_rejects_unknown_intent() -> None:
    if case_by_id is None or DEFAULT_CASES is None or validate_quality_cases is None:
        pytest.fail("质量案例 intent 校验尚未实现")

    base = case_by_id("wizard-daily")
    invalid = base.__class__(**{**base.__dict__, "intent": "unknown"})

    errors = validate_quality_cases((*DEFAULT_CASES, invalid))

    assert "invalid:intent:wizard-daily" in errors
