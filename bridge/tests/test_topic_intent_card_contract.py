"""`intent="topic"`（游戏端「找话题」）的卡片契约（2026-09-22）。

## 背景（用户实测）

> 「索菲亚六句话里面四句关于画，并且说话文艺腔太重，不贴角色」

云端复跑 12 轮「找话题」后查清的根因不在人设，而在**这条意图路径自己的卡片**：
`topic` 是「系统请 NPC 主动开口」，**没有本轮玩家输入**——
`app._build_context` 与 `smapi/BridgeClient.SendAsync` 都会把 `message` 清空
（`ConversationIntent.Topic` 分支）。但这条路径上四张卡全都是**为「玩家说了话」写的**：

| 卡片 | 字段 | 原文（stranger） |
|---|---|---|
| `stage_execution_card` | `initiative` | 不主动开启新话题，不为延长对话而反问 |
| `stage_execution_card` | `responseShape` | 轻柔地用 1 句**回答**… |
| `stage_execution_card` | `instruction` | 先**落角色自己的立场或态度**…表达预算：角色化的**态度或反应是主句** |
| `turn_plan` | `instruction` | 先**落角色自己的态度**，再给一个具体、轻量的继续入口 |

四个"回答/接住"一起否定这次请求本身，而 `topic_response_contract` 又写着
「允许从角色自己的近况、记忆、兴趣或眼前观察主动开启新话题」——
模型收到的是互相排斥的目标，只能退回到最保守的读法。

本文件钉住「起头」与「回答」的分叉：topic 走起头版，**chat 必须一字不变**。

## 为什么用 `app._build_context` 而不是 runner

游戏端请求体（`BridgeDialogueRequest`）**不带 `qualityContext`**，
所以 `naturalMode` 不是 True，`stage_execution_card` 走
`_compact_stage_policy` 分支。评测 runner 会给 adaptive 案例注入
`naturalMode=True`，用它做探针看到的是**另一条路径**（`sophia_liveliness_final`、
`natural_topic_role_override` 等卡只在那边出现）。这个文件必须走真实入口。
"""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest

app_module = importlib.import_module("stardew_ai_bridge.app")


def _game_payload(
    intent: str,
    stage: str = "stranger",
    message: str = "",
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """游戏端真实请求体：没有 qualityContext，compactPrompt 默认 true。"""

    return {
        "npcId": "Sophia",
        "displayName": "索菲亚",
        "message": message,
        "intent": intent,
        "channel": "remote",
        "compactPrompt": True,
        "sourceMods": ["FlashShifter.StardewValleyExpandedCP"],
        "recentFacts": [],
        "history": history or [],
        "gameState": {
            "relationshipStage": stage,
            "friendshipHearts": 0,
            "sourceMods": ["FlashShifter.StardewValleyExpandedCP"],
        },
    }


# 两轮都落在「工作或手艺」面 —— `facetRepeat` 的触发条件（最近 3 轮同面 ≥2 次）。
_SLOT_HISTORY: list[dict[str, Any]] = [
    {
        "role": "assistant",
        "content": "我刚把酒窖那批新酿的塞子检查了一遍。",
        "intent": "topic",
        "relationshipStage": "friend",
    },
    {
        "role": "assistant",
        "content": "新酿的颜色比上一批深一点。",
        "intent": "topic",
        "relationshipStage": "friend",
    },
]


def _cards(intent: str, stage: str = "stranger") -> tuple[dict[str, Any], dict[str, Any]]:
    message = "今天天气不错。" if intent == "chat" else ""
    _, messages = app_module._build_context(
        _game_payload(intent, stage, message),
        compact_prompt=True,
    )
    stage_card = json.loads(
        next(m for m in messages if m.get("name") == "stage_execution_card")["content"]
    )
    turn_plan = json.loads(
        next(m for m in messages if m.get("name") == "turn_plan")["content"]
    )
    return stage_card, turn_plan


@pytest.mark.parametrize(
    "stage",
    ["stranger", "acquaintance", "friend", "close", "dating", "married", "parent"],
)
def test_topic_stage_card_asks_for_an_opening_not_an_answer(stage: str) -> None:
    """七个阶段都要：topic 的阶段卡不再要求她回应一句不存在的话。"""

    stage_card, _ = _cards("topic", stage)

    assert "先直接回答" not in stage_card["responseShape"], stage
    assert "回答" not in stage_card["responseShape"], stage
    assert "起一个话头" in stage_card["responseShape"], stage
    assert "起头" in stage_card["initiative"], stage
    assert "不主动开启新话题" not in stage_card["initiative"], stage
    assert "先让这个角色自己开口表态" not in stage_card["instruction"], stage
    assert "本轮由系统请求 NPC 主动起一个话头" in stage_card["instruction"], stage


def test_topic_turn_plan_starts_instead_of_answering() -> None:
    """`turn_plan` 是模型看到的最后一张行为卡，不能还写着「先回答」。"""

    _, turn_plan = _cards("topic")

    assert turn_plan["instruction"].startswith("本轮由 NPC 主动开场")
    assert "先回答" not in turn_plan["instruction"]
    # 「留一个口子」的语义保留（mode 仍是 answer_plus_lead）。
    assert turn_plan["mode"] == "answer_plus_lead"
    assert "口子" in turn_plan["instruction"]


def test_topic_opening_names_the_scene_before_her_own_chores() -> None:
    """开场入口的顺序与具体度：**先眼前，再近况**。

    起因（2026-09-24 实测）：30 次独立会话里 **30%** 用同一个句式开头
    ——「嗯……我刚把 X 收拾/整理完 → 反问玩家」。原本三种入口是并列的
    （「自己的近况、手里正在做的事或眼前看到的东西」），模型稳定地选第二个：
    它是三者里最容易满足「说清它是什么（最小背景）」的一个。

    修的方向是**给另外两种入口竞争力**，不是禁止这一种：把这三种里
    「眼前看到的」提到最前，并给出具体例子。**没有新增任何禁止性约束**
    —— 反机械感靠减约束、给示例。

    真实场景字段（`prompts.py:6525-6559` 渲染的 `scene` 卡：季节 / 日期 /
    天气 / 时段 / 地点 / 场合）本就齐全，线上 `GameStateCollector` 每次都发，
    所以「眼前」这条入口是有素材可依的。
    """

    _, turn_plan = _cards("topic")
    instruction = turn_plan["instruction"]

    # 「眼前」排在「近况／手边」之前。
    assert instruction.index("眼前") < instruction.index("近况")
    # 具体例子在场（这是让入口真的有竞争力的部分）。
    assert "窗" in instruction or "光" in instruction
    # 没变成一长串禁令：除原有的「不要等待、复述或回应」外不新增「不要……」。
    assert instruction.count("不要") <= 1


@pytest.mark.parametrize("stage", ["stranger", "dating"])
def test_chat_stage_card_is_untouched(stage: str) -> None:
    """普通私聊路径一个字都不能变——本轮修的是 topic 的分叉。"""

    from stardew_ai_bridge.prompts import _TURN_PLAN_COMPACT_INSTRUCTIONS
    from stardew_ai_bridge.stage_policy import build_stage_policy

    stage_card, turn_plan = _cards("chat", stage)
    base = build_stage_policy("Sophia", stage)

    # 与阶段策略数据逐字一致（不是"含某个词"这种松断言）。
    assert stage_card["responseShape"] == base["responseShape"]
    assert stage_card["initiative"] == base["initiative"]
    assert "先让这个角色自己开口表态" in stage_card["instruction"]
    # turn_plan 仍是通用模式文案，没有被 topic 的「起头」版替换。
    assert turn_plan["instruction"] == _TURN_PLAN_COMPACT_INSTRUCTIONS[turn_plan["mode"]]
    assert "本轮由 NPC 主动开场" not in turn_plan["instruction"]


def test_topic_keeps_the_stage_boundary_intact() -> None:
    """只改「起头还是回应」，阶段边界与称呼一个都不许动。"""

    topic_card, _ = _cards("topic", "stranger")
    chat_card, _ = _cards("chat", "stranger")

    assert topic_card["stage"] == chat_card["stage"] == "stranger"
    assert topic_card["boundaryMode"] == chat_card["boundaryMode"]
    assert topic_card["selfDisclosure"] == chat_card["selfDisclosure"]
    assert topic_card["voiceFingerprint"] == chat_card["voiceFingerprint"]


def _slot_card(intent: str) -> dict[str, Any]:
    """带两轮同面历史的请求；让 `rotation_topic_slot` 产出 `facetRepeat` 槽位。"""

    _, messages = app_module._build_context(
        _game_payload(
            intent,
            "friend",
            "嗯。" if intent == "chat" else "",
            history=_SLOT_HISTORY,
        ),
        compact_prompt=True,
    )
    return json.loads(
        next(m for m in messages if m.get("name") == "stage_execution_card")["content"]
    )


def test_topic_slot_drops_the_player_anchor_constraint() -> None:
    """第五处同型矛盾：`playerAnchor` 要求接住「玩家**本轮**点名的对象」。

    topic 路径没有本轮玩家输入（`BridgeClient` 只在非 topic 时带上 message），
    这条「硬约束」在字面上要求她接住一个不存在的东西。槽位自己的 `instruction`
    说的是「先接住那里面的具体东西」（= **上一轮她说过的话**，topic 下有历史、
    成立），所以只摘 `playerAnchor`，槽位其余字段保留。
    """

    topic_card = _slot_card("topic")
    slot = topic_card.get("topicSlot")

    assert slot is not None, "两轮同面历史应触发 facetRepeat 槽位"
    assert slot["trigger"] == "facetRepeat"
    assert "playerAnchor" not in slot
    # 换面指令本身保留（否则槽位就白触发了）。
    assert slot["bannedFacet"] == "工作或手艺"
    assert slot["suggestedTopic"]


def test_chat_slot_keeps_the_player_anchor_constraint() -> None:
    """chat 路径有本轮玩家输入，那条硬约束必须原样保留。"""

    chat_card = _slot_card("chat")
    slot = chat_card.get("topicSlot")

    assert slot is not None
    assert "玩家本轮点名的对象" in slot["playerAnchor"]
