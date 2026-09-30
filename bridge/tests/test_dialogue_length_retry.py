"""对白长度分级重试的固定行为。

这里钉的是 A2 方案：只有**明显超长**才花一次请求重写，
60~68 字那一档继续走既有的截断兜底。阈值与重试次数
是这个方案的**全部成本来源**，两者都不能默默改掉：
阈值下调到 64 会把请求增量抬到 8.4%，重试次数升到 2 就会让
每条超长回复请求量直接翻倍（开发时实测到 `calls=2`）。

`_DIALOGUE_MAX_CHARS`（目标上限，60）与 `_LENGTH_RETRY_THRESHOLD`
（重试阈值，68）**刻意解耦**：前者是「我们希望多长」，后者是
「长到多少才值得花一次请求」。用「上限 × 比例」推导会让调上限
变成偷改成本预算 —— 这条测试同时钉住两者的取值与彼此独立。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.guard import (
    _DIALOGUE_MAX_CHARS,
    _LENGTH_RETRY_THRESHOLD,
    _NATURAL_RETRY_CONTENT,
    LENGTH_RETRY_CONTENT,
    reply_exceeds_dialogue_length,
    retry_for_format_noise,
)
from stardew_ai_bridge.models import ProviderResult

# 字符串重复计数就是字数 —— 判据用 `len()`，与探针同口径。
_THRESHOLD = _LENGTH_RETRY_THRESHOLD


def _over() -> str:
    """刚刚超过阈值的一条对白。"""

    return "啊" * (_THRESHOLD + 1)


def _within() -> str:
    """超了上限、但还在阈值内的一条对白。"""

    return "啊" * _THRESHOLD


def _retry(
    reply: str,
    *,
    rewritten: str | None = None,
) -> tuple[object, list[list[dict[str, str]]]]:
    result = ProviderResult(reply=reply, provider="cloud", fallback=False, latencyMs=12)
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(
            update={"reply": reply if rewritten is None else rewritten}
        )

    return retry_for_format_noise(result, [], generate), calls


def test_length_cap_and_retry_threshold_are_pinned_and_decoupled() -> None:
    """两个量各自的取值与彼此独立性。"""

    assert _DIALOGUE_MAX_CHARS == 60
    # 1.7 是回放 2799 条对白定的（超 68 字占 5.79%），
    # 而 1.6 会把重试量抬到 8.43%。改这个数字 = 改 A2 的成本。
    assert _LENGTH_RETRY_THRESHOLD == 68
    # 解耦：目标上限不能反推出重试阈值。
    assert _DIALOGUE_MAX_CHARS != _LENGTH_RETRY_THRESHOLD
    assert _THRESHOLD == 68


# 边界用**相对阈值**表达：阈值数字本身已由上一个测试钉住，这里只管
# 「阈值上下一字之差」这条行为 —— 否则每次调比例都要来改这里的
# 硬编码序列（这正是 1.6 → 1.7 时挖出来的）。
@pytest.mark.parametrize("size", [0, 1, 30, 40, _DIALOGUE_MAX_CHARS, _THRESHOLD - 1, _THRESHOLD])
def test_reply_at_or_under_threshold_is_not_flagged(size: int) -> None:
    assert reply_exceeds_dialogue_length("啊" * size) is False


@pytest.mark.parametrize("size", [_THRESHOLD + 1, _THRESHOLD + 2, 120, 200, 1000])
def test_reply_over_threshold_is_flagged(size: int) -> None:
    assert reply_exceeds_dialogue_length("啊" * size) is True


@pytest.mark.parametrize("reply", [None, 123, "", "   ", {"text": "啊" * 200}])
def test_non_text_or_blank_reply_is_not_flagged(reply: object) -> None:
    """空值由 `ResponseGuard.check` 按 `empty` / `non_text` 处理，不归长度管。"""

    assert reply_exceeds_dialogue_length(reply) is False


def test_over_long_reply_triggers_exactly_one_length_retry() -> None:
    """只重试一次是 A2 的成本上限。""" 

    retried, calls = _retry(_over())

    assert len(calls) == 1
    assert calls[0][-1]["name"] == "length_retry"
    assert calls[0][-1]["content"] == LENGTH_RETRY_CONTENT
    assert "response_length_retry: over_length" in retried.warnings


def test_reply_under_threshold_never_spends_a_request() -> None:
    """40~64 字这一档不能重试 —— 否则就不是 A2 了。"""

    _, calls = _retry(_within())

    assert calls == []


def test_shorter_retry_is_adopted() -> None:
    """重试变短必须被采纳，否则重试白做。"""

    retried, calls = _retry(_over(), rewritten="啊" * 30)

    assert len(calls) == 1
    assert len(retried.reply) == 30


def test_longer_retry_is_rejected() -> None:
    """重试变长不能被采纳 —— 长度已进 `_retry_quality_key`。"""

    retried, calls = _retry(_over(), rewritten="啊" * 300)

    assert len(calls) == 1
    assert len(retried.reply) == _THRESHOLD + 1


def test_equally_long_retry_still_spends_only_one_request() -> None:
    """重试没改善长度时不能继续重试。"""

    _, calls = _retry(_over())

    assert len(calls) == 1


def test_natural_mode_has_a_length_direction() -> None:
    """自然模式不能退回通用文案 —— 那样重试方向就丢了。"""

    assert "length" in _NATURAL_RETRY_CONTENT
    assert "收短" in _NATURAL_RETRY_CONTENT["length"]


def test_length_retry_content_forbids_truncating_the_sentence() -> None:
    """重试要求压缩，不是截断 —— 截断正是 B 方案的毛病。"""

    assert "不要把句子截断" in LENGTH_RETRY_CONTENT
