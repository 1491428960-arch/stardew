"""`fallback` 与 `evaluation_budget`：两个小而关键、此前没有专门测试的模块。

- **`FallbackProvider`** 是所有上游都不可用时**最后一道兜底**。它返回的结果必须带
  `fallback=True`——上层靠这个标记区分“模型真的回了”与“我们替它回了”。
- **`EvaluationBudget` / `EvaluationBudgetTracker`** 是评测的**成本闸门**。两个精妙设计：
  `can_start_request()` **带副作用**（一旦触碰上限就顺手记下 `stop_reason`，此后永远返回 False，
  也就是熔断是**粘性**的）；`record_usage()` 在**累加之后立刻复查**上限，所以超支能当轮熔断、
  不必等下一轮。另外它和 `providers._non_negative_count` 用了同一手法：**显式排除 `bool`**
  ——`bool` 是 `int` 的子类，不排除的话 `True` 会被当成 1。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.evaluation_budget import (
    EvaluationBudget,
    EvaluationBudgetExceeded,
    EvaluationBudgetTracker,
)
from stardew_ai_bridge.fallback import FallbackProvider
from stardew_ai_bridge.models import DialogueTestRequest, ProviderUsage


def _request(npc_id: str = "Shane") -> DialogueTestRequest:
    return DialogueTestRequest(npcId=npc_id, message="你好")


# --- FallbackProvider -------------------------------------------------------


def test_fallback_marks_its_result_so_callers_can_tell_it_apart() -> None:
    result = FallbackProvider().generate(_request())

    assert result.fallback is True
    assert result.provider == "fallback"
    assert result.latency_ms == 0
    assert result.warnings == []


def test_fallback_reply_defaults_to_a_neutral_apology() -> None:
    assert FallbackProvider().generate(_request()).reply == (
        "（暂时没有合适的回复，请稍后再试。）"
    )


def test_fallback_reply_can_be_overridden() -> None:
    assert FallbackProvider(reply="换一句。").generate(_request()).reply == "换一句。"


def test_fallback_ignores_the_messages_and_the_request_contents() -> None:
    # 兜底不读上下文：无论请求是谁、带不带 messages，结果都一样。
    provider = FallbackProvider()
    first = provider.generate(_request("Shane"), messages=[{"role": "user", "content": "x"}])
    second = provider.generate(_request("Abigail"), messages=None)

    assert first.reply == second.reply
    assert first.provider == second.provider


# --- EvaluationBudget 的校验 ------------------------------------------------


def test_default_budget_limits_nothing_except_player_retries() -> None:
    budget = EvaluationBudget()

    assert budget.max_cases is None
    assert budget.max_requests is None
    assert budget.max_total_tokens is None
    assert budget.max_npc_retries is None
    # 这两项有具体默认值（不是“不限制”）
    assert budget.max_player_retries == 0
    assert budget.compact_prompt is False
    assert budget.dynamic_player_input is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_cases", -1),
        ("max_requests", -1),
        ("max_total_tokens", -1),
        ("max_npc_retries", -1),
        ("max_cases", True),  # bool 必须被拒绝，否则 True 会被当成 1
        ("max_cases", 1.5),
        ("max_cases", "3"),
        ("max_player_retries", -1),
    ],
)
def test_budget_rejects_anything_that_is_not_a_non_negative_int(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError):
        EvaluationBudget(**{field: value})


def test_zero_is_a_valid_limit() -> None:
    # 0 是“一个都不许”，与 None（不限制）是两回事。
    assert EvaluationBudget(max_requests=0).max_requests == 0


def test_economical_budget_is_the_documented_conservative_one() -> None:
    budget = EvaluationBudget.economical()

    assert budget.max_cases == 3
    assert budget.max_requests == 24
    assert budget.max_total_tokens == 100_000
    assert budget.max_npc_retries == 1
    assert budget.max_player_retries == 0
    assert budget.compact_prompt is True


def test_as_dict_uses_camel_case_for_the_wire_format() -> None:
    assert EvaluationBudget.economical().as_dict() == {
        "maxCases": 3,
        "maxRequests": 24,
        "maxTotalTokens": 100_000,
        "maxNpcRetries": 1,
        "maxPlayerRetries": 0,
        "compactPrompt": True,
        "dynamicPlayerInput": True,
    }


# --- EvaluationBudgetTracker -------------------------------------------------


def test_tracker_allows_requests_until_the_request_limit() -> None:
    tracker = EvaluationBudgetTracker(EvaluationBudget(max_requests=2))

    assert tracker.can_start_request() is True
    tracker.reserve_request()
    tracker.reserve_request()

    assert tracker.request_count == 2
    assert tracker.can_start_request() is False
    # 熔断原因是在检查时顺手记下的
    assert tracker.stop_reason == "max_requests"


def test_tracker_stops_on_the_token_limit_too() -> None:
    tracker = EvaluationBudgetTracker(EvaluationBudget(max_total_tokens=10))
    tracker.record_usage(ProviderUsage(totalTokens=12))

    assert tracker.stop_reason == "max_total_tokens"
    assert tracker.can_start_request() is False


def test_stop_reason_is_sticky() -> None:
    tracker = EvaluationBudgetTracker(EvaluationBudget(max_requests=0))

    assert tracker.can_start_request() is False
    assert tracker.stop_reason == "max_requests"
    # 之后无论怎么问都是 False，而且原因不会被别的检查覆盖
    assert tracker.can_start_request() is False
    assert tracker.stop_reason == "max_requests"


def test_reserve_request_raises_with_the_stop_reason() -> None:
    tracker = EvaluationBudgetTracker(EvaluationBudget(max_requests=0))

    with pytest.raises(EvaluationBudgetExceeded) as excinfo:
        tracker.reserve_request()

    assert excinfo.value.reason == "max_requests"
    assert tracker.request_count == 0  # 被拒的请求不计数


def test_record_usage_ignores_none() -> None:
    tracker = EvaluationBudgetTracker(EvaluationBudget())
    tracker.record_usage(None)

    assert tracker.usage_dict() == {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}


def test_record_usage_sums_each_field() -> None:
    tracker = EvaluationBudgetTracker(EvaluationBudget())
    tracker.record_usage(ProviderUsage(inputTokens=10, outputTokens=2, totalTokens=12))
    tracker.record_usage(ProviderUsage(inputTokens=5, outputTokens=1, totalTokens=6))

    assert tracker.usage_dict() == {"inputTokens": 15, "outputTokens": 3, "totalTokens": 18}


def test_record_usage_derives_total_when_it_is_missing() -> None:
    tracker = EvaluationBudgetTracker(EvaluationBudget())
    tracker.record_usage(ProviderUsage(inputTokens=10, outputTokens=5))

    assert tracker.usage_dict() == {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}


def test_record_usage_prefers_an_explicit_total() -> None:
    # 显式给了 total 就不再自行相加（它可能已经含了别的开销）。
    tracker = EvaluationBudgetTracker(EvaluationBudget())
    tracker.record_usage(ProviderUsage(inputTokens=10, outputTokens=5, totalTokens=99))

    assert tracker.usage_dict()["totalTokens"] == 99


def test_usage_dict_uses_camel_case() -> None:
    assert set(EvaluationBudgetTracker(EvaluationBudget()).usage_dict()) == {
        "inputTokens",
        "outputTokens",
        "totalTokens",
    }
