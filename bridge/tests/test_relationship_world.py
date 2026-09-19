from __future__ import annotations

from stardew_ai_bridge.relationship_world import (
    apply_public_relationship_event,
    disclose_relationship,
    project_relationship_context,
    project_relationship_request,
    record_jealousy,
    recover_jealousy,
    resolve_mediation,
)


def test_public_wedding_makes_marriage_known_but_private_dating_stays_local() -> None:
    world = {
        "objectiveRelationships": [
            {"npcId": "Sophia", "relationType": "dating"},
            {
                "npcId": "Sebastian",
                "relationType": "married",
                "publicEventId": "wedding:sebastian",
                "publicOn": "Spring 14",
            },
        ],
        "views": [
            {
                "ownerNpcId": "Alex",
                "subjectNpcId": "Sophia",
                "relationType": "dating",
                "visibility": "unknown",
                "source": "none",
            },
            {
                "ownerNpcId": "Alex",
                "subjectNpcId": "Sebastian",
                "relationType": "married",
                "visibility": "unknown",
                "source": "none",
            },
        ],
    }

    updated = apply_public_relationship_event(world, "wedding:sebastian")
    alex = project_relationship_context("Alex", updated)
    by_subject = {item["subjectNpcId"]: item for item in alex["knowledge"]}

    assert by_subject["Sebastian"]["visibility"] == "known"
    assert by_subject["Sophia"]["visibility"] == "unknown"


def test_direct_disclosure_changes_only_the_current_npc_view() -> None:
    world = {
        "objectiveRelationships": [
            {"npcId": "Sophia", "relationType": "dating"}
        ],
        "views": [
            {
                "ownerNpcId": "Wizard",
                "subjectNpcId": "Sophia",
                "relationType": "dating",
                "visibility": "suspected",
                "source": "rumor",
            },
            {
                "ownerNpcId": "Alex",
                "subjectNpcId": "Sophia",
                "relationType": "dating",
                "visibility": "unknown",
                "source": "none",
            },
        ],
    }

    updated = disclose_relationship(
        world,
        viewer_npc_id="Wizard",
        subject_npc_id="Sophia",
    )

    assert (
        project_relationship_context("Wizard", updated)["knowledge"][0][
            "visibility"
        ]
        == "known"
    )
    assert (
        project_relationship_context("Alex", updated)["knowledge"][0][
            "visibility"
        ]
        == "unknown"
    )


def test_direct_disclosure_creates_a_view_when_the_npc_had_none() -> None:
    world = {
        "objectiveRelationships": [
            {"npcId": "Sophia", "relationType": "dating"}
        ],
        "views": [
            {
                "ownerNpcId": "Alex",
                "subjectNpcId": "Sophia",
                "relationType": "dating",
                "visibility": "unknown",
                "source": "none",
            }
        ],
    }

    updated = disclose_relationship(
        world,
        viewer_npc_id="Wizard",
        subject_npc_id="Sophia",
    )

    # 原本没有 Wizard→Sophia 的视角时要新建一条，来源标记为玩家亲口说明。
    wizard = project_relationship_context("Wizard", updated)
    assert wizard["knowledge"][0]["subjectNpcId"] == "Sophia"
    assert wizard["knowledge"][0]["visibility"] == "known"
    assert len(updated["views"]) == 2
    # 新建只影响这位 NPC，其他人保持原样；输入 world 不被就地修改。
    assert (
        project_relationship_context("Alex", updated)["knowledge"][0]["visibility"]
        == "unknown"
    )
    assert len(world["views"]) == 1


def test_direct_disclosure_without_an_objective_fact_changes_nothing() -> None:
    world = {"objectiveRelationships": [], "views": []}

    updated = disclose_relationship(
        world,
        viewer_npc_id="Wizard",
        subject_npc_id="Sophia",
    )

    # 没有可披露的客观关系时不能凭空造出一条“已知”。
    assert updated["views"] == []


def test_mediation_result_is_scoped_to_one_npc_and_does_not_remove_future_jealousy() -> None:
    world = {
        "acceptanceByNpc": {"Sophia": "not_ready", "Alex": "conditional"},
        "mediationByNpc": {"Sophia": {"status": "active", "outcome": None}},
        "jealousyByNpc": {
            "Sophia": {
                "active": True,
                "trigger": "time",
                "intensity": "light",
                "need": "固定的独处时间",
            },
        },
    }

    updated = resolve_mediation(world, "Sophia", "accepted")

    assert updated["acceptanceByNpc"]["Sophia"] == "accepted"
    assert updated["acceptanceByNpc"]["Alex"] == "conditional"
    assert updated["jealousyByNpc"]["Sophia"]["active"] is True


def test_jealousy_recovery_requires_a_concrete_response() -> None:
    jealousy = {
        "active": True,
        "trigger": "broken_promise",
        "intensity": "moderate",
        "need": "解释并履约",
    }

    assert recover_jealousy(jealousy, "generic_romantic_line")["active"] is True
    assert recover_jealousy(jealousy, "acknowledge_and_explain")["active"] is False


def test_private_dating_is_not_promoted_to_known_by_an_unrelated_event() -> None:
    world = {
        "objectiveRelationships": [
            {"npcId": "Sophia", "relationType": "dating"},
        ],
        "views": [],
    }

    updated = apply_public_relationship_event(world, "wedding:sophia")

    assert project_relationship_context("Alex", updated)["knowledge"] == []


def test_mediation_can_end_not_ready_without_becoming_a_provider_error() -> None:
    world = {"acceptanceByNpc": {"Sophia": "conditional", "Alex": "accepted"}}

    updated = resolve_mediation(
        world,
        "Sophia",
        "not_ready",
        next_step="先保留独处空间",
    )

    assert updated["acceptanceByNpc"] == {
        "Sophia": "not_ready",
        "Alex": "accepted",
    }
    assert updated["mediationByNpc"]["Sophia"]["outcome"] == "not_ready"


def test_projected_relationship_context_hides_internal_mediation_next_step() -> None:
    world = {
        "mediationByNpc": {
            "Sophia": {
                "status": "resolved",
                "outcome": "conditional",
                "nextStep": "固定周末独处",
            }
        }
    }

    context = project_relationship_context("Sophia", world)
    request = project_relationship_request("Sophia", world)

    assert context["mediation"] == {
        "status": "resolved",
        "outcome": "conditional",
    }
    assert request["mediationByNpc"]["Sophia"] == {
        "status": "resolved",
        "outcome": "conditional",
    }


def test_jealousy_trigger_is_bounded_and_can_recur_after_recovery() -> None:
    world = record_jealousy(
        {},
        "Sophia",
        "companionship",
        "light",
        "固定的陪伴时间",
    )
    recovered = {
        **world,
        "jealousyByNpc": {
            "Sophia": recover_jealousy(
                world["jealousyByNpc"]["Sophia"],
                "offer_time",
            ),
        },
    }
    recurring = record_jealousy(
        recovered,
        "Sophia",
        "broken_promise",
        "moderate",
        "解释并履约",
    )

    assert recurring["jealousyByNpc"]["Sophia"]["active"] is True
    assert recurring["jealousyByNpc"]["Sophia"]["trigger"] == "broken_promise"


def test_open_loops_are_projected_only_for_current_npc_and_active_status() -> None:
    world = {
        "openLoops": [
            {
                "loopId": "wizard:one",
                "npcId": "Wizard",
                "topic": "rune_review",
                "originChannel": "remote",
                "nextChannel": "face_to_face",
                "status": "open",
                "shortSummary": "核对符文",
                "createdOn": "Spring 14",
            },
            {
                "loopId": "sophia:one",
                "npcId": "Sophia",
                "topic": "private_topic",
                "originChannel": "remote",
                "nextChannel": "face_to_face",
                "status": "open",
                "shortSummary": "不应泄露",
                "createdOn": "Spring 14",
            },
            {
                "loopId": "wizard:done",
                "npcId": "Wizard",
                "topic": "old_topic",
                "originChannel": "remote",
                "nextChannel": "face_to_face",
                "status": "resolved",
                "shortSummary": "已完成",
                "createdOn": "Spring 13",
            },
        ],
    }

    context = project_relationship_context("Wizard", world)
    request = project_relationship_request("Wizard", world)

    assert [item["loopId"] for item in context["openLoops"]] == ["wizard:one"]
    assert [item["loopId"] for item in request["openLoops"]] == ["wizard:one"]
