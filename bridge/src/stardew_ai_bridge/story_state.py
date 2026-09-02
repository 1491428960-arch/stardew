from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .personas import canonical_npc_id


_STAGES = {
    "stranger",
    "acquaintance",
    "friend",
    "close",
    "dating",
    "married",
    "parent",
}
_TRUSTED_STAGES = {"close", "dating", "married", "parent"}
_LOW_MOODS = {
    "bad",
    "exhausted",
    "frustrated",
    "low",
    "low_mood",
    "sad",
    "tired",
}
_EVENT_TOKEN_RE = re.compile(r"[^a-z0-9一-鿿]+", re.IGNORECASE)

_ROLE_INITIATIVE_BIASES = {
    "Wizard": "measured_interest",
    "Sophia": "gentle_sharing",
    "Shane": "practical_warmth",
    "Sebastian": "quiet_presence",
    "Alex": "direct_playfulness",
}

# 这些是“事件已经完成”后才允许使用的状态标签，不是事件剧情文本。
# 同一个游戏事件可能从不同采集路径进入，因此保留稳定 ID、尾部 ID 和旧式短 ID。
_BUILT_IN_EVENT_RULES: dict[str, tuple[dict[str, Any], ...]] = {
    "Shane": (
        {
            "stateId": "recovery",
            "eventIds": (
                "vanilla:shane-heart-6",
                "shane-heart-6",
                "Shane6",
            ),
            "allowedDisclosure": ["current_struggle", "specific_help"],
            "initiativeBias": "practical_warmth",
        },
    ),
}


def _normalise_stage(value: object) -> str:
    stage = str(value).strip().casefold()
    return stage if stage in _STAGES else "stranger"


def _event_tokens(value: object) -> set[str]:
    text = str(value).strip().casefold()
    if not text:
        return set()
    candidates = {text}
    if ":" in text:
        candidates.add(text.rsplit(":", 1)[-1])
    tokens: set[str] = set()
    for candidate in candidates:
        tokens.add(candidate)
        tokens.add(_EVENT_TOKEN_RE.sub("", candidate))
    return {token for token in tokens if token}


def _matches_event(candidate: object, completed: set[str]) -> bool:
    candidate_tokens = _event_tokens(candidate)
    return bool(candidate_tokens.intersection(completed))


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, Iterable):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _event_state_ids(event: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("storyStateId", "stateId", "completedStoryState"):
        values.extend(_string_list(event.get(key)))
    values.extend(_string_list(event.get("completedStoryStates")))
    return list(dict.fromkeys(values))


def _event_ids(event: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("eventId", "requiredEventId", "sourceKey"):
        values.extend(_string_list(event.get(key)))
    values.extend(_string_list(event.get("eventIds")))
    return list(dict.fromkeys(values))


def _apply_event_rule(
    state: dict[str, Any],
    event: Mapping[str, Any],
    completed: set[str],
) -> None:
    event_ids = _event_ids(event)
    is_completed = (
        str(event.get("status", "")).strip().casefold() == "completed"
        or any(_matches_event(event_id, completed) for event_id in event_ids)
    )
    if not is_completed:
        return

    for state_id in _event_state_ids(event):
        if state_id not in state["completedStoryStates"]:
            state["completedStoryStates"].append(state_id)

    allowed = _string_list(event.get("allowedDisclosure"))
    for disclosure in allowed:
        if disclosure not in state["allowedDisclosure"]:
            state["allowedDisclosure"].append(disclosure)
    initiative = str(event.get("initiativeBias", "")).strip()
    if initiative:
        state["initiativeBias"] = initiative


def build_story_state(
    npc_id: object,
    relationship_stage: object,
    completed_event_ids: Iterable[object] = (),
    *,
    story_events: Iterable[Mapping[str, Any]] = (),
    current_mood: object = "",
) -> dict[str, Any]:
    """把关系阶段、完成事件和暂时情绪压缩成可审查的运行时状态。"""

    canonical_id = canonical_npc_id(npc_id)
    stage = _normalise_stage(relationship_stage)
    completed = {
        token
        for event_id in completed_event_ids
        for token in _event_tokens(event_id)
    }
    trusted = stage in _TRUSTED_STAGES
    state: dict[str, Any] = {
        "npcId": canonical_id,
        "relationshipStage": stage,
        "trustState": "established" if trusted else "developing" if stage == "friend" else "unestablished",
        "completedStoryStates": [],
        "allowedDisclosure": (
            ["current_feelings", "specific_help"] if trusted else []
        ),
        "initiativeBias": _ROLE_INITIATIVE_BIASES.get(
            canonical_id,
            "measured_interest" if trusted else "reserved_response",
        ),
    }
    if trusted:
        state["behaviorInstruction"] = (
            "信任已经建立；保持角色原本的缺点和说话节奏，"
            "可以主动关心、分享或提出一个具体下一步。"
        )
    elif stage == "friend":
        state["behaviorInstruction"] = (
            "关系正在变得可靠；可以承认小幅脆弱，但仍以具体事实和行动为主。"
        )
    elif stage == "acquaintance":
        state["behaviorInstruction"] = "保持礼貌和分寸，只分享与当前话题相关的近况。"
    else:
        state["behaviorInstruction"] = "关系尚未建立；短答、直接，不主动暴露私人脆弱。"

    for event in _BUILT_IN_EVENT_RULES.get(canonical_id, ()):
        if any(_matches_event(event_id, completed) for event_id in event["eventIds"]):
            _apply_event_rule(state, event, completed)
    for event in story_events:
        if isinstance(event, Mapping):
            _apply_event_rule(state, event, completed)

    mood = str(current_mood).strip().casefold().replace("-", "_")
    if mood in _LOW_MOODS:
        state["temporaryBoundary"] = (
            "可以简短拒绝或结束，但不得退回初识式冷淡。"
        )
        state["behaviorInstruction"] += (
            "当前状态较差时可以减少主动性、明确说需要空间或结束对话，"
            "但这只是暂时边界，不改变已经建立的信任。"
        )
    return state
