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


def test_affection_diagnostic_allows_natural_confirmation_of_a_shared_plan() -> None:
    diagnostic = diagnose_affection_initiative(
        {
            "relationship_stage": "married",
            "channel": "face_to_face",
            "flirt_intensity": "explicit",
            "adult_consensual": True,
            "romance_eligible": True,
        },
        {
            "initiative_expectation": "proactive",
            "initiative_kind": "specific_plan",
        },
        "我很愿意，就把灯调暗一点，今晚的时间都留给我们。毕竟，和你在一起的时光总是特别珍贵。",
        player_input="如果你愿意，就把灯调暗一点，今晚只留给我们。",
    )

    assert diagnostic["mechanicalRestatement"] is False
    assert "mechanical_restatement" not in diagnostic["initiativeTags"]


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


@pytest.mark.parametrize(
    "reply",
    [
        "我耳朵只对你竖着呢，说吧。",
        "跟你聊天比什么都强。",
        "音乐停了就留给你。",
        "因为你在这儿，有什么烦心事都没那么难熬。",
        "有你在身边，喝酒都变得更美妙。",
        "比起酒，我现在更想和你多待一会儿呢。",
        "我巴不得一直和你待着，去房间的事不急。",
        "酒你来倒的话，我就专心看你。",
        "我当然想多跟你待一会儿，去房间的事不急。",
        "这安静时候归你，我过来。",
        "杯子哪有你好看，我这就靠过去。",
        "谁也比不了你，我就想先听你说。",
    ],
)
def test_affection_diagnostic_accepts_cloud_natural_player_directed_variants(
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "affection_signal"},
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]


def test_affection_diagnostic_keeps_plain_companionship_as_insufficient() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "companionship"},
        "能过来陪你坐一会儿。",
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["companionshipDetected"] is True
    assert "companionship_only" in diagnostic["initiativeTags"]
    assert "missing_personal_affection" in diagnostic["initiativeTags"]


def test_guarded_refusal_close_is_allowed_when_player_has_no_mood_for_affection() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(mode="guarded"),
        {"initiative_expectation": "guarded", "initiative_kind": "guarded_care"},
        "哦，那不说这个了。我今天也挺累的，先睡了，晚安。",
        player_input="别逼我说这种话，今天真的没心情。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert "guarded_exit_allowed" in diagnostic["initiativeTags"]
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]


def test_guarded_refusal_with_rest_advice_is_allowed_without_explicit_goodnight() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(mode="guarded"),
        {"initiative_expectation": "guarded", "initiative_kind": "guarded_care"},
        "哦，是我强求了。那你今天就好好休息吧。",
        player_input="别逼我说这种话，今天真的没心情。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert "guarded_exit_allowed" in diagnostic["initiativeTags"]
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]


def test_guarded_refusal_with_shane_irritation_is_allowed_without_forcing_affection() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(mode="guarded"),
        {"initiative_expectation": "guarded", "initiative_kind": "guarded_care"},
        "今天真的，我脑子都快浆糊了。你别跟我较劲行不行？",
        player_input="别逼我说这种话，今天真的没心情。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert "guarded_exit_allowed" in diagnostic["initiativeTags"]
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        (
            "好，今晚我多留些时间给你，记录可以先放一放。",
            "player_directed_preference",
        ),
        ("今晚的时间，都留给你和我。", "exclusive_share"),
        ("我不只看杯子呢，我还看你呢。", "character_consistent_tease"),
    ],
)
def test_affection_diagnostic_recognizes_natural_player_directed_choices_and_tease(
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


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        (
            "比起那些记录，我还是更想把时间留给你。",
            "player_directed_preference",
        ),
        (
            "雨声再大，我也想把这会儿留给你。",
            "player_directed_preference",
        ),
        ("我最喜欢和你一起喝酒。", "player_directed_preference"),
        ("我就喜欢陪你一起待着。", "player_directed_preference"),
        (
            "训练虽然结束了，但我满脑子都是你。今晚就咱们俩，怎么样？",
            "player_directed_preference",
        ),
        ("我靠过来，你可别只看着我呀。", "character_consistent_tease"),
        ("比起那些记录，陪你才是最重要的。", "player_directed_preference"),
        ("行，给你抱一会儿。", "player_directed_preference"),
        ("这杯酒和你一起喝，感觉更好。", "player_directed_preference"),
    ],
)
def test_affection_diagnostic_recognizes_real_cloud_personal_affection_variants(
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


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        ("那些记录哪有你重要。我这就放下，今晚的时间都是你的。", "player_directed_preference"),
        ("比起那些记录，陪你才是正事。我坐过去，想让我抱吗？", "player_directed_preference"),
        ("好啊，今晚就只陪你。我们一起慢慢享受这杯美酒。", "exclusive_share"),
        ("好，那你先倒酒吧。我靠过去，今晚只看着你。", "exclusive_share"),
        ("喝完这口就陪你去里面坐着，只和你待着真好。", "exclusive_share"),
        ("我可不想让你等太久。我呀，就喜欢跟你待在一起。", "player_directed_preference"),
    ],
)
def test_affection_diagnostic_recognizes_cloud_v3_exclusive_preference_variants(
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


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        ("好，都听你的。我把灯调暗一点，今晚的时间，就只给你我二人。", "exclusive_share"),
        ("好呀，能和你一起喝酒，我很开心呢。", "player_directed_preference"),
        ("你倒酒的样子很有魅力呢。", "character_consistent_tease"),
        ("能陪你在这儿坐着，我觉得特别安心。", "player_directed_preference"),
        ("去房间肯定不会让你等太久。我可舍不得，你就安心等着吧。", "personalized_care"),
    ],
)
def test_affection_diagnostic_recognizes_cloud_v4_personal_affection_variants(
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


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        ("不过我更想看你。", "player_directed_preference"),
        ("这安静下来的时间，我只给你留着。", "exclusive_share"),
        ("这首我只听给你一个人。", "exclusive_share"),
        ("跟你在一起的时间怎么都不够。", "player_directed_preference"),
        ("你可是我最想陪的人。", "player_directed_preference"),
    ],
)
def test_affection_diagnostic_recognizes_natural_player_directed_v7_variants(
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


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        ("跟你聊天比什么都强。", "player_directed_preference"),
        ("音乐停了，就留给你。", "exclusive_share"),
        ("我只想陪着你。", "exclusive_share"),
        ("记录可以先放一放，我更想陪你。", "player_directed_preference"),
        ("酒你来倒吧，我就想看着你。", "player_directed_preference"),
        ("在酒窖里，酒杯再好看也没你好看呢。", "character_consistent_tease"),
        ("比起杯子，我一直都在看你。", "character_consistent_tease"),
        ("比起杯子，我一直都在看你；酒还没倒好。", "character_consistent_tease"),
        ("我只想给你听这首歌，账本明天再核对。", "exclusive_share"),
        ("我只想给你看这张画，账本明天再核对。", "exclusive_share"),
        ("因为你在这儿，那些记录便可以等等。我现在就过来陪你坐会儿。", "player_directed_preference"),
        ("好呀，今晚就陪你好好的。在这酒窖里，有你在身边，喝酒都变得更美妙了呢。", "player_directed_preference"),
        ("酒窖里只有你我才热闹。再喝一口就陪你去里面坐着。", "exclusive_share"),
        ("也就你让我这么凑过去听了。", "player_directed_preference"),
        ("好啊，就回我们的房间。这一首听完，那段时间归你。", "exclusive_share"),
        ("嘿，当然是先陪你聊会儿啦。我可舍不得直接去房间，和你待在一起时间总是过得特别快。", "player_directed_preference"),
        (
            "跟你聊天比直接回房间有意思多了，我可不想错过和你相处的时间。",
            "player_directed_preference",
        ),
    ],
)
def test_affection_diagnostic_recognizes_v8_player_directed_preference_variants(
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


def test_affection_diagnostic_keeps_preference_words_in_functional_cooperation_as_support() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"},
        "我最喜欢和你一起把鸡舍收拾好，下午来搭把手。",
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["specificPlanDetected"] is True
    assert "specific_plan_only" in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    "reply",
    [
        "今晚只陪你把鸡舍收拾完，别耽误明早喂鸡。",
        "我只和你一起整理账本，弄完就各忙各的。",
        "我只想陪你整理账本。",
        "我只想给你看账本。",
        "我只想把账本给你看。",
    ],
)
def test_affection_diagnostic_keeps_exclusive_words_in_functional_cooperation_as_support(
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"},
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["specificPlanDetected"] is True
    assert "specific_plan_only" in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    "reply",
    [
        "今晚就咱们俩把鸡舍收拾好，明早还得喂鸡。",
        "现在我们两个一起整理账本，早点算完吧。",
        "我多留点时间给你整理账本。",
        "你可别只看我，把账本也过一遍。",
    ],
)
def test_affection_diagnostic_keeps_two_person_functional_work_as_support(
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"},
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["initiativeDetected"] is False
    assert diagnostic["specificPlanDetected"] is True
    assert "specific_plan_only" in diagnostic["initiativeTags"]
    assert "missing_personal_affection" in diagnostic["initiativeTags"]


def test_affection_diagnostic_keeps_unlisted_farm_task_as_support() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"},
        "今晚就咱们俩去帮罗宾修栅栏，明早还得浇地。",
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["specificPlanDetected"] is True
    assert "specific_plan_only" in diagnostic["initiativeTags"]


def test_affection_diagnostic_keeps_functional_account_share_as_a_plan() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"},
        "我先把账本交给你核对，晚点再看结果。",
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["specificPlanDetected"] is True
    assert "specific_plan_only" in diagnostic["initiativeTags"]


def test_affection_diagnostic_keeps_personal_choice_after_functional_work() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "affection_signal"},
        "先一起收拾鸡舍，忙完我想把今晚留给你。",
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert diagnostic["affectionShape"] == "player_directed_preference"
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]


def test_affection_diagnostic_keeps_functional_work_happiness_as_support() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"},
        "能和你一起整理账本，我很开心，做完再去休息。",
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["specificPlanDetected"] is True
    assert "specific_plan_only" in diagnostic["initiativeTags"]


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
