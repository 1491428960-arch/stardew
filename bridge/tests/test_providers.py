from __future__ import annotations

from dataclasses import dataclass
import json

import httpx
import pytest

from stardew_ai_bridge.config import BridgeSettings
from stardew_ai_bridge.models import DialogueTestRequest, ProviderResult
from stardew_ai_bridge.providers import (
    FakeProvider,
    OpenAICompatibleProvider,
    Provider,
    ProviderRouter,
)


REQUEST = DialogueTestRequest(npcId="Rasmodia", message="你好")


@dataclass
class StubProvider(Provider):
    provider_name: str
    reply: str | None = None
    error: Exception | None = None

    @property
    def name(self) -> str:
        return self.provider_name

    def generate(self, request: DialogueTestRequest) -> ProviderResult:
        if self.error is not None:
            raise self.error
        assert self.reply is not None
        return ProviderResult(
            reply=self.reply,
            provider=self.name,
            fallback=False,
            latencyMs=0,
            warnings=[],
        )


def test_fake_provider_is_minimal_provider_implementation() -> None:
    provider = FakeProvider()

    assert isinstance(provider, Provider)
    assert provider.name == "fake"


def test_fake_provider_returns_fixed_rasmodia_result() -> None:
    provider = FakeProvider()
    request = DialogueTestRequest(npcId="Rasmodia", message="你好")

    result = provider.generate(request)

    assert isinstance(result, ProviderResult)
    assert result.reply == FakeProvider.REPLY
    assert "Rasmodia" in result.reply
    assert result.provider == "fake"
    assert result.fallback is False
    assert result.warnings == []


def test_models_serialize_api_field_aliases() -> None:
    request = DialogueTestRequest(
        npcId="Rasmodia",
        displayName="Rasmodia",
        sourceMods=["SVE"],
        recentFacts=["玩家来过法师塔"],
        message="你好",
    )

    assert request.model_dump(by_alias=True)["npcId"] == "Rasmodia"
    assert request.model_dump(by_alias=True)["displayName"] == "Rasmodia"
    assert request.model_dump(by_alias=True)["sourceMods"] == ["SVE"]
    assert request.model_dump(by_alias=True)["recentFacts"] == ["玩家来过法师塔"]


def test_router_returns_local_result_without_calling_cloud_or_fallback() -> None:
    local = StubProvider("local", reply="本地回复")
    cloud = StubProvider("cloud", error=AssertionError("不应调用云端"))
    fallback = StubProvider("fallback", error=AssertionError("不应调用预设回复"))
    router = ProviderRouter(
        local_provider=local,
        cloud_provider=cloud,
        fallback_provider=fallback,
        cloud_enabled=True,
    )

    result = router.generate(REQUEST)

    assert result.reply == "本地回复"
    assert result.provider == "local"
    assert result.fallback is False
    assert result.latency_ms >= 0
    assert result.warnings == []


def test_router_uses_cloud_after_local_timeout() -> None:
    local = StubProvider("local", error=TimeoutError("本地超时"))
    cloud = StubProvider("cloud", reply="云端回复")
    fallback = StubProvider("fallback", error=AssertionError("不应调用预设回复"))
    router = ProviderRouter(
        local_provider=local,
        cloud_provider=cloud,
        fallback_provider=fallback,
        cloud_enabled=True,
    )

    result = router.generate(REQUEST)

    assert result.reply == "云端回复"
    assert result.provider == "cloud"
    assert result.fallback is False
    assert any("local" in warning for warning in result.warnings)


def test_router_uses_fallback_after_local_and_cloud_fail() -> None:
    local = StubProvider("local", error=RuntimeError("本地 503"))
    cloud = StubProvider("cloud", error=RuntimeError("云端 500"))
    fallback = StubProvider("fallback", reply="预设回复")
    router = ProviderRouter(
        local_provider=local,
        cloud_provider=cloud,
        fallback_provider=fallback,
        cloud_enabled=True,
    )

    result = router.generate(REQUEST)

    assert result.reply == "预设回复"
    assert result.provider == "fallback"
    assert result.fallback is True
    assert any("local" in warning for warning in result.warnings)
    assert any("cloud" in warning for warning in result.warnings)


def test_router_uses_explicit_fake_provider_without_network() -> None:
    fake = FakeProvider()
    local = StubProvider("local", error=AssertionError("不应调用本地网络"))
    cloud = StubProvider("cloud", error=AssertionError("不应调用云端网络"))
    router = ProviderRouter(
        local_provider=local,
        cloud_provider=cloud,
        fake_provider=fake,
        cloud_enabled=True,
    )
    request = DialogueTestRequest(
        npcId="Rasmodia",
        message="你好",
        provider="fake",
    )

    result = router.generate(request)

    assert result.provider == "fake"
    assert result.reply == FakeProvider.REPLY
    assert result.fallback is False


@pytest.mark.parametrize("status", [408, 500])
def test_router_contract_includes_warnings_for_provider_failures(status: int) -> None:
    local = StubProvider("local", error=RuntimeError(f"HTTP {status}"))
    cloud = StubProvider("cloud", error=RuntimeError("云端失败"))
    fallback = StubProvider("fallback", reply="预设回复")
    router = ProviderRouter(
        local_provider=local,
        cloud_provider=cloud,
        fallback_provider=fallback,
        cloud_enabled=True,
    )

    result = router.generate(REQUEST)

    assert result.latency_ms >= 0
    assert len(result.warnings) == 2


def test_bridge_settings_read_provider_configuration_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BRIDGE_LOCAL_URL", "http://127.0.0.1:11434/v1/chat/completions")
    monkeypatch.setenv("BRIDGE_LOCAL_MODEL", "local-model")
    monkeypatch.setenv("BRIDGE_LOCAL_TIMEOUT", "1.5")
    monkeypatch.setenv("BRIDGE_CLOUD_ENABLED", "true")
    monkeypatch.setenv("BRIDGE_CLOUD_URL", "https://cloud.invalid/v1/chat/completions")
    monkeypatch.setenv("BRIDGE_CLOUD_MODEL", "cloud-model")
    monkeypatch.setenv("BRIDGE_CLOUD_API_KEY", "secret-key")

    settings = BridgeSettings.from_env()

    assert settings.local.url == "http://127.0.0.1:11434/v1/chat/completions"
    assert settings.local.model == "local-model"
    assert settings.local.timeout == 1.5
    assert settings.cloud_enabled is True
    assert settings.cloud.url == "https://cloud.invalid/v1/chat/completions"
    assert settings.cloud.model == "cloud-model"
    assert settings.cloud.api_key == "secret-key"


def test_openai_compatible_provider_uses_async_http_without_exposing_api_key() -> None:
    received: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["authorization"] = request.headers.get("authorization")
        received["body"] = request.read()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "本地模型回复"}}]},
        )

    from stardew_ai_bridge.config import ProviderSettings

    provider = OpenAICompatibleProvider(
        ProviderSettings(
            name="local",
            url="https://local.invalid/v1/chat/completions",
            model="local-model",
            api_key="secret-key",
            timeout=2.0,
        ),
        transport=httpx.MockTransport(handler),
    )

    result = provider.generate(REQUEST)

    assert result.reply == "本地模型回复"
    assert result.provider == "local"
    assert result.fallback is False
    assert "secret-key" not in repr(result)
    assert received["authorization"] == "Bearer secret-key"
    assert b"secret-key" not in received["body"]


def test_openai_compatible_provider_posts_app_built_messages_unchanged() -> None:
    received: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["body"] = request.read()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "完整上下文回复"}}]},
        )

    from stardew_ai_bridge.config import ProviderSettings

    provider = OpenAICompatibleProvider(
        ProviderSettings(
            name="local",
            url="https://local.invalid/v1/chat/completions",
            model="local-model",
            timeout=2.0,
        ),
        transport=httpx.MockTransport(handler),
    )
    messages = [
        {"role": "system", "name": "game_state", "content": "Summer / 1830"},
        {"role": "user", "name": "player_input", "content": "你好"},
    ]

    result = provider.generate(REQUEST, messages=messages)

    assert result.reply == "完整上下文回复"
    assert json.loads(received["body"])["messages"] == messages  # type: ignore[arg-type]
