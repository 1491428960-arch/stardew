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
