from __future__ import annotations

import pytest

from stardew_ai_bridge.stage_policy import build_stage_policy


CHARACTERS = ("Wizard", "Sophia", "Shane", "Sebastian", "Alex")
STAGES = ("stranger", "acquaintance", "friend", "close")


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
        assert all(isinstance(policy[key], str) and policy[key] for key in policy)


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
    assert "affectionInitiative" not in build_stage_policy("Wizard", "parent")

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
        "不只礼貌回应" in policy["minimumExpression"]
        or "至少" in policy["minimumExpression"]
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


def test_high_affinity_reply_prioritizes_personal_affection_before_topic_or_plan() -> None:
    for npc_id in CHARACTERS:
        for stage in ("dating", "married"):
            policy = build_stage_policy(npc_id, stage)
            affection = policy["affectionInitiative"]

            assert affection["responseOrder"] == [
                "personal_affection",
                "current_topic",
                "optional_plan",
            ]
            assert "先表达" in policy["responseShape"]
            assert "先表达" in policy["initiative"]
            assert "玩家本人" in affection["minimumExpression"]


def test_dating_and_married_policy_requires_a_personal_first_signal() -> None:
    for npc_id in CHARACTERS:
        for stage in ("dating", "married"):
            policy = build_stage_policy(npc_id, stage)
            instruction = policy["affectionInitiative"]["minimumExpression"]

            assert "先" in instruction
            assert "玩家本人" in instruction
