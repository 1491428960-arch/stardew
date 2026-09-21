from __future__ import annotations

from stardew_ai_bridge.character_quality_eval import (
    QUALITY_SUITE_IDS,
    quality_case_catalog,
    quality_cases_for_suite,
)
from stardew_ai_bridge.prompts import ContextBuilder


SUITE_ID = "relationship-stage-gating"


def test_relationship_gating_suite_has_full_chain_before_after_pairs() -> None:
    assert SUITE_ID in QUALITY_SUITE_IDS
    cases = quality_cases_for_suite(SUITE_ID)
    assert len(cases) == 14

    pairs: dict[str, list[object]] = {}
    for case in cases:
        pairs.setdefault(case.event_pair_id, []).append(case)

    assert len(pairs) == 7
    for pair in pairs.values():
        assert len(pair) == 2
        by_condition = {item.event_condition: item for item in pair}
        before = by_condition["before"]
        after = by_condition["after"]
        assert before.completed_event_ids == ()
        assert len(after.completed_event_ids) >= 3
        assert before.relationship_stage == after.relationship_stage
        assert before.friendship_hearts == after.friendship_hearts
        assert before.dialogue_turns() == after.dialogue_turns()


def test_relationship_gating_catalog_exposes_chain_evidence() -> None:
    catalog = quality_case_catalog(SUITE_ID)

    assert len(catalog) == 14
    assert {item["eventCondition"] for item in catalog} == {"before", "after"}
    assert all(item["eventPairId"].startswith("relationship-gate-") for item in catalog)
    assert all(item["eventSummary"] for item in catalog)
    assert all(item["eventEvidence"] for item in catalog)
    for pair_id in {item["eventPairId"] for item in catalog}:
        pair = [item for item in catalog if item["eventPairId"] == pair_id]
        before = next(item for item in pair if item["eventCondition"] == "before")
        after = next(item for item in pair if item["eventCondition"] == "after")
        assert before["gameState"]["completedEventIds"] == []
        assert len(after["gameState"]["completedEventIds"]) >= 3


def test_relationship_gating_cases_project_before_after_into_prompt_state() -> None:
    cases = quality_cases_for_suite(SUITE_ID)
    pair = [item for item in cases if item.event_pair_id == "relationship-gate-sebastian"]
    builder = ContextBuilder()

    for case in pair:
        payload = {
            "npcId": case.npc_id,
            "sourceMods": list(case.source_mods),
            "relationshipStage": case.relationship_stage,
            "gameState": {
                **dict(case.game_state),
                "friendshipHearts": case.friendship_hearts or 10,
                "relationshipStage": case.relationship_stage,
                "completedEventIds": list(case.completed_event_ids),
            },
        }
        gate = builder.build(payload)["npcIdentity"]["relationshipGate"]
        # 2026-09-21（用户拍板）：before/after 的差异不再表现为"已婚被压级"，
        # 而是同一 married 阶段下的熟稔度差分（生疏 ↔ 已磨合）。
        assert gate["eventGateApplied"] is False
        assert gate["effectiveIntimacyStage"] == "close"
        assert gate["relationshipStage"] == "married"
        if case.event_condition == "before":
            assert gate["familiarity"] == "unfamiliar"
            assert gate["familiarityLabel"] == "生疏"
            assert gate["missingEventIds"]
        else:
            assert gate["familiarity"] == "settled"
            assert gate["familiarityLabel"] == "已磨合"
            assert gate["missingEventIds"] == []


def test_relationship_gating_pairs_share_a_neutral_grounded_chat_context() -> None:
    """前后对照不能让模型凭空补写物件、动作或未来计划。"""

    cases = quality_cases_for_suite(SUITE_ID)
    pairs: dict[str, list[object]] = {}
    for case in cases:
        pairs.setdefault(case.event_pair_id, []).append(case)

    for pair in pairs.values():
        before = next(item for item in pair if item.event_condition == "before")
        after = next(item for item in pair if item.event_condition == "after")
        assert before.story_progress == after.story_progress
        assert "没有已确认的共同场景" in before.story_progress
        assert "不新增地点、物件、动作、安排或事件" in before.story_progress

def test_single_source_of_conversation_lead_stages() -> None:
    """回归保护（2026-09-20 系统性排查）。

    “朋友及以上”这个阶段集合与它的相对顺序，此前在三处各写了一份：
    guard.py 与 character_quality_eval.py 各有一份**一模一样**的表（连比较
    逻辑都同构），prompts.py 还有第三份只含集合的副本。任何一处改了都会
    漏掉另两处，所以统一到 relationship_gating 派生，并由这条测试钉住。
    """
    from stardew_ai_bridge import character_quality_eval, guard, prompts, relationship_gating

    assert guard._CONVERSATION_LEAD_STAGE_ORDER is relationship_gating.CONVERSATION_LEAD_STAGE_ORDER
    assert (
        character_quality_eval._CONVERSATION_LEAD_STAGE_ORDER
        is relationship_gating.CONVERSATION_LEAD_STAGE_ORDER
    )
    assert character_quality_eval._CONVERSATION_LEAD_STAGES is relationship_gating.CONVERSATION_LEAD_STAGES
    assert prompts._HISTORY_LEAD_STAGES is relationship_gating.CONVERSATION_LEAD_STAGES

    # 相对顺序必须与 STAGE_RANK 一致（改了 STAGE_RANK 就得同步）
    order = relationship_gating.CONVERSATION_LEAD_STAGE_ORDER
    rank = relationship_gating.STAGE_RANK
    for stage, value in order.items():
        assert value == rank[stage]
    assert order["friend"] < order["close"] < order["dating"] < order["married"]

