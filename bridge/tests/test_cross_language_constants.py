"""跨语言常量的单一来源（语义层审计 P3 第 47、48 条）。

这两条是同一类问题：**同一个东西在 C# 与 Python 里各写一份**。

- **#47 安全兜底文案**——上游全不可用时给玩家看的那句话，此前在四处逐字重复：
  `config.py` 的配置默认值、`fallback.py` 的构造默认参数、`app.py` 的
  `_SAFE_FALLBACK_REPLY`，以及 C# 侧 `BridgeClient.Offline`。
- **#48 topic 回声过滤正则**——Bridge 用它判断模型是不是把提示词原样吐回来了，
  SMAPI 也用它做同一层过滤（`ConversationIntent.Topic` 分支）。

跨语言没法共享代码，所以做法是：**Python 侧先收敛到单一常量，再用本测试逐字
比对 C# 源文件里的那一份**。这样“改一边忘另一边”会立刻失败，而不是等到玩家
看到两种不同的兜底话术、或两种不一致的回声判定。
"""

from __future__ import annotations

import re
from pathlib import Path

from stardew_ai_bridge import app as bridge_app
from stardew_ai_bridge.config import DEFAULT_FALLBACK_REPLY, BridgeSettings
from stardew_ai_bridge.fallback import FallbackProvider
from stardew_ai_bridge.guard import ResponseGuard
from stardew_ai_bridge.models import MAX_COMPLETED_EVENT_IDS, DialogueTestRequest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE_CLIENT = _REPO_ROOT / "smapi" / "BridgeClient.cs"
_GAME_STATE_COLLECTOR = _REPO_ROOT / "smapi" / "GameStateCollector.cs"


def _csharp_source() -> str:
    # C# 源文件是 UTF-8（可能带 BOM）。
    return _BRIDGE_CLIENT.read_text(encoding="utf-8-sig")


# --- #47 安全兜底文案 -------------------------------------------------------


def test_python_fallback_reply_has_a_single_source() -> None:
    assert BridgeSettings().fallback_reply == DEFAULT_FALLBACK_REPLY
    assert FallbackProvider().reply == DEFAULT_FALLBACK_REPLY
    assert bridge_app._SAFE_FALLBACK_REPLY == DEFAULT_FALLBACK_REPLY


def test_csharp_offline_reply_matches_the_python_source() -> None:
    source = _csharp_source()
    match = re.search(r'Reply\s*=\s*"([^"]+)"', source)
    assert match, "BridgeClient.Offline 里找不到 Reply 字面量"

    assert match.group(1) == DEFAULT_FALLBACK_REPLY, (
        "C# 的离线兜底文案与 Python 的 DEFAULT_FALLBACK_REPLY 不一致："
        "两边会同屏出现不同的兜底话术，改一处必须同时改另一处"
    )


# --- #48 topic 回声过滤正则 -------------------------------------------------


def _csharp_topic_echo_pattern(source: str) -> str:
    block = re.search(
        r"TopicPromptEcho\s*=\s*new\((.*?)\);",
        source,
        re.DOTALL,
    )
    assert block, "BridgeClient 里找不到 TopicPromptEcho 正则"
    # C# 用 verbatim 字符串（@"..."）分片拼接，去掉换行与加号即可还原。
    parts = re.findall(r'@"((?:[^"]|"")*)"', block.group(1))
    assert parts, "TopicPromptEcho 里找不到 verbatim 字符串"
    return "".join(parts)


def test_topic_prompt_echo_pattern_is_identical_in_both_languages() -> None:
    python_pattern = ResponseGuard._topic_prompt_echo.pattern

    assert _csharp_topic_echo_pattern(_csharp_source()) == python_pattern, (
        "C# 与 Python 的 topic 回声过滤正则已漂移：同一段提示词泄露会在一边被拦、"
        "另一边放过"
    )


def test_the_pattern_actually_matches_a_leaked_line() -> None:
    """防止上面两条只做“两边一样”的字符串比较而掩盖正则本身失效。"""

    leaked = "请主动找一个自然的话题来聊吧。"

    assert ResponseGuard.is_topic_prompt_echo(leaked) is True
    assert ResponseGuard.is_topic_prompt_echo("我今天在矿洞里捡了块石头。") is False


# --- #46 compactPrompt 的默认值：刻意的不同，不是漂移 -------------------------


def test_compact_prompt_defaults_are_intentionally_different() -> None:
    """两边默认值相反是**有意设计**，不是为了统一。

    这条用例的作用是**拦住「顺手统一」**：有人看到两个相反的默认值会想改成一致，
    但改了哪一边，都等于改变「不传 compactPrompt 的调用方」拿到的 prompt 形态 ——
    · 游戏端（C#）默认紧凑：线上往返省 token；
    · Bridge 侧默认完整：离线评测与脚本需要完整 gameState 才能评质量。
    两个默认值服务不同调用方、从不同时生效（游戏端总是显式发送该字段）。
    """

    payload = {"npcId": "Abigail", "message": "你好", "provider": "fake"}
    assert DialogueTestRequest.model_validate(payload).compact_prompt is False

    match = re.search(
        r"public bool CompactPrompt \{ get; init; \} = (\w+);",
        _csharp_source(),
    )
    assert match, "BridgeClient 里找不到 CompactPrompt 的默认值"
    assert match.group(1) == "true", (
        "C# 的 CompactPrompt 默认值被改了：它与 Bridge 侧的 False 是刻意不同的一对，"
        "改动前请先确认所有调用方都显式传值，并同步这一条护栏与代码注释"
    )


# --- #49 `completedEventIds` 上限：两处必须同值 ---------------------------------
#
# 2026-09-21：这个上限曾是 128，在 C# 与 Python 里各写一份，于是「只改一处」会以
# 两种不同的方式坏掉 —— C# 侧更小是**静默截断**（事件链被判成没走完，已完成的门控
# 事件被丢掉，14 心已婚被压回 acquaintance），Python 侧更小是**直接 422**
# （请求被拒、退化成兜底回复）。用户存档 391 条撞上的正是前者。
#
# 现在两边各自收敛到一个具名常量，再用本测试把它们钉在一起，
# 并禁止 C# 侧再出现第二份字面量上限。


def test_completed_event_id_cap_matches_between_csharp_and_python() -> None:
    source = _GAME_STATE_COLLECTOR.read_text(encoding="utf-8-sig")
    match = re.search(r"MaxCompletedEventIds\s*=\s*(\d+)\s*;", source)
    assert match, "GameStateCollector 里找不到 MaxCompletedEventIds 常量"

    assert int(match.group(1)) == MAX_COMPLETED_EVENT_IDS, (
        "SMAPI 的 GameStateCollector.MaxCompletedEventIds 与 Bridge 的 "
        "models.MAX_COMPLETED_EVENT_IDS 不一致：C# 侧更小会静默丢掉已完成的事件、"
        "让事件门控误判；Python 侧更小会让请求 422 退化成兜底回复"
    )


def test_csharp_event_cap_has_a_single_literal() -> None:
    """C# 侧的两处消费点都必须走同一个常量，不能再冒出字面量上限。"""

    source = _GAME_STATE_COLLECTOR.read_text(encoding="utf-8-sig")

    assert "maxCount: MaxCompletedEventIds" in source, (
        "ReadEnumerableStrings(eventsSeen, ...) 的 maxCount 不再是常量："
        "这里写死数字会与 Bridge 的上限各走各的"
    )
    assert ".Take(MaxCompletedEventIds)" in source, (
        "NormalizeEventIds 的 Take 不再是常量：只改上面一处会被这里二次截断"
    )
    assert not re.search(r"maxCount:\s*\d+", source), (
        "GameStateCollector 里出现了字面量 maxCount —— 事件上限必须只有一份来源"
    )
    assert not re.search(r"\.Take\(\s*\d+\s*\)", source), (
        "GameStateCollector 里出现了字面量 Take(N) —— 事件上限必须只有一份来源"
    )
