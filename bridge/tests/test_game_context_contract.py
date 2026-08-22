from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from stardew_ai_bridge.models import DialogueTestRequest, ProviderResult
from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder
from stardew_ai_bridge.personas import PersonaStore


ROOT_PAYLOAD = {
    "npcId": "Wizard",
    "message": "今天过得怎么样？",
    "displayName": "运行时法师",
    "sourceMods": ["legacy-mod"],
    "recentFacts": ["玩家带来了紫色蘑菇"],
    "history": [
        {"role": "user", "content": "上次见面时我问过天气。"},
        {"role": "assistant", "content": "那天的风很温柔。"},
    ],
    "gameState": {
        "npcId": "Wizard",
        "displayName": "运行时法师",
        "sourceMods": ["SVE", "FlashShifter.SVECode"],
        "season": "Summer",
        "date": "14",
        "weather": "rain",
        "time": 1830,
        "location": "WizardTower",
        "friendship": 128,
        "relationship": "friend",
        "gender": "Male",
    },
}


def test_request_accepts_nested_game_state_and_legacy_context_fields() -> None:
    request = DialogueTestRequest.model_validate(ROOT_PAYLOAD)

    assert request.game_state is not None
    assert request.game_state.season == "Summer"
    assert request.game_state.time == 1830
    assert request.game_state.source_mods == ["SVE", "FlashShifter.SVECode"]
    assert request.game_state.display_name == "运行时法师"
    assert request.source_mods == ["legacy-mod"]
    assert request.display_name == "运行时法师"
    assert request.recent_facts == ["玩家带来了紫色蘑菇"]
    assert request.history[0]["content"] == "上次见面时我问过天气。"


def test_context_builder_merges_nested_state_and_legacy_top_level_fields() -> None:
    context = ContextBuilder(
        PersonaStore(Path(__file__).parents[2] / "data" / "personas")
    ).build(ROOT_PAYLOAD)

    assert context["modSources"] == ["legacy-mod"]
    assert context["npcIdentity"]["displayName"] == "运行时法师"
    assert context["gameState"] == {
        "season": "Summer",
        "date": "14",
        "weather": "rain",
        "time": 1830,
        "location": "WizardTower",
        "friendship": 128,
        "relationship": "friend",
    }
    assert context["recentFacts"] == ["玩家带来了紫色蘑菇"]
    assert context["history"] == ROOT_PAYLOAD["history"]


def test_prompt_contains_persona_state_mods_facts_and_history() -> None:
    context = ContextBuilder().build(ROOT_PAYLOAD)
    messages = PromptBuilder().build(context, ROOT_PAYLOAD["message"])
    rendered = json.dumps(messages, ensure_ascii=False)

    for value in (
        "运行时法师",
        "coreTraits",
        "legacy-mod",
        "Summer",
        "1830",
        "玩家带来了紫色蘑菇",
        "上次见面时我问过天气。",
    ):
        assert value in rendered


@dataclass
class RecordingRouter:
    messages: list[dict[str, Any]] | None = None

    def has_configured_upstream(self) -> bool:
        return True

    def generate(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, Any]] | None = None,
    ) -> ProviderResult:
        del request
        self.messages = messages
        return ProviderResult(
            reply="已收到完整上下文",
            provider="recording",
            fallback=False,
            latencyMs=0,
            warnings=[],
        )


def test_dialogue_passes_app_built_messages_to_provider_router(
    monkeypatch: Any,
) -> None:
    app_module = importlib.import_module("stardew_ai_bridge.app")
    router = RecordingRouter()
    monkeypatch.setattr(app_module, "provider_router", router)

    response = TestClient(app_module.app).post("/api/dialogue/test", json=ROOT_PAYLOAD)

    assert response.status_code == 200
    assert router.messages is not None
    rendered = json.dumps(router.messages, ensure_ascii=False)
    assert "Summer" in rendered
    assert "legacy-mod" in rendered
    assert "玩家带来了紫色蘑菇" in rendered
    assert "上次见面时我问过天气。" in rendered


def test_provider_router_forwards_complete_messages_to_provider() -> None:
    from stardew_ai_bridge.providers import ProviderRouter

    class RecordingProvider:
        name = "recording"

        def __init__(self) -> None:
            self.messages: list[dict[str, Any]] | None = None

        def generate(
            self,
            request: DialogueTestRequest,
            *,
            messages: list[dict[str, Any]] | None = None,
        ) -> ProviderResult:
            del request
            self.messages = messages
            return ProviderResult(
                reply="收到",
                provider=self.name,
                fallback=False,
                latencyMs=0,
                warnings=[],
            )

    provider = RecordingProvider()
    router = ProviderRouter(local_provider=provider)
    expected = [{"role": "system", "name": "game_state", "content": "Summer"}]

    result = router.generate(
        DialogueTestRequest(npcId="Wizard", message="你好"),
        messages=expected,
    )

    assert result.reply == "收到"
    assert provider.messages == expected
