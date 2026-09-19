"""`guard.retry_for_format_noise` 的重试与失败回退。

2026-09-20 用覆盖率定位到 `guard.py` 93%，其中 **L1427–1439（13 行连续）** 是
“重试时抛非预算异常”的分支，从未被执行。它的契约是：**不把异常抛给调用方**，
而是保留已有回复、记两条警告，交给调用方现有兜底链路。

顺带钉住两条相关契约：

- 重试**成功但更差**时不采用它（只留一条“已重试”的警告）。
- 经济模式耗尽预算（`EvaluationBudgetExceeded`）时，把“预算停止”**如实**写进警告，
  不伪装成 ProviderError。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.evaluation_budget import EvaluationBudgetExceeded
from stardew_ai_bridge.guard import ResponseGuard, retry_for_format_noise
from stardew_ai_bridge.models import ProviderResult

_PROMPT = [
    {"role": "system", "content": "你是 Shane。"},
    {"role": "user", "content": "你好"},
]

_DIRTY_REPLY = "（笑了笑）你好。"  # stage_direction


def _result(reply: str, warnings: list[str] | None = None) -> ProviderResult:
    return ProviderResult(
        reply=reply,
        provider="fake",
        fallback=False,
        latencyMs=1,
        warnings=list(warnings or []),
    )


# --- format_issue 的分类 ----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("你好。", None),
        ("（笑了笑）你好。", "stage_direction"),
        ("你好（笑）", "stage_direction"),
        ("*微笑* 你好", "markdown"),
        ("**你好**", "markdown"),
        ("你好 [pause]", "english"),
        # 中文引号是正常排版，不该被判成 markdown
        ("他说“你好”。", None),
    ],
)
def test_format_issue_classifies_common_noise(text: str, expected: str | None) -> None:
    assert ResponseGuard.format_issue(text) == expected


# --- 重试失败：绝不抛给调用方 -----------------------------------------------


def test_a_failing_retry_keeps_the_original_reply_and_records_two_warnings() -> None:
    # 这是本次补测的核心契约：上游在重试时炸了，也不该让整轮对话失败。
    def boom(messages: list[dict[str, str]]) -> ProviderResult:
        raise RuntimeError("上游炸了")

    outcome = retry_for_format_noise(_result(_DIRTY_REPLY), _PROMPT, boom)

    assert outcome.reply == _DIRTY_REPLY
    assert outcome.warnings == [
        "response_format_retry: stage_direction",
        "response_format_retry_failed: provider_error",
    ]


def test_a_retry_failure_does_not_mutate_the_input_result() -> None:
    def boom(messages: list[dict[str, str]]) -> ProviderResult:
        raise RuntimeError("上游炸了")

    original = _result(_DIRTY_REPLY)
    retry_for_format_noise(original, _PROMPT, boom)

    # 原对象保持干净（内部用的是 model_copy）
    assert original.warnings == []


def test_budget_exhaustion_is_reported_as_budget_not_as_a_provider_error() -> None:
    # 经济模式可能在初始回复后耗尽预算；这不该被伪装成上游故障。
    def exhausted(messages: list[dict[str, str]]) -> ProviderResult:
        raise EvaluationBudgetExceeded("max_requests")

    outcome = retry_for_format_noise(_result(_DIRTY_REPLY), _PROMPT, exhausted)

    assert outcome.reply == _DIRTY_REPLY
    # 与“重试失败”分支的区别值得注意：预算不足时**根本没有发起重试**，
    # 所以只有一条“已跳过”，不会出现“尝试过/失败”的记录。
    assert outcome.warnings == ["response_format_retry_skipped: budget_max_requests"]
    assert not any("provider_error" in warning for warning in outcome.warnings)


# --- 重试成功但结果更差 -----------------------------------------------------


def test_a_worse_retry_is_not_adopted() -> None:
    def still_dirty(messages: list[dict[str, str]]) -> ProviderResult:
        return _result("（还是带动作）嗯。")

    outcome = retry_for_format_noise(_result(_DIRTY_REPLY), _PROMPT, still_dirty)

    assert outcome.reply == _DIRTY_REPLY
    # 只有一条“已重试”的警告，没有失败标记
    assert outcome.warnings == ["response_format_retry: stage_direction"]


def test_a_better_retry_replaces_the_reply() -> None:
    def clean(messages: list[dict[str, str]]) -> ProviderResult:
        return _result("鸡舍那边挺忙的，不过还行。")

    outcome = retry_for_format_noise(_result(_DIRTY_REPLY), _PROMPT, clean)

    assert outcome.reply == "鸡舍那边挺忙的，不过还行。"
    assert outcome.warnings == ["response_format_retry: stage_direction"]


def test_clean_reply_is_returned_untouched_without_calling_generate() -> None:
    def should_not_be_called(messages: list[dict[str, str]]) -> ProviderResult:
        raise AssertionError("干净回复不该触发重试")

    original = _result("鸡舍那边挺忙的，不过还行。")
    outcome = retry_for_format_noise(original, _PROMPT, should_not_be_called)

    assert outcome is original


def test_skip_short_circuits_the_retry() -> None:
    def should_not_be_called(messages: list[dict[str, str]]) -> ProviderResult:
        raise AssertionError("skip=True 时不该重试")

    original = _result(_DIRTY_REPLY)
    outcome = retry_for_format_noise(original, _PROMPT, should_not_be_called, skip=True)

    assert outcome is original
