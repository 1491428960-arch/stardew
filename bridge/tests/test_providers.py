from __future__ import annotations

from stardew_ai_bridge.models import DialogueTestRequest, ProviderResult
from stardew_ai_bridge.providers import FakeProvider, Provider


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
