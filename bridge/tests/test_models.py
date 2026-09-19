from __future__ import annotations

import pytest
from pydantic import ValidationError

from stardew_ai_bridge.models import DialogueTestRequest, OpenLoopSignal


def test_dialogue_request_accepts_relationship_world_with_aliases() -> None:
    request = DialogueTestRequest.model_validate(
        {
            "npcId": "Alex",
            "message": "你听说我和 Sophia 在约会了吗？",
            "relationshipWorld": {
                "objectiveRelationships": [
                    {"npcId": "Sophia", "relationType": "dating"},
                ],
                "views": [
                    {
                        "ownerNpcId": "Alex",
                        "subjectNpcId": "Sophia",
                        "relationType": "dating",
                        "visibility": "suspected",
                        "source": "rumor",
                    },
                ],
            },
        }
    )

    assert request.relationship_world is not None
    assert request.relationship_world.views[0].visibility == "suspected"


def test_dialogue_request_accepts_current_csharp_relationship_snapshot_shape() -> None:
    request = DialogueTestRequest.model_validate(
        {
            "npcId": "Alex",
            "message": "最近农场有点忙，但今天还是想和你聊聊。",
            "relationshipWorld": {
                "objectiveRelationships": [],
                "views": [],
                "mediation": {
                    "npcId": "Alex",
                    "status": "active",
                    "outcome": "conditional",
                    "nextStep": "先把误会说清楚",
                },
                "jealousy": {
                    "npcId": "Alex",
                    "active": True,
                    "trigger": "companionship",
                    "intensity": "light",
                    "need": "希望被认真回应",
                },
                "openLoops": [
                    {
                        "loopId": "Alex:trust:Spring-14",
                        "npcId": "Alex",
                        "topic": "trust_repair",
                        "originChannel": "remote",
                        "nextChannel": "face_to_face",
                        "status": "open",
                        "shortSummary": "线上留下了需要当面解释的关系话题",
                        "createdOn": "Spring 14",
                    },
                ],
            },
        }
    )

    assert request.relationship_world is not None
    assert request.relationship_world.mediation_by_npc["Alex"].status == "active"
    assert request.relationship_world.jealousy_by_npc["Alex"].active is True
    assert request.relationship_world.open_loops[0].loop_id == "Alex:trust:Spring-14"


def test_relationship_world_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValidationError):
        DialogueTestRequest.model_validate(
            {
                "npcId": "Alex",
                "message": "你好",
                "relationshipWorld": {"notAField": True},
            }
        )


def test_relationship_view_rejects_unknown_visibility() -> None:
    with pytest.raises(ValidationError):
        DialogueTestRequest.model_validate(
            {
                "npcId": "Alex",
                "message": "你好",
                "relationshipWorld": {
                    "views": [
                        {
                            "ownerNpcId": "Alex",
                            "subjectNpcId": "Sophia",
                            "relationType": "dating",
                            "visibility": "certain_but_private",
                            "source": "rumor",
                        },
                    ],
                },
            }
        )


def test_relationship_fact_rejects_empty_npc_id() -> None:
    with pytest.raises(ValidationError):
        DialogueTestRequest.model_validate(
            {
                "npcId": "Alex",
                "message": "你好",
                "relationshipWorld": {
                    "objectiveRelationships": [
                        {"npcId": "", "relationType": "dating"},
                    ],
                },
            }
        )


def test_relationship_world_accepts_active_open_loop_for_prompt_context() -> None:
    request = DialogueTestRequest.model_validate(
        {
            "npcId": "Wizard",
            "message": "我们继续聊符文。",
            "channel": "face_to_face",
            "relationshipWorld": {
                "openLoops": [
                    {
                        "loopId": "wizard:rune:Spring-14",
                        "npcId": "Wizard",
                        "topic": "rune_review",
                        "originChannel": "remote",
                        "nextChannel": "face_to_face",
                        "status": "open",
                        "shortSummary": "线上留下了核对符文数据的话题",
                        "createdOn": "Spring 14",
                    },
                ],
            },
        }
    )

    assert request.relationship_world is not None
    assert request.relationship_world.open_loops[0].loop_id == "wizard:rune:Spring-14"


def test_open_loop_signal_requires_safe_action_and_open_fields() -> None:
    signal = OpenLoopSignal.model_validate(
        {
            "action": "open",
            "loopId": "wizard:rune:Spring-14",
            "topic": "rune_review",
            "shortSummary": "线上留下了核对符文数据的话题",
        }
    )

    assert signal.action == "open"

    with pytest.raises(ValidationError):
        OpenLoopSignal.model_validate(
            {
                "action": "open",
                "loopId": "wizard:rune:Spring-14",
                "topic": "rune_review",
                "shortSummary": "核对符文",
                "scheduledAt": "Spring 15",
            }
        )
