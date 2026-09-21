from __future__ import annotations

import json

import pytest

from stardew_ai_bridge.stage_policy import (
    build_stage_policy,
    relationship_discussion_policy,
)


CHARACTERS = ("Wizard", "Sophia", "Shane", "Sebastian", "Alex")
NEW_FEMALE_BACHELOR_CHARACTERS = ("Elliott", "Harvey", "Sam")
STAGES = ("stranger", "acquaintance", "friend", "close")


def test_stage_changes_discussion_readiness_but_not_acceptance_result() -> None:
    stranger = relationship_discussion_policy("Alex", "acquaintance")
    close = relationship_discussion_policy("Alex", "close")

    assert stranger["canDiscuss"] is True
    assert stranger["readiness"] == "limited"
    assert close["readiness"] == "open_to_negotiation"
    assert "acceptance" not in stranger or stranger["acceptance"] == "unset"


def test_role_policy_keeps_jealousy_role_specific() -> None:
    assert "承诺" in relationship_discussion_policy("Wizard", "dating")["roleGuidance"]
    assert "空间" in relationship_discussion_policy("Shane", "dating")["roleGuidance"]
    assert "音乐" in relationship_discussion_policy("Sebastian", "dating")["roleGuidance"]
    assert "行动" in relationship_discussion_policy("Alex", "dating")["roleGuidance"]


def test_relationship_discussion_policy_limits_replies_to_current_round_actions() -> None:
    forbidden_future_commitments = ("排期", "预约", "未来日期", "自动履约")

    for npc_id in CHARACTERS:
        policy = relationship_discussion_policy(npc_id, "dating")
        rendered = json.dumps(policy, ensure_ascii=False)

        assert "当前轮即时可发生的动作" in rendered
        assert all(
            marker not in policy["roleGuidance"]
            for marker in forbidden_future_commitments
        )


@pytest.mark.parametrize("npc_id", ("Wizard", "Sophia", "Shane", "Sebastian", "Alex"))
@pytest.mark.parametrize("stage", ("dating", "married"))
def test_high_stage_policy_does_not_request_future_schedule_commitments(
    npc_id: str,
    stage: str,
) -> None:
    rendered = json.dumps(build_stage_policy(npc_id, stage), ensure_ascii=False)

    assert "日期" not in rendered
    assert "排期" not in rendered
    assert "预约" not in rendered
    assert "自动履约" not in rendered


@pytest.mark.parametrize("stage", ["friend", "close", "dating", "married"])
def test_conversation_lead_stays_in_the_five_character_trial(stage: str) -> None:
    policies = {
        npc_id: build_stage_policy(npc_id, stage)["conversationLead"]
        for npc_id in CHARACTERS
    }

    assert build_stage_policy("Rasmodia", stage)["conversationLead"] == policies["Wizard"]
    assert "conversationLead" not in build_stage_policy("Caroline", stage)
    assert "conversationLead" not in build_stage_policy("Marnie", stage)
    assert len({tuple(policy["allowedKinds"]) for policy in policies.values()}) > 1


@pytest.mark.parametrize("npc_id", CHARACTERS)
def test_friend_conversation_lead_is_optional_but_close_and_above_remain_usual(
    npc_id: str,
) -> None:
    assert build_stage_policy(npc_id, "friend")["conversationLead"]["required"] == "optional"
    assert build_stage_policy(npc_id, "close")["conversationLead"]["required"] == "usually"
    assert build_stage_policy(npc_id, "dating")["conversationLead"]["required"] == "usually"


def test_shane_conversation_lead_allows_guarded_care_as_a_conditional_response() -> None:
    allowed_kinds = build_stage_policy("Shane", "dating")["conversationLead"]["allowedKinds"]

    assert "guarded_care" in allowed_kinds


@pytest.mark.parametrize("stage", ["friend", "close", "dating", "married"])
def test_alex_conversation_lead_can_start_with_a_brief_self_share(stage: str) -> None:
    allowed_kinds = build_stage_policy("Alex", stage)["conversationLead"]["allowedKinds"]

    assert "self_share" in allowed_kinds


def test_alex_conversation_lead_guidance_keeps_self_share_brief_and_specific() -> None:
    guidance = build_stage_policy("Alex", "dating")["conversationLead"]["roleGuidance"]

    assert "先分享一句自己的具体近况" in guidance
    assert "短、具体、带一点自信或轻微炫耀" in guidance
    assert "不要变成教练式说教" in guidance


def test_shane_conversation_lead_guidance_allows_guarded_short_careful_closing() -> None:
    guidance = build_stage_policy("Shane", "dating")["conversationLead"]["roleGuidance"]

    assert "短答或带一点嘴硬的实际照顾收口" in guidance
    assert "不需要硬补情话" in guidance


@pytest.mark.parametrize(
    ("npc_id", "required_fragments"),
    [
        (
            "Wizard",
            ("不要停在泛泛的‘你想聊什么’", "法师塔、研究记录、符文读数"),
        ),
        (
            "Sebastian",
            ("只有玩家明确提出拥抱、想抱或抱一下时", "普通靠近、分耳机、听歌或回房间时不强制拥抱"),
        ),
        (
            "Alex",
            ("按玩家的动作方向回应", "不要把玩家的陪伴改写成"),
        ),
    ],
)
def test_role_specific_conversation_lead_guidance_targets_known_quality_gaps(
    npc_id: str,
    required_fragments: tuple[str, ...],
) -> None:
    guidance = build_stage_policy(npc_id, "dating")["conversationLead"]["roleGuidance"]

    assert all(fragment in guidance for fragment in required_fragments)


def test_sophia_conversation_lead_guidance_connects_current_object_to_small_plan() -> None:
    guidance = build_stage_policy("Sophia", "dating")["conversationLead"]["roleGuidance"]

    assert "先明确接住玩家点名的酒、酒窖、喝一口等当前对象" in guidance
    assert "保留玩家点名的核心对象和数量" in guidance
    assert "再写因玩家而产生的个人感受" in guidance
    assert "最后给一个具体、可商量的小安排" in guidance


def test_sophia_conversation_lead_guidance_bridges_cellar_and_creative_topics() -> None:
    """本条的意图是「酒窖方向与创作方向都要覆盖」，不是钉死某几个词。

    2026-09-21：原断言写的是「葡萄品种 / 发酵过程 / 绘画过程」。后两个词是
    **过程导向**，会把模型推向工序名（用户实测「刚把最后一层罩光放到窗边」）。
    改成对象导向后，桥接意图由「酒窖」与「画笔／画里的具体东西」承担。
    过程导向的回归闸见 `test_role_guidance_object_focus.py`。
    """

    guidance = build_stage_policy("Sophia", "dating")["conversationLead"]["roleGuidance"]

    assert "葡萄" in guidance
    assert "酒窖" in guidance  # 酿造方向
    assert "画笔" in guidance  # 创作方向
    assert "画里的具体东西" in guidance
    assert "因为是玩家才愿意分享" in guidance


@pytest.mark.parametrize("npc_id", NEW_FEMALE_BACHELOR_CHARACTERS)
@pytest.mark.parametrize("stage", ["friend", "close", "dating", "married"])
def test_new_female_bachelor_roles_have_executable_conversation_and_relationship_policy(
    npc_id: str,
    stage: str,
) -> None:
    policy = build_stage_policy(npc_id, stage)

    assert "conversationLead" in policy
    assert policy["conversationLead"]["allowedKinds"]
    assert policy["conversationLead"]["roleGuidance"]
    assert "relationshipDiscussion" in policy
    assert policy["relationshipDiscussion"]["roleGuidance"]
    assert policy["voiceFingerprint"]
    if stage in {"dating", "married"}:
        affection = policy["affectionInitiative"]
        assert affection["allowedKinds"]
        assert affection["warmthSignals"]
        assert affection["maxActions"] == 1


def test_new_female_bachelor_roles_have_distinct_voice_and_role_guidance() -> None:
    policies = {
        npc_id: build_stage_policy(npc_id, "dating")
        for npc_id in NEW_FEMALE_BACHELOR_CHARACTERS
    }

    assert len(
        {policy["voiceFingerprint"] for policy in policies.values()}
    ) == len(NEW_FEMALE_BACHELOR_CHARACTERS)
    expected_fragments = {
        "Elliott": ("具体", "修辞"),
        "Harvey": ("照料", "专业"),
        "Sam": ("音乐", "行动"),
    }
    for npc_id, fragments in expected_fragments.items():
        rendered = json.dumps(policies[npc_id], ensure_ascii=False)
        assert all(fragment in rendered for fragment in fragments)


def test_female_bachelor_expansion_does_not_turn_sophia_or_normal_npcs_into_trial_roles() -> None:
    assert "conversationLead" in build_stage_policy("Sophia", "dating")
    assert "conversationLead" not in build_stage_policy("Caroline", "dating")
    assert "conversationLead" not in build_stage_policy("Marnie", "dating")
    assert "conversationLead" not in build_stage_policy("Linus", "dating")


def test_sebastian_conversation_lead_guidance_distinguishes_hug_from_other_closeness() -> None:
    guidance = build_stage_policy("Sebastian", "dating")["conversationLead"]["roleGuidance"]

    assert "只有玩家明确提出拥抱、想抱或抱一下时" in guidance
    assert "普通靠近、分耳机、听歌或回房间时不强制拥抱" in guidance
    assert "最近一轮已经出现拥抱时" in guidance
    assert "回复必须直接出现‘抱、抱一下、抱住、抱着’中的一种" not in guidance


def test_sebastian_conversation_lead_guidance_keeps_short_replies_substantive() -> None:
    guidance = build_stage_policy("Sebastian", "dating")["conversationLead"]["roleGuidance"]

    assert "少话不等于空或只做功能确认" in guidance
    assert "至少保留一个具体感受、判断或细节" in guidance


def test_each_evaluation_character_has_a_distinct_executable_voice_fingerprint() -> None:
    policies = {
        npc_id: build_stage_policy(npc_id, "dating")
        for npc_id in CHARACTERS
    }
    fingerprints = {
        npc_id: policy["voiceFingerprint"]
        for npc_id, policy in policies.items()
    }

    assert len(set(fingerprints.values())) == len(CHARACTERS)
    expected_fragments = {
        "Wizard": ("短判断", "观察"),
        "Sophia": ("轻柔接住", "葡萄"),
        "Shane": ("短答", "自嘲"),
        "Sebastian": ("具体对象", "冷幽默"),
        "Alex": ("短答", "具体细节", "挑战"),
    }
    for npc_id, fragments in expected_fragments.items():
        assert all(fragment in fingerprints[npc_id] for fragment in fragments)


def test_rasmodia_reuses_wizards_voice_fingerprint() -> None:
    assert build_stage_policy("Rasmodia", "dating")["voiceFingerprint"] == (
        build_stage_policy("Wizard", "dating")["voiceFingerprint"]
    )


@pytest.mark.parametrize("npc_id", CHARACTERS)
def test_every_evaluation_character_has_executable_policy_for_each_stage(
    npc_id: str,
) -> None:
    for stage in STAGES:
        policy = build_stage_policy(npc_id, stage)

        assert policy["stage"] == stage
        assert {
            "responseShape",
            "selfDisclosure",
            "initiative",
            "followUp",
            "boundaryMode",
        } <= set(policy)
        assert all(
            isinstance(policy[key], str) and policy[key]
            for key in (
                "stage",
                "responseShape",
                "selfDisclosure",
                "initiative",
                "followUp",
                "boundaryMode",
            )
        )
        if stage in {"friend", "close"}:
            assert {
                "required",
                "allowedKinds",
                "minimumExpression",
                "variationRule",
                "skipWhen",
            } <= set(policy["conversationLead"])
        else:
            assert "conversationLead" not in policy


def test_stage_policy_uses_shared_progression_but_character_specific_behavior() -> None:
    stranger = {
        npc_id: build_stage_policy(npc_id, "stranger")
        for npc_id in CHARACTERS
    }
    friend = {
        npc_id: build_stage_policy(npc_id, "friend")
        for npc_id in CHARACTERS
    }

    assert all(
        stranger[npc_id]["responseShape"] != friend[npc_id]["responseShape"]
        for npc_id in CHARACTERS
    )
    assert "不主动" in stranger["Shane"]["initiative"]
    assert "主动" in friend["Alex"]["initiative"]
    assert "创作" in friend["Sophia"]["selfDisclosure"]
    assert "编程" in friend["Sebastian"]["followUp"]
    assert "恐惧" in build_stage_policy("Wizard", "close")["selfDisclosure"]


def test_rasmodia_and_wizard_share_the_same_stage_policy() -> None:
    assert build_stage_policy("Rasmodia", "friend") == build_stage_policy(
        "Wizard", "friend"
    )


def test_unknown_stage_and_character_fall_back_safely() -> None:
    policy = build_stage_policy("Unknown", "not-a-stage")

    assert policy["stage"] == "stranger"
    assert "直接回答" in policy["responseShape"]


def test_shane_high_affection_policy_assumes_trust_but_preserves_a_boundary() -> None:
    close = build_stage_policy("Shane", "close")
    dating = build_stage_policy("Shane", "dating")
    married = build_stage_policy("Shane", "married")

    assert "信任" in close["initiative"]
    assert "初识式冷淡" in close["boundaryMode"]
    assert "主动" in dating["initiative"]
    assert "具体" in married["followUp"]


def test_dating_and_married_policies_expose_structured_affection_initiative() -> None:
    dating = {
        npc_id: build_stage_policy(npc_id, "dating")
        for npc_id in CHARACTERS
    }
    married = {
        npc_id: build_stage_policy(npc_id, "married")
        for npc_id in CHARACTERS
    }

    assert all(
        policy["affectionInitiative"]["initiativeMode"] == "proactive"
        for policy in dating.values()
        if policy["affectionInitiative"]["initiativeMode"] != "guarded"
    )
    assert all(
        policy["affectionInitiative"]["maxActions"] == 1
        for policy in (*dating.values(), *married.values())
    )
    assert {
        "initiativeMode",
        "allowedIntensities",
        "allowedKinds",
        "maxActions",
        "channelRules",
    } <= set(dating["Wizard"]["affectionInitiative"])
    assert "affectionInitiative" not in build_stage_policy("Wizard", "friend")
    # 2026-09-20（用户拍板）：parent 是「与玩家有孩子」，**继承 married 的亲密契约**。
    # 此前这里断言 parent 没有 affectionInitiative——那是遗漏而非设计：
    # parent 卡片本身的 initiative 文案就是“主动照顾彼此和孩子的实际需要”。
    assert "affectionInitiative" in build_stage_policy("Wizard", "parent")

    kinds = {
        npc_id: tuple(dating[npc_id]["affectionInitiative"]["allowedKinds"])
        for npc_id in CHARACTERS
    }
    assert len(set(kinds.values())) >= 4
    assert "guarded_care" in kinds["Shane"]
    assert "conversation_exit" in kinds["Shane"]


def test_high_affinity_policy_declares_role_specific_minimum_expression() -> None:
    policies = {
        npc_id: build_stage_policy(npc_id, "dating")["affectionInitiative"]
        for npc_id in CHARACTERS
    }

    assert all(policy["minimumExpression"] for policy in policies.values())
    assert all(
        "当前话题" in policy["minimumExpression"]
        and "不要求每轮" in policy["minimumExpression"]
        for policy in policies.values()
    )
    assert len({policy["minimumExpression"] for policy in policies.values()}) >= 4
    assert "状态允许时" in policies["Shane"]["minimumExpression"]


def test_high_affinity_policy_exposes_role_specific_warmth_signals() -> None:
    policies = {
        npc_id: build_stage_policy(npc_id, "dating")["affectionInitiative"]
        for npc_id in CHARACTERS
    }

    assert all(policy["warmthSignals"] for policy in policies.values())
    assert len({tuple(policy["warmthSignals"]) for policy in policies.values()}) >= 4
    assert any("想念" in signal for signal in policies["Wizard"]["warmthSignals"])
    assert any("实际" in signal for signal in policies["Shane"]["warmthSignals"])


def test_sebastian_and_alex_married_warmth_signals_explain_why_the_player_is_special() -> None:
    sebastian = build_stage_policy("Sebastian", "married")["affectionInitiative"]
    alex = build_stage_policy("Alex", "married")["affectionInitiative"]

    assert "音乐停下后的安静明确留给玩家" in sebastian["warmthSignals"][0]
    assert "拥抱" in sebastian["warmthSignals"][0]
    assert "今晚先选玩家" in alex["warmthSignals"][0]


def test_sophia_and_alex_married_warmth_signals_keep_a_character_specific_reason() -> None:
    sophia = build_stage_policy("Sophia", "married")["affectionInitiative"]
    alex = build_stage_policy("Alex", "married")["affectionInitiative"]

    assert any(
        "酒窖" in signal and "酒杯" in signal and "更想看玩家" in signal
        for signal in sophia["warmthSignals"]
    )
    assert any(
        "不舍得" in signal and "玩家" in signal and "时间" in signal
        for signal in alex["warmthSignals"]
    )


def test_wizard_married_warmth_signal_keeps_his_private_time_for_the_player() -> None:
    wizard = build_stage_policy("Wizard", "married")["affectionInitiative"]

    assert "因为是玩家" in wizard["warmthSignals"][0]
    assert "放下记录" in wizard["warmthSignals"][0]


def test_high_affinity_reply_prioritizes_topic_before_affection_or_plan() -> None:
    for npc_id in CHARACTERS:
        for stage in ("dating", "married"):
            policy = build_stage_policy(npc_id, stage)
            affection = policy["affectionInitiative"]

            assert affection["responseOrder"] == [
                "current_topic",
                "personal_affection",
                "optional_plan",
            ]
            assert (
                "当前话题" in policy["responseShape"]
                or "眼前事情" in policy["responseShape"]
            )
            assert (
                "当前话题" in policy["initiative"]
                or "眼前事情" in policy["initiative"]
            )
            assert "不要求每轮使用强专属情话" in affection["minimumExpression"]


def test_dating_and_married_policy_allows_topic_first_without_strong_expression() -> None:
    for npc_id in CHARACTERS:
        for stage in ("dating", "married"):
            policy = build_stage_policy(npc_id, stage)
            instruction = policy["affectionInitiative"]["minimumExpression"]

            assert "先接住当前话题" in instruction
            assert "不要求每轮使用强专属情话" in instruction


@pytest.mark.parametrize("npc_id", CHARACTERS)
@pytest.mark.parametrize("stage", ("dating", "married"))
def test_high_affinity_policy_distinguishes_personal_signals_from_support_actions(
    npc_id: str,
    stage: str,
) -> None:
    affection = build_stage_policy(npc_id, stage)["affectionInitiative"]

    assert {
        "personalSignals",
        "supportSignals",
        "variationRule",
    } <= set(affection)
    assert "exclusive_share" in affection["personalSignals"]
    assert "specific_plan" in affection["supportSignals"]
    assert "不能单独充当" in affection["minimumExpression"]
    assert affection["variationRule"]


def test_non_romance_policy_does_not_project_personal_signal_contract() -> None:
    affection = build_stage_policy("Sophia", "friend").get("affectionInitiative", {})

    assert affection == {}


@pytest.mark.parametrize("npc_id", CHARACTERS)
@pytest.mark.parametrize("stage", ["dating", "married"])
def test_high_affection_policy_exposes_bounded_expression_pacing(
    npc_id: str,
    stage: str,
) -> None:
    affection = build_stage_policy(npc_id, stage)["affectionInitiative"]
    pacing = affection["pacing"]

    assert affection["responseOrder"] == [
        "current_topic",
        "personal_affection",
        "optional_plan",
    ]
    assert pacing == {
        "defaultIntensity": "light",
        "strongSignalWindow": 3,
        "maxStrongSignals": 1,
        "strongSignalKinds": [
            "exclusive_share",
            "player_directed_preference",
            "player_caused_anticipation",
        ],
        "explicitRequestOverride": True,
        "followUpAfterStrong": [
            "current_topic",
            "support_signal",
            "conversation_exit",
        ],
        "semanticCooldown": "强专属表达按同一语义族计数，连续轮次不换词绕过冷却。",
    }
    assert "强专属" in affection["minimumExpression"]
    assert "不要求" in affection["minimumExpression"]


def test_friend_and_non_romance_policies_do_not_gain_strong_affection_pacing() -> None:
    for npc_id in CHARACTERS:
        assert "affectionInitiative" not in build_stage_policy(npc_id, "friend")
    assert "pacing" not in build_stage_policy("Caroline", "married")["affectionInitiative"]


def test_role_specific_warmth_signals_remain_distinct_after_pacing_is_added() -> None:
    policies = {
        npc_id: build_stage_policy(npc_id, "married")["affectionInitiative"]
        for npc_id in CHARACTERS
    }

    assert "记录" in "；".join(policies["Wizard"]["warmthSignals"])
    assert "酒窖" in "；".join(policies["Sophia"]["warmthSignals"])
    assert "实际" in "；".join(policies["Shane"]["warmthSignals"])
    assert "音乐" in "；".join(policies["Sebastian"]["warmthSignals"])
    assert "一起吃饭" in "；".join(policies["Alex"]["warmthSignals"])
