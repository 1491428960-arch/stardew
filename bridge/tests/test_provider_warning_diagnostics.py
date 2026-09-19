"""`ProviderRouter._warning` 的可观测性：响应泛化，但日志要能诊断。

## 背景（2026-09-20 正式环境真机验证发现）

SMAPI 日志里出现过一次：

    [StardewAI.Bridge] response provider=cloud; fallback=false; latencyMs=3976; warningCount=2

而同一批请求其余 7 次都在 1 秒内完成。也就是说**路由跳过了 2 个失败的候选后才成功**。
但**查不到是哪两个候选、为什么失败**——因为 `_warning` 里写着 `del error`：

    @staticmethod
    def _warning(provider: Provider, error: Exception) -> str:
        del error
        return f"{provider.name} provider failed"

**响应文案应当保持泛化**（不把上游细节暴露给游戏端），这一点是对的；
但**服务端日志必须留下可诊断信息**。否则一旦上游开始不稳定，我们只能看到
“延迟变高 + warningCount 上升”，却没有任何线索——这正是本条要修的问题。

## 两条约束

1. **响应不变**：仍返回 `<name> provider failed`（已有测试依赖这个形态）。
2. **日志可诊断**：记下候选名、异常类型、异常消息，**且消息里的密钥必须脱敏**
   （`httpx` 的异常消息常带完整 URL，而 URL 里可能有 `?key=...`）。
"""

from __future__ import annotations

import logging

import pytest

from stardew_ai_bridge.providers import ProviderRouter


class _StubProvider:
    """`_warning` 只用到 `provider.name`，所以桩只需要一个 name。"""

    def __init__(self, name: str) -> None:
        self.name = name


# --- 约束 1：响应文案不变 ---------------------------------------------------


def test_the_response_text_stays_generic() -> None:
    warning = ProviderRouter._warning(_StubProvider("cloud"), RuntimeError("boom"))

    assert warning == "cloud provider failed"


def test_the_response_text_does_not_leak_the_exception_message() -> None:
    # 上游细节不进游戏端。
    exc = RuntimeError("https://api.example.com/v1?key=sk-leak-me failed")

    warning = ProviderRouter._warning(_StubProvider("cloud"), exc)

    assert "sk-leak-me" not in warning
    assert "http" not in warning


# --- 约束 2：日志要能诊断 ---------------------------------------------------


def test_the_log_records_the_candidate_name(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        ProviderRouter._warning(_StubProvider("local"), RuntimeError("boom"))

    assert "local" in caplog.text


def test_the_log_records_the_exception_type_and_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        ProviderRouter._warning(_StubProvider("cloud"), ValueError("bad json body"))

    assert "ValueError" in caplog.text
    assert "bad json body" in caplog.text


def test_the_log_records_something_for_every_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # 关键：不能有“静默跳过”的候选。
    with caplog.at_level(logging.WARNING):
        ProviderRouter._warning(_StubProvider("vertex"), Exception())

    assert caplog.records, "候选失败必须留下一条日志"


# --- 脱敏：日志里不能出现密钥 ----------------------------------------------


def test_the_log_redacts_a_query_string_key(caplog: pytest.LogCaptureFixture) -> None:
    exc = RuntimeError("request to https://api.example.com/v1?key=sk-super-secret failed")

    with caplog.at_level(logging.WARNING):
        ProviderRouter._warning(_StubProvider("cloud"), exc)

    assert "sk-super-secret" not in caplog.text
    # 但要有线索说明这里被脱敏了，而不是整条消息被吞掉
    assert "api.example.com" in caplog.text


@pytest.mark.parametrize(
    "secret_url",
    [
        "https://api.example.com/v1?api_key=sk-aaa",
        "https://api.example.com/v1?api-key=sk-bbb",
        "https://api.example.com/v1?token=sk-ccc",
        "https://api.example.com/v1?access_token=sk-ddd",
        "https://api.example.com/v1?password=sk-eee",
        "https://user:sk-fff@api.example.com/v1",
        "Authorization: Bearer sk-ggg",
    ],
)
def test_common_secret_shapes_are_redacted(
    caplog: pytest.LogCaptureFixture, secret_url: str
) -> None:
    with caplog.at_level(logging.WARNING):
        ProviderRouter._warning(_StubProvider("cloud"), RuntimeError(secret_url))

    for shape in ("sk-aaa", "sk-bbb", "sk-ccc", "sk-ddd", "sk-eee", "sk-fff", "sk-ggg"):
        assert shape not in caplog.text, f"{shape} 泄漏进了日志"
