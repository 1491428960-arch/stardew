from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from stardew_ai_bridge.app import app


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
