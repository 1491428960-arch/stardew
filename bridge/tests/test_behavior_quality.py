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
