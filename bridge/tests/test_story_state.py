from __future__ import annotations

from stardew_ai_bridge.story_state import build_story_state


def test_shane_close_stage_is_trusted_not_stranger_cold() -> None:
    state = build_story_state("Shane", "close", [])

    assert state["trustState"] == "established"
    assert "初识" not in state["behaviorInstruction"]


def test_completed_story_event_enables_shane_recovery_disclosure() -> None:
    state = build_story_state(
        "Shane",
        "close",
        ["vanilla:shane-heart-6"],
    )

    assert "recovery" in state["completedStoryStates"]
    assert "current_struggle" in state["allowedDisclosure"]


def test_temporary_bad_mood_does_not_erase_established_trust() -> None:
    state = build_story_state(
        "Shane",
        "married",
        ["vanilla:shane-heart-6"],
        current_mood="low",
    )

    assert state["trustState"] == "established"
    assert state["temporaryBoundary"] == "可以简短拒绝或结束，但不得退回初识式冷淡。"


def test_unfinished_story_event_does_not_grant_story_disclosure() -> None:
    state = build_story_state("Shane", "close", [])

    assert state["completedStoryStates"] == []
    assert "current_struggle" not in state["allowedDisclosure"]


def test_story_event_metadata_can_define_a_character_specific_state() -> None:
    state = build_story_state(
        "Sophia",
        "dating",
        ["sve:sophia-heart-8"],
        story_events=[
            {
                "eventId": "sve:sophia-heart-8",
                "storyStateId": "shared_creative_memory",
                "allowedDisclosure": ["new_painting"],
                "initiativeBias": "gentle_invitation",
            }
        ],
    )

    assert state["completedStoryStates"] == ["shared_creative_memory"]
    assert "new_painting" in state["allowedDisclosure"]
    assert state["initiativeBias"] == "gentle_invitation"
