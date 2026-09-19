"""`OpenAICompatibleProvider` 的错误路径：网络失败与坏响应。

2026-09-20 用覆盖率定位到 `providers.py` 91%，其中 **L550–560（两类 `except`）** 从未执行：

- `httpx.HTTPError` / `asyncio.TimeoutError` → `ProviderError("… request failed")`
- 空内容 / 坏结构 → `ProviderError("… returned an invalid response")`

它们的意义在于**把各种上游故障统一成 `ProviderError`**，这样路由器只需处理一种异常
就能安全兜底；而**已经包装好的 `ProviderError` 不该被二次包装**（否则错误信息会套娃）。

用的是与 `test_providers.py` 相同的手法：`httpx.MockTransport`。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from stardew_ai_bridge.config import ProviderSettings
from stardew_ai_bridge.models import DialogueTestRequest
from stardew_ai_bridge.providers import OpenAICompatibleProvider, ProviderError

REQUEST = DialogueTestRequest(npcId="Shane", message="你好")

_SETTINGS = ProviderSettings(
    name="local",
    url="https://local.invalid/v1/chat/completions",
    model="local-model",
    api_key="secret-key",
    timeout=2.0,
)


def _sse(*chunks: dict[str, object]) -> bytes:
    body = "".join(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in chunks)
    return (body + "data: [DONE]\n\n").encode("utf-8")


def _delta(content: str) -> dict[str, object]:
    return {"choices": [{"delta": {"content": content}}]}


def _provider(handler) -> OpenAICompatibleProvider:  # type: ignore[no-untyped-def]
    return OpenAICompatibleProvider(_SETTINGS, transport=httpx.MockTransport(handler))


def _ok_response(content: bytes) -> httpx.Response:
    return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"})


# --- 对照组：正常流式 -------------------------------------------------------


def test_a_well_formed_stream_is_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response(_sse(_delta("模型"), _delta("回复")))

    result = _provider(handler).generate(REQUEST)

    assert result.reply == "模型回复"
    assert result.fallback is False


# --- 坏响应 → invalid response ----------------------------------------------


def test_an_empty_stream_is_rejected() -> None:
    # 只有 [DONE]，没有任何 content——不能把空串当回复交给玩家。
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response(_sse())

    with pytest.raises(ProviderError) as excinfo:
        _provider(handler).generate(REQUEST)

    assert "invalid response" in str(excinfo.value)


def test_a_whitespace_only_stream_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response(_sse(_delta("   ")))

    with pytest.raises(ProviderError) as excinfo:
        _provider(handler).generate(REQUEST)

    assert "invalid response" in str(excinfo.value)


def test_a_non_stream_body_is_rejected(tmp_path=None) -> None:
    # 上游没按 SSE 返回（例如回了一个 JSON 错误对象）时也该转成 ProviderError。
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response(b'{"error": "quota exceeded"}')

    with pytest.raises(ProviderError):
        _provider(handler).generate(REQUEST)


# --- 网络故障 → request failed ----------------------------------------------


def test_a_connection_error_becomes_a_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(ProviderError) as excinfo:
        _provider(handler).generate(REQUEST)

    assert "request failed" in str(excinfo.value)
    # 原始异常保留在 __cause__ 里，便于排查
    assert isinstance(excinfo.value.__cause__, httpx.HTTPError)


def test_a_timeout_becomes_a_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise asyncio.TimeoutError()

    with pytest.raises(ProviderError) as excinfo:
        _provider(handler).generate(REQUEST)

    assert "request failed" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, asyncio.TimeoutError)


def test_error_messages_never_leak_the_api_key() -> None:
    # 错误信息会进日志与评测工件，绝不能带上密钥。
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(ProviderError) as excinfo:
        _provider(handler).generate(REQUEST)

    assert "secret-key" not in str(excinfo.value)


# --- 可选字段 ---------------------------------------------------------------


def test_missing_usage_is_tolerated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response(_sse(_delta("回复")))  # 没有 usage 字段

    result = _provider(handler).generate(REQUEST)

    assert result.reply == "回复"
    assert result.usage is None


def test_a_malformed_open_loop_becomes_a_warning_not_a_failure() -> None:
    # openLoop 只是可选元数据：解析不出来时应当降级成警告，而不是整轮失败。
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response(_sse({**_delta("回复"), "openLoop": "不是对象"}))

    result = _provider(handler).generate(REQUEST)

    assert result.reply == "回复"
    assert result.open_loop is None
    assert result.warnings == ["openLoop: invalid metadata"]
