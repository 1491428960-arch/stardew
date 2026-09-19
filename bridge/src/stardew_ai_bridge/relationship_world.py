"""纯函数关系领域层。

这里保存“客观关系事实”和“某个 NPC 看到的关系信息”的边界。
它不访问 Provider、游戏进程、存档或配置文件，也不负责生成对白。
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pydantic import BaseModel


_ACCEPTANCE_STATES = {"accepted", "conditional", "not_ready"}
_JEALOUSY_TRIGGERS = {
    "time",
    "companionship",
    "broken_promise",
    "comparison",
    "affection_imbalance",
}
_JEALOUSY_INTENSITIES = {"light", "moderate", "high"}
_RECOVERY_ACTIONS = {
    "acknowledge_and_explain",
    "keep_promise",
    "offer_time",
    "give_space",
}
_VISIBILITY_PRIORITY = {"unknown": 0, "suspected": 1, "known": 2}


def _copy_world(world: Mapping[str, Any] | BaseModel) -> dict[str, Any]:
    if isinstance(world, BaseModel):
        raw = world.model_dump(by_alias=True, exclude_none=True)
    elif isinstance(world, Mapping):
        raw = dict(world)
    else:
        raise TypeError("关系世界状态必须是 Mapping 或 Pydantic 模型")

    copied = deepcopy(raw)
    if not isinstance(copied.get("objectiveRelationships"), list):
        copied["objectiveRelationships"] = []
    if not isinstance(copied.get("views"), list):
        copied["views"] = []
    if not isinstance(copied.get("acceptanceByNpc"), dict):
        copied["acceptanceByNpc"] = {}
    if not isinstance(copied.get("mediationByNpc"), dict):
        copied["mediationByNpc"] = {}
    if not isinstance(copied.get("jealousyByNpc"), dict):
        copied["jealousyByNpc"] = {}
    if not isinstance(copied.get("openLoops"), list):
        copied["openLoops"] = []
    return copied


def _copy_state(state: Mapping[str, Any] | BaseModel) -> dict[str, Any]:
    if isinstance(state, BaseModel):
        raw = state.model_dump(by_alias=True, exclude_none=True)
    elif isinstance(state, Mapping):
        raw = dict(state)
    else:
        raise TypeError("关系状态必须是 Mapping 或 Pydantic 模型")
    return deepcopy(raw)


def _facts(world: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        item
        for item in world.get("objectiveRelationships", [])
        if isinstance(item, Mapping)
    ]


def _views(world: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in world.get("views", [])
        if isinstance(item, dict)
    ]


def _open_loops(world: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        item
        for item in world.get("openLoops", [])
        if isinstance(item, Mapping)
    ]


def _fact_for_subject(
    world: Mapping[str, Any],
    subject_npc_id: str,
) -> Mapping[str, Any] | None:
    return next(
        (
            fact
            for fact in _facts(world)
            if fact.get("npcId") == subject_npc_id
        ),
        None,
    )


def apply_public_relationship_event(
    world: Mapping[str, Any] | BaseModel,
    public_event_id: str,
) -> dict[str, Any]:
    """把登记过的婚礼公开为社区事实，不公开普通恋爱。"""

    updated = _copy_world(world)
    if not isinstance(public_event_id, str) or not public_event_id.strip():
        return updated

    public_facts = [
        fact
        for fact in _facts(updated)
        if fact.get("relationType") == "married"
        and fact.get("npcId")
        and fact.get("publicEventId") == public_event_id
    ]
    for fact in public_facts:
        subject_npc_id = fact["npcId"]
        for view in _views(updated):
            if view.get("subjectNpcId") != subject_npc_id:
                continue
            view.update(
                {
                    "relationType": "married",
                    "visibility": "known",
                    "source": "wedding",
                }
            )
            if fact.get("publicOn") is not None:
                view["observedOn"] = fact["publicOn"]
            view["evidence"] = public_event_id
    return updated


def disclose_relationship(
    world: Mapping[str, Any] | BaseModel,
    *,
    viewer_npc_id: str,
    subject_npc_id: str,
) -> dict[str, Any]:
    """记录主角向一个 NPC 直接说明关系，只更新该 NPC 的视角。"""

    updated = _copy_world(world)
    fact = _fact_for_subject(updated, subject_npc_id)
    if fact is None:
        return updated

    matching = [
        view
        for view in _views(updated)
        if view.get("ownerNpcId") == viewer_npc_id
        and view.get("subjectNpcId") == subject_npc_id
    ]
    if not matching:
        updated["views"].append(
            {
                "ownerNpcId": viewer_npc_id,
                "subjectNpcId": subject_npc_id,
                "relationType": fact.get("relationType"),
                "visibility": "known",
                "source": "player_statement",
            }
        )
        return updated

    for view in matching:
        view.update(
            {
                "relationType": fact.get("relationType"),
                "visibility": "known",
                "source": "player_statement",
            }
        )
    return updated


def _public_marriage_views(
    world: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        str(fact["npcId"]): {
            "subjectNpcId": fact["npcId"],
            "relationType": "married",
            "visibility": "known",
            "source": "wedding",
            **(
                {"observedOn": fact["publicOn"]}
                if fact.get("publicOn") is not None
                else {}
            ),
            **(
                {"evidence": fact["publicEventId"]}
                if fact.get("publicEventId") is not None
                else {}
            ),
        }
        for fact in _facts(world)
        if fact.get("relationType") == "married"
        and fact.get("npcId")
        and fact.get("publicEventId")
    }


def _project_mediation_state(value: object) -> dict[str, Any]:
    """只向 NPC 视角投影当前调解状态，不暴露内部后续步骤。"""

    if not isinstance(value, Mapping):
        return {"status": "none"}
    projected = {
        key: deepcopy(value[key])
        for key in ("status", "outcome")
        if key in value and value[key] is not None
    }
    return projected or {"status": "none"}


def project_relationship_context(
    viewer_npc_id: str,
    world: Mapping[str, Any] | BaseModel,
) -> dict[str, Any]:
    """投影一个 NPC 能使用的最小关系上下文。

    客观关系表永远不会从该函数返回；只有该 NPC 自己的视角和公开婚姻
    事实进入 knowledge。其它 NPC 的接受度、调解和嫉妒也不会泄漏。
    """

    copied = _copy_world(world)
    knowledge_by_subject: dict[str, dict[str, Any]] = {}
    for view in _views(copied):
        if view.get("ownerNpcId") != viewer_npc_id:
            continue
        subject_npc_id = view.get("subjectNpcId")
        if not subject_npc_id:
            continue
        projected = {
            key: view[key]
            for key in (
                "subjectNpcId",
                "relationType",
                "visibility",
                "source",
                "observedOn",
                "evidence",
            )
            if key in view and view[key] is not None
        }
        current = knowledge_by_subject.get(str(subject_npc_id))
        if current is None or _VISIBILITY_PRIORITY.get(
            str(projected.get("visibility")), 0
        ) >= _VISIBILITY_PRIORITY.get(str(current.get("visibility")), 0):
            knowledge_by_subject[str(subject_npc_id)] = projected

    for subject_npc_id, public_view in _public_marriage_views(copied).items():
        knowledge_by_subject[subject_npc_id] = public_view

    mediation = copied["mediationByNpc"].get(viewer_npc_id)
    jealousy = copied["jealousyByNpc"].get(viewer_npc_id)
    open_loops = [
        deepcopy(loop)
        for loop in _open_loops(copied)
        if loop.get("npcId") == viewer_npc_id
        and loop.get("status") in {"open", "in_progress"}
    ]
    return {
        "policy": {
            "pluralRelationshipsLegal": True,
            "localMonogamyDefault": True,
            "truthfulDisclosureRequired": True,
        },
        "knowledge": list(knowledge_by_subject.values()),
        "acceptance": copied["acceptanceByNpc"].get(viewer_npc_id),
        "mediation": _project_mediation_state(mediation),
        "jealousy": deepcopy(jealousy) if isinstance(jealousy, Mapping) else {"active": False},
        "openLoops": open_loops,
    }


def project_relationship_request(
    viewer_npc_id: str,
    world: Mapping[str, Any] | BaseModel,
) -> dict[str, Any]:
    """生成可放入 DialogueTestRequest 的视角隔离形状。

    与 ``project_relationship_context`` 的 Prompt 语义投影不同，这里保留
    RelationshipWorldContext 的字段名，清空 objectiveRelationships，并把
    当前 NPC 可见的 knowledge 转回带 ownerNpcId 的 views。这样 Provider
    即使检查 request，也不会拿到完整关系图。
    """

    projected = project_relationship_context(viewer_npc_id, world)
    views: list[dict[str, Any]] = []
    for item in projected.get("knowledge", []):
        if not isinstance(item, Mapping):
            continue
        subject_npc_id = item.get("subjectNpcId")
        relation_type = item.get("relationType")
        visibility = item.get("visibility")
        source = item.get("source")
        if not all(
            isinstance(value, str)
            for value in (
                subject_npc_id,
                relation_type,
                visibility,
                source,
            )
        ):
            continue
        view: dict[str, Any] = {
            "ownerNpcId": viewer_npc_id,
            "subjectNpcId": subject_npc_id,
            "relationType": relation_type,
            "visibility": visibility,
            "source": source,
        }
        for key in ("observedOn", "evidence"):
            if item.get(key) is not None:
                view[key] = item[key]
        views.append(view)

    acceptance = projected.get("acceptance")
    mediation = projected.get("mediation", {"status": "none"})
    jealousy = projected.get("jealousy", {"active": False})
    return {
        "objectiveRelationships": [],
        "views": views,
        "acceptanceByNpc": (
            {viewer_npc_id: acceptance} if isinstance(acceptance, str) else {}
        ),
        "mediationByNpc": (
            {viewer_npc_id: dict(mediation)}
            if isinstance(mediation, Mapping)
            else {}
        ),
        "jealousyByNpc": (
            {viewer_npc_id: dict(jealousy)}
            if isinstance(jealousy, Mapping)
            else {}
        ),
        "openLoops": [
            deepcopy(item)
            for item in projected.get("openLoops", [])
            if isinstance(item, Mapping)
        ],
    }


def resolve_mediation(
    world: Mapping[str, Any] | BaseModel,
    npc_id: str,
    outcome: str,
    *,
    next_step: str | None = None,
) -> dict[str, Any]:
    """完成一个 NPC 的一对一调解，不覆盖其它 NPC 的状态。"""

    if outcome not in _ACCEPTANCE_STATES:
        raise ValueError(f"非法调解结果: {outcome}")
    updated = _copy_world(world)
    updated["acceptanceByNpc"][npc_id] = outcome
    updated["mediationByNpc"][npc_id] = {
        "status": "resolved",
        "outcome": outcome,
        **({"nextStep": next_step} if next_step is not None else {}),
    }
    return updated


def record_jealousy(
    world: Mapping[str, Any] | BaseModel,
    npc_id: str,
    trigger: str,
    intensity: str,
    need: str,
) -> dict[str, Any]:
    """记录一个可复发的、针对具体关系体验的嫉妒状态。"""

    if trigger not in _JEALOUSY_TRIGGERS:
        raise ValueError(f"非法嫉妒触发器: {trigger}")
    if intensity not in _JEALOUSY_INTENSITIES:
        raise ValueError(f"非法嫉妒强度: {intensity}")
    updated = _copy_world(world)
    previous = updated["jealousyByNpc"].get(npc_id)
    state = {
        "active": True,
        "trigger": trigger,
        "intensity": intensity,
        "need": need,
    }
    if isinstance(previous, Mapping) and previous.get("lastResolvedTrigger"):
        state["lastResolvedTrigger"] = previous["lastResolvedTrigger"]
    updated["jealousyByNpc"][npc_id] = state
    return updated


def recover_jealousy(
    jealousy: Mapping[str, Any] | BaseModel,
    response_action: str,
) -> dict[str, Any]:
    """只有承认、解释、兑现当前承诺、即时陪伴或给空间才会恢复嫉妒。"""

    state = _copy_state(jealousy)
    if response_action not in _RECOVERY_ACTIONS or not state.get("active"):
        return state

    trigger = state.get("trigger")
    state.update(
        {
            "active": False,
            "trigger": None,
            "intensity": None,
            "need": None,
        }
    )
    if trigger is not None:
        state["lastResolvedTrigger"] = trigger
    return state
