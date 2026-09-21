"""开场反重复链路：长度窗口与前导语气颗粒（2026-09-21 用户实测）。

用户实测「开场结构逐字重复」——索菲亚第 1 轮与第 3 轮都以
「（嘿，）我刚从蓝月亮葡萄园回来，手上还沾着葡萄藤的青涩味儿」起句。
排查结论是**这条链路离线**，而不是"拦了没拦住"，且需要两处同时修：

1. `prompts._history_openings` 的长度窗口原先写死 24，而被复用的那条开场首分句
   正好 **25 字**，整条被丢弃 ⇒ `avoidOpenings` 为空 ⇒ `post_history_voice_guard`
   里「不要重复历史中的开场」没有任何依据可依，`guard._has_repeated_opening`
   永远返回 False。
2. `dialogue_boundaries.reply_opens_with_marker` 原先用逐字前缀匹配，第 3 轮多带
   一个「嘿，」就完全不命中。

只修任一处，索菲亚那条 case 仍然漏过（四格对照见文件末尾的
`test_only_relaxing_the_length_window_is_not_enough`）。
"""

from __future__ import annotations

import json

import pytest

from stardew_ai_bridge.app import _build_context
from stardew_ai_bridge.dialogue_boundaries import (
    LEADING_SPEECH_PARTICLES,
    reply_opens_with_marker,
    strip_leading_speech_particles,
)
from stardew_ai_bridge.guard import retry_for_format_noise
from stardew_ai_bridge.models import ProviderResult
from stardew_ai_bridge.prompts import (
    _HISTORY_OPENING_LIMIT,
    _history_openings,
    _opening_prefixes,
)

SOPHIA_MODS = ["vanilla", "SVE", "FlashShifter.StardewValleyExpandedCP"]

# 用户截图里的原文（第 1 轮）。首分句 25 字，正是旧窗口放过的那一条。
SOPHIA_OPENING = "我刚从蓝月亮葡萄园回来，手上还沾着葡萄藤的青涩味儿"
SOPHIA_T1 = (
    SOPHIA_OPENING + "。画笔昨天就搁在酒窖那张木桌上了，我总觉得还差一笔。"
    "你觉得是摆到窗边亮一点的地方好，还是就留在桌边闻着酒香看？"
)
SOPHIA_T2 = "那幅画我今天又添了两笔，颜料干得比想象中快。酒窖那批新酿也快好了。"
# 第 3 轮：同一条开场，前面多了一个「嘿，」。
SOPHIA_T3_REPEATED = (
    "嘿，" + SOPHIA_OPENING + "。先别管那幅画了，酒窖那批新酿今天开桶，你来不来尝一口？"
)
CLEAN_REPLY = (
    "镇上今天有人在广场上为摊位的事吵起来了，我路过听了一耳朵。你要不要晚上过来坐坐？"
)


def _payload(npc: str, replies: list[str], mods: list[str]) -> dict:
    history: list[dict[str, str]] = []
    for index, reply in enumerate(replies):
        history.append({"role": "user", "content": f"第{index + 1}轮提问"})
        history.append({"role": "assistant", "content": reply})
    return {
        "npcId": npc, "message": "今天过得怎么样？", "intent": "chat", "provider": "fake",
        "compactPrompt": True, "channel": "face_to_face",
        "sourceMods": mods, "recentFacts": [], "history": history,
        "gameState": {
            "npcId": npc, "displayName": npc, "gender": "Female", "location": "Town",
            "season": "spring", "date": "25", "weather": "clear", "time": 1200,
            "friendship": 1500, "friendshipHearts": 6, "relationship": "friend",
        },
    }


def _sophia_history() -> list[dict[str, str]]:
    return [
        {"role": "user", "content": "第1轮提问"},
        {"role": "assistant", "content": SOPHIA_T1},
        {"role": "user", "content": "第2轮提问"},
        {"role": "assistant", "content": SOPHIA_T2},
    ]


# --- 1. 长度窗口 --------------------------------------------------------------


def test_history_openings_keeps_the_opening_that_was_actually_reused() -> None:
    """被复用的那条开场首分句 25 字，必须进 avoidOpenings。"""

    openings = _history_openings(_sophia_history())

    assert SOPHIA_OPENING in openings
    assert len(SOPHIA_OPENING) > 24  # 旧窗口的上界，回归时钉住
    assert len(SOPHIA_OPENING) <= _HISTORY_OPENING_LIMIT


def test_history_openings_still_skips_empty_and_oversized_text() -> None:
    """放宽不等于不设界：空片段与超出窗口的长段落仍不入列表。"""

    history = [
        {"role": "assistant", "content": "。只有标点。"},
        {"role": "assistant", "content": "很" * (_HISTORY_OPENING_LIMIT + 1) + "。"},
    ]

    assert _history_openings(history) == []


# --- 2. 前缀生成 --------------------------------------------------------------


def test_opening_prefixes_include_structure_beyond_the_leading_particle() -> None:
    """「嘿，我刚从……」既要给出「嘿」，也要给出剥掉语气词后的「我刚」。"""

    prefixes = _opening_prefixes(["嘿，我刚从蓝月亮葡萄园回来"])

    assert "嘿" in prefixes
    assert "我刚" in prefixes


def test_opening_prefixes_keep_a_plain_opening_readable() -> None:
    """没有语气颗粒的开场，前缀就是它自己的前两个字。"""

    assert _opening_prefixes([SOPHIA_OPENING]) == ["我刚"]


# --- 3. 共享判定 --------------------------------------------------------------


@pytest.mark.parametrize("particle", LEADING_SPEECH_PARTICLES)
def test_reply_opens_with_marker_ignores_leading_speech_particle(particle: str) -> None:
    """逐字匹配会让「嘿，+同一开场」逃逸；比对必须忽略句首语气颗粒。"""

    reply = f"{particle}，" + SOPHIA_OPENING + "。"

    assert reply_opens_with_marker(reply, (SOPHIA_OPENING, "我刚"))
    assert reply.startswith(particle)  # 确认这条回复真的带了颗粒


def test_reply_opens_with_marker_still_rejects_a_different_opening() -> None:
    """忽略语气颗粒不等于忽略开场本身。"""

    reply = "酒窖那批新酿今天开桶，你来不来尝一口？"

    assert reply_opens_with_marker(reply, (SOPHIA_OPENING, "我刚")) is False


def test_strip_leading_speech_particles_is_the_single_source() -> None:
    assert strip_leading_speech_particles("嘿，你来了。") == "你来了。"
    assert strip_leading_speech_particles("你来了。") == "你来了。"


# --- 4. 端到端：真实 prompt + 真实重试链 ---------------------------------------


def _compact_messages(replies: list[str]) -> list[dict[str, str]]:
    _, messages = _build_context(_payload("Sophia", replies, SOPHIA_MODS))
    return messages


def _guard_payload(messages: list[dict[str, str]]) -> dict:
    for message in messages:
        if message.get("name") == "post_history_voice_guard":
            return json.loads(message["content"])
    raise AssertionError("prompt 里没有 post_history_voice_guard 卡")


def test_avoid_openings_reaches_the_live_compact_prompt() -> None:
    """端到端：游戏路径（compactPrompt=True）里 avoidOpenings 必须非空。"""

    guard = _guard_payload(_compact_messages([SOPHIA_T1, SOPHIA_T2]))

    assert SOPHIA_OPENING in guard["avoidOpenings"]
    assert "我刚" in guard["avoidOpeningPrefixes"]


def test_repeated_opening_is_retried_and_the_reply_is_rewritten() -> None:
    """重试链：复用历史开场的那条回复会被换掉。"""

    messages = _compact_messages([SOPHIA_T1, SOPHIA_T2])
    calls: list[list[dict[str, str]]] = []

    def generate(retry_messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(retry_messages)
        return ProviderResult(reply=CLEAN_REPLY, provider="cloud", fallback=False, latencyMs=10)

    result = retry_for_format_noise(
        ProviderResult(
            reply=SOPHIA_T3_REPEATED, provider="cloud", fallback=False, latencyMs=10
        ),
        messages,
        generate,
    )

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "opening_retry"
    assert "response_opening_retry: repeated" in result.warnings
    assert result.reply == CLEAN_REPLY


def test_a_fresh_opening_does_not_trigger_the_retry() -> None:
    """对照：不重复历史的回复不该被重试（避免把这条修复变成过度重试）。"""

    messages = _compact_messages([SOPHIA_T1, SOPHIA_T2])
    calls: list[list[dict[str, str]]] = []

    def generate(retry_messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(retry_messages)
        return ProviderResult(reply=CLEAN_REPLY, provider="cloud", fallback=False, latencyMs=10)

    result = retry_for_format_noise(
        ProviderResult(reply=CLEAN_REPLY, provider="cloud", fallback=False, latencyMs=10),
        messages,
        generate,
    )

    assert calls == []
    assert result.reply == CLEAN_REPLY


def test_only_relaxing_the_length_window_is_not_enough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """四格对照的另一半：长度窗口修好、判定仍逐字时，这条 case 依然漏过。

    它不是"重复测试"，而是钉住**两处修复缺一不可**；将来若有人把
    `reply_opens_with_marker` 改回逐字匹配，这条会立刻变红。
    """

    import stardew_ai_bridge.guard as guard_module

    def legacy_opens_with_marker(reply: object, markers: tuple[str, ...]) -> bool:
        if not isinstance(reply, str) or not reply.strip() or not markers:
            return False
        text = reply.strip()
        return any(text.startswith(marker) for marker in markers if marker)

    monkeypatch.setattr(
        guard_module, "reply_opens_with_marker", legacy_opens_with_marker
    )
    messages = _compact_messages([SOPHIA_T1, SOPHIA_T2])
    calls: list[list[dict[str, str]]] = []

    def generate(retry_messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(retry_messages)
        return ProviderResult(reply=CLEAN_REPLY, provider="cloud", fallback=False, latencyMs=10)

    result = retry_for_format_noise(
        ProviderResult(
            reply=SOPHIA_T3_REPEATED, provider="cloud", fallback=False, latencyMs=10
        ),
        messages,
        generate,
    )

    assert _guard_payload(messages)["avoidOpenings"]  # 窗口已放宽
    assert calls == []  # 但逐字判定仍然漏过
    assert result.reply == SOPHIA_T3_REPEATED
