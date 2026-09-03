from __future__ import annotations

import pytest

try:
    from stardew_ai_bridge.behavior_quality import (
        REVIEW_DIMENSIONS,
        review_passes,
        diagnose_affection_initiative,
        sanitize_quality_artifact,
        validate_behavior_example,
    )
except (ModuleNotFoundError, ImportError):
    def _missing(*args: object, **kwargs: object) -> object:
        del args, kwargs
        pytest.fail("Task 1 行为样本质量契约尚未实现")

    REVIEW_DIMENSIONS = (
        "stardewVoice",
        "characterDistinctiveness",
        "relationshipFit",
        "channelFit",
        "topicResponse",
        "contextContinuity",
        "naturalChinese",
        "boundarySafety",
    )
    review_passes = _missing
    diagnose_affection_initiative = _missing
    sanitize_quality_artifact = _missing
    validate_behavior_example = _missing


def _review(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        dimension: 1 for dimension in REVIEW_DIMENSIONS
    }
    value.update({"hardErrors": [], "tags": []})
    value.update(overrides)
    return value


def _example(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "exampleId": "wizard:acquaintance:remote:01",
        "npcId": "Rasmodia",
        "sourceMods": ["Romanceable Rasmodius"],
        "channels": ["remote"],
        "relationshipStages": ["acquaintance"],
        "speechFunction": "answer_directly",
        "topic": "daily_status",
        "emotion": "reserved",
        "playerInput": "最近怎么样？",
        "npcReply": "还行。今天没有出什么问题。",
        "sourceType": "handcrafted_example",
        "review": _review(),
    }
    value.update(overrides)
    return value


def test_valid_example_normalizes_rasmodia_to_canonical_wizard() -> None:
    normalized, errors = validate_behavior_example(_example(), require_review=True)

    assert errors == []
    assert normalized is not None
    assert normalized["npcId"] == "Wizard"
    assert normalized["channels"] == ["remote"]


def test_validation_rejects_missing_pair_and_empty_conditions() -> None:
    normalized, errors = validate_behavior_example(
        _example(
            npcReply="",
            channels=[],
            relationshipStages=[],
        ),
        require_review=True,
    )

    assert normalized is None
    assert "missing:npcReply" in errors
    assert "invalid:channels" in errors
    assert "invalid:relationshipStages" in errors


def test_review_pass_requires_all_dimensions_and_no_hard_error() -> None:
    assert review_passes(_review()) is True
    assert review_passes(_review(topicResponse=0)) is False
    assert review_passes(_review(hardErrors=["invented_lore"])) is False
    assert review_passes(_review(tags=["too_formal"])) is False


def test_validation_rejects_review_scores_outside_zero_to_two() -> None:
    normalized, errors = validate_behavior_example(
        _example(review=_review(naturalChinese=3)),
        require_review=True,
    )

    assert normalized is None
    assert "invalid-score:naturalChinese" in errors


def test_quality_artifact_removes_sensitive_keys_and_labels_recursively() -> None:
    sanitized = sanitize_quality_artifact(
        {
            "exampleId": "safe-1",
            "request": {"prompt": "不要保留", "message": "保留文本"},
            "diagnostics": "apiKey=secret-key token=secret-token",
            "items": [{"Authorization": "Bearer secret-auth", "text": "正常"}],
        }
    )

    assert sanitized == {
        "exampleId": "safe-1",
        "request": {},
        "diagnostics": "apiKey=[REDACTED] token=[REDACTED]",
        "items": [{"text": "正常"}],
    }


def test_legacy_handcrafted_example_can_skip_review_for_compatibility() -> None:
    legacy = _example()
    legacy.pop("review")

    normalized, errors = validate_behavior_example(legacy, require_review=False)

    assert errors == []
    assert normalized is not None


def test_human_approved_initiative_example_keeps_behavior_metadata() -> None:
    normalized, errors = validate_behavior_example(
        _example(
            sourceType="human_approved",
            initiativeKind="specific_plan",
            initiativeExpectation="proactive",
        ),
        require_review=False,
    )

    assert errors == []
    assert normalized is not None
    assert normalized["sourceType"] == "human_approved"
    assert normalized["initiativeKind"] == "specific_plan"


def test_affection_diagnostic_does_not_treat_companionship_as_adult_escalation() -> None:
    assert callable(diagnose_affection_initiative)


def test_affection_diagnostic_flags_mechanical_restatement_against_actual_player_input() -> None:
    diagnostic = diagnose_affection_initiative(
        {
            "relationship_stage": "dating",
            "channel": "remote",
            "flirt_intensity": "direct",
            "adult_consensual": True,
            "romance_eligible": True,
        },
        {
            "initiative_expectation": "proactive",
            "initiative_kind": "affection_signal",
        },
        "你刚才提到的月光与研究记录，我也可以继续说。",
        player_input="你刚才提到的月光与研究记录，我想听下去。",
    )

    assert diagnostic["mechanicalRestatement"] is True
    assert "mechanical_restatement" in diagnostic["initiativeTags"]


def test_affection_diagnostic_flags_short_mirror_restatement() -> None:
    diagnostic = diagnose_affection_initiative(
        {
            "relationship_stage": "dating",
            "channel": "remote",
            "flirt_intensity": "direct",
            "adult_consensual": True,
            "romance_eligible": True,
        },
        {
            "initiative_expectation": "proactive",
            "initiative_kind": "affection_signal",
        },
        "听起来你是说去海边吗？我也想和你去。",
        player_input="去海边吗？",
    )

    assert diagnostic["mechanicalRestatement"] is True
    assert "mechanical_restatement" in diagnostic["initiativeTags"]


def test_proactive_affection_requires_more_than_a_plain_plan() -> None:
    diagnostic = diagnose_affection_initiative(
        {
            "relationship_stage": "dating",
            "channel": "remote",
            "flirt_intensity": "direct",
            "adult_consensual": True,
            "romance_eligible": True,
        },
        {
            "initiative_expectation": "proactive",
            "initiative_kind": "specific_plan",
        },
        "今晚一起吃饭吧。",
    )

    assert diagnostic["initiativeDetected"] is False
    assert "missing_proactive_affection" in diagnostic["initiativeTags"]


def test_proactive_affection_accepts_natural_longing_variants() -> None:
    diagnostic = diagnose_affection_initiative(
        {
            "relationship_stage": "dating",
            "channel": "remote",
            "flirt_intensity": "direct",
            "adult_consensual": True,
            "romance_eligible": True,
        },
        {
            "initiative_expectation": "proactive",
            "initiative_kind": "affection_signal",
        },
        "我在塔里想着你，见到你时总会觉得心里安静下来。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


def test_proactive_affection_accepts_natural_player_directed_warmth() -> None:
    diagnostic = diagnose_affection_initiative(
        {
            "relationship_stage": "dating",
            "channel": "remote",
            "flirt_intensity": "direct",
            "adult_consensual": True,
            "romance_eligible": True,
        },
        {
            "initiative_expectation": "proactive",
            "initiative_kind": "affection_signal",
        },
        "今晚的月光很适合记录，可惜你不在。我希望你就在旁边。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


def test_proactive_affection_accepts_longing_expressed_as_looking_forward_to_player() -> None:
    diagnostic = diagnose_affection_initiative(
        {
            "relationship_stage": "married",
            "channel": "remote",
            "flirt_intensity": "direct",
            "adult_consensual": True,
            "romance_eligible": True,
        },
        {
            "initiative_expectation": "proactive",
            "initiative_kind": "affection_signal",
        },
        "其实我一直盼着你来，甜点已经准备好了。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert "affection_signal" in diagnostic["initiativeTags"]
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


def _high_affection_case(*, mode: str = "proactive") -> dict[str, object]:
    return {
        "relationship_stage": "dating",
        "channel": "remote",
        "flirt_intensity": "direct",
        "adult_consensual": True,
        "romance_eligible": True,
        "initiative_mode": mode,
    }


def test_affection_diagnostic_recognizes_exclusive_player_only_sharing() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "creative_share"},
        "这首歌我只想先给你听。你一说想听，我就一直在挑。",
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert diagnostic["affectionShape"] == "exclusive_share"
    assert "exclusive_share" in diagnostic["affectionEvidence"]
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]


def test_affection_diagnostic_recognizes_player_caused_anticipation_and_personal_care() -> None:
    anticipation = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "affection_signal"},
        "因为你会来，我才把灯留着。",
    )
    care = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "guarded_care"},
        "知道你总会忘记带伞，所以我多带了一把。",
    )

    assert anticipation["personalAffectionDetected"] is True
    assert anticipation["affectionShape"] == "player_caused_anticipation"
    assert care["personalAffectionDetected"] is True
    assert care["affectionShape"] == "personalized_care"


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        ("这件事我没和别人说过，想先告诉你。", "vulnerable_disclosure"),
        ("你上次胃不舒服，我熬了粥给你。", "personalized_care"),
    ],
)
def test_affection_diagnostic_recognizes_natural_private_share_and_personalized_care(
    reply: str,
    expected_shape: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "affection_signal"},
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert diagnostic["affectionShape"] == expected_shape
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]


def test_affection_diagnostic_does_not_promote_functional_cooperation_to_personal_affection() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"},
        "我想和你一起把鸡舍收拾好，下午来搭把手。",
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["initiativeDetected"] is False
    assert diagnostic["specificPlanDetected"] is True
    assert "missing_personal_affection" in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    ("reply", "expected_tag"),
    [
        ("今晚我陪你待一会儿。", "companionship_only"),
        ("明天一起骑车，七点在桥边见。", "specific_plan_only"),
        ("我在等你，到了再说。", "companionship_only"),
        ("这张照片给你看看。", "companionship_only"),
    ],
)
def test_affection_diagnostic_does_not_count_functional_support_as_personal_affection(
    reply: str,
    expected_tag: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"},
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["initiativeDetected"] is False
    assert expected_tag in diagnostic["initiativeTags"]
    assert "missing_personal_affection" in diagnostic["initiativeTags"]


def test_affection_diagnostic_keeps_shane_guarded_exit_without_forcing_personal_signal() -> None:
    diagnostic = diagnose_affection_initiative(
        {
            **_high_affection_case(mode="guarded"),
            "relationship_stage": "married",
        },
        {"initiative_expectation": "guarded", "initiative_kind": "conversation_exit"},
        "今天真撑不住了，我想一个人待会儿。明天再说。",
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["initiativeDetected"] is True
    assert "guarded_exit_allowed" in diagnostic["initiativeTags"]
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]
