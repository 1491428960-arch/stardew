from __future__ import annotations

from stardew_ai_bridge.character_quality_eval import (
    QUALITY_SUITE_IDS,
    quality_case_catalog,
    quality_cases_for_suite,
)


def test_event_impact_suite_has_control_and_completed_event_pairs() -> None:
    assert "topic-start-event-impact" in QUALITY_SUITE_IDS
    cases = quality_cases_for_suite("topic-start-event-impact")
    assert len(cases) == 14

    pairs: dict[str, list[object]] = {}
    for case in cases:
        pairs.setdefault(case.event_pair_id, []).append(case)

    assert len(pairs) == 7
    for pair_id, pair in pairs.items():
        assert len(pair) == 2, pair_id
        by_condition = {item.event_condition: item for item in pair}
        before = by_condition["before"]
        after = by_condition["after"]
        assert before.event_condition == "before"
        assert after.event_condition == "after"
        # before 有意保持空事件状态：它测的就是「事件没发生」那一侧。
        assert before.completed_event_ids == ()
        # after 声明的是「被测事件 + 该角色 close 档完整登记链」。
        # 2026-09-20 前这里只声明单个被测事件，事件锁会把已婚 10 心的案例
        # 收窄到 acquaintance，把「事件记忆差异」误判成「亲密越界」。
        assert after.event_id in after.completed_event_ids
        assert len(after.completed_event_ids) >= 3
        assert before.event_id == after.event_id
        assert before.dialogue_turns() == after.dialogue_turns()
        assert before.follow_up_mode == after.follow_up_mode == "fixed"
        assert before.topic_seed == after.topic_seed
        assert before.story_progress == after.story_progress
        assert before.game_state == after.game_state


def test_event_impact_catalog_exposes_pair_and_event_evidence() -> None:
    catalog = quality_case_catalog("topic-start-event-impact")
    assert len(catalog) == 14
    assert {item["eventCondition"] for item in catalog} == {"before", "after"}
    assert {item["eventPairId"] for item in catalog} == {
        "wizard-112",
        "shane-3900074",
        "sebastian-384882",
        "alex-20",
        "elliott-40",
        "harvey-56",
        "sophia-8185290",
    }
    assert all(item["eventId"] for item in catalog)
    assert all(item["eventSummary"] for item in catalog)
    assert all(item["eventEvidence"] for item in catalog)
    sophia = next(item for item in catalog if item["eventPairId"] == "sophia-8185290")
    assert sophia["eventSourceStatus"] == "unresolved_i18n"
