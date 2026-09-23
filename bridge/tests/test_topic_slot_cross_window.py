"""跨轮次状态：让「这条素材谈过了」活过 history 窗口（2026-09-23）。

## 要修的形状

`rotation_topic_slot` 的 `spoken`（"这条素材最近说过了"）与 `speech_evidence` /
`style_samples` 的轮转去重，判据都只看得见 `history` —— 而真机 history 被
`smapi/BridgeClient.MaxHistoryItems = 6` 封顶（每轮追加 user + assistant 两条 ⇒
只覆盖 **3 轮**）。第 4 轮起，更早谈过的素材被挤出窗口、重新变回"没谈过"，
于是槽位反复建议同几条、素材卡也反复递同几条。这正是用户说的「聊不长」。

⇒ 加一条**跨窗口**通道：请求体多带一份"她最近说过的原文"（`recentReplies`），
比发送窗口长，**只用于判"说过没有"**，不进模型看到的 history。

## 为什么把窗口拉长是安全的（离线实测，不是推断）

`.tmp/topic-probe/crosswindow-diagnose.py` 在三批真机产物（12 / 24 / 24 轮）上量过：
2-gram ≥ 0.5 的判据在 **24 轮窗口**下的**假阳只有 0~1 条**（同一段文本上，"素材关键词"
参照判出 8~9 条、判据只判 4~5 条）⇒ 判据**偏保守**：漏报多、误判几乎没有。
保守地多排除几条不会凭空砍掉素材池；会砍掉素材池的是反方向（误判）。

## 本文件钉住的三件事

1. 跨窗口谈过的素材，**不再被选为**落点（`spoken_replies`）；
2. 判据的窗口语义是**显式**的：默认仍是"最近两条"（既有行为一个字不改），
   跨窗口调用必须显式传 `window=None` —— 否则传进去的长窗口会被静默截回两条；
3. 跨窗口那一份**不进模型消息**：它只喂判定，不喂对话。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from stardew_ai_bridge import app as app_module
from stardew_ai_bridge.models import DialogueTestRequest
from stardew_ai_bridge.personas import PersonaStore
from stardew_ai_bridge.prompts import (
    ContextBuilder,
    PromptBuilder,
    _evidence_already_spoken,
    _recent_npc_replies,
)
from stardew_ai_bridge.stage_policy import (
    _topic_already_spoken,
    rotation_topic_slot,
)

ROOT = Path(__file__).resolve().parents[2]
PERSONAS_DIR = ROOT / "data" / "personas"
SOPHIA_MODS = ["vanilla", "SVE", "FlashShifter.StardewValleyExpandedCP"]

# 池子四条，四条都落在**不同**的生活面（工作面两条、吃喝一条、爱好一条）。
# 触发用最近两轮的天气句：它们判得出「天气季节」且重复两次 ⇒ `facetRepeat` 触发。
WEATHER_REPLIES = [
    "外面下雨了，风也很大。",
    "今天天气真好啊，云很淡。",
]
BREW_TOPIC = "酒窖里这一批新酿"
CLOTH_TOPIC = "手工房的布料"
FOOD_TOPIC = "格斯做的菜"
HOBBY_TOPIC = "动漫展"
POOL = [BREW_TOPIC, CLOTH_TOPIC, FOOD_TOPIC, HOBBY_TOPIC]

# 跨窗口那一份：比发送窗口长，且**逐字**包含素材条目（判据要按原文的 2-gram 判）。
BREW_SPOKEN = "我刚才把酒窖里这一批新酿装进橡木桶了。"
CLOTH_SPOKEN = "手工房的布料还剩半卷没裁完。"
FOOD_SPOKEN = "今天我又想起格斯做的菜了。"
CROSS_REPLIES = [BREW_SPOKEN, CLOTH_SPOKEN, FOOD_SPOKEN]


def test_cross_window_spoken_topics_are_excluded_from_the_slot() -> None:
    """跨窗口谈过的三条都被排除，只剩没谈过的那条。"""

    slot = rotation_topic_slot(
        POOL,
        recent_replies=WEATHER_REPLIES,
        spoken_replies=CROSS_REPLIES,
    )

    assert slot, "天气面重复两次应当触发换面槽位"
    assert slot["trigger"] == "facetRepeat"
    assert slot["suggestedTopic"] == HOBBY_TOPIC, (
        "跨窗口已经谈过的素材不该再被建议："
        f"得到 {slot['suggestedTopic']!r}"
    )


def test_without_the_cross_window_the_slot_still_picks_a_spoken_topic() -> None:
    """**改前的形状**：不给跨窗口那一份时，早已谈过的素材照样会被选中。

    这条是上一条的对照组 —— 没有它就说不清"排除"到底是不是跨窗口带来的。
    """

    slot = rotation_topic_slot(POOL, recent_replies=WEATHER_REPLIES)

    assert slot["suggestedTopic"] in {BREW_TOPIC, CLOTH_TOPIC, FOOD_TOPIC}


def test_slot_still_answers_when_every_topic_was_already_spoken() -> None:
    """池子全谈光时仍然给出一条（降级到"允许重复"，不返回空）。"""

    slot = rotation_topic_slot(
        [BREW_TOPIC, CLOTH_TOPIC],
        recent_replies=WEATHER_REPLIES,
        spoken_replies=[BREW_SPOKEN, CLOTH_SPOKEN],
    )

    assert slot["suggestedTopic"] in {BREW_TOPIC, CLOTH_TOPIC}


def test_the_echo_criterion_window_is_explicit() -> None:
    """默认只看最近两条（既有行为），跨窗口必须显式要求整段。"""

    replies = [BREW_SPOKEN, *WEATHER_REPLIES]

    assert _topic_already_spoken(BREW_TOPIC, replies) is False
    assert _topic_already_spoken(BREW_TOPIC, replies, window=None) is True


def test_context_builder_exposes_the_cross_window_replies() -> None:
    """请求里的 `recentReplies` 要落进 context，并规整成可直接用的文本。"""

    builder = ContextBuilder(PersonaStore(PERSONAS_DIR))
    context = builder.build(
        {
            "npcId": "Sophia",
            "sourceMods": SOPHIA_MODS,
            "recentReplies": ["   ", BREW_SPOKEN, "长" * 400],
        }
    )

    assert context["recentReplies"] == [BREW_SPOKEN, "长" * 180], (
        "空白项要丢掉、单项要按 NPC 回复的口径限长（与 "
        "`_recent_npc_replies` 的 180 一致）"
    )


def test_recent_npc_replies_prefers_the_cross_window() -> None:
    """取"她最近说过什么"时优先用跨窗口那一份，退化回 history。"""

    history_only = {
        "history": [{"role": "assistant", "content": "history 里那句"}],
    }
    assert _recent_npc_replies(history_only) == ["history 里那句"]

    with_cross = dict(history_only, recentReplies=[BREW_SPOKEN])
    assert _recent_npc_replies(with_cross) == [BREW_SPOKEN]


def test_cross_window_replies_never_reach_the_model_messages() -> None:
    """护栏：这一份只喂判定，不喂对话。"""

    builder = ContextBuilder(PersonaStore(PERSONAS_DIR))
    context = builder.build(
        {
            "npcId": "Sophia",
            "sourceMods": SOPHIA_MODS,
            "intent": "topic",
            "recentReplies": ["这是只该用于判定的跨窗口句子。"],
        }
    )
    messages = PromptBuilder().build(context, "", compact=True)
    blob = " ".join(str(message.get("content", "")) for message in messages)

    assert "只该用于判定" not in blob


def test_the_evidence_criterion_sees_the_whole_cross_window() -> None:
    """素材轮转的判据要看**整段**跨窗口文本，不能被静默截回 4 条。

    这条钉住 2026-09-23 删掉的那个切片（`recent_replies[-4:]`）：4 是 history
    那条退化路径的上界（发送窗口 6 条 ⇒ 最多 3 条 NPC 回复，取 4 是"全都看"），
    一旦调用方换成跨窗口那一份（几十条），切片会把长窗口**悄悄**截回最近 4 条
    —— 跨窗口就白接了，而且没有任何报错。
    """

    sample = {"text": "我刚把新酿装进橡木桶。"}
    # 目标出现在窗口**最前面**，后面垫 6 条无关的回复（超出旧的 4 条截断线）。
    long_window = ["我刚把新酿装进橡木桶。"] + [
        f"这是第{index}条无关的话。" for index in range(1, 7)
    ]

    assert _evidence_already_spoken(sample, long_window) is True


def test_request_model_and_field_whitelist_carry_recent_replies() -> None:
    """字段要在请求模型**和** app 的白名单里 —— 少一处就被静默吞掉。"""

    request = DialogueTestRequest.model_validate(
        {
            "npcId": "Sophia",
            "message": "你好",
            "recentReplies": [BREW_SPOKEN],
        }
    )

    assert request.recent_replies == [BREW_SPOKEN]
    assert "recentReplies" in app_module._DIALOGUE_FIELDS

    with pytest.raises(ValidationError):
        DialogueTestRequest.model_validate(
            {
                "npcId": "Sophia",
                "message": "你好",
                "recentReplies": ["x"] * 41,
            }
        )
