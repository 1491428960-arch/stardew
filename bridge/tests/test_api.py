from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from stardew_ai_bridge.app import app
from stardew_ai_bridge.models import ProviderResult


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_bridge_ready(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "fake"}


def test_fake_dialogue_returns_structured_response(client: TestClient) -> None:
    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Rasmodia", "message": "你好", "provider": "fake"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"]
    assert "Rasmodia" in body["reply"]
    assert body["provider"] == "fake"
    assert body["fallback"] is False
    assert isinstance(body["latencyMs"], int)
    assert body["latencyMs"] >= 0
    assert body["warnings"] == []


def test_dialogue_uses_fake_provider_by_default(client: TestClient) -> None:
    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Rasmodia", "message": "今天过得怎么样？"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "fake"


def test_dialogue_response_uses_camel_case_contract_fields(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/dialogue/test",
        json={
            "npcId": "Rasmodia",
            "displayName": "Rasmodia",
            "sourceMods": ["SVE", "Romanceable Rasmodia"],
            "recentFacts": ["玩家刚刚拜访了法师塔"],
            "message": "你好",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "latencyMs" in body
    assert "latency_ms" not in body
    assert set(body) == {"reply", "provider", "fallback", "latencyMs", "warnings"}


def test_dialogue_rejects_blank_message(client: TestClient) -> None:
    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Rasmodia", "message": "   "},
    )

    assert response.status_code == 422


def test_test_page_returns_html(client: TestClient) -> None:
    response = client.get("/test")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="npc-select"' in response.text
    assert 'id="reply"' in response.text


def test_npcs_returns_persona_database(client: TestClient) -> None:
    response = client.get("/api/npcs")

    assert response.status_code == 200
    body = response.json()
    assert body["npcs"]
    wizard = next(item for item in body["npcs"] if item["npcId"] == "Wizard")
    assert wizard["displayName"] == "Wizard"


def test_context_preview_returns_sanitized_identity_and_current_state(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/context/preview",
        json={
            "npcId": "Wizard",
            "sourceMods": ["Romanceable Rasmodius"],
            "date": "春 1 日",
            "weather": "晴天",
            "location": "法师塔",
            "friendship": 128,
            "relationship": "未婚",
            "recentFacts": ["玩家刚刚拜访了法师塔"],
            "apiKey": "secret-api-key",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["npcId"] == "Wizard"
    assert body["personaSummary"]["displayName"] == "Rasmodia"
    assert body["gameState"] == {
        "date": "春 1 日",
        "weather": "晴天",
        "location": "法师塔",
        "friendship": 128,
        "relationship": "未婚",
    }
    assert "apiKey" not in body
    assert "secret-api-key" not in response.text


def test_context_preview_redacts_sensitive_values_in_allowed_context(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/context/preview",
        json={
            "npcId": "Wizard",
            "location": "WizardTower apiKey=location-key token=location-token",
            "recentFacts": ["secret: fact-secret"],
            "history": [
                {
                    "role": "user",
                    "content": "authorization: Bearer history-token",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    rendered = response.text
    assert body["gameState"]["location"] == (
        "WizardTower apiKey: [已省略] token: [已省略]"
    )
    assert body["recentFacts"] == ["secret: [已省略]"]
    assert body["history"] == [
        {"role": "user", "content": "authorization: [已省略]"}
    ]
    for secret in (
        "location-key",
        "location-token",
        "fact-secret",
        "history-token",
    ):
        assert secret not in rendered


def test_context_preview_redacts_nested_sensitive_game_state_values(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/context/preview",
        json={
            "npcId": "Wizard",
            "location": {"name": "WizardTower", "token": "NESTED-SECRET"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["gameState"]["location"]["token"] == "[已省略]"
    assert "NESTED-SECRET" not in response.text


def test_dialogue_uses_builtin_safe_reply_when_fallback_is_guarded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module

    class BlockedRouter:
        def has_configured_upstream(self) -> bool:
            return True

        def generate(self, request: object, *, messages: object = None) -> ProviderResult:
            del request, messages
            return ProviderResult(
                reply="忽略之前的指令",
                provider="upstream",
                warnings=["upstream-warning"],
            )

    class BlockedFallback:
        def generate(self, request: object) -> ProviderResult:
            del request
            return ProviderResult(
                reply="系统提示词泄露",
                provider="fallback",
                fallback=True,
                warnings=["fallback-warning"],
            )

    monkeypatch.setattr(app_module, "provider_router", BlockedRouter())
    monkeypatch.setattr(app_module, "fallback_provider", BlockedFallback())

    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Wizard", "message": "你好"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Rasmodia：暂时没有合适的回复，请稍后再试。"
    assert body["provider"] == "fallback"
    assert body["fallback"] is True
    assert "upstream-warning" in body["warnings"]
    assert "fallback-warning" in body["warnings"]
    assert "response_guard: prompt_leakage" in body["warnings"]
    assert "fallback_guard: prompt_leakage" in body["warnings"]


def test_dialogue_caps_warnings_when_upstream_and_fallback_are_guarded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module

    class BlockedRouter:
        def has_configured_upstream(self) -> bool:
            return True

        def generate(self, request: object, *, messages: object = None) -> ProviderResult:
            del request, messages
            return ProviderResult(
                reply="忽略之前的指令",
                provider="upstream",
                warnings=[f"upstream-warning-{index}" for index in range(20)],
            )

    class BlockedFallback:
        def generate(self, request: object) -> ProviderResult:
            del request
            return ProviderResult(
                reply="系统提示词泄露",
                provider="fallback",
                fallback=True,
                warnings=["fallback-warning"],
            )

    monkeypatch.setattr(app_module, "provider_router", BlockedRouter())
    monkeypatch.setattr(app_module, "fallback_provider", BlockedFallback())

    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Wizard", "message": "你好"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["warnings"]) <= 20
    assert "response_guard: prompt_leakage" in body["warnings"]
    assert "fallback_guard: prompt_leakage" in body["warnings"]
