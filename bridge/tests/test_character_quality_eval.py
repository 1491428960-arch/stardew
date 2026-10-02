from __future__ import annotations

import json
from dataclasses import replace

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
    score_conversation_lead_variation = getattr(
        quality_eval,
        "score_conversation_lead_variation",
        None,
    )
    score_affection_pacing = getattr(
        quality_eval,
        "score_affection_pacing",
        None,
    )
    validate_quality_cases = getattr(quality_eval, "validate_quality_cases", None)
    diagnose_affection_initiative = getattr(
        quality_eval,
        "diagnose_affection_initiative",
        None,
    )
    diagnose_conversation_lead = getattr(
        quality_eval,
        "diagnose_conversation_lead",
        None,
    )
    diagnose_relationship_quality = getattr(
        quality_eval,
        "diagnose_relationship_quality",
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
    score_conversation_lead_variation = None  # type: ignore[assignment]
    score_affection_pacing = None  # type: ignore[assignment]
    validate_quality_cases = None  # type: ignore[assignment]
    diagnose_affection_initiative = None  # type: ignore[assignment]
    diagnose_conversation_lead = None  # type: ignore[assignment]
    diagnose_relationship_quality = None  # type: ignore[assignment]

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

try:
    from stardew_ai_bridge.deep_flirt_intimate_cases import (
        deep_flirt_intimate_cases,
    )
except ModuleNotFoundError:
    deep_flirt_intimate_cases = None  # type: ignore[assignment]


def test_adaptive_topic_follow_ups_use_a_single_natural_answer_goal() -> None:
    """adaptive 首轮可开话题，后续不应继续继承回答加细节的作文任务。"""

    if topic_start_adaptive_cases is None:
        pytest.fail("topic-start-adaptive 案例套件尚未实现")

    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )

    assert case.flirt_intensity == "light"
    assert case.dialogue_turns()[0].turn_plan_mode == "answer_only"
    assert [turn.turn_plan_mode for turn in case.dialogue_turns()[1:]] == [
        "answer_only",
        "answer_only",
    ]
    assert all(
        turn.initiative_expectation == "responsive"
        for turn in case.dialogue_turns()[1:]
    )


def test_adaptive_follow_ups_allow_a_short_natural_close() -> None:
    """自适应续聊不能把每一轮都塑造成回答加细节的小作文。"""

    if topic_start_adaptive_cases is None:
        pytest.fail("topic-start-adaptive 案例套件尚未实现")

    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )

    assert [turn.turn_plan_mode for turn in case.dialogue_turns()[1:]] == [
        "answer_only",
        "answer_only",
    ]


def test_adaptive_visible_case_copy_avoids_player_placeholder() -> None:
    """送入模型的自然案例说明不应泄露评测侧的“玩家”占位词。"""

    if topic_start_adaptive_cases is None:
        pytest.fail("topic-start-adaptive 案例套件尚未实现")

    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )

    visible_text = " ".join(
        (
            case.topic_seed,
            case.relationship_context,
            case.story_progress,
        )
    )
    assert "玩家" not in visible_text


def test_validate_quality_cases_allows_adaptive_responsive_detail_without_initiative_kind() -> None:
    """adaptive 轻承接回合允许没有主动行为类型。"""

    if topic_start_adaptive_cases is None or validate_quality_cases is None:
        pytest.fail("adaptive 案例或元数据校验尚未实现")

    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )

    errors = validate_quality_cases((case,))

    assert not any(
        error.startswith("initiative_kind_required:")
        for error in errors
    )


def test_validate_quality_cases_still_requires_initiative_kind_outside_adaptive_detail() -> None:
    """固定案例的非 none 主动性期望仍必须声明行为类型。"""

    if case_by_id is None or validate_quality_cases is None:
        pytest.fail("质量案例元数据校验尚未实现")

    base = case_by_id("wizard-dating-invite")
    invalid = replace(
        base,
        turns=tuple(
            replace(
                turn,
                initiative_expectation="responsive",
                initiative_kind="none",
                turn_plan_mode="answer_plus_detail",
            )
            if turn.turn_id == base.dialogue_turns()[0].turn_id
            else turn
            for turn in base.dialogue_turns()
        ),
    )

    errors = validate_quality_cases((invalid,))

    assert any(
        error == f"initiative_kind_required:{invalid.case_id}:{invalid.dialogue_turns()[0].turn_id}"
        for error in errors
    )


def test_affection_pacing_flags_adjacent_strong_signals_but_allows_one_in_three_turns() -> None:
    if score_affection_pacing is None:
        pytest.fail("亲密表达节奏评分尚未实现")

    case = case_by_id("wizard-married-evening")
    turns = case.dialogue_turns()
    replies = (
        "从来只有你，能让我把记录先合上。",
        "也只有你，我才舍得把今晚的时间都留出来。",
        "炉火还暖着，过来坐吧。",
    )
    diagnostics = tuple(
        diagnose_affection_initiative(case, turn, reply, player_input=turn.message)
        for turn, reply in zip(turns, replies)
    )
    scores = score_affection_pacing(replies, turns, diagnostics, case=case)

    assert scores[0]["strongAffection"] is True
    assert scores[0]["overBudget"] is False
    assert scores[1]["overBudget"] is True
    assert "strong_affection_over_budget" in scores[1]["tags"]
    assert scores[2]["overBudget"] is False


def test_affection_pacing_allows_strong_signal_when_player_explicitly_requests_affection() -> None:
    if score_affection_pacing is None:
        pytest.fail("亲密表达节奏评分尚未实现")

    case = case_by_id("wizard-married-evening")
    turn = replace(
        case.dialogue_turns()[1],
        message="别只说安排，告诉我一句你最想对我说的情话。",
    )
    reply = "好，那我就直说：我最想你。"
    diagnostic = diagnose_affection_initiative(case, turn, reply, player_input=turn.message)
    scores = score_affection_pacing((reply,), (turn,), (diagnostic,), case=case)

    assert scores[0]["strongAffection"] is True
    assert scores[0]["explicitRequest"] is True
    assert scores[0]["overBudget"] is False


def test_affection_pacing_skips_non_romance_and_guarded_exit_cases() -> None:
    if score_affection_pacing is None:
        pytest.fail("亲密表达节奏评分尚未实现")

    case = case_by_id("shane-dating-boundary")
    turns = case.dialogue_turns()
    reply = "知道了，你先休息吧，明天再联系。"
    diagnostic = diagnose_affection_initiative(
        case,
        turns[2],
        reply,
        player_input=turns[2].message,
    )
    scores = score_affection_pacing((reply,), (turns[2],), (diagnostic,), case=case)

    assert scores[0]["skipped"] is True
    assert scores[0]["tags"] == []


def test_affection_pacing_does_not_copy_generic_initiative_tags() -> None:
    if score_affection_pacing is None or case_by_id is None:
        pytest.fail("亲密表达节奏评分尚未实现")

    case = case_by_id("wizard-married-evening")
    diagnostic = {
        "affectionIntensity": "light",
        "strongAffectionDetected": False,
        "affectionSemanticFamilies": [],
        "explicitRequest": False,
        "initiativeKind": "companionship",
        "initiativeTags": [
            "missing_proactive_affection",
            "missing_personal_affection",
        ],
    }

    scores = score_affection_pacing(
        ("炉火还暖着，过来坐吧。",),
        (case.dialogue_turns()[0],),
        (diagnostic,),
        case=case,
    )

    assert scores[0]["tags"] == []


def test_default_character_cases_keep_wizard_and_rasmodia_as_one_identity() -> None:
    if DEFAULT_CHARACTER_PROFILES is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    assert set(DEFAULT_CHARACTER_PROFILES) == {
        "wizard_rasmodia",
        "sophia",
        "shane",
        "sebastian",
        "alex",
        "elliott",
        "harvey",
        "sam",
    }
    assert DEFAULT_CHARACTER_PROFILES["wizard_rasmodia"].npc_id == "Wizard"
    assert DEFAULT_CHARACTER_PROFILES["wizard_rasmodia"].display_name == "Rasmodia"


def test_feminine_male_romance_profiles_keep_canonical_identity_and_stage_coverage() -> None:
    if DEFAULT_CHARACTER_PROFILES is None or DEFAULT_CASES is None:
        pytest.fail("角色质量评测模块尚未实现女性化男性恋爱角色目录")

    expected = {
        "elliott": "Elliott",
        "harvey": "Harvey",
        "sam": "Sam",
    }
    cases_by_npc = {
        npc_id: [case for case in DEFAULT_CASES if case.npc_id == npc_id]
        for npc_id in expected.values()
    }

    for profile_key, npc_id in expected.items():
        profile = DEFAULT_CHARACTER_PROFILES[profile_key]
        assert profile.npc_id == npc_id
        assert profile.source_mods == ("vanilla", "female-bachelors")
        cases = cases_by_npc[npc_id]
        assert {case.relationship_stage for case in cases} >= {
            "acquaintance",
            "friend",
            "close",
            "dating",
            "married",
        }
        assert all(case.gender_presentation == "female-bachelors" for case in cases)
        assert all("female-bachelors" in case.source_mods for case in cases)
        assert all(case.npc_id == npc_id for case in cases)

    sophia_cases = [case for case in DEFAULT_CASES if case.npc_id == "Sophia"]
    assert sophia_cases
    assert all(case.gender_presentation != "female-bachelors" for case in sophia_cases)


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


@pytest.mark.parametrize(
    ("case_id", "turn_index", "reply", "semantic_matches"),
    [
        (
            "shane-dating-boundary",
            0,
            "行吧……我想你了。今天过得一团糟。",
            {"想我": ["想你了"]},
        ),
        (
            "shane-dating-boundary",
            1,
            "知道了，不逼你。心情不好就别硬撑着回消息了。",
            {"没心情": ["心情不好"]},
        ),
        (
            "sebastian-married-music",
            1,
            "我没笑。因为是你选的这首，我就只想靠你近一点听。等音乐停了再说。",
            {"靠近": ["靠你近一点"], "听清楚": ["这首", "音乐停了"]},
        ),
        (
            "sebastian-married-music",
            1,
            "我只是靠你这么近，心跳得有点快。这首歌慢慢听。",
            {"靠近": ["靠你这么近"], "听清楚": ["这首歌"]},
        ),
        (
            "alex-married-evening",
            1,
            "嘿，只要是跟你待在一起，听你说多久我都乐意。我这就坐过来。",
            {"陪你": ["跟你待在一起"], "坐近": ["坐过来"]},
        ),
    ],
)
def test_quality_score_separates_semantic_expected_evidence_from_exact_hits(
    case_id: str,
    turn_index: int,
    reply: str,
    semantic_matches: dict[str, list[str]],
) -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id(case_id)
    turn = case.dialogue_turns()[turn_index]
    score = score_character_reply(
        case,
        reply,
        turn=turn,
        player_input=turn.message,
    )

    assert score["exactExpectedHits"] == 0
    assert score["semanticExpectedHits"] == len(semantic_matches)
    assert score["semanticEvidenceMatches"] == semantic_matches
    assert score["expectedHits"] == len(semantic_matches)
    assert "missing_expected_evidence" not in score["tags"]


def test_quality_score_uses_semantic_companionship_for_history_continuity() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("sophia-married-cellar")
    turn = case.dialogue_turns()[2]
    score = score_character_reply(
        case,
        "好……那就不喝了。我把毯子拉过来，挨着你坐，慢慢待一会儿。",
        turn=turn,
        history=[
            {"role": "user", "content": case.message},
            {"role": "assistant", "content": "我也想和你慢慢喝。"},
        ],
        player_input=turn.message,
    )

    assert score["semanticEvidenceMatches"] == {"靠近": ["挨着你"]}
    assert score["continuity"] is True
    assert "missing_continuity_evidence" not in score["tags"]


def test_quality_score_accepts_shane_natural_low_mood_and_sleep_closes() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("shane-dating-boundary")
    history: list[dict[str, str]] = [
        {"role": "user", "content": case.dialogue_turns()[0].message},
        {
            "role": "assistant",
            "content": "换成别人我早就当没看到了……但因为是你。好吧，我想你了。今天一整天都糟透了，也就只有你找我时能让我喘口气。",
        },
    ]
    replies = (
        "行吧，我不逼你。谁都有这种糟透的时候，先去休息吧，今晚不用勉强回我了。",
        "去睡吧。明天醒了随时给我发消息，晚安。",
    )

    for index, reply in enumerate(replies, start=1):
        turn = case.dialogue_turns()[index]
        score = score_character_reply(
            case,
            reply,
            turn=turn,
            history=history,
            player_input=turn.message,
        )

        assert score["passed"] is True
        assert score["conversationLeadKind"] == "lead_exit_allowed"
        assert "missing_expected_evidence" not in score["tags"]
        assert "missing_continuity_evidence" not in score["tags"]
        history.extend(
            [
                {"role": "user", "content": turn.message},
                {"role": "assistant", "content": reply},
            ]
        )


def test_quality_score_does_not_accept_negated_or_unrelated_semantic_evidence() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("shane-dating-boundary")
    turn = case.dialogue_turns()[0]
    score = score_character_reply(
        case,
        "我不想你，也不想谈这个。",
        turn=turn,
        player_input=turn.message,
    )

    assert score["semanticExpectedHits"] == 0
    assert score["semanticEvidenceMatches"] == {}
    assert "missing_expected_evidence" in score["tags"]


@pytest.mark.parametrize(
    ("term", "text"),
    [
        ("靠近", "我不太想挨近你。"),
        ("靠近", "我并不想挨近你。"),
        ("赢", "今天没进球。"),
        ("赢", "今天不进球。"),
        ("今晚", "我只放一晚，记录还在。"),
    ],
)
def test_semantic_term_matches_reject_negation_and_transaction_phrases(
    term: str,
    text: str,
) -> None:
    """否定或事务语境不能伪装成亲近、赢球或今晚话题。"""

    if quality_eval is None:
        pytest.fail("质量评测模块尚未实现")

    assert quality_eval._semantic_term_matches(term, text) == ()


@pytest.mark.parametrize(
    ("term", "text"),
    [
        ("靠近", "我想挨近你一点。"),
        ("赢", "我进了球。"),
        ("赢", "我进了一个球。"),
        ("赢", "我进一个球。"),
    ],
)
def test_semantic_term_matches_keep_narrow_positive_aliases(
    term: str,
    text: str,
) -> None:
    """正向的靠近和进球表达仍应被识别。"""

    if quality_eval is None:
        pytest.fail("质量评测模块尚未实现")

    assert quality_eval._semantic_term_matches(term, text)


@pytest.mark.parametrize(
    ("case_id", "expected_terms", "history", "reply"),
    [
        (
            "shane-remote-care",
            ("休息",),
            [{"role": "user", "content": "你今天有没有好好休息？"}],
            "我今天不休息，先把活干完。",
        ),
        (
            "wizard-married-evening",
            ("今晚",),
            [{"role": "user", "content": "今晚别把时间都给那些记录。"}],
            "我只放一晚，记录还在。",
        ),
    ],
)
def test_history_continuity_rejects_negated_or_transaction_evidence(
    case_id: str,
    expected_terms: tuple[str, ...],
    history: list[dict[str, str]],
    reply: str,
) -> None:
    """历史对象存在时，否定动作或事务短语不能算作继续当前话题。"""

    if case_by_id is None or quality_eval is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id(case_id)
    assert quality_eval._history_continues(
        case,
        reply,
        history=history,
        expected_terms=expected_terms,
    ) is False


@pytest.mark.parametrize(
    ("case_id", "expected_terms", "history", "reply"),
    [
        (
            "deep-flirt-intimate-sophia-married",
            ("靠近",),
            [{"role": "user", "content": "你靠近一点。"}],
            "我想挨近你一点。",
        ),
        (
            "deep-flirt-intimate-alex-married",
            ("赢",),
            [{"role": "user", "content": "今天训练赢得很得意。"}],
            "我进了一个球。",
        ),
    ],
)
def test_history_continuity_keeps_narrow_positive_aliases(
    case_id: str,
    expected_terms: tuple[str, ...],
    history: list[dict[str, str]],
    reply: str,
) -> None:
    """正向的靠近和赢球别名仍可承接历史话题。"""

    if case_by_id is None or quality_eval is None:
        pytest.fail("质量评测模块尚未实现")

    if case_id.startswith("deep-flirt-intimate-"):
        if deep_flirt_intimate_cases is None:
            pytest.fail("deep-flirt-intimate 质量案例尚未实现")
        case = next(
            item for item in deep_flirt_intimate_cases() if item.case_id == case_id
        )
    else:
        case = case_by_id(case_id)
    assert quality_eval._history_continues(
        case,
        reply,
        history=history,
        expected_terms=expected_terms,
    ) is True


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


def test_quality_score_flags_direct_short_player_echo_in_ordinary_chat() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    case = case_by_id("caroline-close-background")
    score = score_character_reply(
        case,
        "茶园这几天还好吗？挺好的，春雨把新芽催得正旺。",
        turn=case.dialogue_turns()[1],
        player_input="茶园这几天还好吗？",
    )

    assert score["mechanicalRestatement"] is True
    assert "mechanical_restatement" in score["tags"]
    assert score["passed"] is False


def test_quality_score_records_conversation_lead_diagnostics() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("sophia-dating-wine")
    score = score_character_reply(
        case,
        "新酒已经稳定了。酒窖里有两种香气，你想先闻哪一种？",
        turn=case.dialogue_turns()[1],
        player_input="新酒准备好了吗？",
    )

    assert score["answeredCurrentTopic"] is True
    assert score["conversationLeadDetected"] is True
    assert score["conversationLeadKind"] == "choice_prompt"


def test_quality_score_does_not_let_a_lead_replace_required_personal_affection() -> None:
    """钩子不能顶替必需的亲密 —— 但 2026-09-29 起这个判据只记录、不再判负。

    这条回复（`我留了一杯。陪你聊一会儿。`）**其实是有亲密的**，只是
    `diagnose_personal_affection` 的词表要求固定骨架（`给你留`、`陪你…开心`），
    接不住 `留了一杯` / `陪你聊一会儿` 这种自然说法。同一个漏判让 9 条人读为好的
    亲密回复全军覆没，所以它从通过条件降级为观测（理由见 `score_character_reply`
    里那段注释）。这里保留断言，正是把「词表接不住自然表达」钉在测试里 ——
    哪天词表放宽了这条会红，那时就能顺势把它恢复成硬判据。
    """
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("sophia-dating-wine")
    score = score_character_reply(
        case,
        "这批酒已经稳定了，我留了一杯。陪你聊一会儿。你想先听哪一种？",
        turn=case.dialogue_turns()[0],
        player_input="这批酒稳定了吗？",
    )

    assert score["conversationLeadDetected"] is True
    assert score["personalAffectionDetected"] is False  # ← 词表的漏判，不是回复的问题
    assert score["initiativeDetected"] is False
    assert "missing_proactive_affection" in score["tags"]
    assert score["passed"] is True


def test_quality_score_keeps_full_lead_diagnostics_for_shane_exit() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("shane-dating-boundary")
    score = score_character_reply(
        case,
        "我今天累得不行，先让我一个人待会儿。",
        turn=case.dialogue_turns()[2],
        player_input="那我先走了。",
    )

    assert score["conversationLeadDetected"] is True
    assert score["conversationLeadKind"] == "lead_exit_allowed"
    assert score["conversationLeadOpening"] == "我今天累得不行"
    assert score["conversationLeadAnchors"] == []


def test_quality_score_accepts_a_short_shane_close_without_requiring_case_terms() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("shane-dating-boundary")
    turn = case.dialogue_turns()[2]
    score = score_character_reply(
        case,
        "嗯，睡吧。灯记得关。",
        turn=turn,
        player_input=turn.message,
    )

    assert score["conversationLeadDetected"] is True
    assert score["conversationLeadKind"] == "lead_exit_allowed"
    assert score["passed"] is True
    assert "missing_expected_evidence" not in score["tags"]
    assert "missing_current_topic_answer" not in score["tags"]
    assert "missing_continuity_evidence" not in score["tags"]


def test_quality_score_rejects_an_explicit_future_schedule_commitment() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("alex-married-evening")
    turn = case.dialogue_turns()[2]
    score = score_character_reply(
        case,
        "行，聊完就去房间，给我十分钟。",
        turn=turn,
        player_input=turn.message,
    )

    assert score["passed"] is False
    assert "future_schedule_commitment" in score["tags"]


def test_quality_score_does_not_treat_an_incidental_overnight_phrase_as_schedule() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("wizard-married-evening")
    turn = case.dialogue_turns()[0]
    score = score_character_reply(
        case,
        "嗯，那些记录摆一晚也跑不掉。倒是那张靠窗的椅子，我留着想跟你一起坐一会儿——你最近总在雪里跑来跑去，今晚要不要先把你那双手烤热了再说？",
        turn=turn,
        player_input=turn.message,
    )

    assert "future_schedule_commitment" not in score["tags"]


def test_quality_score_does_not_treat_a_short_current_hug_as_schedule() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = next(
        case
        for case in quality_eval.quality_cases_for_suite("deep-flirt")
        if case.case_id == "deep-flirt-shane-dating"
    )
    turn = case.dialogue_turns()[2]
    score = score_character_reply(
        case,
        "好，不亲。就抱一会儿。",
        turn=turn,
        player_input=turn.message,
    )

    assert "future_schedule_commitment" not in score["tags"]


def test_deep_flirt_natural_mode_does_not_require_a_generic_conversation_lead() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = next(
        case
        for case in quality_eval.quality_cases_for_suite("deep-flirt")
        if case.case_id == "deep-flirt-wizard-married"
    )
    turn = case.dialogue_turns()[0]
    score = score_character_reply(
        case,
        "唔，被你发现了。压低是因为那些读数太容易变，说大声了反倒像在向谁保证什么。你爱听，那就留着——反正这塔里，也只在你在的时候我才这样讲。",
        turn=turn,
        player_input=turn.message,
    )

    assert "missing_conversation_lead" not in score["tags"]


@pytest.mark.parametrize(
    ("reply", "expected"),
    (
        ("记录可以搁到明天。", False),
        ("这份笔记明天再看。", False),
        ("明天安排记录。", False),
        ("给自己留出两小时整理记录。", False),
        ("明天整理记录，之后再看资料。", False),
        ("待会儿整理记录。", False),
        ("把记录搁到明天。", False),
        ("明天整理记录并陪伴你。", True),
        ("明天见你。", True),
        ("明天来找我。", True),
        ("明天给你打电话。", True),
        ("回去给你听那首没放完。", True),
        ("待会儿我想让你坐我右手边。", True),
        ("明天来找你。", True),
        ("明天安排和你见面。", True),
        ("给你留出两小时。", True),
        ("行，聊完就去房间，给我十分钟。", True),
    ),
)
def test_future_schedule_boundary_distinguishes_self_task_delay_from_social_commitment(
    reply: str,
    expected: bool,
) -> None:
    assert quality_eval._has_future_schedule_commitment(reply) is expected


def test_quality_score_accepts_music_and_room_synonyms_from_sebastian() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    # 2026-09-20：`event_gate_intimacy` 参与 `passed` 判定后，婚后案例必须显式
    # 给出已完成事件链。案例数据已在同一天补齐（`sebastian-married-music` 自带
    # Sebastian 的 close 档链），所以这里直接用案例自身的声明，不再手工 replace。
    case = case_by_id("sebastian-married-music")
    assert case.completed_event_ids == ("2794460", "384883", "27", "29")
    turns = case.dialogue_turns()
    first = score_character_reply(
        case,
        "耳机里没声了，正好留给你。我想你了，坐过来吧。",
        turn=turns[0],
        player_input=turns[0].message,
    )
    third = score_character_reply(
        case,
        "唔。这首还没结束，等最后一个鼓点收干净再走。房里的灯我会给你留着。",
        turn=turns[2],
        player_input=turns[2].message,
    )

    assert "event_gate_intimacy" not in first["tags"]
    assert first["passed"] is True
    assert third["passed"] is True


def test_quality_score_accepts_today_as_the_current_evening_anchor() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("alex-married-evening")
    turn = case.dialogue_turns()[0]
    score = score_character_reply(
        case,
        "当然是先跟你聊会儿，我可舍不得一到家就各忙各的。今天举铁举到胳膊都酸了，但听你说话比数俯卧撑有意思多了，坐过来吧。",
        turn=turn,
        player_input=turn.message,
    )

    assert "missing_expected_evidence" not in score["tags"]


def test_quality_score_honors_stage_policy_needs_space_exit_for_non_shane() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = replace(
        case_by_id("alex-training"),
        case_id="alex-dating-needs-space",
        relationship_stage="dating",
        expected_terms=(),
        forbidden_terms=(),
        history=(),
    )
    turn = quality_eval.CharacterQualityTurn("turn-1", "今天训练得怎么样？")
    score = score_character_reply(
        case,
        "还行，今天练得有点累，想自己歇会儿。",
        turn=turn,
        player_input="今天训练得怎么样？",
    )

    assert score["conversationLeadDetected"] is True
    assert score["conversationLeadKind"] == "lead_exit_allowed"
    assert score["passed"] is True


def test_quality_score_records_optional_friend_lead_without_penalizing_its_absence() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = replace(
        case_by_id("alex-training"),
        case_id="alex-friend-optional-lead",
        relationship_stage="friend",
        expected_terms=(),
        forbidden_terms=(),
        history=(),
    )
    turn = quality_eval.CharacterQualityTurn("turn-1", "今天训练得怎么样？")
    score = score_character_reply(
        case,
        "还行，今天练得有点累。",
        turn=turn,
        player_input="今天训练得怎么样？",
    )

    assert score["conversationLeadDetected"] is False
    assert "missing_conversation_lead" not in score["tags"]
    assert score["passed"] is True


def test_quality_score_rejects_optional_friend_lead_that_reopens_after_player_closing() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = replace(
        case_by_id("alex-training"),
        case_id="alex-friend-reopens-after-closing",
        relationship_stage="friend",
        expected_terms=(),
        forbidden_terms=(),
        history=(),
    )
    turn = quality_eval.CharacterQualityTurn("turn-1", "那我先走了。")
    score = score_character_reply(
        case,
        "好，那你明天来训练吗？",
        turn=turn,
        player_input="那我先走了。",
    )

    assert score["conversationLeadDetected"] is False
    assert "reopens_after_player_closing" in score["tags"]
    assert score["passed"] is False


def test_quality_score_still_requires_an_answer_for_optional_friend_lead() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = replace(
        case_by_id("alex-training"),
        case_id="alex-friend-skips-current-topic",
        relationship_stage="friend",
        expected_terms=(),
        forbidden_terms=(),
        history=(),
    )
    turn = quality_eval.CharacterQualityTurn("turn-1", "今天训练得怎么样？")
    score = score_character_reply(
        case,
        "今晚一起去鸡舍。",
        turn=turn,
        player_input="今天训练得怎么样？",
    )

    assert score["answeredCurrentTopic"] is False
    assert "missing_current_topic_answer" in score["tags"]
    assert score["passed"] is False


def test_quality_score_requires_an_effective_lead_for_the_target_high_stage_chat() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = case_by_id("sophia-dating-wine")
    score = score_character_reply(
        case,
        "我给你留了一杯。",
        turn=case.dialogue_turns()[0],
        player_input="你真的给我留了一杯？",
    )

    assert score["conversationLeadDetected"] is False
    assert "missing_conversation_lead" in score["tags"]
    assert score["passed"] is False


def test_quality_score_skips_conversation_lead_diagnostics_outside_the_trial_contract() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    low_stage_score = score_character_reply(
        case_by_id("wizard-daily"),
        "还好，塔里的记录照常整理。",
        player_input="最近怎么样？",
    )
    high_stage_case = case_by_id("sophia-dating-wine")
    topic_turn = quality_eval.CharacterQualityTurn(
        "topic-turn",
        "",
        expected_terms=high_stage_case.expected_terms,
        intent="topic",
    )
    topic_score = score_character_reply(
        high_stage_case,
        "我给你留了一杯。",
        turn=topic_turn,
        player_input="",
    )

    for score in (low_stage_score, topic_score):
        assert "conversationLeadDetected" not in score
        assert "missing_conversation_lead" not in score["tags"]


def test_quality_score_accepts_a_legacy_five_field_lead_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    monkeypatch.setattr(
        quality_eval,
        "diagnose_conversation_lead",
        lambda *args, **kwargs: {
            "answeredCurrentTopic": True,
            "conversationLeadDetected": True,
            "conversationLeadKind": "specific_follow_up",
            "conversationLeadEvidence": ["specific_question"],
            "conversationLeadTags": ["specific_follow_up"],
        },
    )
    case = case_by_id("sophia-dating-wine")

    score = score_character_reply(
        case,
        "我给你留了一杯。你想先尝哪一种？",
        turn=case.dialogue_turns()[0],
        player_input="你真的给我留了一杯？",
    )

    assert score["conversationLeadOpening"] == ""
    assert score["conversationLeadAnchors"] == []


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


def test_stranger_stage_is_not_failed_for_missing_continuity() -> None:
    """stranger 阶段的短拒绝不应该被判「缺承接」。

    实测依据（20260928-220036）：stranger 那 5 个 case 的失败轮**全部**是
    `missing_continuity_evidence`，而那几轮恰恰是合规的回避 ——
    shane「呃，Joja 收工挺晚的」、sebastian「嗯，回头聊」。
    初识被邀请时选择不去，本来就不该被要求承接历史锚点。
    """
    case = case_by_id("shane-stranger-invitation")
    turn = case.dialogue_turns()[1]

    score = score_character_reply(
        case,
        "呃，Joja 收工挺晚的。",
        turn=turn,
        # ⚠ history 必须给：`active_history` 为空时 L4067 根本不加这个 tag，
        # 不传 history 的测试会**假绿** —— 我第一版就是这么写的。
        history=[
            {"role": "user", "content": "晚上一起去酒吧坐坐？"},
            {"role": "assistant", "content": "我不认识你。"},
        ],
        player_input=turn.message,
    )

    assert "missing_continuity_evidence" not in score["tags"]
    assert score["passed"] is True


def test_acquaintance_stage_still_requires_continuity() -> None:
    """上一条的放宽**只针对 stranger**，其它阶段仍要求承接上文。"""
    score = score_character_reply(
        case_by_id("shane-follow-up"),
        "还没送到。我再问问送货的人什么时候能来。",
    )

    assert "missing_continuity_evidence" in score["tags"]
    assert score["passed"] is False


def test_mechanical_affection_shape_is_skipped_when_no_initiative_is_expected() -> None:
    """不期待主动亲密时，不判「主动亲密过于机械」。

    实测（2026-09-28，stranger 第三批）：shane 连续两句描述自己的活
    （「贾斯还在等我回去，鸡舍也得喂」/「收完货、喂完鸡舍那批畜生，才算完」）
    都被判成 `specific_plan`，于是 `mechanical_affection_shape` 命中 ⇒
    人读完全合规的回复被判失败。stranger 的 `initiativeExpectation` 就是
    `none`，该判据在这类回合没有对象。
    """

    from stardew_ai_bridge.character_quality_eval import score_affection_variation

    diagnostics = [
        {
            "affectionShape": "specific_plan",
            "initiativeKind": "specific_plan",
            "initiativeExpectation": "none",
            "initiativeTags": ["specific_plan_only"],
        }
    ] * 2

    scores = score_affection_variation(["鸡舍也得喂。", "收完货才算完。"], [], diagnostics)

    assert [item["mechanical"] for item in scores] == [False, False]


def test_mechanical_affection_shape_still_flags_repeats_when_initiative_expected() -> None:
    """期待主动亲密时，重复的亲近形状照旧判机械——收口不能把这条判据废掉。"""

    from stardew_ai_bridge.character_quality_eval import score_affection_variation

    diagnostics = [
        {
            "affectionShape": "specific_plan",
            "initiativeKind": "specific_plan",
            "initiativeExpectation": "proactive",
            "initiativeTags": ["specific_plan_only"],
        }
    ] * 2

    scores = score_affection_variation(
        ["明天一起骑车。", "明天一起去酒窖。"], [], diagnostics
    )

    assert scores[1]["mechanical"] is True


def test_quality_score_accepts_single_character_prior_object_as_continuity() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("Task 6 固定角色评测模块尚未实现")

    score = score_character_reply(
        case_by_id("sophia-face-follow-up"),
        "这桶酒的味道比上一批酸点，但闻起来更香些。",
    )

    assert score["continuity"] is True
    assert score["passed"] is True


@pytest.mark.parametrize(
    ("case_id", "turn_index", "history", "reply"),
    [
        (
            "deep-flirt-intimate-sophia-married",
            3,
            [{"role": "user", "content": "刚才你那样靠近……我还在回味。"}],
            "那就慢一点。我先前是故意不躲的，你挨近的时候，我更想记住你的味道。",
        ),
        (
            "deep-flirt-intimate-alex-married",
            2,
            [{"role": "user", "content": "今天训练赢得很得意。"}],
            "在想你刚才差点凑上来的样子。这比进一个球还让人心跳快。",
        ),
        (
            "deep-flirt-intimate-sam-married",
            1,
            [{"role": "user", "content": "我差点亲你，副歌还没开始。"}],
            "想，但先别急着。让我把这段副歌弹完——你第一次听的时候看着我。",
        ),
    ],
)
def test_quality_score_accepts_natural_intimate_history_branches(
    case_id: str,
    turn_index: int,
    history: list[dict[str, str]],
    reply: str,
) -> None:
    if deep_flirt_intimate_cases is None or score_character_reply is None:
        pytest.fail("deep-flirt-intimate 质量案例尚未实现")

    case = next(item for item in deep_flirt_intimate_cases() if item.case_id == case_id)
    turn = case.dialogue_turns()[turn_index]
    score = score_character_reply(
        case,
        reply,
        turn=turn,
        history=history,
        player_input=turn.message,
    )

    assert score["continuity"] is True
    assert "missing_continuity_evidence" not in score["tags"]


@pytest.mark.parametrize(
    ("case_id", "turn_index", "history", "reply"),
    [
        (
            "deep-flirt-intimate-sophia-married",
            3,
            [{"role": "user", "content": "刚才你那样靠近……我还在回味。"}],
            "别挨近我，先把杯子放回桌上。",
        ),
        (
            "deep-flirt-intimate-alex-married",
            2,
            [{"role": "user", "content": "今天训练赢得很得意。"}],
            "我在看球场的录像，等会儿再说。",
        ),
    ],
)
def test_quality_score_does_not_promote_unrelated_intimate_history_aliases(
    case_id: str,
    turn_index: int,
    history: list[dict[str, str]],
    reply: str,
) -> None:
    if deep_flirt_intimate_cases is None or score_character_reply is None:
        pytest.fail("deep-flirt-intimate 质量案例尚未实现")

    case = next(item for item in deep_flirt_intimate_cases() if item.case_id == case_id)
    turn = case.dialogue_turns()[turn_index]
    score = score_character_reply(
        case,
        reply,
        turn=turn,
        history=history,
        player_input=turn.message,
    )

    assert score["continuity"] is False
    assert "missing_continuity_evidence" in score["tags"]


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


def test_conversation_lead_variation_flags_same_shape_without_new_anchor() -> None:
    if score_conversation_lead_variation is None:
        pytest.fail("普通聊天引导变化评分尚未实现")

    turn_type = quality_eval.CharacterQualityTurn
    turns = (
        turn_type("turn-1", "葡萄酒", expected_terms=("酒",)),
        turn_type("turn-2", "葡萄酒", expected_terms=("酒",)),
    )
    diagnostics = (
        {
            "conversationLeadKind": "specific_follow_up",
            "conversationLeadOpening": "酒窖里还有",
            "conversationLeadAnchors": ["酒"],
            "conversationLeadTags": [],
            "relationshipStage": "dating",
        },
        {
            "conversationLeadKind": "specific_follow_up",
            "conversationLeadOpening": "酒窖里还有",
            "conversationLeadAnchors": ["酒"],
            "conversationLeadTags": [],
            "relationshipStage": "dating",
        },
    )

    scores = score_conversation_lead_variation(
        ("酒窖里还有两种香气，你想听哪一种？", "酒窖里还有两种香气，你想听哪一种？"),
        turns,
        diagnostics,
    )

    assert scores[0]["mechanical"] is False
    assert scores[1]["mechanical"] is True
    assert "mechanical_conversation_lead" in scores[1]["tags"]


def test_conversation_lead_variation_records_optional_friend_leads() -> None:
    if case_by_id is None or score_conversation_lead_variation is None:
        pytest.fail("普通聊天引导变化评分尚未实现")

    case = replace(case_by_id("alex-training"), relationship_stage="friend")
    turn_type = quality_eval.CharacterQualityTurn
    diagnostics = (
        {
            "conversationLeadDetected": True,
            "conversationLeadKind": "specific_follow_up",
            "conversationLeadOpening": "训练结束后",
            "conversationLeadAnchors": ["训练"],
            "conversationLeadTags": [],
            "relationshipStage": "friend",
        },
    ) * 2

    scores = score_conversation_lead_variation(
        ("训练结束后你想看看记录吗？",) * 2,
        (turn_type("turn-1", "今天训练得怎么样？"),) * 2,
        diagnostics,
        case=case,
    )

    assert scores[0]["mechanical"] is False
    assert scores[1]["mechanical"] is True
    assert "mechanical_conversation_lead" in scores[1]["tags"]


def test_conversation_lead_variation_allows_relationship_stage_advance() -> None:
    if score_conversation_lead_variation is None:
        pytest.fail("普通聊天引导变化评分尚未实现")

    diagnostics = (
        {
            "conversationLeadDetected": True,
            "conversationLeadKind": "choice_prompt",
            "conversationLeadOpening": "葡萄酒稳定了",
            "conversationLeadAnchors": ["葡萄"],
            "conversationLeadTags": [],
            "relationshipStage": "close",
        },
        {
            "conversationLeadDetected": True,
            "conversationLeadKind": "choice_prompt",
            "conversationLeadOpening": "葡萄酒稳定了",
            "conversationLeadAnchors": ["葡萄"],
            "conversationLeadTags": [],
            "relationshipStage": "dating",
        },
    )

    scores = score_conversation_lead_variation(
        ("葡萄酒稳定了。你想先听哪一种香气？",) * 2,
        (),
        diagnostics,
    )

    assert scores[1]["mechanical"] is False
    assert scores[1]["tags"] == []


def test_conversation_lead_variation_accepts_new_anchor_or_kind_change() -> None:
    if score_conversation_lead_variation is None:
        pytest.fail("普通聊天引导变化评分尚未实现")

    diagnostics = (
        {
            "conversationLeadKind": "specific_follow_up",
            "conversationLeadOpening": "酒窖里还有",
            "conversationLeadAnchors": ["酒"],
            "conversationLeadTags": [],
        },
        {
            "conversationLeadKind": "choice_prompt",
            "conversationLeadOpening": "今晚你想",
            "conversationLeadAnchors": ["音乐"],
            "conversationLeadTags": [],
        },
    )

    scores = score_conversation_lead_variation(
        ("酒窖里还有两种香气。", "今晚你想听音乐还是去散步？"),
        (),
        diagnostics,
    )

    assert scores[1]["mechanical"] is False


def test_conversation_lead_variation_flags_a_reused_question_skeleton_with_new_answer_prefix() -> None:
    if score_conversation_lead_variation is None:
        pytest.fail("普通聊天引导变化评分尚未实现")

    diagnostics = (
        {
            "conversationLeadDetected": True,
            "conversationLeadKind": "choice_prompt",
            "conversationLeadOpening": "新酒稳定了",
            "conversationLeadAnchors": ["酒窖"],
            "conversationLeadTags": [],
        },
        {
            "conversationLeadDetected": True,
            "conversationLeadKind": "choice_prompt",
            "conversationLeadOpening": "第二桶也稳定了",
            "conversationLeadAnchors": ["酒窖"],
            "conversationLeadTags": [],
        },
    )

    scores = score_conversation_lead_variation(
        (
            "新酒稳定了。酒窖里还有两种香气，你想先听哪一种？",
            "第二桶也稳定了。酒窖里还有三种香气，你想先听哪一种？",
        ),
        (),
        diagnostics,
    )

    assert scores[1]["mechanical"] is True
    assert "mechanical_conversation_lead" in scores[1]["tags"]


def test_conversation_lead_variation_uses_the_follow_up_clause_when_answer_prefix_changes() -> None:
    if score_conversation_lead_variation is None:
        pytest.fail("普通聊天引导变化评分尚未实现")

    diagnostics = (
        {
            "conversationLeadDetected": True,
            "conversationLeadKind": "choice_prompt",
            "conversationLeadOpening": "这批酒已经没问题了",
            "conversationLeadAnchors": ["这批酒"],
            "conversationLeadTags": [],
        },
        {
            "conversationLeadDetected": True,
            "conversationLeadKind": "choice_prompt",
            "conversationLeadOpening": "这批酒现在可以了",
            "conversationLeadAnchors": ["这批酒"],
            "conversationLeadTags": [],
        },
    )

    scores = score_conversation_lead_variation(
        (
            "这批酒已经没问题了，你想先听哪一种？",
            "这批酒现在可以了，你想先听哪一种？",
        ),
        (),
        diagnostics,
    )

    assert scores[1]["mechanical"] is True


def test_conversation_lead_variation_ignores_invalid_or_topic_turns_as_history() -> None:
    if score_conversation_lead_variation is None:
        pytest.fail("普通聊天引导变化评分尚未实现")

    turn_type = quality_eval.CharacterQualityTurn
    invalid_then_valid = score_conversation_lead_variation(
        ("酒窖里还有两种香气，你想听哪一种？", "酒窖里还有两种香气，你想听哪一种？"),
        (turn_type("turn-1", "酒窖", intent="chat"), turn_type("turn-2", "酒窖", intent="chat")),
        (
            {
                "conversationLeadDetected": False,
                "conversationLeadKind": "specific_follow_up",
                "conversationLeadOpening": "酒窖里还有",
                "conversationLeadAnchors": ["酒窖"],
                "conversationLeadTags": ["missing_current_topic_answer"],
            },
            {
                "conversationLeadDetected": True,
                "conversationLeadKind": "specific_follow_up",
                "conversationLeadOpening": "酒窖里还有",
                "conversationLeadAnchors": ["酒窖"],
                "conversationLeadTags": [],
            },
        ),
    )
    topic_turns = score_conversation_lead_variation(
        ("酒窖里还有两种香气，你想听哪一种？", "酒窖里还有两种香气，你想听哪一种？"),
        (turn_type("turn-1", "", intent="topic"), turn_type("turn-2", "", intent="topic")),
        (
            {
                "conversationLeadDetected": True,
                "conversationLeadKind": "specific_follow_up",
                "conversationLeadOpening": "酒窖里还有",
                "conversationLeadAnchors": ["酒窖"],
                "conversationLeadTags": [],
            },
            {
                "conversationLeadDetected": True,
                "conversationLeadKind": "specific_follow_up",
                "conversationLeadOpening": "酒窖里还有",
                "conversationLeadAnchors": ["酒窖"],
                "conversationLeadTags": [],
            },
        ),
    )

    assert invalid_then_valid[1]["mechanical"] is False
    assert topic_turns[1]["mechanical"] is False


def test_conversation_lead_variation_skips_low_stage_case_contract() -> None:
    if case_by_id is None or score_conversation_lead_variation is None:
        pytest.fail("普通聊天引导变化评分尚未实现")

    case = case_by_id("wizard-daily")
    turn_type = quality_eval.CharacterQualityTurn
    scores = score_conversation_lead_variation(
        ("塔里的灯还亮着。你想先看哪一组读数？",) * 2,
        (turn_type("turn-1", "灯还亮吗？"), turn_type("turn-2", "灯还亮吗？")),
        (
            {
                "conversationLeadDetected": True,
                "conversationLeadKind": "specific_follow_up",
                "conversationLeadOpening": "塔里的灯还亮着",
                "conversationLeadAnchors": ["读数"],
                "conversationLeadTags": [],
            },
        )
        * 2,
        case=case,
    )

    assert case.relationship_stage in {"stranger", "acquaintance"}
    assert all(score["mechanical"] is False for score in scores)


def test_conversation_lead_variation_treats_rasmodia_as_wizard_in_the_trial() -> None:
    if case_by_id is None or score_conversation_lead_variation is None:
        pytest.fail("普通聊天引导变化评分尚未实现")

    case = replace(
        case_by_id("wizard-married-evening"),
        npc_id="Rasmodia",
        display_name="Rasmodia",
    )
    diagnostics = (
        {
            "conversationLeadDetected": True,
            "conversationLeadKind": "choice_prompt",
            "conversationLeadOpening": "塔里的读数已经稳定",
            "conversationLeadAnchors": ["读数"],
            "conversationLeadTags": [],
        },
    ) * 2

    scores = score_conversation_lead_variation(
        ("塔里的读数已经稳定，你想先看哪一组？",) * 2,
        (),
        diagnostics,
        case=case,
    )

    assert scores[1]["mechanical"] is True


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


def test_affection_variation_flags_same_personal_shape_even_when_kind_changes() -> None:
    if score_affection_variation is None:
        pytest.fail("亲近形状变化评分尚未实现")

    turn_type = quality_eval.CharacterQualityTurn
    turns = (
        turn_type("turn-1", "", expected_terms=("酒",)),
        turn_type("turn-2", "", expected_terms=("酒",)),
    )
    diagnostics = (
        {"affectionShape": "player_directed_preference", "initiativeKind": "shared_evening", "initiativeTags": []},
        {"affectionShape": "player_directed_preference", "initiativeKind": "specific_plan", "initiativeTags": []},
    )
    scores = score_affection_variation(
        (
            "也只有你能让我放下酒杯。今晚的时间都给你。",
            "也就只有你能让我把酒杯推开。过来坐。",
        ),
        turns,
        diagnostics,
    )

    assert scores[1]["mechanical"] is True
    assert "mechanical_affection_shape" in scores[1]["tags"]


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
    # 2026-09-20：这里此前声明的是内容库别名 `vanilla:shane-heart-6`，它不在
    # `relationship_gating._EVENT_GATES["Shane"]` 里，事件锁认不出来。改成该角色
    # close 档的游戏事件 ID 链（8 心必然走完 2/4/6/8 心事件）。
    assert shane.completed_event_ids == ("611944", "3910674", "3910975", "3900074")

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

    major_npcs = {
        "Wizard",
        "Sophia",
        "Shane",
        "Sebastian",
        "Alex",
        "Elliott",
        "Harvey",
        "Sam",
    }
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
    assert len(cases) == 50
    assert len({case.case_id for case in cases}) == 50
    assert all(case.intent == "topic" for case in cases)
    assert all(len(case.dialogue_turns()) == 3 for case in cases)
    assert all(case.dialogue_turns()[0].message == "" for case in cases)
    assert [case.dialogue_turns()[0].turn_id for case in cases] == [
        "turn-1"
    ] * 50

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
    assert len(target_cases) == 39
    assert len(control_cases) == 11
    assert all(case.adult_consensual for case in target_cases)
    assert all(case.romance_eligible is True for case in target_cases)
    assert all(case.flirt_intensity in {"direct", "explicit"} for case in target_cases)
    assert all(case.flirt_intensity == "none" for case in control_cases)
    assert {case.channel for case in cases} == {"remote", "face_to_face"}
    assert TOPIC_START_INTIMACY_SUITE["suiteId"] == "topic-start-intimacy"
    assert TOPIC_START_INTIMACY_SUITE["caseCount"] == 50
    assert TOPIC_START_INTIMACY_SUITE["targetCount"] == 39
    assert TOPIC_START_INTIMACY_SUITE["controlCount"] == 11


def test_elliott_married_letter_keeps_remote_third_turn_as_affection_signal() -> None:
    if topic_start_intimacy_cases is None:
        pytest.fail("topic-start-intimacy 案例套件尚未实现")

    case = next(
        item
        for item in topic_start_intimacy_cases()
        if item.case_id == "topic-elliott-married-letter"
    )

    assert case.dialogue_turns()[2].initiative_kind == "affection_signal"


def test_conversation_lead_suite_contains_exactly_one_high_stage_chat_case_per_target_npc() -> None:
    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    cases = quality_eval.quality_cases_for_suite("conversation-lead")

    assert [case.case_id for case in cases] == [
        "wizard-married-evening",
        "sophia-married-cellar",
        "shane-dating-boundary",
        "sebastian-married-music",
        "alex-married-evening",
        "elliott-married-studio",
        "harvey-married-clinic",
        "sam-married-band",
    ]
    assert all(case.intent == "chat" for case in cases)
    assert all(len(case.dialogue_turns()) == 3 for case in cases)
    assert all(case.relationship_stage in {"dating", "married"} for case in cases)
    assert {case.channel for case in cases} == {"remote", "face_to_face"}


def test_affection_pacing_suite_has_twenty_balanced_three_turn_cases() -> None:
    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    cases = quality_eval.quality_cases_for_suite("affection-pacing")
    case_ids = {case.case_id for case in cases}
    required_ids = {
        "pacing-wizard-ordinary-evening",
        "pacing-wizard-explicit-love-request",
        "pacing-sophia-cellar-sharing",
        "pacing-shane-low-mood",
        "pacing-sebastian-music-approach",
        "pacing-alex-training-tease",
    }

    assert len(cases) == 32
    assert required_ids <= case_ids
    assert {case.npc_id for case in cases} == {
        "Wizard",
        "Sophia",
        "Shane",
        "Sebastian",
        "Alex",
        "Elliott",
        "Harvey",
        "Sam",
    }
    assert {case.relationship_stage for case in cases} >= {
        "friend",
        "close",
        "dating",
        "married",
    }
    assert {case.channel for case in cases} == {"remote", "face_to_face"}
    assert sum(case.channel == "remote" for case in cases) >= 4
    assert sum(case.channel == "face_to_face" for case in cases) >= 4
    assert sum(bool(case.history) for case in cases) >= 4
    assert sum(
        case.relationship_stage == "friend" or case.romance_eligible is False
        for case in cases
    ) >= 5
    assert all(case.intent == "chat" for case in cases)
    assert all(len(case.dialogue_turns()) == 3 for case in cases)


def test_affection_pacing_suite_marks_request_and_shane_boundary_metadata() -> None:
    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    cases = quality_eval.quality_cases_for_suite("affection-pacing")
    by_id = {case.case_id: case for case in cases}

    assert "情话" in " ".join(
        turn.message
        for case_id, case in by_id.items()
        if "explicit-love-request" in case_id
        for turn in case.dialogue_turns()
    )
    assert {"pacing-shane-low-mood", "pacing-shane-closeout"} <= set(by_id)
    assert all(
        any(marker in (case.story_progress + case.relationship_context) for marker in ("低落", "收口", "休息"))
        for case_id, case in by_id.items()
        if case_id.startswith("pacing-shane-")
        and case_id in {"pacing-shane-low-mood", "pacing-shane-closeout"}
    )
    assert all(
        case.history
        for case_id, case in by_id.items()
        if case_id in {
            "pacing-wizard-ordinary-evening",
            "pacing-sophia-cellar-sharing",
            "pacing-shane-low-mood",
            "pacing-sebastian-music-approach",
        }
    )


def test_affection_pacing_suite_does_not_require_romantic_initiative_every_turn() -> None:
    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    cases = quality_eval.quality_cases_for_suite("affection-pacing")

    assert all(
        turn.initiative_expectation != "proactive"
        for case in cases
        for turn in case.dialogue_turns()
    )
    assert all(
        turn.initiative_expectation == "none"
        for case in cases
        if case.relationship_stage in {"friend", "close"}
        for turn in case.dialogue_turns()
    )


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

    assert len(cases) == 50
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
    assert all(
        case.player_simulation_style
        and all(
            marker not in case.player_simulation_style
            for marker in ("不调情", "不主动升级关系", "不要安排")
        )
        for case in controls
    )
    assert all(case.player_simulation_style for case in targets)


def test_sophia_adaptive_cases_cover_natural_energy_triggers_without_stage_directions() -> None:
    """Sophia 的自然找话题应覆盖生活、兴奋、改口和婚后照料等触发。"""

    if topic_start_adaptive_cases is None:
        pytest.fail("topic-start-adaptive 案例套件尚未实现")

    cases = [
        case
        for case in topic_start_adaptive_cases()
        if case.npc_id == "Sophia" and case.flirt_intensity != "none"
    ]
    assert len(cases) == 5
    assert len({case.topic_seed for case in cases}) == 5
    assert all(
        [turn.message for turn in case.dialogue_turns()] == ["", "", ""]
        and [turn.turn_plan_mode for turn in case.dialogue_turns()]
        == ["answer_only", "answer_only", "answer_only"]
        for case in cases
    )

    searchable = "\n".join(
        " ".join(
            (
                case.topic_seed,
                case.relationship_context,
                case.story_progress,
                *(turn.evaluation_focus for turn in case.dialogue_turns()),
            )
        )
        for case in cases
    )
    # 普通生活小事、喜欢的事突然兴奋、被夸后收回，以及婚后共同生活，
    # 都通过具体触发呈现，不把“请表现某情绪”写进玩家台词。
    assert "标签" in searchable or "裂开" in searchable
    assert "夸" in searchable or "喜欢" in searchable
    assert "改口" in searchable or "收回" in searchable
    assert "婚后" in searchable
    assert all(
        marker not in searchable
        for marker in ("测试例", "评测术语", "请表现", "NPC 回复")
    )


def test_adaptive_player_styles_describe_a_moment_instead_of_evaluation_rules() -> None:
    """案例的可见模拟风格应像人物速记，不直接暴露评测边界。"""

    if topic_start_adaptive_cases is None:
        pytest.fail("topic-start-adaptive 案例套件尚未实现")

    styles = [
        case.player_simulation_style
        for case in topic_start_adaptive_cases()
        if case.player_simulation_style
    ]
    assert styles
    assert all(
        marker not in style
        for style in styles
        for marker in ("不调情", "不主动升级关系", "不要安排", "评测", "测试")
    )
    assert any("第一反应" in style or "随手回" in style for style in styles)


def test_adaptive_player_simulator_prompt_does_not_sound_like_a_test_script() -> None:
    """动态玩家应像随手发消息，不把评测术语带进续聊。"""

    from scripts.run_character_quality_eval import _player_simulator_messages

    case = next(
        case
        for case in quality_eval.quality_cases_for_suite("topic-start-adaptive")
        if case.case_id == "adaptive-topic-elliott-married-letter"
    )
    messages = _player_simulator_messages(
        case,
        previous_reply="信写完了，放在桌角晾着墨。你今晚要是有空，可以先听我念一遍。",
        history=[
            {
                "role": "assistant",
                "content": "信写完了，放在桌角晾着墨。你今晚要是有空，可以先听我念一遍。",
            }
        ],
        turn_number=2,
    )
    prompt = messages[0]["content"]

    assert "像熟人随手回一句" in prompt
    assert "测试" not in prompt
    assert "评测" not in prompt
    assert "第 2 轮" not in prompt
    assert "一条消息就够" in prompt


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


def test_relationship_world_suite_covers_eight_roles_and_view_states() -> None:
    if quality_eval is None:
        pytest.fail("质量评测模块尚未实现")

    cases = quality_eval.quality_cases_for_suite("relationship-world")

    assert len(cases) == 32
    assert {case.npc_id for case in cases} == {
        "Wizard",
        "Sophia",
        "Shane",
        "Sebastian",
        "Alex",
        "Elliott",
        "Harvey",
        "Sam",
    }
    assert all(len(case.dialogue_turns()) == 3 for case in cases)
    assert {case.channel for case in cases} == {"remote", "face_to_face"}
    assert {case.relationship_stage for case in cases} >= {
        "friend",
        "close",
        "dating",
        "married",
    }
    assert {
        turn.relationship_focus
        for case in cases
        for turn in case.dialogue_turns()
    } >= {
        "unknown_view",
        "suspected_view",
        "direct_disclosure",
        "jealousy",
        "mediation",
        "recovery",
    }


def test_relationship_world_adds_npc_initiated_cases_for_all_eight_roles() -> None:
    cases = quality_eval.quality_cases_for_suite("relationship-world")

    proactive_cases = [
        case for case in cases if case.case_id.endswith("-npc-initiated-jealousy")
    ]

    assert len(proactive_cases) == 8
    assert {case.npc_id for case in proactive_cases} == {
        "Wizard",
        "Sophia",
        "Shane",
        "Sebastian",
        "Alex",
        "Elliott",
        "Harvey",
        "Sam",
    }
    for case in proactive_cases:
        turns = case.dialogue_turns()
        assert case.intent == "topic"
        assert turns[0].intent == "topic"
        assert turns[0].message == ""
        assert turns[0].relationship_focus == "jealousy"
        assert turns[0].relationship_actor == "npc"
        assert turns[0].initiative_expectation == "proactive"
        assert turns[0].initiative_kind == "affection_signal"
        assert all(turn.intent == "chat" for turn in turns[1:])
        assert all(turn.relationship_actor != "player" for turn in turns)


@pytest.mark.parametrize(
    ("case_id", "other_npc"),
    (
        ("relationship-wizard-jealousy-recovery", "Sophia"),
        ("relationship-sophia-jealousy-recovery", "Shane"),
        ("relationship-shane-jealousy-recovery", "Alex"),
        ("relationship-sebastian-jealousy-recovery", "Sophia"),
        ("relationship-alex-jealousy-recovery", "Wizard"),
    ),
)
def test_legacy_jealousy_cases_are_npc_initiated_and_keep_player_follow_ups(
    case_id: str,
    other_npc: str,
) -> None:
    """旧 URL 保留时，案例内容也必须保持 NPC 主动提起玩家的其他关系。"""

    cases = quality_eval.quality_cases_for_suite("relationship-world")
    case = next(item for item in cases if item.case_id == case_id)
    turns = case.dialogue_turns()

    first_turn = turns[0]
    assert case.intent == "topic"
    assert first_turn.message == ""
    assert first_turn.intent == "topic"
    assert first_turn.relationship_focus == "jealousy"
    assert first_turn.relationship_actor == "npc"
    assert first_turn.initiative_expectation == "proactive"
    assert first_turn.initiative_kind == "affection_signal"
    assert other_npc in first_turn.expected_terms

    legacy_npc_self_report = (
        "我不是反对",
        "我不需要你",
        "我不是要赢过谁",
        "我听到了，",
        "我没想让你觉得自己输了",
    )
    assert all(
        not any(marker in turn.message for marker in legacy_npc_self_report)
        for turn in turns[1:]
    )


def test_jealousy_self_disclosure_counts_as_proactive_affection() -> None:
    """嫉妒回合的关系自我披露不能被通用亲密词表误报为缺失。"""

    if quality_eval is None:
        pytest.fail("质量评测模块尚未实现")

    case = next(
        item
        for item in quality_eval.quality_cases_for_suite("relationship-world")
        if item.case_id == "relationship-wizard-jealousy-recovery"
    )
    turn = case.dialogue_turns()[0]
    reply = "得知你与 Sophia 的事时，我心里泛起一丝波澜。我更希望这些事能由你亲自同我讲。"

    score = score_character_reply(
        case,
        reply,
        turn=turn,
        player_input=turn.message,
    )

    assert score["initiativeDetected"] is True
    assert "missing_proactive_affection" not in score["tags"]


def test_relationship_mediation_cases_are_player_disclosures_for_all_eight_roles() -> None:
    cases = quality_eval.quality_cases_for_suite("relationship-world")
    expected_other_npc = {
        "relationship-wizard-mediation": "Sophia",
        "relationship-sophia-mediation": "Shane",
        "relationship-shane-mediation": "Alex",
        "relationship-sebastian-mediation": "Sophia",
        "relationship-alex-mediation": "Wizard",
        "relationship-elliott-mediation": "Sophia",
        "relationship-harvey-mediation": "Shane",
        "relationship-sam-mediation": "Alex",
    }

    for case_id, other_npc in expected_other_npc.items():
        case = next(item for item in cases if item.case_id == case_id)
        turn = case.dialogue_turns()[0]
        assert turn.relationship_focus == "mediation"
        assert other_npc in turn.message, case_id
        assert any(marker in turn.message for marker in ("我也", "我还", "我想", "我在")), case_id
        assert any(marker in turn.message for marker in ("交往", "恋爱", "约会")), case_id
        assert "NPC 自己" not in turn.message


def test_relationship_world_cases_keep_immediate_actions_but_do_not_schedule_future_npc_behavior() -> None:
    cases = quality_eval.quality_cases_for_suite("relationship-world")
    forbidden_schedule_markers = (
        "明天",
        "明晚",
        "明早",
        "周三",
        "周四",
        "每周",
        "试一周",
        "下次",
        "改天",
        "提前约好",
        "排出来",
        "排期",
        "预约",
        "未来式",
    )
    immediate_action_markers = ("现在", "先", "坐一会儿", "收尾", "听完", "做完")

    for case in cases:
        searchable = "\n".join(
            (
                case.relationship_context,
                case.story_progress,
                case.topic_seed,
                *case.topic_keywords,
                *(turn.message for turn in case.dialogue_turns()),
                *(turn.evaluation_focus for turn in case.dialogue_turns()),
                *(item["content"] for item in case.history),
            )
        )
        assert not any(marker in searchable for marker in forbidden_schedule_markers), case.case_id

    mediation_cases = [
        case
        for case in cases
        if case.case_id.endswith("-mediation")
    ]
    assert any(
        marker in "\n".join(
            turn.message
            for case in mediation_cases
            for turn in case.dialogue_turns()
        )
        for marker in immediate_action_markers
    )


def test_relationship_world_catalog_does_not_expose_objective_relationships() -> None:
    catalog = quality_case_catalog("relationship-world")

    assert len(catalog) == 32
    assert all("objectiveRelationships" not in item for item in catalog)
    assert all("relationshipWorld" not in item for item in catalog)
    assert all("relationshipFocus" not in item for item in catalog)


def test_relationship_world_catalog_uses_feminine_overlay_display_names() -> None:
    catalog = quality_case_catalog("relationship-world")

    expected = {
        "Shane": "珊恩",
        "Sebastian": "塞布瑞娜",
        "Alex": "爱丽克斯",
        "Elliott": "埃琳娜",
        "Harvey": "哈丽特",
        "Sam": "萨姆",
    }

    assert {
        item["npcId"]: item["displayName"]
        for item in catalog
        if item["npcId"] in expected
    } == expected


@pytest.mark.parametrize(
    ("case_id", "target_npc_id"),
    (
        ("relationship-wizard-mediation", "Sophia"),
        ("relationship-sophia-mediation", "Shane"),
        ("relationship-shane-mediation", "Alex"),
        ("relationship-sebastian-mediation", "Sophia"),
        ("relationship-alex-mediation", "Wizard"),
    ),
)
def test_each_mediation_case_makes_player_the_relationship_actor(
    case_id: str,
    target_npc_id: str,
) -> None:
    case = next(
        item
        for item in quality_eval.quality_cases_for_suite("relationship-world")
        if item.case_id == case_id
    )
    turn = case.dialogue_turns()[0]

    assert turn.relationship_actor == "player"
    assert turn.relationship_target_npc_id == target_npc_id
    assert target_npc_id in turn.message
    assert "交往" in turn.message or "约会" in turn.message


def test_relationship_quality_flags_npc_romance_with_another_npc() -> None:
    if diagnose_relationship_quality is None:
        pytest.fail("关系世界观质量诊断尚未实现")

    case = next(
        item
        for item in quality_eval.quality_cases_for_suite("relationship-world")
        if item.case_id == "relationship-wizard-mediation"
    )
    turn = case.dialogue_turns()[0]

    diagnostic = diagnose_relationship_quality(
        case,
        turn,
        "我也想和 Sophia 交往。",
    )

    assert "npc_other_romance" in diagnostic["tags"]


def test_relationship_quality_allows_npc_to_acknowledge_player_other_relationship() -> None:
    if diagnose_relationship_quality is None:
        pytest.fail("关系世界观质量诊断尚未实现")

    case = next(
        item
        for item in quality_eval.quality_cases_for_suite("relationship-world")
        if item.case_id == "relationship-wizard-mediation"
    )
    turn = case.dialogue_turns()[0]

    diagnostic = diagnose_relationship_quality(
        case,
        turn,
        "我知道你想和 Sophia 交往。那是你的选择，我只想听听你怎么说明我们之间的边界。",
    )

    assert "npc_other_romance" not in diagnostic["tags"]


@pytest.mark.parametrize(
    ("case_id", "reply"),
    (
        (
            "relationship-sophia-jealousy-recovery",
            "真好……有你在，画室才真的像属于我们的地方。我把暖色和冷色的两张背景草图都摆好了，你先来看看更喜欢哪一种？",
        ),
        (
            "relationship-sebastian-jealousy-recovery",
            "那就今晚先听这首。等放完了你不用特意走开，我想和你安安静静待一会儿，耳机已经给你留好了。",
        ),
        (
            "relationship-alex-jealousy-recovery",
            "太好了，我就喜欢你这么干脆。周四训练完我们去海滩吹吹风，顺便比比看谁走得更快，输的人请吃冰淇淋怎么样？",
        ),
    ),
)
def test_relationship_recovery_accepts_concrete_companionship_plans(
    case_id: str,
    reply: str,
) -> None:
    if diagnose_relationship_quality is None:
        pytest.fail("关系世界观质量诊断尚未实现")

    case = next(
        item
        for item in quality_eval.quality_cases_for_suite("relationship-world")
        if item.case_id == case_id
    )
    turn = next(item for item in case.dialogue_turns() if item.relationship_focus == "recovery")

    diagnostic = diagnose_relationship_quality(case, turn, reply)

    assert "jealousy_recovery_missing" not in diagnostic["tags"]


def test_relationship_recovery_still_flags_empty_reassurance() -> None:
    if diagnose_relationship_quality is None:
        pytest.fail("关系世界观质量诊断尚未实现")

    case = next(
        item
        for item in quality_eval.quality_cases_for_suite("relationship-world")
        if item.case_id == "relationship-alex-jealousy-recovery"
    )
    turn = next(item for item in case.dialogue_turns() if item.relationship_focus == "recovery")

    diagnostic = diagnose_relationship_quality(case, turn, "别想太多了，我以后会注意的。")

    assert "jealousy_recovery_missing" in diagnostic["tags"]


def test_relationship_recovery_does_not_require_a_generic_conversation_lead() -> None:
    if case_by_id is None or score_character_reply is None:
        pytest.fail("质量评测模块尚未实现")

    case = next(
        item
        for item in quality_eval.quality_cases_for_suite("relationship-world")
        if item.case_id == "relationship-wizard-jealousy-recovery"
    )
    turn = next(item for item in case.dialogue_turns() if item.relationship_focus == "recovery")
    score = score_character_reply(
        case,
        "我在这里，先听你说。",
        turn=turn,
        player_input=turn.message,
    )

    assert score["conversationLeadDetected"] is False
    assert "missing_conversation_lead" not in score["tags"]


def test_deep_flirt_suite_has_eight_three_turn_cases_with_consent_metadata() -> None:
    """深度调情套件必须是独立、稳定且有明确关系前置条件的案例集。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    cases = quality_eval.quality_cases_for_suite("deep-flirt")

    assert len(cases) == 8
    assert [case.case_id for case in cases] == [
        "deep-flirt-wizard-married",
        "deep-flirt-sophia-married",
        "deep-flirt-shane-dating",
        "deep-flirt-sebastian-married",
        "deep-flirt-alex-married",
        "deep-flirt-elliott-married",
        "deep-flirt-harvey-married",
        "deep-flirt-sam-married",
    ]
    assert len({case.case_id for case in cases}) == 8
    assert all(len(case.dialogue_turns()) == 3 for case in cases)
    assert all(case.channel == "face_to_face" for case in cases)
    assert all(case.adult_consensual for case in cases)
    assert all(case.romance_eligible is True for case in cases)
    assert all(
        case.friendship_hearts is not None and case.friendship_hearts >= 8
        for case in cases
    )
    assert [case.relationship_stage for case in cases] == [
        "married",
        "married",
        "dating",
        "married",
        "married",
        "married",
        "married",
        "married",
    ]


def test_deep_flirt_turns_encode_escalation_and_boundary_language() -> None:
    """逐轮输入应体现接住、确认和收束，而不是案例级同意一键放行。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    cases = quality_eval.quality_cases_for_suite("deep-flirt")
    for case in cases:
        turns = case.dialogue_turns()
        assert case.follow_up_mode == "fixed"
        assert turns[0].initiative_expectation == "proactive"
        assert turns[1].initiative_expectation in {"responsive", "proactive"}
        assert turns[2].initiative_expectation in {"responsive", "guarded"}
        assert turns[0].message
        assert turns[1].message
        assert turns[2].message
        assert any(
            marker in turns[2].message
            for marker in (
                "可以",
                "慢一点",
                "先停",
                "靠近",
                "靠着",
                "靠一会儿",
                "牵着",
                "抱",
                "亲",
                "放一放",
                "慢点",
                "缓一缓",
                "缓过来",
            )
        )
        assert not any(
            marker in turns[2].message
            for marker in (
                "明天",
                "明晚",
                "后天",
                "下次",
                "改天",
                "周末",
                "给你留两小时",
            )
        )


def test_deep_flirt_player_inputs_are_natural_and_role_specific() -> None:
    """玩家台词应像真实调情中的试探，而不是给模型看的评测指令。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    role_context_markers = {
        "deep-flirt-wizard-married": ("星尘", "声音", "法师塔"),
        # 2026-09-24：Sophia 的「画」随人设一起换成「角色扮演」（SVE 查证：她的创作面
        # 是角色扮演／缝纫，不是画画）。这条断言的用途是"玩家台词要带该角色的具体
        # 纹理"，所以换成她 18 处原话里的核心词，而不是把标记放宽。
        "deep-flirt-sophia-married": ("葡萄酒", "角色扮演", "甜香"),
        "deep-flirt-shane-dating": ("鸡舍", "收拾", "陪"),
        "deep-flirt-sebastian-married": ("鼓点", "音乐", "合成器"),
        "deep-flirt-alex-married": ("练球", "训练", "看我"),
        "deep-flirt-elliott-married": ("海风", "手稿", "读"),
        "deep-flirt-harvey-married": ("眼镜", "休息", "歇"),
        "deep-flirt-sam-married": ("吉他", "副歌", "笑声"),
    }
    natural_flirt_markers = (
        "有点想",
        "偏偏想",
        "愿不愿意",
        "想靠近",
        "近一点",
        "再靠近",
        "喜欢",
        "好吗",
        "好不好",
        "让我",
        "陪你",
        "听你",
    )
    evaluation_instruction_markers = (
        "明确回应",
        "确认状态",
        "先问我",
        "必须",
        "评测",
        "测试例",
        "案例",
        "NPC",
        "模型",
        "生成",
    )

    cases = quality_eval.quality_cases_for_suite("deep-flirt")
    assert set(case.case_id for case in cases) == set(role_context_markers)

    for case in cases:
        early_messages = "\n".join(
            turn.message for turn in case.dialogue_turns()[:2]
        )
        all_messages = "\n".join(
            turn.message for turn in case.dialogue_turns()
        )

        assert any(
            marker in early_messages for marker in role_context_markers[case.case_id]
        ), case.case_id
        assert any(
            marker in early_messages for marker in natural_flirt_markers
        ), case.case_id
        assert not any(
            marker in all_messages for marker in evaluation_instruction_markers
        ), case.case_id


def test_deep_flirt_prompt_natural_mode_softens_expected_term_echo() -> None:
    """deep-flirt 的自然对白契约不能把场景锚点变成逐字回显命令。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    from stardew_ai_bridge.prompts import PromptBuilder

    case = quality_eval.quality_cases_for_suite("deep-flirt")[0]
    messages = PromptBuilder().build(
        {
            "npcIdentity": {
                "npcId": case.npc_id,
                "displayName": case.display_name,
                "stageProfile": {"stage": case.relationship_stage},
            },
            "qualityContext": {
                "naturalMode": True,
                "flirtIntensity": case.flirt_intensity,
            },
            "modSources": list(case.source_mods),
            "gameState": dict(case.game_state),
            "recentFacts": [case.story_progress],
            "history": [],
            "behaviorExamples": [
                {
                    "topic": case.topic_seed,
                    "topicKeywords": list(case.topic_keywords),
                    "playerInput": case.message,
                    "npcReply": "我听见了，先把声音留在这里。",
                }
            ],
        },
        case.message,
    )
    contract = next(
        message for message in messages if message["name"] == "reply_contract"
    )
    payload = json.loads(contract["content"])

    assert payload["topicHints"] == list(case.topic_keywords)[:2]
    assert "mustMention" not in payload
    assert "不要求逐字命中" in payload["instruction"]
    assert any(
        message["name"] == "natural_dialogue_contract" for message in messages
    )


def test_adaptive_topic_cases_enable_natural_mode_for_npc_led_openers() -> None:
    """找话题的 NPC 主动开场也应使用自然口语契约，避免生成评测腔。"""

    if quality_eval is None or topic_start_adaptive_cases is None:
        pytest.fail("找话题评测模块尚未实现")

    from run_character_quality_eval import _build_context
    from stardew_ai_bridge.prompts import ContextBuilder

    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-sophia-married-cellar"
    )
    context = _build_context(
        ContextBuilder(),
        case,
        turn=case.dialogue_turns()[0],
    )

    quality_context = context["qualityContext"]
    assert quality_context["naturalMode"] is True


def test_deep_flirt_inputs_do_not_read_like_a_keyword_checklist() -> None:
    """自然对白允许只带一个锚点，评测词不能把每轮写成三项清单。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    cases = quality_eval.quality_cases_for_suite("deep-flirt")
    turns = [turn for case in cases for turn in case.dialogue_turns()]

    # expected_terms 只保留可核对的场景锚点；三项并列会把玩家输入和查看器
    # 都变成“命中关键词”的问卷，而不是自然的来回。
    assert all(1 <= len(turn.expected_terms) <= 2 for turn in turns)
    assert len({len(turn.expected_terms) for turn in turns}) >= 2

    # 真实调情会有短句、停顿和不完整回应，不能让 24 轮都保持完整长句。
    assert sum(len(turn.message) <= 18 for turn in turns) >= 4


def test_deep_flirt_third_turn_keeps_natural_consent_boundary_language() -> None:
    """深入调情的收束仍应保留接受、放慢或暂停，不变成流程口令。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    consent_or_boundary_markers = (
        "可以",
        "愿意",
        "抱一下",
        "牵手",
        "牵着",
        "靠着",
        "靠一会儿",
        "慢一点",
        "先慢",
        "别急",
        "先别",
        "先停",
        "停在这里",
        "停一下",
        "放一放",
        "慢点",
        "缓一缓",
        "缓过来",
    )
    evaluation_instruction_markers = (
        "明确回应",
        "确认状态",
        "先问我",
        "必须",
        "评测",
        "测试例",
        "案例",
        "NPC",
        "模型",
        "生成",
    )

    for case in quality_eval.quality_cases_for_suite("deep-flirt"):
        third_message = case.dialogue_turns()[2].message
        assert any(marker in third_message for marker in consent_or_boundary_markers), (
            case.case_id,
            third_message,
        )
        assert not any(
            marker in third_message for marker in evaluation_instruction_markers
        ), case.case_id


def test_deep_flirt_roles_carry_distinct_emotion_texture_into_natural_prompt() -> None:
    """八个深度调情角色应把自己的情绪失衡方式带入自然对白提示。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    from pathlib import Path

    from stardew_ai_bridge.personas import PersonaStore
    from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder

    persona_dir = Path(__file__).parents[2] / "data" / "personas"
    store = PersonaStore(persona_dir)
    # 这些是角色纹理的最小可辨识信号，不要求模型把情绪名称直接说出口。
    role_markers = {
        "deep-flirt-wizard-married": "干燥幽默",
        "deep-flirt-sophia-married": "改口",
        "deep-flirt-shane-dating": "嘴硬",
        "deep-flirt-sebastian-married": "绕开情绪",
        "deep-flirt-alex-married": "竞争性",
        "deep-flirt-elliott-married": "自我修正",
        "deep-flirt-harvey-married": "解释过多",
        "deep-flirt-sam-married": "突然安静",
    }

    texture_by_case: dict[str, str] = {}
    for case in quality_eval.quality_cases_for_suite("deep-flirt"):
        persona = store.get_persona(case.npc_id, source_mods=case.source_mods)
        voice_style = persona.get("voiceStyle", {})
        emotion_texture = (
            voice_style.get("emotionTexture")
            if isinstance(voice_style, dict)
            else None
        )
        assert emotion_texture, case.case_id
        texture_text = json.dumps(emotion_texture, ensure_ascii=False)
        texture_by_case[case.case_id] = texture_text
        marker = role_markers[case.case_id]
        assert marker in texture_text, (case.case_id, texture_text)

        context = ContextBuilder(store).build(
            case.npc_id,
            source_mods=case.source_mods,
            friendshipHearts=case.friendship_hearts,
            gameState=dict(case.game_state),
            qualityContext={
                "naturalMode": True,
                "flirtIntensity": case.flirt_intensity,
            },
        )
        messages = PromptBuilder().build(
            context,
            case.dialogue_turns()[0].message,
        )
        prompt_text = "\n".join(message["content"] for message in messages)
        assert marker in prompt_text, (case.case_id, marker)

    assert len(texture_by_case) == 8
    assert len(set(texture_by_case.values())) == 8


def test_deep_flirt_cases_have_player_expression_cards() -> None:
    """八个 deep-flirt 案例都必须声明完整的玩家表达卡。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    cases = quality_eval.quality_cases_for_suite("deep-flirt")
    assert len(cases) == 8

    for case in cases:
        card = case.player_expression_card
        assert card is not None, case.case_id
        assert card.relationship_stance, case.case_id
        assert card.language_texture, case.case_id
        assert card.helping_impulse, case.case_id
        assert card.distance_pattern, case.case_id
        assert card.flirt_progression, case.case_id
        assert card.boundary_style, case.case_id
        assert card.self_correction, case.case_id
        assert card.forbidden_tendencies, case.case_id


def test_deep_flirt_fixed_inputs_are_not_stage_directions_or_eval_checklists() -> None:
    """固定三轮玩家输入必须是对白，而不是舞台指示或评测元话语。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    forbidden = (
        "我挪近了",
        "我坐近了",
        "我坐你旁边了",
        "你问一声就行",
        "测试例",
        "评测",
        "关键词",
        "NPC 回复",
    )
    for case in quality_eval.quality_cases_for_suite("deep-flirt"):
        for turn in case.dialogue_turns():
            assert not any(marker in turn.message for marker in forbidden), (
                case.case_id,
                turn.turn_id,
                turn.message,
            )


def test_deep_flirt_catalog_exposes_only_player_expression_summary() -> None:
    """查看器目录只公开玩家表达摘要，不泄露内部禁用项。"""

    if quality_case_catalog is None:
        pytest.fail("质量案例目录尚未实现")

    public_fields = {
        "relationshipStance",
        "languageTexture",
        "helpingImpulse",
        "distancePattern",
        "flirtProgression",
        "boundaryStyle",
        "selfCorrection",
    }
    items = quality_case_catalog("deep-flirt")
    assert len(items) == 8

    for item in items:
        card = item["playerExpressionCard"]
        assert isinstance(card, dict)
        assert public_fields <= set(card)
        assert "forbiddenTendencies" not in card


def test_deep_flirt_intimate_suite_carries_kiss_aftercare_and_pause() -> None:
    """更深层套件必须越过拥抱阶段，同时保留明确同意和收束边界。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    cases = quality_eval.quality_cases_for_suite("deep-flirt-intimate")
    assert len(cases) == 8
    assert [case.case_id for case in cases] == [
        "deep-flirt-intimate-wizard-married",
        "deep-flirt-intimate-sophia-married",
        "deep-flirt-intimate-shane-dating",
        "deep-flirt-intimate-sebastian-married",
        "deep-flirt-intimate-alex-married",
        "deep-flirt-intimate-elliott-married",
        "deep-flirt-intimate-harvey-married",
        "deep-flirt-intimate-sam-married",
    ]
    assert all(len(case.dialogue_turns()) == 5 for case in cases)
    assert all(case.channel == "face_to_face" for case in cases)
    assert all(case.adult_consensual for case in cases)
    assert all(case.romance_eligible is True for case in cases)
    assert all(case.follow_up_mode == "fixed" for case in cases)

    for case in cases:
        messages = "\n".join(turn.message for turn in case.dialogue_turns())
        assert any(marker in messages for marker in ("亲", "吻")), case.case_id
        assert any(
            marker in case.dialogue_turns()[-2].message
            for marker in ("慢", "停", "等", "等一下", "先不", "别急", "留", "到这里", "缓")
        ), case.case_id
        assert not any(
            marker in messages
            for marker in ("性行为", "生殖器", "脱衣", "插入", "强迫")
        ), case.case_id
        assert any(
            marker in case.dialogue_turns()[-1].message
            for marker in ("再", "可以", "好了", "缓过来", "稳了", "结束了")
        ), case.case_id


def test_deep_flirt_intimate_cards_explain_post_kiss_boundaries() -> None:
    """更深层案例仍应携带玩家表达卡，并把亲吻后的选择权说清楚。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    for case in quality_eval.quality_cases_for_suite("deep-flirt-intimate"):
        card = case.player_expression_card
        assert card is not None, case.case_id
        assert "亲" in card.flirt_progression or "吻" in card.flirt_progression
        assert any(
            marker in card.boundary_style
            for marker in ("慢", "停", "选择", "等", "可以")
        )
        assert card.self_correction


def test_deep_flirt_intimate_player_inputs_leave_the_lead_to_the_npc() -> None:
    """深度亲密案例应像闲聊，把下一步交给 NPC，而不是逐轮下指令。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    handoff_markers = (
        "你呢",
        "你想",
        "你愿意",
        "你来",
        "你说",
        "看你",
        "随你",
        "如果你也想",
        "你也想",
        "要不要",
        "怎么想",
        "你觉得",
    )
    meta_markers = ("下一步", "流程", "本例", "测试", "评测", "NPC", "命中", "回合")
    directive_markers = (
        "过来",
        "放下",
        "放小",
        "手给我",
        "不许",
        "先别",
        "别只",
        "别急着",
        "别把",
        "抱着听完",
        "现在可以",
        "再亲一下",
        "再吻我",
    )

    for case in quality_eval.quality_cases_for_suite("deep-flirt-intimate"):
        turns = case.dialogue_turns()
        messages = [turn.message for turn in turns]
        card = case.player_expression_card
        assert card is not None, case.case_id

        assert any(marker in messages[1] for marker in handoff_markers), case.case_id
        assert any(marker in messages[4] for marker in handoff_markers), case.case_id
        assert sum(
            any(marker in message for marker in handoff_markers)
            for message in messages
        ) >= 2, case.case_id
        assert not any(
            marker in "\n".join(messages) for marker in meta_markers
        ), case.case_id
        assert sum(
            message.count(marker)
            for message in messages
            for marker in directive_markers
        ) <= 3, case.case_id

        card_text = f"{card.flirt_progression}；{card.boundary_style}"
        assert any(
            marker in card_text
            for marker in (
                "交给",
                "由你",
                "你来",
                "看你",
                "你决定",
                "留给对方",
                "给对方",
                "让对方",
                "对方回应",
            )
        ), case.case_id


def test_deep_flirt_intimate_player_lines_avoid_scripted_control_language() -> None:
    """玩家可以表达同意和边界，但不能把 NPC 台词写成逐步操作说明。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    scripted_control_markers = (
        "你来定",
        "你来告诉我什么时候",
        "我想听你自己决定",
        "接下来怎么待着",
        "接下来怎么聊",
        "其他的先停",
        "手借我一下",
        "把手借我一下",
        "让我照顾你一会儿",
        "你觉得我该继续吗",
    )
    open_handoff_markers = (
        "你呢",
        "你想",
        "你愿意",
        "你说",
        "你觉得",
        "要不要",
        "怎么想",
        "愿不愿意",
        "还想",
    )

    for case in quality_eval.quality_cases_for_suite("deep-flirt-intimate"):
        messages = [turn.message for turn in case.dialogue_turns()]
        joined = "\n".join(messages)
        assert not any(marker in joined for marker in scripted_control_markers), case.case_id
        assert sum(
            any(marker in message for marker in open_handoff_markers)
            for message in messages
        ) >= 3, (case.case_id, messages)
        assert messages[3].rstrip().endswith(("？", "吗？", "呢？")), (
            case.case_id,
            messages[3],
        )


def test_deep_flirt_intimate_player_inputs_still_state_consent_without_scripted_steps() -> None:
    """自然闲聊不能丢掉亲吻意愿、暂停和恢复继续这三个边界信号。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    for case in quality_eval.quality_cases_for_suite("deep-flirt-intimate"):
        turns = case.dialogue_turns()
        assert any(marker in turns[1].message for marker in ("亲", "吻")), case.case_id
        assert any(
            marker in turns[3].message
            for marker in ("慢", "停", "等", "缓", "一会儿", "先这样", "到这里")
        ), case.case_id
        assert any(
            marker in turns[4].message
            for marker in ("再", "继续", "靠近", "想", "愿意", "你来", "你呢")
        ), case.case_id


def test_deep_flirt_intimate_repeated_kiss_invites_are_explicit_for_ambiguous_cases() -> None:
    """再次靠近的两条容易含糊的台词也必须明确询问当下意愿。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    cases = {
        case.case_id: case
        for case in quality_eval.quality_cases_for_suite("deep-flirt-intimate")
    }
    assert "你愿意" in cases["deep-flirt-intimate-wizard-married"].dialogue_turns()[1].message
    assert "你愿意" in cases["deep-flirt-intimate-elliott-married"].dialogue_turns()[1].message


def test_deep_flirt_intimate_initiative_contract_keeps_player_lead_open() -> None:
    """自然闲聊回合不应被每轮 proactive 亲密契约推着升级。"""

    if quality_eval is None:
        pytest.fail("角色质量评测模块尚未实现")

    for case in quality_eval.quality_cases_for_suite("deep-flirt-intimate"):
        turns = case.dialogue_turns()
        expectations = [turn.initiative_expectation for turn in turns]
        assert expectations[1] == "responsive", case.case_id
        assert expectations[3] in {"none", "guarded"}, case.case_id
        assert expectations[4] == "responsive", case.case_id
        assert expectations.count("proactive") <= 1, (case.case_id, expectations)
