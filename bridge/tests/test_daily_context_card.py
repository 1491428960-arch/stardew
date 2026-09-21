"""L2a 同住标记 + L2b 今日安排：`daily_context` 卡的渲染、门控与语义边界。

**这一层要解决的问题**：`GameStateCollector` 早就把 `Game1.player.spouse` 读出来了
（`ReadRuntimeStoryState`），却只拿它决定要不要数孩子——「是不是配偶/室友」这个
布尔算出来直接丢掉；同时模型完全不知道 NPC 今天大致怎么过。

**用户已批准代价**：给「今天的大致安排」会剧透 NPC 接下来在哪。因此卡里只给
时段粒度、不给钟点，并用 instruction 钉死「这是计划快照，不是实时位置」。

**两个语义边界**（都在 instruction 里）：
① 同住 = **住处**，不是行踪——配偶 NPC 白天照样出门；
② 今日安排 = **快照**——会因天气/节日/事件变，且与 `NPC.Schedule` 的实时性有偏差。
"""

from __future__ import annotations

import json
from typing import Any

from stardew_ai_bridge.app import _build_context
from stardew_ai_bridge.models import NpcGameState
from stardew_ai_bridge.prompts import PromptBuilder
from stardew_ai_bridge.today_schedule import build_daily_context_card


SOPHIA = "Sophia"
SCHEDULE = [
    {"time": 900, "location": "葡萄园"},
    {"time": 1300, "location": "酒窖"},
    {"time": 2100, "location": "家"},
]


def _payload(
    *,
    extra_state: dict[str, object] | None = None,
    compact: bool = True,
    intent: str = "chat",
    quality_context: dict[str, object] | None = None,
) -> dict[str, object]:
    state: dict[str, object] = {
        "npcId": SOPHIA,
        "displayName": SOPHIA,
        "season": "spring",
        "date": "25",
        "weather": "clear",
        "location": "Forest",
        "time": 900,
        "friendship": 1500,
        "friendshipHearts": 6,
        "relationship": "married",
        "marriageStatus": "married",
    }
    if extra_state:
        state.update(extra_state)
    body: dict[str, object] = {
        "npcId": SOPHIA,
        "message": "今天过得怎么样？",
        "intent": intent,
        "provider": "fake",
        "compactPrompt": compact,
        "sourceMods": ["SVE"],
        "recentFacts": [],
        "history": [],
        "gameState": state,
    }
    if quality_context is not None:
        body["qualityContext"] = quality_context
    return body


def _messages(**kwargs: Any) -> list[dict[str, str]]:
    _, prompt = _build_context(_payload(**kwargs))
    return prompt


def _card(messages: list[dict[str, str]], name: str) -> dict[str, Any] | None:
    entry = next((item for item in messages if item.get("name") == name), None)
    return json.loads(entry["content"]) if entry else None


# --- 卡片内容 ---------------------------------------------------------------


def test_schedule_only_card_carries_the_projected_plan() -> None:
    card = _card(_messages(extra_state={"todaySchedule": SCHEDULE}), "daily_context")

    assert card is not None
    assert card["今日安排"] == ["上午在葡萄园", "下午在酒窖", "晚上在家"]
    assert "同住" not in card


def test_lives_with_player_true_renders_the_home_flag() -> None:
    card = _card(_messages(extra_state={"livesWithPlayer": True}), "daily_context")

    assert card is not None
    assert card["同住"] is True
    assert "今日安排" not in card


def test_lives_with_player_false_or_null_never_renders_the_flag() -> None:
    """`False` 与 `None` 都不写进卡里。

    `False` = 玩家有配偶/室友但不是这个 NPC；`None` = 读不到。后者不是 `False`，
    但两者对当前 NPC 的对白都没有增量——写出来只会被读成「关系疏远」。
    """

    for value in (False, None):
        card = _card(
            _messages(
                extra_state={
                    "livesWithPlayer": value,
                    "todaySchedule": SCHEDULE,
                }
            ),
            "daily_context",
        )

        assert card is not None, value
        assert "同住" not in card, value
        assert card["今日安排"] == ["上午在葡萄园", "下午在酒窖", "晚上在家"]


def test_both_signals_share_one_card_with_precedence_note() -> None:
    card = _card(
        _messages(
            extra_state={"livesWithPlayer": True, "todaySchedule": SCHEDULE}
        ),
        "daily_context",
    )

    assert card is not None
    assert card["同住"] is True
    assert card["今日安排"] == ["上午在葡萄园", "下午在酒窖", "晚上在家"]
    assert "以今日安排为准" in card["instruction"]


def test_home_instruction_pins_the_semantics_boundary() -> None:
    """L2a 的语义边界：**住处不等于行踪**。这条 instruction 是唯一的护栏，钉死它。"""

    card = _card(_messages(extra_state={"livesWithPlayer": True}), "daily_context")

    assert card is not None
    instruction = card["instruction"]
    assert "不代表对方此刻在家" in instruction
    assert "白天照样按自己的日程外出" in instruction


def test_schedule_instruction_pins_the_snapshot_semantics() -> None:
    """L2b 的语义边界：**快照、时段粒度、不给钟点**。"""

    card = _card(_messages(extra_state={"todaySchedule": SCHEDULE}), "daily_context")

    assert card is not None
    instruction = card["instruction"]
    assert "计划快照" in instruction
    assert "不是此时此刻的位置" in instruction
    assert "不要补出具体钟点" in instruction
    assert "以场景卡为准" in instruction


# --- 降级路径 ---------------------------------------------------------------


def test_no_card_when_there_is_nothing_to_say() -> None:
    messages = _messages()

    assert "daily_context" not in [item.get("name") for item in messages]


def test_no_card_for_a_broken_schedule() -> None:
    for broken in ("900 葡萄园", [{"time": None}], [{"location": "酒窖"}], []):
        messages = _messages(extra_state={"todaySchedule": broken})

        assert "daily_context" not in [
            item.get("name") for item in messages
        ], broken


def test_card_builder_returns_empty_for_useless_input() -> None:
    assert build_daily_context_card() == {}
    assert build_daily_context_card(lives_with_player=False) == {}
    assert build_daily_context_card(lives_with_player=None, today_schedule=[]) == {}


def test_card_keeps_working_when_only_one_signal_survives() -> None:
    """日程坏掉但同住成立 → 卡还在，只是少了「今日安排」。

    降级粒度是**字段**而不是整张卡：一处数据坏掉不该把另一处的信息也带走。
    """

    card = build_daily_context_card(
        lives_with_player=True,
        today_schedule=[{"time": 760, "location": "葡萄园"}],
    )

    assert card["同住"] is True
    assert "今日安排" not in card


# --- 路径与门控 -------------------------------------------------------------


def test_card_appears_on_both_prompt_paths() -> None:
    """线上游戏端走 compact，评测走完整路径；两边都要有。"""

    state = {"livesWithPlayer": True, "todaySchedule": SCHEDULE}

    compact_card = _card(_messages(compact=True, extra_state=state), "daily_context")
    full_card = _card(_messages(compact=False, extra_state=state), "daily_context")

    assert compact_card is not None
    assert compact_card == full_card


def test_raw_schedule_is_hidden_from_the_game_state_card() -> None:
    """原始日程条目**不进** `game_state` 卡：它的渲染由 `daily_context` 独占。

    让模型同时看到压缩结果与带坐标粒度的原始条目，等于把「计划」和「实时位置」
    摆在同一个上下文里——那正是这一层最容易出的错。
    """

    messages = _messages(
        compact=False,
        extra_state={"livesWithPlayer": True, "todaySchedule": SCHEDULE},
    )
    game_state = _card(messages, "game_state")

    assert game_state is not None
    assert "todaySchedule" not in game_state["gameState"]
    assert "livesWithPlayer" not in game_state["gameState"]
    assert _card(messages, "daily_context") is not None


def test_context_layer_still_carries_the_raw_fields() -> None:
    """prompt 里藏起来，但上下文层保留完整字段（预览接口与将来的消费者要用）。"""

    context, _ = _build_context(
        _payload(extra_state={"livesWithPlayer": True, "todaySchedule": SCHEDULE})
    )
    game_state = context["gameState"]

    assert game_state["livesWithPlayer"] is True
    assert game_state["todaySchedule"] == SCHEDULE


def test_natural_topic_skips_the_card_but_keeps_the_routine() -> None:
    """自然找话题路径不发今日安排（防铺场景），但 L3 的作息照发。

    这条门控与 `recent_memory` 一致：运行时实况在那条路径上会诱发
    「今天上午我在葡萄园……」式开场；而作息是角色资料，不是今天的实况。
    """

    messages = _messages(
        intent="topic",
        quality_context={"naturalMode": True},
        extra_state={"livesWithPlayer": True, "todaySchedule": SCHEDULE},
    )
    names = [item.get("name") for item in messages]

    assert "daily_context" not in names
    assert "daily_routine" in names


# --- 传输契约 ---------------------------------------------------------------


def test_model_accepts_the_game_client_field_names() -> None:
    """字段名与 C# 侧 `GameStateCollector` 的 `JsonPropertyName` 必须逐字相同。

    两侧不同步时 `extra="forbid"` 会直接把请求打成 422，整轮对话退化成兜底回复。
    """

    state = NpcGameState.model_validate(
        {
            "npcId": SOPHIA,
            "livesWithPlayer": True,
            "todaySchedule": SCHEDULE,
        }
    )

    assert state.lives_with_player is True
    assert [entry.location for entry in state.today_schedule] == ["葡萄园", "酒窖", "家"]
    dumped = state.model_dump(by_alias=True, exclude_none=True)
    assert dumped["livesWithPlayer"] is True
    assert dumped["todaySchedule"] == SCHEDULE


def test_model_defaults_are_backward_compatible() -> None:
    """旧版游戏端不发这两个字段时不能报错，也不能当成「明确不同住」。"""

    state = NpcGameState.model_validate({"npcId": SOPHIA})

    assert state.lives_with_player is None
    assert state.today_schedule == []


def test_the_same_card_is_reachable_through_the_prompt_builder() -> None:
    """直接经 PromptBuilder 也要能渲染（内部调用路径不经过 ContextBuilder）。"""

    messages = PromptBuilder().build(
        {
            "npcIdentity": {"npcId": SOPHIA},
            "gameState": {
                "livesWithPlayer": True,
                "todaySchedule": SCHEDULE,
            },
            "recentFacts": [],
            "history": [],
            "modSources": ["SVE"],
        },
        "今天过得怎么样？",
        compact=True,
    )
    card = _card(messages, "daily_context")

    assert card is not None
    assert card["同住"] is True
    assert card["今日安排"] == ["上午在葡萄园", "下午在酒窖", "晚上在家"]
