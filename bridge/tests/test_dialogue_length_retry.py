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
    _LENGTH_RETRY_THRESHOLD_BY_STAGE,
    _NATURAL_RETRY_CONTENT,
    _length_retry_threshold,
    _retry_quality_key,
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


# ── 按阶段放宽长度阈值（2026-10-01）──────────────────────────────────────
#
# parent 是唯一一个 prompt 侧「内容要求压过篇幅要求」的阶段：`stage_policy.py`
# 的 responseShape 写「可用 1–2 句…涉及孩子时先说安全和实际安排」，而
# Sebastian / Elliott / Harvey / Sam 的角色覆盖更写成「先把安全和具体安排
# 说清楚，**再补一句**感受」。两个块都要求具体，1–2 句装不下。
#
# 实测 `artifacts/character-quality-eval/` 下 parent 阶段 55 轮（已剔除演示
# 模式占位回复）：超长组中位 83 字 / 6 句、每句 15.9 字；达标组 51 字 /
# 3 句、每句 15.2 字。**每句字数几乎相同，差的全是句数** —— 是内容块多，
# 不是句子注水。所以这不是「允许 parent 啰嗦」，是「不再拦它把话说完」。
#
# 下面钉四件事：只有 parent 放宽、未登记阶段退回全局、不传 stage 时行为
# 与改动前一致、以及**择优键与触发判据同源**（最后一条最容易被漏掉）。

_PARENT_LIMIT = _LENGTH_RETRY_THRESHOLD_BY_STAGE["parent"]
_OVER_GLOBAL = _LENGTH_RETRY_THRESHOLD + 1  # 69 字：全局算超长，parent 不算
_OVER_PARENT = _PARENT_LIMIT + 1  # 91 字：连 parent 也算超长


def _stage_reply(size: int) -> str:
    """按目标字数造一条**两句、带句读、不含语气助词**的回复。

    中性字很关键：用「啊」会命中语气密度检查，用无标点长串会命中格式检查，
    两种都会让测试绕过长度分支。
    """

    head = size // 2
    body = "田" * head + "。" + "禾" * (size - head - 2) + "。"
    assert len(body) == size, f"构造 {size} 字失败，实得 {len(body)}"
    return body


def _retry_stage(
    reply: str,
    *,
    stage: str | None = None,
    rewritten: str | None = None,
) -> tuple[object, list[list[dict[str, str]]]]:
    """与 `_retry` 同形，但能指定 stage（不动既有 helper）。"""

    result = ProviderResult(reply=reply, provider="cloud", fallback=False, latencyMs=12)
    calls: list[list[dict[str, str]]] = []

    def generate(messages: list[dict[str, str]]) -> ProviderResult:
        calls.append(messages)
        return result.model_copy(
            update={"reply": reply if rewritten is None else rewritten}
        )

    return retry_for_format_noise(result, [], generate, stage=stage), calls


def test_parent_stage_gets_a_wider_length_threshold() -> None:
    """parent 放宽到 90，边界落在 90 / 91 之间。"""

    assert _PARENT_LIMIT == 90
    assert (
        reply_exceeds_dialogue_length(_stage_reply(_OVER_GLOBAL), stage="parent")
        is False
    )
    assert (
        reply_exceeds_dialogue_length(_stage_reply(_PARENT_LIMIT), stage="parent")
        is False
    )
    assert (
        reply_exceeds_dialogue_length(_stage_reply(_OVER_PARENT), stage="parent")
        is True
    )
    # 同一条文本在全局口径下仍然算超长 —— 放宽只对 parent 生效。
    assert reply_exceeds_dialogue_length(_stage_reply(_OVER_GLOBAL)) is True


def test_only_parent_is_widened() -> None:
    """没有测量依据的阶段一律退回 68 —— 不许顺手一起放宽。

    close 的超长内容尚未测过；stranger / friend 的超长是另一回事。
    """

    for stage in ("stranger", "acquaintance", "friend", "close", "dating", "married"):
        assert _length_retry_threshold(stage) == _LENGTH_RETRY_THRESHOLD
        assert (
            reply_exceeds_dialogue_length(_stage_reply(_OVER_GLOBAL), stage=stage)
            is True
        )


def test_stage_lookup_tolerates_case_and_padding() -> None:
    """阶段名的来源不可控，大小写与空白差异不该让它退回全局阈值。"""

    assert _length_retry_threshold("parent") == _PARENT_LIMIT
    assert _length_retry_threshold("PARENT") == _PARENT_LIMIT
    assert _length_retry_threshold("  Parent  ") == _PARENT_LIMIT


@pytest.mark.parametrize("stage", [None, ""])
def test_missing_stage_keeps_the_global_threshold(stage: str | None) -> None:
    """不传 stage 必须与加参数之前完全一致 —— 既有调用方不用改。"""

    assert _length_retry_threshold(stage) == _LENGTH_RETRY_THRESHOLD
    assert reply_exceeds_dialogue_length(_stage_reply(_OVER_GLOBAL), stage=stage) is True


def test_quality_key_uses_the_same_stage_threshold() -> None:
    """触发判据与择优键必须同源。

    只改触发、不改择优，就会出现「按 parent 阈值触发了重试，择优时却仍按
    68 判长度」—— 重试结果在 style_clean 上打平甚至落败，重试白做。
    这与 `_retry_quality_key` 里那条注释警告过的粒度问题同形。
    """

    reply = _stage_reply(_OVER_GLOBAL)
    global_key = _retry_quality_key([], reply)
    parent_key = _retry_quality_key([], reply, stage="parent")

    # 末位是 style_clean：全局口径判超长（0），parent 口径不判（1）。
    assert global_key[-1] == 0
    assert parent_key[-1] == 1
    # 其余各位完全一致 —— 差异确实只来自长度这一项。
    assert parent_key[:-1] == global_key[:-1]


def test_parent_reply_within_widened_limit_spends_no_request() -> None:
    """端到端：parent 下 80 字是自然长度，不该花一次请求去压它。"""

    reply = _stage_reply(80)
    retried, calls = _retry_stage(reply, stage="parent")

    assert calls == []
    assert retried.reply == reply


def test_same_reply_triggers_length_retry_without_stage() -> None:
    """端到端对照：同一条 80 字在全局口径下必须触发长度重试。"""

    retried, calls = _retry_stage(_stage_reply(80))

    assert len(calls) == 1
    assert "response_length_retry: over_length" in retried.warnings
