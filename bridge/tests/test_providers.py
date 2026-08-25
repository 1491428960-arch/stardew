from __future__ import annotations

from dataclasses import dataclass
import json

import httpx
import pytest

from stardew_ai_bridge.config import BridgeSettings
from stardew_ai_bridge.models import (
    DialogueTestRequest,
    ItemConversationContext,
    NpcGameState,
    ProviderResult,
)
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


def test_fake_provider_returns_contextual_local_demo_result() -> None:
    provider = FakeProvider()
    request = DialogueTestRequest(
        npcId="Wizard",
        displayName="Rasmodia",
        message="今天天气怎么样？",
        recentFacts=["玩家昨天来过法师塔"],
        gameState=NpcGameState(
            season="spring",
            weather="rain",
            time=830,
            location="WizardHouse",
            friendshipHearts=4,
        ),
    )

    result = provider.generate(request)
    different = provider.generate(
        DialogueTestRequest(
            npcId="Wizard",
            displayName="Rasmodia",
            message="晚上好",
            gameState=NpcGameState(season="summer", weather="sunny", time=1930),
        )
    )

    assert isinstance(result, ProviderResult)
    assert FakeProvider.DEMO_MARKER in result.reply
    assert "非真实 AI" in result.reply
    assert "Rasmodia" in result.reply
    assert "春" in result.reply
    assert "雨" in result.reply
    assert "早上" in result.reply
    assert result.reply != different.reply
    assert result.provider == "fake"
    assert result.fallback is False
    assert result.warnings == []


def test_fake_provider_never_reflects_untrusted_request_text() -> None:
    sentinel = "PRIVATE_TOKEN_9f26"
    request = DialogueTestRequest(
        npcId=sentinel,
        displayName=sentinel,
        message=f"天气 {sentinel}",
        recentFacts=[sentinel],
        gameState=NpcGameState(
            displayName=sentinel,
            season="spring",
            weather="rain",
            time=830,
        ),
        intent="item",
        itemContext=ItemConversationContext(
            itemId=sentinel,
            displayName=sentinel,
            category=sentinel,
            quality=0,
            action="display",
            giftTaste=0,
        ),
    )

    result = FakeProvider().generate(request)

    assert sentinel not in result.reply
    assert FakeProvider.DEMO_MARKER in result.reply


def test_fake_provider_uses_relationship_stage_and_history_as_safe_context() -> None:
    provider = FakeProvider()
    close_request = DialogueTestRequest(
        npcId="Wizard",
        message="最近怎么样？",
        history=[
            {"role": "user", "content": "昨天农场下雨了"},
            {"role": "assistant", "content": "记得带伞"},
        ],
        gameState=NpcGameState(
            friendshipHearts=8,
            season="summer",
            weather="sunny",
            time=1930,
        ),
    )
    stranger_request = close_request.model_copy(
        update={
            "history": [],
            "game_state": NpcGameState(
                friendshipHearts=0,
                season="summer",
                weather="sunny",
                time=1930,
            ),
        }
    )

    close_reply = provider.generate(close_request).reply
    stranger_reply = provider.generate(stranger_request).reply

    assert "亲近" in close_reply
    assert "聊过 2 条" in close_reply
    assert "亲近" not in stranger_reply
    assert close_reply != stranger_reply


def test_fake_provider_marks_topic_requests_as_proactive_demo_topics() -> None:
    result = FakeProvider().generate(
        DialogueTestRequest(
            npcId="Wizard",
            message="请找个话题",
            intent="topic",
            gameState=NpcGameState(
                friendshipHearts=4,
                season="winter",
                weather="snow",
                time=1930,
            ),
        )
    )

    assert "主动找话题" in result.reply
    assert "冬天" in result.reply
    assert "晚上" in result.reply


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
    assert FakeProvider.DEMO_MARKER in result.reply
    assert "Rasmodia" in result.reply
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
