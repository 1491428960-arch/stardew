from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from stardew_ai_bridge.app import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_topic_intent_adds_active_opening_instruction(client: TestClient) -> None:
    preview = client.post(
        "/api/context/preview",
        json={
            "npcId": "Rasmodia",
            "message": "请主动找一个自然的话题。",
            "intent": "topic",
        },
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["interaction"]["intent"] == "topic"
    assert any(item["name"] == "interaction" for item in body["promptSummary"])


def test_item_intent_keeps_item_context_in_preview_and_prompt(
    client: TestClient,
) -> None:
    preview = client.post(
        "/api/context/preview",
        json={
            "npcId": "Abigail",
            "message": "我想给你看看这个。",
            "intent": "item",
            "itemContext": {
                "itemId": "(W)Sword",
                "displayName": "银河之剑",
                "category": "武器",
                "quality": 0,
                "action": "display",
                "giftTaste": -2,
            },
        },
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["interaction"] == {
        "intent": "item",
        "itemContext": {
            "itemId": "(W)Sword",
            "displayName": "银河之剑",
            "category": "武器",
            "quality": 0,
            "action": "display",
            "giftTaste": -2,
        },
    }

    response = client.post(
        "/api/dialogue/test",
        json={
            "npcId": "Abigail",
            "message": "我想给你看看这个。",
            "intent": "item",
            "itemContext": body["interaction"]["itemContext"],
        },
    )
    assert response.status_code == 200
