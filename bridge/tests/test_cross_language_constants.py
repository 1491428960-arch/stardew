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

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE_CLIENT = _REPO_ROOT / "smapi" / "BridgeClient.cs"


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
