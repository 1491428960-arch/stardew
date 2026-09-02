"""质量评测的请求与 Token 预算。"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ProviderUsage


class EvaluationBudgetExceeded(RuntimeError):
    """表示本批次不应再发起新的 Provider 请求。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class EvaluationBudget:
    """一次评测批次的显式成本边界。

    ``None`` 表示沿用旧行为，不限制该项。经济模式只作为评测脚本的
    opt-in 配置，不影响游戏运行时的 Provider 路由。
    """

    max_cases: int | None = None
    max_requests: int | None = None
    max_total_tokens: int | None = None
    max_npc_retries: int | None = None
    max_player_retries: int = 0
    compact_prompt: bool = False
    dynamic_player_input: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_cases",
            "max_requests",
            "max_total_tokens",
            "max_npc_retries",
            "max_player_retries",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} 必须是非负整数或 None")

    @classmethod
    def economical(cls) -> "EvaluationBudget":
        """返回适合少量 smoke 的保守预算。"""

        return cls(
            max_cases=3,
            max_requests=24,
            max_total_tokens=100_000,
            max_npc_retries=1,
            max_player_retries=0,
            compact_prompt=True,
            dynamic_player_input=True,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "maxCases": self.max_cases,
            "maxRequests": self.max_requests,
            "maxTotalTokens": self.max_total_tokens,
            "maxNpcRetries": self.max_npc_retries,
            "maxPlayerRetries": self.max_player_retries,
            "compactPrompt": self.compact_prompt,
            "dynamicPlayerInput": self.dynamic_player_input,
        }


@dataclass
class EvaluationBudgetTracker:
    """按实际 Provider 调用累计成本，并在达到边界后停止后续调用。"""

    budget: EvaluationBudget
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    stop_reason: str | None = None

    def can_start_request(self) -> bool:
        if self.stop_reason is not None:
            return False
        if (
            self.budget.max_requests is not None
            and self.request_count >= self.budget.max_requests
        ):
            self.stop_reason = "max_requests"
            return False
        if (
            self.budget.max_total_tokens is not None
            and self.total_tokens >= self.budget.max_total_tokens
        ):
            self.stop_reason = "max_total_tokens"
            return False
        return True

    def reserve_request(self) -> None:
        if not self.can_start_request():
            raise EvaluationBudgetExceeded(self.stop_reason or "budget")
        self.request_count += 1

    def record_usage(self, usage: ProviderUsage | None) -> None:
        if usage is None:
            return
        values = usage.model_dump(by_alias=True, exclude_none=True)
        for key, attribute in (
            ("inputTokens", "input_tokens"),
            ("outputTokens", "output_tokens"),
            ("totalTokens", "total_tokens"),
        ):
            value = values.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                setattr(self, attribute, getattr(self, attribute) + value)
        if "totalTokens" not in values and {
            "inputTokens",
            "outputTokens",
        } <= values.keys():
            self.total_tokens += int(values["inputTokens"]) + int(values["outputTokens"])
        if (
            self.budget.max_total_tokens is not None
            and self.total_tokens >= self.budget.max_total_tokens
        ):
            self.stop_reason = "max_total_tokens"

    def usage_dict(self) -> dict[str, int]:
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "totalTokens": self.total_tokens,
        }
