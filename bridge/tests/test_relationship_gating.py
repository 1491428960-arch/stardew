from __future__ import annotations

import pytest

from stardew_ai_bridge.prompts import ContextBuilder
from stardew_ai_bridge.relationship_gating import (
    relationship_event_gates,
    resolve_relationship_gate,
)


_ALL_EVENT_GATE_ROLES = (
    "Wizard",
    "Sophia",
    "Shane",
    "Sebastian",
    "Alex",
    "Elliott",
    "Harvey",
)


@pytest.mark.parametrize("npc_id", _ALL_EVENT_GATE_ROLES)
def test_all_event_gate_roles_cover_unknown_before_and_after_matrix(
    npc_id: str,
) -> None:
    gates = relationship_event_gates(npc_id)
    assert gates
    close_event_ids = gates[-1].required_event_ids

    unknown = resolve_relationship_gate(
        npc_id,
        relationship_stage="married",
        friendship_hearts=10,
    )
    assert unknown.effective_stage == "married"
    assert unknown.effective_intimacy_stage == "married"
    assert unknown.event_gate_applied is False
    assert unknown.relationship_status_preserved is True

    before = resolve_relationship_gate(
        npc_id,
        relationship_stage="married",
        friendship_hearts=10,
        completed_event_ids=(),
    )
    assert before.effective_stage == "married"
    assert before.effective_intimacy_stage == "acquaintance"
    assert before.event_gate_applied is True
    assert before.relationship_status_preserved is True
    assert before.missing_event_ids == gates[0].required_event_ids

    after = resolve_relationship_gate(
        npc_id,
        relationship_stage="married",
        friendship_hearts=10,
        completed_event_ids=close_event_ids,
    )
    assert after.effective_stage == "married"
    assert after.effective_intimacy_stage == "close"
    assert after.event_gate_applied is False
    assert after.relationship_status_preserved is True
    assert after.missing_event_ids == ()


def test_high_hearts_without_first_event_are_capped_at_acquaintance() -> None:
    result = resolve_relationship_gate(
        "Sebastian",
        relationship_stage="close",
        friendship_hearts=8,
        completed_event_ids=(),
    )

    assert result.heart_stage == "close"
    assert result.event_unlocked_stage == "acquaintance"
    assert result.effective_stage == "acquaintance"
    assert result.missing_event_ids == ("2794460",)


def test_event_chain_unlocks_the_next_narrative_stage() -> None:
    result = resolve_relationship_gate(
        "Sebastian",
        relationship_stage="close",
        friendship_hearts=8,
        completed_event_ids=("2794460", "384883", "27", "29"),
    )

    assert result.event_unlocked_stage == "close"
    assert result.effective_stage == "close"
    assert result.missing_event_ids == ()


def test_missing_event_state_does_not_trigger_an_assumed_downgrade() -> None:
    result = resolve_relationship_gate(
        "Sebastian",
        relationship_stage="close",
        friendship_hearts=8,
    )

    assert result.effective_stage == "close"
    assert result.event_gate_configured is True
    assert result.event_gate_applied is False


def test_marriage_status_is_preserved_while_event_gate_caps_intimacy() -> None:
    result = resolve_relationship_gate(
        "Sebastian",
        relationship_stage="married",
        friendship_hearts=10,
        completed_event_ids=(),
    )

    assert result.effective_stage == "married"
    assert result.effective_intimacy_stage == "acquaintance"
    assert result.relationship_status_preserved is True


def test_completed_event_chain_does_not_leave_marriage_gate_active() -> None:
    result = resolve_relationship_gate(
        "Sebastian",
        relationship_stage="married",
        friendship_hearts=10,
        completed_event_ids=("2794460", "384883", "27", "29"),
    )

    assert result.effective_stage == "married"
    assert result.effective_intimacy_stage == "close"
    assert result.event_gate_applied is False


def test_unresolved_event_configuration_does_not_downgrade_sophia() -> None:
    result = resolve_relationship_gate(
        "Sophia",
        relationship_stage="close",
        friendship_hearts=8,
        completed_event_ids=(),
    )

    assert result.event_gate_configured is True
    assert result.effective_stage == "acquaintance"
    assert "8185291" in result.missing_event_ids


def test_context_uses_effective_stage_profile_and_exposes_gate_state() -> None:
    context = ContextBuilder().build(
        "Sebastian",
        friendshipHearts=8,
        relationshipStage="close",
        completedEventIds=[],
    )

    identity = context["npcIdentity"]
    assert identity["stageProfile"]["stage"] == "acquaintance"
    assert identity["stagePolicy"]["stage"] == "acquaintance"
    assert identity["relationshipGate"]["effectiveStage"] == "acquaintance"

def test_single_source_of_heart_stage_thresholds() -> None:
    """回归保护（2026-09-20 系统性排查 · 语义层）。

    「好感心数 → 关系阶段」此前有五套实现（relationship_gating / prompts /
    providers / corpus + 语料标注），且**已经漂移**：2 心时 gating 与 prompts
    判 acquaintance，而 providers 判 stranger（连带走 stranger 的短答与不主动
    策略）。夹具恰好只喂 3／4 心，所以这条分歧一直没被照到。

    现在统一到 relationship_gating.hearts_to_stage，这里把三个消费者钉在一起。
    """
    from stardew_ai_bridge import providers, relationship_gating
    from stardew_ai_bridge.models import NpcGameState

    # 权威表：2 心就是 acquaintance（这条此前被 test_relationship_gating_edges 锚定）
    assert relationship_gating.hearts_to_stage(2) == "acquaintance"
    assert relationship_gating.hearts_to_stage(1) == "stranger"
    assert relationship_gating.hearts_to_stage(6) == "friend"
    assert relationship_gating.hearts_to_stage(8) == "close"

    # providers 的整段推导必须与之一致（此前它是 3）
    for hearts, expected in ((1, "stranger"), (2, "acquaintance"), (5, "acquaintance"),
                             (6, "friend"), (8, "close")):
        state = NpcGameState(npcId="Abigail", friendshipHearts=hearts)
        assert providers.FakeProvider._relationship_stage(state) == expected, (
            f"{hearts} 心时 providers 给出 "
            f"{providers.FakeProvider._relationship_stage(state)}，应为 {expected}"
        )

    # 显式标记仍然优先于心数（此前 providers 完全忽略它们）
    assert providers.FakeProvider._relationship_stage(
        NpcGameState(npcId="Abigail", friendshipHearts=0, marriageStatus="married")
    ) == "married"
    assert providers.FakeProvider._relationship_stage(
        NpcGameState(npcId="Abigail", friendshipHearts=0, childrenCount=1)
    ) == "parent"

