"""`completedEventIds` 上限 512，以及「只作门控输入、不进 prompt」这条契约。

背景（2026-09-21）：用户存档的 `eventsSeen` 有 **391 条**，但发往 Bridge 时被四处
128 上限截断到 128 条，事件门控于是把已完成的事件链判成没走完，把 14 心已婚的
亲密权限压回 `acquaintance`——prompt 里随之出现「不得使用爱称、主动暧昧、
固定爱称或事件后专属熟稔」，模型老实照做。7 个配了事件门的角色里 6 个被压级
（Harvey / Elliott / Shane / Sophia → acquaintance，Sebastian → friend）。

四处上限必须一起改，只改一处会被下一处截断：

| 位置 | 原值 |
|---|---|
| `smapi/GameStateCollector.cs` `ReadEnumerableStrings(eventsSeen, ...)` | 128 |
| `smapi/GameStateCollector.cs` `NormalizeEventIds(...).Take(...)` | 128 |
| `bridge/src/stardew_ai_bridge/models.py` `NpcGameState.completed_event_ids` | 128 |
| `bridge/src/stardew_ai_bridge/prompts.py` `[:128]` | 128 |

本文件守住三件事：

1. **391 条不再被截断**（model 边界 → `ContextBuilder` 全程）；
2. **门控真的看见了完整事件链**（`eventUnlockedStage` 回到 `close`、`missingEventIds`
   清空，心级角色的阶段不再被误压）；
3. **`completedEventIds` 不进 prompt 卡片**，但门控 / 语料检索 / `context` 仍拿得到。

第 1、2 条用一份「与存档同形」的合成事件表：前 128 条全是无关填充，所有事件门
需要的 ID 都排在 129 条之后。这样「旧的 `[:128]` 必然丢掉门控事件」是与枚举顺序
无关的硬结论，复现的是截断机制本身，而不是 `HashSet` 的某一次遍历顺序。

> 断言口径说明：这里刻意只断言**事件链本身的判定**（`eventUnlockedStage` /
> `missingEventIds` / 心级阶段的收窄），不断言「已婚被压到哪一档」——后者是
> `relationship_gating` 里另一条并行改动（既成关系阶段下限）决定的，与本文件
> 要守的「事件上限」是两件事，不该被绑在一起。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from stardew_ai_bridge.models import MAX_COMPLETED_EVENT_IDS, DialogueTestRequest
from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder
from stardew_ai_bridge.relationship_gating import (
    relationship_event_gates,
    resolve_relationship_gate,
)

# 用户存档里被压级的 6 个角色中，除 Alex 以外的 5 个。
# Alex 不在内：他 close 级要求的 `288847` 在存档里根本不存在，
# 与截断无关，属于另一件事（见诊断报告 §3.3 / 方案 C）。
_GATE_ROLES = ("Harvey", "Elliott", "Shane", "Sophia", "Sebastian")

# 用户存档 `test2_412086775` 的 `eventsSeen` 实际条数。
_SAVE_EVENT_COUNT = 391

# 配偶的标准好感上限；`_heart_stage` 因此落在 close。
_SPOUSE_HEARTS = 14

# 心级（非既成亲密关系）角色的对照：8 心 → heart_stage=close、raw_stage=friend。
_HEART_STAGE_HEARTS = 8


def _gate_event_ids() -> list[str]:
    """这些角色各自 close 级事件门需要的全部事件 ID（去重保序）。"""

    collected: list[str] = []
    for role in _GATE_ROLES:
        for event_id in relationship_event_gates(role)[-1].required_event_ids:
            if event_id not in collected:
                collected.append(event_id)
    return collected


def _save_like_events() -> list[str]:
    """构造与存档同形的 391 条事件：门控事件一律排在 128 条之后。"""

    gate_ids = _gate_event_ids()
    filler = [
        f"filler-{index}" for index in range(_SAVE_EVENT_COUNT - len(gate_ids))
    ]
    return filler + gate_ids


def _payload(
    npc_id: str,
    event_ids: list[str] | None,
    *,
    hearts: int = _SPOUSE_HEARTS,
    married: bool = True,
) -> dict[str, object]:
    state: dict[str, object] = {
        "season": "spring",
        "date": "25",
        "weather": "clear",
        "time": 1830,
        "location": "FarmHouse",
        "friendship": hearts * 250,
        "friendshipHearts": hearts,
        "relationship": "Married" if married else "Friendly",
        "childrenCount": 0,
        "completedEventIds": event_ids,
    }
    if married:
        state["marriageStatus"] = "Married"
    return {"npcId": npc_id, "message": "今天过得怎么样？", "gameState": state}


def test_save_like_event_table_actually_reproduces_the_truncation() -> None:
    """自检：合成表确实是 391 条，且 128 条截断必然丢掉门控事件。"""

    events = _save_like_events()

    assert len(events) == _SAVE_EVENT_COUNT
    assert _gate_event_ids(), "至少要有一个事件门才有复现意义"
    assert all(
        event_id not in events[:128] for event_id in _gate_event_ids()
    ), "门控事件必须全部落在第 129 条之后，否则复现不了截断"


@pytest.mark.parametrize("npc_id", _GATE_ROLES)
def test_truncated_event_list_cannot_see_the_finished_chain(npc_id: str) -> None:
    """改前行为：只发前 128 条时，事件链被判成只走到 acquaintance。"""

    result = resolve_relationship_gate(
        npc_id,
        relationship_stage="married",
        friendship_hearts=_SPOUSE_HEARTS,
        completed_event_ids=_save_like_events()[:128],
    )

    assert result.event_unlocked_stage == "acquaintance"
    assert result.missing_event_ids == relationship_event_gates(npc_id)[
        0
    ].required_event_ids


@pytest.mark.parametrize("npc_id", _GATE_ROLES)
def test_full_event_list_completes_the_chain(npc_id: str) -> None:
    """改后行为：391 条全量发过去，事件链被判成已走完（这就是上限修复的效果）。"""

    result = resolve_relationship_gate(
        npc_id,
        relationship_stage="married",
        friendship_hearts=_SPOUSE_HEARTS,
        completed_event_ids=_save_like_events(),
    )

    assert result.event_unlocked_stage == "close"
    assert result.missing_event_ids == ()


@pytest.mark.parametrize("npc_id", _GATE_ROLES)
def test_heart_stage_role_is_no_longer_capped_by_event_truncation(
    npc_id: str,
) -> None:
    """心级角色的阶段收窄同样由上限决定：截断压到 acquaintance，全量回到 friend。

    这一条与既成关系（dating/married）无关，是事件上限本身的效果。
    """

    events = _save_like_events()

    truncated = resolve_relationship_gate(
        npc_id,
        relationship_stage="friend",
        friendship_hearts=_HEART_STAGE_HEARTS,
        completed_event_ids=events[:128],
    )
    assert truncated.event_gate_applied is True
    assert truncated.effective_stage == "acquaintance"

    complete = resolve_relationship_gate(
        npc_id,
        relationship_stage="friend",
        friendship_hearts=_HEART_STAGE_HEARTS,
        completed_event_ids=events,
    )
    assert complete.event_gate_applied is False
    assert complete.effective_stage == "friend"


def test_model_accepts_a_full_save_event_list() -> None:
    """Bridge 的 `max_length` 必须容得下 SMAPI 现在会发的条数。"""

    assert MAX_COMPLETED_EVENT_IDS == 512, (
        "上限与 SMAPI 的 GameStateCollector.MaxCompletedEventIds 必须一致；"
        "改这里就要同步改 smapi/GameStateCollector.cs"
    )

    events = [f"evt-{index}" for index in range(_SAVE_EVENT_COUNT)]
    request = DialogueTestRequest.model_validate(_payload("Harvey", events))

    assert request.game_state is not None
    assert request.game_state.completed_event_ids == events


def test_model_accepts_exactly_the_cap_and_rejects_one_more() -> None:
    """超限会 422 并退化成兜底回复，所以边界必须钉死。"""

    at_cap = [f"evt-{index}" for index in range(MAX_COMPLETED_EVENT_IDS)]
    request = DialogueTestRequest.model_validate(_payload("Harvey", at_cap))
    assert request.game_state is not None
    assert len(request.game_state.completed_event_ids) == MAX_COMPLETED_EVENT_IDS

    over_cap = [f"evt-{index}" for index in range(MAX_COMPLETED_EVENT_IDS + 1)]
    with pytest.raises(ValidationError):
        DialogueTestRequest.model_validate(_payload("Harvey", over_cap))


def test_context_keeps_every_completed_event_id() -> None:
    """`prompts.py` 的 `[:128]` 去掉后，context 里应当是完整的 391 条。"""

    events = _save_like_events()
    context = ContextBuilder().build(_payload("Harvey", events))

    assert context["gameState"]["completedEventIds"] == events


@pytest.mark.parametrize("npc_id", _GATE_ROLES)
def test_production_context_path_sees_the_complete_chain(npc_id: str) -> None:
    """生产路径（`ContextBuilder`）的证据：门控拿到的就是完整事件链。"""

    events = _save_like_events()

    truncated_gate = ContextBuilder().build(
        _payload(npc_id, events[:128])
    )["npcIdentity"]["relationshipGate"]
    assert truncated_gate["eventUnlockedStage"] == "acquaintance"
    assert truncated_gate["missingEventIds"] == list(
        relationship_event_gates(npc_id)[0].required_event_ids
    )

    complete_gate = ContextBuilder().build(_payload(npc_id, events))["npcIdentity"][
        "relationshipGate"
    ]
    assert complete_gate["eventUnlockedStage"] == "close"
    assert complete_gate["missingEventIds"] == []


def test_production_context_path_narrows_a_heart_stage_role_only_when_truncated() -> None:
    """心级角色的可见差异：截断时出现 eventGate 卡，全量时不再出现。"""

    events = _save_like_events()

    narrow_context = ContextBuilder().build(
        _payload("Harvey", events[:128], hearts=_HEART_STAGE_HEARTS, married=False)
    )
    narrowed = narrow_context["npcIdentity"]["stagePolicy"]
    assert narrowed["eventGate"]["effectiveIntimacyStage"] == "acquaintance"
    assert "爱称" in narrowed["eventGate"]["instruction"]

    full_context = ContextBuilder().build(
        _payload("Harvey", events, hearts=_HEART_STAGE_HEARTS, married=False)
    )
    assert "eventGate" not in full_context["npcIdentity"]["stagePolicy"]


@pytest.mark.parametrize("npc_id", _GATE_ROLES)
def test_prompt_never_renders_the_completed_event_id_list(npc_id: str) -> None:
    """`completedEventIds` 只作门控输入：390+ 条事件 ID 不得进 prompt。"""

    events = _save_like_events()
    context = ContextBuilder().build(_payload(npc_id, events))
    messages = PromptBuilder().build(context, "今天过得怎么样？")

    game_state_cards = [
        message for message in messages if message.get("name") == "game_state"
    ]
    assert game_state_cards, "game_state 卡必须仍然存在（只摘掉门控专用字段）"

    rendered = "\n".join(card["content"] for card in game_state_cards)
    assert "completedEventIds" not in rendered
    for event_id in events:
        assert event_id not in rendered

    # 同一张卡里的其他运行时字段不受影响。
    assert "friendshipHearts" in rendered
    assert "marriageStatus" in rendered


def test_prompt_still_renders_game_state_card_when_only_gate_field_present() -> None:
    """`game_state` 卡不会因为摘掉唯一字段而消失。"""

    context = ContextBuilder().build(_payload("Harvey", _save_like_events()))
    # 人为构造「只有门控字段」的极端上下文。
    context["gameState"] = {"completedEventIds": ["20"]}
    messages = PromptBuilder().build(context, "今天过得怎么样？")

    assert any(message.get("name") == "game_state" for message in messages)
