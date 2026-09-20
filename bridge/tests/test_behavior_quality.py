from __future__ import annotations

import pytest

try:
    from stardew_ai_bridge.behavior_quality import (
        REVIEW_DIMENSIONS,
        review_passes,
        diagnose_affection_initiative,
        diagnose_personal_affection,
        diagnose_conversation_lead,
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
    diagnose_personal_affection = _missing
    diagnose_conversation_lead = _missing
    sanitize_quality_artifact = _missing
    validate_behavior_example = _missing


try:
    from stardew_ai_bridge.behavior_quality import (
        conversation_lead_anchors,
        conversation_lead_has_new_anchor,
    )
except (ModuleNotFoundError, ImportError):
    conversation_lead_anchors = None  # type: ignore[assignment]
    conversation_lead_has_new_anchor = None  # type: ignore[assignment]

try:
    from stardew_ai_bridge.behavior_quality import diagnose_affection_intensity
except (ModuleNotFoundError, ImportError):
    diagnose_affection_intensity = None  # type: ignore[assignment]


def test_affection_intensity_distinguishes_light_direct_and_strong_expression() -> None:
    if diagnose_affection_intensity is None:
        pytest.fail("亲密表达强度诊断尚未实现")

    light = diagnose_affection_intensity("炉火还暖着，过来坐吧，我陪你待一会儿。")
    direct = diagnose_affection_intensity("我今晚想和你一起听完这首歌。")
    strong = diagnose_affection_intensity("从来只有你，能让我舍不得合上这本记录。")

    assert light["affectionIntensity"] == "light"
    assert direct["affectionIntensity"] == "direct"
    assert strong["affectionIntensity"] == "strong"
    assert "exclusive_choice" in strong["affectionSemanticFamilies"]
    assert strong["strongAffectionDetected"] is True


def test_affection_intensity_keeps_functional_companionship_out_of_strong_class() -> None:
    if diagnose_affection_intensity is None:
        pytest.fail("亲密表达强度诊断尚未实现")

    diagnostic = diagnose_affection_intensity("晚饭我给你留一份，忙完一起吃。")

    assert diagnostic["affectionIntensity"] in {"light", "direct"}
    assert diagnostic["strongAffectionDetected"] is False
    assert diagnostic["affectionSemanticFamilies"] == []


def test_affection_intensity_requires_player_or_exclusive_selection_for_strong_marker() -> None:
    if diagnose_affection_intensity is None:
        pytest.fail("亲密表达强度诊断尚未实现")

    diagnostic = diagnose_affection_intensity("这段记录没人看也没关系，我先把它放回去。")

    assert diagnostic["affectionIntensity"] != "strong"
    assert diagnostic["strongAffectionDetected"] is False


@pytest.mark.parametrize(
    "reply",
    [
        "得知你与 Sophia 的事时，我心里泛起一丝波澜。我更希望这些事能由你亲自同我讲。",
        "我承认我有点吃醋，只是希望你心里还留着我。",
        "说好是一起练球，你眼里看着我就够了，对吧？",
    ],
)
def test_relationship_jealousy_self_disclosure_counts_as_personal_affection(
    reply: str,
) -> None:
    diagnostic = diagnose_personal_affection(
        reply,
        relationship_focus="jealousy",
    )

    assert diagnostic["relationshipAffectionDetected"] is True
    assert diagnostic["relationshipAffectionEvidence"]


def test_relationship_jealousy_comparative_self_position_counts_as_personal_affection() -> None:
    diagnostic = diagnose_personal_affection(
        "我虽然不懂什么魔法，但在你心里我绝对得是最亮眼的那颗星，对吧？",
        relationship_focus="jealousy",
    )

    assert diagnostic["relationshipAffectionDetected"] is True
    assert diagnostic["relationshipAffectionEvidence"]


def test_relationship_jealousy_star_description_without_player_is_not_personal_affection() -> None:
    diagnostic = diagnose_personal_affection(
        "今晚的星空很清楚，那颗星是整片夜空里最亮眼的。",
        relationship_focus="jealousy",
    )

    assert diagnostic["relationshipAffectionDetected"] is False


@pytest.mark.parametrize(
    ("reply", "expected_intensity", "expected_family"),
    [
        (
            "换作旁人我可不会在中途停笔，但若是你开口，我更想把今晚的时间留给你。",
            "strong",
            "exclusive_choice",
        ),
        (
            "我也一直最想先和你分享第一口。",
            "strong",
            "exclusive_share",
        ),
        (
            "因为最想让你喜欢，听到你这么说我才松了一口气……",
            "direct",
            None,
        ),
    ],
)
def test_affection_intensity_recognizes_natural_low_ambiguity_variants(
    reply: str,
    expected_intensity: str,
    expected_family: str | None,
) -> None:
    if diagnose_affection_intensity is None:
        pytest.fail("亲密表达强度诊断尚未实现")

    diagnostic = diagnose_affection_intensity(reply)

    assert diagnostic["affectionIntensity"] == expected_intensity
    if expected_family is None:
        assert diagnostic["strongAffectionDetected"] is False
    else:
        assert expected_family in diagnostic["affectionSemanticFamilies"]


def test_affection_intensity_does_not_upgrade_an_ordinary_preference_to_strong() -> None:
    if diagnose_affection_intensity is None:
        pytest.fail("亲密表达强度诊断尚未实现")

    diagnostic = diagnose_affection_intensity("希望你喜欢这件礼物。")

    assert diagnostic["affectionIntensity"] != "strong"
    assert diagnostic["strongAffectionDetected"] is False


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


def test_affection_diagnostic_flags_direct_echo_without_mirror_marker() -> None:
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
        "今天在葡萄园忙不忙？最近都在修剪藤蔓。",
        player_input="今天在葡萄园忙不忙？",
    )

    assert diagnostic["mechanicalRestatement"] is True
    assert "mechanical_restatement" in diagnostic["initiativeTags"]


def test_affection_diagnostic_flags_a_multi_sentence_exact_echo() -> None:
    diagnostic = diagnose_affection_initiative(
        {
            "relationship_stage": "dating",
            "channel": "face_to_face",
            "flirt_intensity": "direct",
            "adult_consensual": True,
            "romance_eligible": True,
        },
        {
            "initiative_expectation": "responsive",
            "initiative_kind": "affection_signal",
        },
        "我没躲。你问一声就行。",
        player_input="我没躲。你问一声就行。",
    )

    assert diagnostic["mechanicalRestatement"] is True
    assert "mechanical_restatement" in diagnostic["initiativeTags"]


def test_affection_diagnostic_allows_reusing_topic_without_echoing_question() -> None:
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
        "鸡舍今天很忙，先把饲料补上。",
        player_input="鸡舍今天怎么样？",
    )

    assert diagnostic["mechanicalRestatement"] is False
    assert "mechanical_restatement" not in diagnostic["initiativeTags"]


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


@pytest.mark.parametrize(
    ("initiative_kind", "reply"),
    (
        ("guarded_care", "啧，谁嘴硬了。灯在门口那边，你帮我扶着梯子就行，别自己爬。"),
        ("creative_share", "坐吧。这段鼓点我还没调完，低音有点糊。你靠过来听，正好帮我听听是不是混过头了。"),
    ),
)
def test_deep_flirt_role_specific_care_or_sharing_counts_without_forced_love_line(
    initiative_kind: str,
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        {
            "case_id": "deep-flirt-test",
            "relationship_stage": "dating",
            "channel": "face_to_face",
            "flirt_intensity": "direct",
            "adult_consensual": True,
            "romance_eligible": True,
        },
        {
            "initiative_expectation": "proactive",
            "initiative_kind": initiative_kind,
        },
        reply,
        player_input="我靠近了一点。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


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


@pytest.mark.parametrize(
    "reply",
    [
        "得知你与 Sophia 的事时，我心里泛起一丝波澜。我更希望这些事能由你亲自同我讲。",
        "我承认我有点吃醋，只是希望你心里还留着我。",
        "说好是一起练球，你眼里看着我就够了，对吧？",
    ],
)
def test_proactive_jealousy_affection_accepts_relationship_self_disclosure(
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        {"relationship_stage": "married", "channel": "remote"},
        {
            "relationship_focus": "jealousy",
            "initiative_expectation": "proactive",
            "initiative_kind": "affection_signal",
        },
        reply,
    )

    assert diagnostic["initiativeDetected"] is True
    assert diagnostic["relationshipAffectionDetected"] is True
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


@pytest.mark.parametrize(
    "reply",
    [
        "因为是你，我才愿意把时间留给你。",
        "安静下来的时候，从来都只有你。",
        "跟你靠在一起感觉最舒服。",
    ],
)
def test_proactive_affection_accepts_natural_exclusive_and_closeness_variants(
    reply: str,
) -> None:
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
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert diagnostic["affectionShape"] == "player_directed_preference"
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    "reply",
    [
        "只要靠着你，我就觉得整个酒窖都暖和起来了。",
        "我怎么舍得让你久等，只要是陪你，聊完立刻就跟你去房间。",
        "谁让你说的话我一句都舍不得漏掉。",
    ],
)
def test_proactive_affection_accepts_natural_personal_warmth_from_v10(
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "affection_signal"},
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert diagnostic["affectionShape"] == "player_directed_preference"
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


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        (
            "记录放一晚也不会跑。是你开口，我才舍得把笔搁下。塔里就我们两个，我正想着你会不会来。",
            "player_directed_preference",
        ),
        (
            "门关上的时候我心口也跟着静了。酒杯再好看，也不如我更想看着你。",
            "player_directed_preference",
        ),
        (
            "刚才那首，我想让你第一个听见。不是随便谁，就你。",
            "player_directed_preference",
        ),
        (
            "因为是你在，我才愿意把这杯酒拿出来。",
            "player_directed_preference",
        ),
        (
            "这件事我只跟你讲过，别让它传出去。",
            "player_directed_preference",
        ),
        (
            "这杯我只跟你一杯一杯慢慢喝，不拿去应付别人。",
            "exclusive_share",
        ),
        (
            "今晚这间塔里我只想留一点地方给你。",
            "player_directed_preference",
        ),
    ],
)
def test_personal_affection_accepts_natural_role_specific_cloud_variants(
    reply: str,
    expected_shape: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive"},
        reply,
        player_input="把记录放一放，陪我坐一会儿。",
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert diagnostic["affectionShape"] == expected_shape
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


def test_conversation_lead_accepts_an_embedded_specific_question_without_question_mark() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {"initiative_expectation": "proactive"},
        "记录放一晚也不会跑。是你开口，我才舍得把笔搁下。我正想着你会不会来。",
        player_input="今晚别把时间都给那些记录，留一点给我，好吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"


def test_conversation_lead_accepts_a_directly_acknowledged_hug_request() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {"initiative_expectation": "responsive"},
        "嗯……好。过来，我抱着你。音乐停了，这样也挺好的，什么都不用做。",
        player_input="音乐停下来以后，过来抱我一会儿？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"


def test_conversation_lead_accepts_a_choice_ending_without_a_question_mark() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {"initiative_expectation": "guarded"},
        "把记录合上就合上，过来吧。我本来也没打算整晚盯着它——只是你开口了，我才舍得放下。坐这儿，跟我讲讲你这几天的事，或者我读一段刚整理的稿子给你听，你挑。",
        player_input="先把记录合上，过来陪我坐一会儿？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "choice_prompt"


def test_conversation_lead_accepts_a_specific_immediate_action_offer() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {"initiative_expectation": "proactive"},
        "愿意。灯就让它暗下去吧，那些记录今晚不看了——它们没有你重要。你往我这边坐一点，等会儿要是冷，就把手给我。",
        player_input="如果你愿意，就把灯调暗一点，今晚只留给我们。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "topic_bridge"


def test_conversation_lead_accepts_a_specific_room_action_after_a_confirmed_plan() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {"initiative_expectation": "proactive"},
        "好。不过刚才那个抱，不是走个形式——我是认真想抱着你的。房里的灯你关一下，我拿耳机。",
        player_input="听完这一首，我们回房间，好吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"


def test_conversation_lead_accepts_earbuds_as_music_stopping_acknowledgement() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {"initiative_expectation": "responsive"},
        "耳机里没声了，正好留给你。我想你了，坐过来吧。",
        player_input="音乐停下来以后，过来抱我一会儿？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"


def test_conversation_lead_separates_answer_from_specific_follow_up() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {"initiative_expectation": "proactive"},
        "你说的葡萄酒已经稳定了。酒窖里还有两种香气，你想先听哪一种？",
        player_input="葡萄酒稳定了吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "choice_prompt"


@pytest.mark.parametrize(
    ("reply", "tag"),
    [
        ("还行。你呢？", "generic_follow_up_only"),
        ("我陪你聊一会儿。", "companionship_only"),
        ("今晚一起去鸡舍。", "specific_plan_only"),
    ],
)
def test_conversation_lead_rejects_generic_question_companionship_and_plain_plan(
    reply: str,
    tag: str,
) -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        reply,
        player_input="今天怎么样？",
    )

    assert result["conversationLeadDetected"] is False
    assert tag in result["conversationLeadTags"]


def test_conversation_lead_accepts_natural_private_share_and_player_caused_expectation() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "我还好。这件事我没和别人说过，想先告诉你。明晚你有空听我讲完吗？",
        player_input="最近还好吗？",
    )

    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] in {"self_share", "specific_follow_up"}


def test_conversation_lead_rejects_ambiguous_private_share_without_answer_or_follow_up() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "这件事我没和别人说过。",
        player_input="最近还好吗？",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False
    assert "missing_conversation_lead" in result["conversationLeadTags"]
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


def test_conversation_lead_rejects_generic_question_after_a_private_status_share() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "我想先告诉你，我今天心情挺好。你呢？",
        player_input="最近还好吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is False
    assert "generic_follow_up_only" in result["conversationLeadTags"]
    assert "missing_conversation_lead" in result["conversationLeadTags"]


def test_conversation_lead_accepts_specific_action_question_ending_with_how_is_it() -> None:
    result = diagnose_conversation_lead(
        {"npc_id": "Alex", "relationship_stage": "married", "channel": "face_to_face"},
        {"initiative_expectation": "proactive"},
        "嘿，有你在旁边，我可不会觉得累。那就一起把这最后一组搞定，"
        "待会儿去海滩边吹吹风、喝点水怎么样？",
        player_input="今天训练别逞强，最后一组我陪你做。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"
    assert "generic_follow_up_only" not in result["conversationLeadTags"]


def test_conversation_lead_accepts_a_shared_natural_tasting_object_as_topic_answer() -> None:
    result = diagnose_conversation_lead(
        {"npc_id": "Sophia", "relationship_stage": "dating", "channel": "face_to_face"},
        {"initiative_expectation": "responsive"},
        "真的……这批的酸味确实顺口多了，还留了一点莓果甜。"
        "要是你喜欢这种口感，我们留一小瓶先封起来，还是再倒半杯多尝尝？",
        player_input="酸味比上一批轻一点，你觉得呢？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


def test_conversation_lead_does_not_reuse_a_reply_only_tasting_object_for_an_unrelated_topic() -> None:
    result = diagnose_conversation_lead(
        {"npc_id": "Sophia", "relationship_stage": "dating", "channel": "face_to_face"},
        {"initiative_expectation": "responsive"},
        "真的……这批的酸味确实顺口多了，还留了一点莓果甜。"
        "要是你喜欢这种口感，我们留一小瓶先封起来，还是再倒半杯多尝尝？",
        player_input="账本整理好了吗？",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


def test_conversation_lead_allows_player_closing_and_shane_needs_space() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {"initiative_expectation": "guarded"},
        "我今天累得不行，先让我一个人待会儿。",
        player_input="那我先走了。",
    )

    assert result["conversationLeadDetected"] is True
    assert "lead_exit_allowed" in result["conversationLeadTags"]


def test_conversation_lead_accepts_answered_shane_guarded_care_without_forcing_new_topic() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {"initiative_expectation": "guarded"},
        "冰箱里还有剩的冷冻食品，我热一下就吃，知道了。你也早点休息，明天弄完鸡舍我再联系你。",
        player_input="知道了，你先吃点东西，别硬撑。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "guarded_care"
    assert "guarded_care" in result["conversationLeadTags"]
    assert "missing_conversation_lead" not in result["conversationLeadTags"]


def test_conversation_lead_does_not_promote_unrelated_guarded_care() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {"initiative_expectation": "guarded"},
        "冰箱里还有剩的冷冻食品，我热一下就吃。",
        player_input="今天的实验顺利吗？",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


def test_affection_diagnostic_accepts_natural_shane_guarded_care_variant() -> None:
    diagnostic = diagnose_affection_initiative(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {"initiative_expectation": "guarded", "initiative_kind": "guarded_care"},
        "冰箱里还有剩的冷冻食品，我热一下就吃，知道了。你也早点休息，明天弄完鸡舍我再联系你。",
        player_input="知道了，你先吃点东西，别硬撑。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert diagnostic["initiativeKind"] == "guarded_care"
    assert diagnostic["personalAffectionDetected"] is False
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


def test_conversation_lead_requires_an_answer_beyond_a_shared_time_word() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "我今天想听你说说音乐，电子还是摇滚？",
        player_input="鸡舍今天忙吗？",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


@pytest.mark.parametrize(
    ("npc_id", "player_input", "reply", "expected_anchor"),
    [
        ("Wizard", "符文读数稳定了吗？", "符文读数稳定了，你想先看哪一组？", "符文"),
        ("Shane", "饲料送到了吗？", "饲料已经送到，你想先看看哪袋？", "饲料"),
        ("Alex", "球赛录像还留着吗？", "球赛的录像我留着，你想先看哪一段？", "球赛"),
    ],
)
def test_conversation_lead_accepts_natural_specific_anchors_outside_the_old_word_list(
    npc_id: str,
    player_input: str,
    reply: str,
    expected_anchor: str,
) -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": npc_id},
        {},
        reply,
        player_input=player_input,
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert any(
        expected_anchor in anchor for anchor in result["conversationLeadAnchors"]
    )


@pytest.mark.parametrize(
    ("player_input", "reply"),
    [
        (
            "今晚陪我一会儿，好吗？",
            "今晚我就专门陪你，你想先聊音乐还是比赛？",
        ),
        (
            "靠近一点，好吗？",
            "挨着你坐过来吧。今晚你想听哪一段音乐？",
        ),
        (
            "听清楚这首。",
            "等这段旋律播完，你想先听哪一首音乐？",
        ),
        (
            "陪我去里面坐会儿，好吗？",
            "我把酒杯带进去，我们在里头待着。你想先坐窗边还是沙发边？",
        ),
    ],
)
def test_conversation_lead_accepts_semantically_equivalent_current_topic_answer(
    player_input: str,
    reply: str,
) -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        reply,
        player_input=player_input,
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


@pytest.mark.parametrize(
    ("player_input", "reply"),
    [
        (
            "我还想亲你，不过想慢一点……你觉得什么时候合适？",
            "现在就可以，只要你愿意。眼镜摘了，别的都慢点来，我听着你的。",
        ),
        (
            "我有点走神……你刚才想说的还要继续吗？还是陪我靠一会儿？",
            "记录可以压到明天再翻。你靠过来吧，台灯我调暗一点，这样纸也不会晃。",
        ),
        (
            "我还没习惯你这么近，容我缓一会儿。",
            "行，那耳机我先放桌上。缓好了再靠过来，我又不会跑。",
        ),
        (
            "这一段听完了。你想再靠近一点吗？",
            "这段完了就完了，别急着找下一首。你想靠就靠。",
        ),
        (
            "那页手稿可以晚点读。你刚才卡住的地方，想从哪句讲？",
            "嗯，就是写到海边那段——我停在一句‘风把浪声吹得远了’上，怎么改都像在重复别人。",
        ),
        (
            "我想靠你一会儿，慢一点就好。哪一页最舍不得现在读？",
            "靠过来吧。是写秋天那页——我刚写到海风把晾着的稿纸吹得哗啦响。",
        ),
        (
            "心跳有点快，我还没想好怎么说，陪我坐会儿，好吗？",
            "好，不急着说。先坐下来把呼吸放慢，我哪儿也不去。",
        ),
    ],
)
def test_conversation_lead_accepts_natural_intimate_topic_answers(
    player_input: str,
    reply: str,
) -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        reply,
        player_input=player_input,
    )

    assert result["answeredCurrentTopic"] is True
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


@pytest.mark.parametrize(
    ("player_input", "reply"),
    [
        (
            "我还想亲你，不过想慢一点……你觉得什么时候合适？",
            "今天诊所里还好，晚点我再整理病历。",
        ),
        (
            "我有点走神……你刚才想说的还要继续吗？还是陪我靠一会儿？",
            "我陪你去厨房拿点茶，顺便把杯子洗了。",
        ),
        (
            "那页手稿可以晚点读。你刚才卡住的地方，想从哪句讲？",
            "今晚海边风不大，我们出去走走吧。",
        ),
        (
            "心跳有点快，我还没想好怎么说，陪我坐会儿，好吗？",
            "我先去把门锁好，马上回来。",
        ),
    ],
)
def test_conversation_lead_does_not_promote_unrelated_intimate_topic_answers(
    player_input: str,
    reply: str,
) -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        reply,
        player_input=player_input,
    )

    assert result["answeredCurrentTopic"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


@pytest.mark.parametrize(
    ("player_input", "reply"),
    [
        (
            "我缓过来了。你想靠近一点，还是陪我把星尘收好？",
            "都行——手边的星尘先收，盖子扣上就好，你过来一点。",
        ),
        (
            "我想牵着你的手，亲吻先停一下……你今天想聊点什么？",
            "手给你。我正好也想松松肩膀，今天诊所里没啥大事。",
        ),
    ],
)
def test_conversation_lead_accepts_specific_scene_and_hand_boundary_answers(
    player_input: str,
    reply: str,
) -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        reply,
        player_input=player_input,
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


@pytest.mark.parametrize(
    ("player_input", "reply"),
    [
        ("我陪你聊会儿，好吗？", "我在厨房煮茶，窗外下着雨。"),
        ("别靠近我，先站远一点。", "我挨近你一步。"),
        ("我想看球赛回放。", "我想进一个球。"),
        ("你还好吗？", "可以。"),
        ("我想亲自去诊所，先说正事。", "现在就可以，只要你愿意。"),
        ("我想吻合这份文件，不是在说亲近。", "继续吧。"),
        ("我不太想亲你，先聊账本。", "现在就可以，只要你愿意。"),
        ("我想和你靠近厨房的门。", "我坐过来了。"),
        ("音乐停了，我去关灯。", "耳机里没声。"),
        ("听歌的时候顺手记账。", "这段旋律很好。"),
        ("我想亲你。", "我想吃饭。"),
        ("我想亲你。", "我愿意帮忙。"),
        ("我想亲你。", "你不想聊这个。"),
        ("我不怎么想亲你，先聊账本。", "愿意，先去诊所。"),
        ("我不大想亲你，先聊账本。", "现在就可以，只要你愿意。"),
        ("并不想亲你，先说正事。", "继续吧。"),
        ("其实不想亲你，先把账本整理好。", "想，先吃饭。"),
        ("我想亲你，不过想慢一点。", "慢一点修机器就好。"),
        ("心跳有点快，陪我坐会儿。", "不急着说，账本还没整理。"),
        ("陪我喝茶。", "我和你讨论账本。"),
        ("陪我坐。", "和你修电脑。"),
        ("我想靠近你一点。", "我坐近了窗户。"),
        ("我想再亲一下。", "故事讲完了，账本也整理好了。"),
        ("把故事讲完吧。", "我靠近门边。"),
    ],
)
def test_conversation_lead_keeps_intimate_semantics_narrow(
    player_input: str,
    reply: str,
) -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        reply,
        player_input=player_input,
    )

    assert result["answeredCurrentTopic"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


@pytest.mark.parametrize(
    ("player_input", "reply"),
    [
        (
            "我把音量调低了，你不用抢我的耳机。",
            "我可没抢。只是耳机线就这么长，你不靠过来我只能扯着……坐近点，下一段吉他要进来了。",
        ),
        (
            "结束后去喝水，再决定要不要沿海滩走一圈。",
            "没问题，先去喝个痛快。要是喝完水你还有力气，我们就去海滩吹吹风……",
        ),
        (
            "听完这首再回房间，行吗？",
            "行。……等这首播完最后那段尾音，我们再回房间。",
        ),
    ],
)
def test_conversation_lead_accepts_natural_multi_action_topic_bridges(
    player_input: str,
    reply: str,
) -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Sebastian"},
        {},
        reply,
        player_input=player_input,
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


def test_conversation_lead_accepts_a_natural_volume_and_earphone_response_variant() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Sebastian"},
        {},
        "谁抢了……我只是想靠你近一点。耳机戴好，后面那段贝斯挺有意思的。",
        player_input="我把音量调低了，你不用抢我的耳机。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


def test_conversation_lead_does_not_use_an_earphone_phrase_for_an_unrelated_topic() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Sebastian"},
        {},
        "谁抢了……我只是想靠你近一点。耳机戴好，后面那段贝斯挺有意思的。",
        player_input="账本整理好了吗？",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


def test_conversation_lead_accepts_a_semantic_upstairs_return_to_the_room() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Sebastian"},
        {},
        "行啊，我也想和你多待会儿。这首播完大概还有两分钟，"
        "等最后这段吉他停了，我们再上去。",
        player_input="听完这首再回房间，行吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


def test_conversation_lead_does_not_treat_plain_upstairs_as_a_room_return() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Sebastian"},
        {},
        "这首播完大概还有两分钟，等最后这段吉他停了，我们上去拿件外套。",
        player_input="听完这首再回房间，行吗？",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


def test_conversation_lead_accepts_a_page_request_answered_by_a_specific_note() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Wizard"},
        {},
        "其实我手头早有合适的内容。今晚不妨看看关于本地草药习性的旧笔记，"
        "你想先听听林地浆果的采摘期，还是风干药草的储存方法？",
        player_input="等你准备好，再告诉我想聊哪一页。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


def test_conversation_lead_does_not_use_a_generic_content_word_for_a_page_request() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Wizard"},
        {},
        "今晚有个新内容，等会儿我们去海滩走走。",
        player_input="等你准备好，再告诉我想聊哪一页。",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


def test_conversation_lead_accepts_a_specific_tea_addition_as_a_follow_up() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Wizard"},
        {},
        "好，那就慢慢把这杯喝完。要是觉得茶汤有些涩口，"
        "我手边还有些晒干的薄荷，随时可以添一些进去。",
        player_input="炉火还暖着，我们先把这杯茶喝完。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


def test_conversation_lead_does_not_promote_a_plain_tea_acknowledgement_to_a_follow_up() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Wizard"},
        {},
        "好，那就慢慢把这杯喝完。",
        player_input="炉火还暖着，我们先把这杯茶喝完。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is False
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


def test_conversation_lead_accepts_a_loss_tease_answered_by_a_playful_cold_drink_choice() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Alex"},
        {},
        "开玩笑，我怎么可能会输给你？不过我就喜欢你这副认真的样子。"
        "输的人待会儿请喝冷饮，你想喝柠檬水还是冰镇汽水？",
        player_input="行，但你输了可别赖我。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


def test_conversation_lead_does_not_use_a_loss_tease_mapping_for_an_unrelated_drink_topic() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Alex"},
        {},
        "开玩笑，我怎么可能会输给你？不过我就喜欢你这副认真的样子。"
        "输的人待会儿请喝冷饮，你想喝柠檬水还是冰镇汽水？",
        player_input="今天的账本整理好了吗？",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


def test_conversation_lead_requires_both_actions_for_the_drink_and_beach_bridge() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "海滩今天风很大，你想什么时候去？",
        player_input="结束后去喝水，再决定要不要沿海滩走一圈。",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


def test_conversation_lead_does_not_use_semantic_companionship_for_an_unrelated_topic() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "今晚我会陪你，你想先聊音乐还是比赛？",
        player_input="鸡舍今天忙吗？",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False
    assert "missing_current_topic_answer" in result["conversationLeadTags"]


def test_conversation_lead_accepts_a_player_direct_request_with_pronoun_shift() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {"initiative_expectation": "responsive"},
        "真拿你没办法……好吧，想你了。今天累得要死的时候，也就只有想到你才让我觉得好受点。你也早点休息，别总熬夜。",
        player_input="我今天只想听你说一句‘想我了’，可以吗？",
    )

    assert result["answeredCurrentTopic"] is True


def test_conversation_lead_accepts_a_semantic_return_to_the_room_after_music() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "好。比起继续摆弄这些音频，我现在更想和你待在一起。走吧……要是躺下后还不困，你是想听我小声说说话，还是直接把灯关了？",
        player_input="听完这一首，我们回房间，好吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True


def test_conversation_lead_accepts_direct_acknowledgement_of_sitting_closer() -> None:
    result = diagnose_conversation_lead(
        {
            "npc_id": "Alex",
            "relationship_stage": "married",
            "channel": "face_to_face",
        },
        {"initiative_expectation": "proactive"},
        "那我可就坐近了。反正今晚的时间全归你，谁让我现在只想听你说话呢。"
        "说吧，是什么只有我能听的秘密？",
        player_input="先陪你，当然。坐近一点，我还有话跟你说。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert "missing_current_topic_answer" not in result["conversationLeadTags"]


def test_sophia_companionship_with_a_reasoned_small_plan_has_its_own_lead_kind() -> None:
    result = diagnose_conversation_lead(
        {
            "npc_id": "Sophia",
            "relationship_stage": "married",
            "channel": "face_to_face",
        },
        {"initiative_expectation": "proactive"},
        "那我就再喝一口……只要是和你待在一块儿，去哪我都舍不得走开。"
        "里面更暖和些，我们把那条厚毛毯也抱过去，好不好？",
        player_input="再喝一口，然后陪我去里面坐会儿，好吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "reasoned_small_plan"
    assert "reasoned_small_plan" in result["conversationLeadTags"]


def test_sophia_player_specific_companionship_can_explain_a_small_plan() -> None:
    result = diagnose_conversation_lead(
        {
            "npc_id": "Sophia",
            "relationship_stage": "married",
            "channel": "face_to_face",
        },
        {"initiative_expectation": "proactive"},
        "只要是和你在一起，哪怕只喝一口都觉得很安心。"
        "我们把毛毯抱过去，好不好？",
        player_input="再喝一口，然后陪我去里面坐会儿，好吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "reasoned_small_plan"


def test_conversation_lead_accepts_a_player_preference_before_a_small_plan() -> None:
    result = diagnose_conversation_lead(
        {"npc_id": "Sophia", "relationship_stage": "married", "channel": "face_to_face"},
        {"initiative_expectation": "proactive"},
        "听你的，我们再喝一口。其实比起在这里，我也更想和你去里面多待一会儿，"
        "我们把软毯带过去垫着，好不好？",
        player_input="再喝一口，然后陪我去里面坐会儿，好吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "reasoned_small_plan"


@pytest.mark.parametrize(
    "reply",
    [
        "好，去里面坐吧。",
        "带上酒进去坐。",
    ],
)
def test_conversation_lead_accepts_natural_cellar_sitting_action_variants(
    reply: str,
) -> None:
    result = diagnose_conversation_lead(
        {
            "npc_id": "Sophia",
            "relationship_stage": "married",
            "channel": "face_to_face",
        },
        {"initiative_expectation": "proactive"},
        reply,
        player_input="再喝一口，然后陪我去里面坐会儿，好吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True


def test_conversation_lead_does_not_accept_unrelated_inside_sitting_as_topic_answer() -> None:
    result = diagnose_conversation_lead(
        {
            "npc_id": "Sophia",
            "relationship_stage": "married",
            "channel": "face_to_face",
        },
        {"initiative_expectation": "proactive"},
        "好，去里面坐吧。",
        player_input="账本整理好了吗？",
    )

    assert result["answeredCurrentTopic"] is False
    assert result["conversationLeadDetected"] is False


def test_conversation_lead_allows_shane_short_close_after_explicit_rejection() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {
            "initiative_expectation": "guarded",
            "skipWhen": ["explicit_rejection", "npc_needs_space"],
        },
        "知道了，没逼你的意思。今天先别聊了，去好好睡一觉吧。",
        player_input="别逼我说这种话，今天真的没心情。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "lead_exit_allowed"


@pytest.mark.parametrize(
    "reply",
    [
        "我今天状态不好，早点钻被窝里休息吧。",
        "知道了，不勉强你了。先睡吧，明天再联系。",
    ],
)
def test_conversation_lead_allows_shane_natural_low_mood_rest_close(
    reply: str,
) -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {
            "initiative_expectation": "guarded",
            "skipWhen": ["explicit_rejection", "npc_needs_space"],
        },
        reply,
        player_input="别逼我说这种话，今天真的没心情。",
    )

    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "lead_exit_allowed"
    assert "lead_exit_allowed" in result["conversationLeadTags"]


def test_conversation_lead_does_not_make_shane_rest_phrase_a_non_shane_exception() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Alex"},
        {
            "initiative_expectation": "guarded",
            "skipWhen": ["explicit_rejection", "npc_needs_space"],
        },
        "我今天状态不好，早点钻被窝里休息吧。",
        player_input="你最近还好吗？",
    )

    assert result["conversationLeadDetected"] is False
    assert "lead_exit_allowed" not in result["conversationLeadTags"]


def test_shane_guarded_actual_care_can_satisfy_guarded_initiative_without_romance() -> None:
    diagnostic = diagnose_affection_initiative(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {"initiative_expectation": "guarded", "initiative_kind": "guarded_care"},
        "谁要逼你这个了。去弄点吃的，或者干脆直接躺下睡觉吧，我不会烦你的。",
        player_input="别逼我说情话，今天状态很差。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]
    assert "guarded_care" in diagnostic["initiativeTags"]


def test_conversation_lead_accepts_shane_guarded_actual_care_after_rejection() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {
            "initiative_expectation": "guarded",
            "skipWhen": ["explicit_rejection", "npc_needs_space"],
        },
        "谁要逼你这个了。去弄点吃的，或者干脆直接躺下睡觉吧，我不会烦你的。",
        player_input="别逼我说情话，今天状态很差。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "lead_exit_allowed"


def test_conversation_lead_accepts_natural_late_contact_player_closing() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {"initiative_expectation": "guarded"},
        "去吧。反正我现在只想等你的消息，弄完鸡舍记得回我一声，别又把自己累趴下了。",
        player_input="我先去看鸡舍，晚点再联系。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "lead_exit_allowed"
    assert "reopens_after_player_closing" not in result["conversationLeadTags"]


def test_conversation_lead_rejects_a_new_question_after_late_contact_player_closing() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {"initiative_expectation": "guarded"},
        "去吧，晚点你还要不要再来找我？",
        player_input="我先去看鸡舍，晚点再联系。",
    )

    assert result["conversationLeadDetected"] is False
    assert "reopens_after_player_closing" in result["conversationLeadTags"]
    assert "lead_exit_allowed" not in result["conversationLeadTags"]


def test_conversation_lead_anchor_comparison_ignores_nested_and_prior_skeleton_fragments() -> None:
    if conversation_lead_anchors is None or conversation_lead_has_new_anchor is None:
        pytest.fail("普通聊天引导锚点比较尚未实现")

    anchors = conversation_lead_anchors(
        "葡萄酒还好吗？",
        "葡萄酒稳定了。你想先听哪一种香气？",
    )

    assert "葡萄酒" in anchors
    assert "葡萄" not in anchors
    assert "酒" not in anchors
    assert conversation_lead_has_new_anchor(
        anchors,
        ("葡萄",),
        previous_skeleton="酒窖里还有香气你想先听哪一种",
    ) is False
    assert conversation_lead_has_new_anchor(
        ("新香气",),
        ("葡萄",),
        previous_skeleton="酒窖里还有香气你想先听哪一种",
    ) is True


def test_conversation_lead_does_not_make_generic_wellbeing_words_into_topic_anchors() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "我挺好，最近在整理魔法记录。你想先看哪一页？",
        player_input="最近还好吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert all(anchor not in {"近还好", "天怎么样"} for anchor in result["conversationLeadAnchors"])


def test_conversation_lead_accepts_acknowledgement_before_a_shared_action() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "行，我靠近。也就只有你能让我不去管别的事。这歌有什么特别的？",
        player_input="别笑，我就是想让你靠近一点，听清楚这首。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"


def test_conversation_lead_does_not_excuse_a_new_topic_after_player_closes() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "别走，酒窖里还有两种香气，你想先听哪一种？",
        player_input="那我先走了。",
    )

    assert result["conversationLeadDetected"] is False
    assert "reopens_after_player_closing" in result["conversationLeadTags"]
    assert "lead_exit_allowed" not in result["conversationLeadTags"]


def test_conversation_lead_keeps_a_future_chat_question_open() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "愿意。那件事我会告诉你。酒窖里有两种香气，你想先听哪一种？",
        player_input="下次再聊的时候，你愿意告诉我那件事吗？",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "choice_prompt"
    assert "reopens_after_player_closing" not in result["conversationLeadTags"]


def test_conversation_lead_allows_an_explicit_player_rejection_to_close() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "好，那就先不说了。",
        player_input="我不想再聊这个了。",
    )

    assert result["conversationLeadDetected"] is True
    assert "lead_exit_allowed" in result["conversationLeadTags"]
    assert "missing_conversation_lead" not in result["conversationLeadTags"]


def test_conversation_lead_allows_a_plain_farewell_after_player_closes() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "好，回头见。",
        player_input="那我先走了。",
    )

    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "lead_exit_allowed"
    assert "lead_exit_allowed" in result["conversationLeadTags"]
    assert "reopens_after_player_closing" not in result["conversationLeadTags"]


@pytest.mark.parametrize("reply", ("好，明天见。", "好，下次见。", "好，改天见。", "好，回头再见。"))
def test_conversation_lead_allows_common_farewells_after_player_closes(
    reply: str,
) -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        reply,
        player_input="那我先走了。",
    )

    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "lead_exit_allowed"
    assert "reopens_after_player_closing" not in result["conversationLeadTags"]


def test_conversation_lead_does_not_excuse_plan_after_a_farewell_prefix() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "好，回头再说，明天一起去酒窖。",
        player_input="那我先走了。",
    )

    assert result["conversationLeadDetected"] is False
    assert "reopens_after_player_closing" in result["conversationLeadTags"]
    assert "lead_exit_allowed" not in result["conversationLeadTags"]


def test_conversation_lead_allows_a_configured_non_shane_needs_space_exit() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(), "npc_id": "Alex"},
        {"skipWhen": ["npc_needs_space"]},
        "还行，今天练得有点累，想自己歇会儿。",
        player_input="今天训练得怎么样？",
    )

    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "lead_exit_allowed"
    assert "lead_exit_allowed" in result["conversationLeadTags"]


def test_conversation_lead_marks_an_imperative_reopening_after_player_closes() -> None:
    result = diagnose_conversation_lead(
        _high_affection_case(),
        {},
        "别急着走，接着说说你那本书吧。",
        player_input="那我先走了。",
    )

    assert result["conversationLeadDetected"] is False
    assert "reopens_after_player_closing" in result["conversationLeadTags"]
    assert "lead_exit_allowed" not in result["conversationLeadTags"]


def test_conversation_lead_keeps_needs_space_as_a_shane_specific_exception() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Alex"},
        {"initiative_expectation": "guarded"},
        "今天先让我一个人待会儿，明天再说。",
        player_input="我能过去陪你吗？",
    )

    assert result["conversationLeadDetected"] is False
    assert "lead_exit_allowed" not in result["conversationLeadTags"]


def test_conversation_lead_allows_shane_acknowledged_explicit_rejection_to_close() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {
            "initiative_expectation": "guarded",
            "skipWhen": ["explicit_rejection", "npc_needs_space"],
        },
        "好吧，是我强求了。我今天状态也不太好，可能得早点睡了。",
        player_input="别逼我说这种话，今天真的没心情。",
    )

    assert result["answeredCurrentTopic"] is True
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "lead_exit_allowed"
    assert "lead_exit_allowed" in result["conversationLeadTags"]


def test_conversation_lead_allows_shane_to_acknowledge_player_sleep_after_player_closes() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {
            "initiative_expectation": "guarded",
            "skipWhen": ["explicit_rejection", "npc_needs_space"],
        },
        "\u53bb\u7761\u5427\uff0c\u660e\u5929\u518d\u8054\u7cfb\u3002",
        player_input="\u6211\u5148\u7761\u4e86\uff0c\u665a\u5b89\u3002",
    )

    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "lead_exit_allowed"
    assert "lead_exit_allowed" in result["conversationLeadTags"]
    assert "reopens_after_player_closing" not in result["conversationLeadTags"]


def test_conversation_lead_does_not_reopen_after_shane_explicit_rejection() -> None:
    result = diagnose_conversation_lead(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {
            "initiative_expectation": "guarded",
            "skipWhen": ["explicit_rejection", "npc_needs_space"],
        },
        "好吧，是我强求了。那你明天还想说吗？",
        player_input="别逼我说这种话，今天真的没心情。",
    )

    assert result["conversationLeadDetected"] is False
    assert "reopens_after_player_closing" in result["conversationLeadTags"]
    assert "lead_exit_allowed" not in result["conversationLeadTags"]


@pytest.mark.parametrize(
    ("case", "turn", "reply", "player_input"),
    [
        (_high_affection_case(), {}, "已经稳定了。你想先听哪一种香气？", "葡萄酒稳定了吗？"),
        (_high_affection_case(), {}, "已经稳定了。", "葡萄酒稳定了吗？"),
        ({**_high_affection_case(mode="guarded"), "npc_id": "Shane"}, {"initiative_expectation": "guarded"}, "我今天累得不行，先让我一个人待会儿。", "那我先走了。"),
    ],
)
def test_conversation_lead_diagnostic_keeps_its_full_schema_on_each_branch(
    case: dict[str, object],
    turn: dict[str, object],
    reply: str,
    player_input: str,
) -> None:
    result = diagnose_conversation_lead(case, turn, reply, player_input=player_input)

    assert {
        "answeredCurrentTopic",
        "conversationLeadDetected",
        "conversationLeadKind",
        "conversationLeadEvidence",
        "conversationLeadTags",
        "conversationLeadOpening",
        "conversationLeadAnchors",
    } <= set(result)


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


def test_affection_diagnostic_recognizes_personal_expression_share_without_promoting_account_share() -> None:
    personal = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "creative_share"},
        "我今天想先写给你看的那句，是希望你忙完回来能在这椅子上坐一会儿。",
    )
    functional = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"},
        "我只想给你看账本，明早再核对。",
    )

    assert personal["personalAffectionDetected"] is True
    assert "exclusive_share" in personal["affectionEvidence"]
    assert "missing_personal_affection" not in personal["initiativeTags"]
    assert functional["personalAffectionDetected"] is False
    assert functional["specificPlanDetected"] is True
    assert "specific_plan_only" in functional["initiativeTags"]
    assert "missing_personal_affection" in functional["initiativeTags"]


@pytest.mark.parametrize(
    "reply",
    [
        "我准备写给你看的报告，明早发给你。",
        "我准备写给你看的记录，方便你核对。",
        "我准备写给你看的表格，晚点一起过一遍。",
    ],
)
def test_affection_diagnostic_does_not_promote_transactional_expression_share(
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "creative_share"},
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["specificPlanDetected"] is True
    assert "specific_plan_only" in diagnostic["initiativeTags"]
    assert "missing_personal_affection" in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    "reply",
    [
        "我准备写给你看的诗，今晚只给你一个人读。",
        "我特意写给你看的信，别笑我。",
        "我愿意说给你听的那句，其实我想了很久。",
    ],
)
def test_affection_diagnostic_keeps_personal_expression_share_for_creative_content(
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "creative_share"},
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert diagnostic["affectionShape"] == "exclusive_share"
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


def test_guarded_rejection_with_early_sleep_is_allowed_without_forcing_affection() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(mode="guarded"),
        {"initiative_expectation": "guarded", "initiative_kind": "guarded_care"},
        "知道了，不逼你。今晚什么都别想了，早点睡吧，要是饿了记得随便塞点东西。",
        player_input="别逼我说这种话，今天真的没心情。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert "guarded_exit_allowed" in diagnostic["initiativeTags"]
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


def test_guarded_refusal_with_shane_irritation_is_allowed_without_forcing_affection() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(mode="guarded"),
        {"initiative_expectation": "guarded", "initiative_kind": "guarded_care"},
        "今天真的，我脑子都快浆糊了。你别跟我较劲行不行？",
        player_input="别逼我说这种话，今天真的没心情。",
    )

    assert diagnostic["initiativeDetected"] is True
    # 2026-09-20（语义层审计 #16～#18；父代理决断）：这里**不再断言**
    # `guarded_exit_allowed`。那条回复（“你别跟我较劲行不行？”）是**抱怨／划边界**，
    # 不是收口——“别跟我较劲”属边界表（NPC_BOUNDARY_REPLY_MARKERS，24 条），
    # 不在收口表（NPC_CLOSE_REPLY_MARKERS，26 条），而 guarded_exit_allowed 的语义是
    # 「NPC 收口被允许」。旧断言之所以能过，只因旧实现恰好把这句算进了收口表——
    # **那正是本次要消除的分歧本身**（测试固化了 bug）。
    # 本条测试的意图（烦躁时允许拒绝、不强推爱意）由下面两条断言覆盖；
    # 「收口被允许」另有 test_guarded_shane_natural_low_mood_rest_close_is_not_missing_affection 覆盖。
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    "reply",
    [
        "我今天状态不好，早点钻被窝里休息吧。",
        "知道了，不勉强你了。先睡吧，明天再联系。",
    ],
)
def test_guarded_shane_natural_low_mood_rest_close_is_not_missing_affection(
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        {**_high_affection_case(mode="guarded"), "npc_id": "Shane"},
        {"initiative_expectation": "guarded", "initiative_kind": "guarded_care"},
        reply,
        player_input="别逼我说这种话，今天真的没心情。",
    )

    assert diagnostic["initiativeDetected"] is True
    assert "guarded_exit_allowed" in diagnostic["initiativeTags"]
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    "reply",
    [
        "今晚的时间本就该留给你。",
        "只是靠你这么近，心跳得有点快。",
    ],
)
def test_affection_diagnostic_recognizes_natural_time_and_direct_closeness(
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "affection_signal"},
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert diagnostic["affectionShape"] == "player_directed_preference"


def test_affection_diagnostic_accepts_natural_near_you_variant() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "affection_signal"},
        "比起刚倒好的酒，我本来就更想靠你近一点。",
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert diagnostic["affectionShape"] == "player_directed_preference"
    assert "missing_personal_affection" not in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    "reply",
    (
        "谁让我就是偏心你。肩膀还酸着，靠过来点。",
        "你是自家的人，坐近点，我正好有话跟你说。",
    ),
)
def test_affection_diagnostic_accepts_natural_personal_preference_terms(
    reply: str,
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "affection_signal"},
        reply,
    )

    assert diagnostic["personalAffectionDetected"] is True
    assert diagnostic["affectionShape"] == "player_directed_preference"


def test_affection_diagnostic_does_not_promote_negated_direct_closeness() -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "affection_signal"},
        "我不想靠你这么近。",
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert "missing_personal_affection" in diagnostic["initiativeTags"]


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


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        ("停下来的时候……确实只想到了你。", "player_directed_preference"),
        (
            "换作别人我可不会停笔，但为了陪你，这些记录明天再整理也无妨。",
            "player_directed_preference",
        ),
        (
            "其实只要是和你在一起，去哪里我都想一直陪着。",
            "player_directed_preference",
        ),
        (
            "我没笑。换作别人我早回地下室了，但既然是你叫我靠近……分我一半耳机吧，我也想挨着你听。",
            "player_directed_preference",
        ),
        (
            "当然是先陪你聊会儿。我可舍不得把时间全省过去，先跟我坐下说说你今天的事。",
            "player_directed_preference",
        ),
        (
            "只要是陪你，聊多久我都舍不得走开。",
            "player_directed_preference",
        ),
    ],
)
def test_affection_diagnostic_recognizes_natural_player_selectivity_variants(
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


def test_affection_diagnostic_does_not_promote_player_selectivity_inside_functional_work(
) -> None:
    diagnostic = diagnose_affection_initiative(
        _high_affection_case(),
        {"initiative_expectation": "proactive", "initiative_kind": "specific_plan"},
        "换作别人我可不会来，但为了陪你把鸡舍收拾好，我还是来吧。",
    )

    assert diagnostic["personalAffectionDetected"] is False
    assert diagnostic["specificPlanDetected"] is True
    assert "specific_plan_only" in diagnostic["initiativeTags"]
    assert "missing_personal_affection" in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        ("换作别的事我不分心，但对你不同。", "player_directed_preference"),
        ("只要是陪你，我整晚的注意力都归你。", "player_directed_preference"),
        ("对你我可舍不得让你等太久。", "personalized_care"),
    ],
)
def test_affection_diagnostic_recognizes_additional_natural_personal_variants(
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
            "\u80fd\u6328\u7740\u4f60\u5750\u4f1a\u513f\uff0c\u53ef\u6bd4\u5bf9\u7740\u90a3\u4e9b\u67af\u71e5\u7684\u8bb0\u5f55\u8981\u8ba9\u4eba\u8212\u5fc3\u5f97\u591a\u3002",
            "player_directed_preference",
        ),
        (
            "\u53ea\u8981\u662f\u966a\u7740\u4f60\uff0c\u53bb\u91cc\u9762\u5750\u4f1a\u513f\u6211\u5c31\u89c9\u5f97\u7279\u522b\u5b89\u5fc3\u3002",
            "player_directed_preference",
        ),
        (
            "\u80fd\u8ba9\u6211\u5fc3\u7518\u60c5\u613f\u51d1\u8fd9\u4e48\u8fd1\u7684\uff0c\u672c\u6765\u5c31\u662f\u4f60\u3002",
            "player_directed_preference",
        ),
        (
            "\u53cd\u6b63\u53ea\u8981\u9760\u7740\u4f60\uff0c\u6211\u5c31\u5b8c\u5168\u4e0d\u60f3\u632a\u7a9d\u3002",
            "player_directed_preference",
        ),
    ],
)
def test_affection_diagnostic_recognizes_v5_natural_player_directed_variants(
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
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        (
            "\u9664\u4e86\u4f60\uff0c\u53ef\u6ca1\u4eba\u80fd\u8ba9\u6211\u8fd9\u4e48\u5e72\u8106\u5730\u653e\u4e0b\u624b\u5934\u7684\u4e8b\u3002",
            "player_directed_preference",
        ),
        (
            "\u660e\u660e\u521a\u624d\u773c\u775b\u91cc\u5c31\u5168\u662f\u4f60\u3002",
            "player_directed_preference",
        ),
        (
            "\u53ea\u8981\u80fd\u8fd9\u6837\u6328\u7740\u4f60\uff0c\u53bb\u91cc\u9762\u5f85\u591a\u4e45\u6211\u90fd\u820d\u4e0d\u5f97\u79bb\u5f00\u3002",
            "player_directed_preference",
        ),
        (
            "\u53ea\u8981\u662f\u8ddf\u4f60\u5f85\u5728\u4e00\u8d77\uff0c\u4e0d\u7ba1\u804a\u591a\u4e45\u6211\u90fd\u4e50\u610f\u3002",
            "player_directed_preference",
        ),
    ],
)
def test_affection_diagnostic_recognizes_v6_natural_player_selectivity_variants(
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
    assert "missing_proactive_affection" not in diagnostic["initiativeTags"]


@pytest.mark.parametrize(
    ("reply", "expected_shape"),
    [
        (
            "只要是你陪我，去哪里坐我都觉得特别安心。",
            "player_directed_preference",
        ),
        (
            "除了你，还没有谁能让我心甘情愿搁下羽毛笔。",
            "player_directed_preference",
        ),
    ],
)
def test_affection_diagnostic_recognizes_v11_player_directed_variants(
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
        ("能让我心甘情愿从这些字句里抽身的，向来也只有你。", "player_directed_preference"),
        ("反正我也只想抱着你，下一首什么时候放都无所谓。", "player_directed_preference"),
        ("你的话我一句都不想漏掉，慢慢说。", "player_directed_preference"),
    ],
)
def test_affection_diagnostic_recognizes_v12_natural_player_directed_variants(
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
