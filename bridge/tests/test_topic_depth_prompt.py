"""端到端：话题深度槽位必须真的出现在**游戏那条路**的 prompt 里。

## 这个文件防什么

本项目栽过三次的同一个形状：**产出方改了、消费方没跟上**。

`prompts._compact_stage_policy` 是**白名单重建**（不是"照抄后删几个键"），
凡是没在它里面列出的顶层字段都会**静默消失**。2026-09-21 新增 `topicSlot` 时
就只改了 `build_stage_policy` 那一侧，于是线上（`compactPrompt=True`，
也就是游戏实际走的那条）`ctx.npcIdentity.stagePolicy.topicSlot` 有值、
`stage_execution_card` 里却是 `null` —— **机制"写好了"但一个字节都到不了模型**。

所以这里**不检查中间变量**，只看 `_build_context` 返回的 message 列表：
那是模型真正收到的东西。同理，入口必须是 `app._build_context(compact_prompt=True)`
而不是评测路径（后者会多出 4 张评测专属卡，`naturalMode` 也不是游戏端的形状）。
"""

from __future__ import annotations

import json

from stardew_ai_bridge.app import _build_context

#: 实测里那件被端出来 6 次的事，原文照抄。
_SNOW = (
    "我刚才把毯子往沙发这头又拽了拽，想找个更暖和的角度窝着。"
    "结果一抬头，发现窗外那棵橡树的叶子都快掉光了。……今年第一场雪，我们能一起看吗？"
)


def _payload(
    history: list[dict[str, object]],
    *,
    message: str = "",
    intent: str = "chat",
) -> dict[str, object]:
    """与 `probe_gamereal.py` / `gamereal_probe.py` 一致的游戏端请求体。"""

    return {
        "npcId": "Sophia",
        "displayName": "索菲亚",
        "message": message,
        "intent": intent,
        "channel": "remote",
        "compactPrompt": True,
        "sourceMods": ["FlashShifter.StardewValleyExpandedCP"],
        "recentFacts": [],
        "history": history,
        "gameState": {
            "relationshipStage": "dating",
            "friendshipHearts": 8,
            "sourceMods": ["FlashShifter.StardewValleyExpandedCP"],
        },
    }


def _cards(payload: dict[str, object]) -> dict[str, str]:
    _context, messages = _build_context(payload, compact_prompt=True)
    return {str(item.get("name")): str(item.get("content")) for item in messages}


def _execution_payload(cards: dict[str, str]) -> dict[str, object]:
    """`stage_execution_card` 里的 JSON —— 槽位真正到模型手上要经过这里。"""

    card = cards.get("stage_execution_card")
    assert card, "游戏路径上必须有 stage_execution_card"
    return json.loads(card)


def test_the_execution_card_is_on_the_game_path_at_all() -> None:
    """先钉住前提：这张卡本身出现在游戏路径上。它不出现，下面全是空谈。"""

    cards = _cards(_payload([], message="你好"))

    assert "stage_execution_card" in cards


def test_self_repeat_reaches_the_model_as_its_own_card() -> None:
    """她重复了自己 → 必须有一张**独立的** `topic_depth_card`。

    历史里放三条：毯子与雪、针线盒（无关，隔开）、再重说一遍毯子与雪 ——
    与实测里 6/29 轮的那个形状一致。玩家那句是实义的，所以只会触发
    `selfRepeat`，不会同时触发 `playerContinuation`。

    ⚠ **必须是独立卡**：把它埋在 `stage_execution_card` 那个大 JSON 的某个键里
    时，实测（`prod-topic` 第 28~30 轮）她照旧逐字重复三遍 —— 槽位确实触发了
    （2-gram 覆盖率 1.000），但权重压不过同卡里那些更"具体"的字段。
    探针里改用独立卡做同一个实验时，相邻重复从 6/29 掉到 0/29。
    """

    history = [
        {"role": "assistant", "content": _SNOW},
        {"role": "assistant", "content": "呀——我差点把针线盒打翻了！刚在缝一块新料子。"},
        {"role": "assistant", "content": _SNOW},
    ]

    cards = _cards(_payload(history, message="嗯，你说得真好"))

    raw = cards.get("topic_depth_card")
    assert raw, (
        "没有独立的 topic_depth_card —— 槽位要么没触发，要么又被并进"
        "stage_execution_card 里了（那条路上实测会被无视）"
    )
    slot = json.loads(raw)
    assert slot["depthTrigger"] == "selfRepeat"
    assert "别再原样说一遍" in slot["instruction"]


def test_the_depth_slot_is_not_also_left_in_the_execution_card() -> None:
    """独立卡发了，大 JSON 里就不能再留一份 —— 同一段连发两次白占预算。"""

    history = [
        {"role": "assistant", "content": _SNOW},
        {"role": "assistant", "content": _SNOW},
    ]

    cards = _cards(_payload(history, message="嗯，你说得真好"))

    assert "topic_depth_card" in cards
    assert "topicDepthSlot" not in _execution_payload(cards)


def test_response_shape_stops_asking_for_something_new_on_the_topic_path() -> None:
    """**第六处同型矛盾**：topic 路径的 `responseShape` 原本要求
    「说清手上正在做或刚发生的一件具体小事」= 端出一件**新的**，
    与深度槽位的「别再原样说一遍」直接打架，两层并排时模型取更松的那层。
    """

    history = [
        {"role": "assistant", "content": _SNOW},
        {"role": "assistant", "content": _SNOW},
    ]

    cards = _cards(_payload(history, message="", intent="topic"))
    execution = _execution_payload(cards)

    assert "topic_depth_card" in cards
    shape = str(execution.get("responseShape") or "")
    assert "接着说刚才那件" in shape
    assert "一件具体小事" not in shape


def test_response_shape_is_untouched_when_the_slot_did_not_fire() -> None:
    """没触发时不许动 `responseShape` —— 那是「找话题」路径的正常要求。"""

    cards = _cards(_payload([], message="", intent="topic"))
    execution = _execution_payload(cards)

    assert "topic_depth_card" not in cards
    assert "一件具体小事" in str(execution.get("responseShape") or "")


def test_player_continuation_reaches_the_model() -> None:
    history = [
        {"role": "assistant", "content": "我刚把厨房那锅甜茶倒出来，还在冒着热气。"},
    ]

    cards = _cards(_payload(history, message="然后呢"))
    slot = json.loads(cards["topic_depth_card"])

    assert slot["depthTrigger"] == "playerContinuation"
    assert "只谈一件事" in slot["instruction"]


def test_a_quiet_turn_produces_no_depth_card() -> None:
    """多数轮次不该有这张卡 —— 它必须是例外而非常态。"""

    history = [
        {"role": "assistant", "content": "我刚把厨房那锅甜茶倒出来，还在冒着热气。"},
    ]

    cards = _cards(_payload(history, message="斯嘉丽最近怎么样？"))

    assert "topic_depth_card" not in cards


def test_the_card_never_leaks_a_live_object() -> None:
    """槽位是**自有数据**，不能夹带任何活对象引用。"""

    history = [
        {"role": "assistant", "content": _SNOW},
        {"role": "assistant", "content": _SNOW},
    ]

    slot = json.loads(_cards(_payload(history, message="嗯"))["topic_depth_card"])

    assert set(slot) <= {"depthTrigger", "instruction"}
    assert all(isinstance(value, str) for value in slot.values())
