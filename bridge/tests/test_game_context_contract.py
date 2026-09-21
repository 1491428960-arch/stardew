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


def test_request_accepts_game_client_compact_prompt_flag() -> None:
    request = DialogueTestRequest.model_validate(
        {
            **ROOT_PAYLOAD,
            "compactPrompt": True,
        }
    )

    assert request.compact_prompt is True


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


def test_request_context_accepts_vanilla_story_state_fields() -> None:
    payload = {
        **ROOT_PAYLOAD,
        "gameState": {
            **ROOT_PAYLOAD["gameState"],
            "friendshipHearts": 5,
            "marriageStatus": "married",
            "childrenCount": 2,
            "completedEventIds": ["evt-1", "evt-2"],
        },
    }

    request = DialogueTestRequest.model_validate(payload)
    context = ContextBuilder().build(payload)

    assert request.game_state is not None
    assert request.game_state.friendship_hearts == 5
    assert request.game_state.marriage_status == "married"
    assert request.game_state.children_count == 2
    assert request.game_state.completed_event_ids == ["evt-1", "evt-2"]
    assert context["gameState"]["friendshipHearts"] == 5
    assert context["gameState"]["marriageStatus"] == "married"
    assert context["gameState"]["childrenCount"] == 2
    assert context["gameState"]["completedEventIds"] == ["evt-1", "evt-2"]
    messages = PromptBuilder().build(context, payload["message"])
    rendered = json.dumps(messages, ensure_ascii=False)
    assert "friendshipHearts" in rendered
    assert "marriageStatus" in rendered
    assert "childrenCount" in rendered
    # `completedEventIds` 是门控输入，不进 prompt：它随存档单调增长，整卡渲染只占
    # 预算，模型也无法据此生成对白。但它必须留在 context 里——上面的
    # `context["gameState"]["completedEventIds"]` 断言与
    # `test_relationship_gating.py` 的门控用例共同守住这一点。
    # 这里只检查 `game_state` 卡：别处的 instruction 里会**提到**这个字段名
    # （那是解释规则用的措辞，不是渲染数据）。
    game_state_cards = [
        message for message in messages if message.get("name") == "game_state"
    ]
    assert game_state_cards, "game_state 卡必须仍然存在"
    for card in game_state_cards:
        assert "evt-1" not in card["content"]
        assert "completedEventIds" not in card["content"]


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


def test_dialogue_uses_compact_prompt_when_game_client_requests_it(
    monkeypatch: Any,
) -> None:
    app_module = importlib.import_module("stardew_ai_bridge.app")
    router = RecordingRouter()

    class RecordingPromptBuilder:
        compact: bool | None = None
        runtime_compact: bool | None = None

        def build(
            self,
            context: dict[str, Any],
            player_input: str,
            *,
            compact: bool = False,
        ) -> list[dict[str, str]]:
            del player_input
            self.compact = compact
            self.runtime_compact = context.get("_runtime_compact") is True
            return [{"role": "system", "content": "captured prompt"}]

    prompt_builder = RecordingPromptBuilder()
    monkeypatch.setattr(app_module, "provider_router", router)
    monkeypatch.setattr(app_module, "prompt_builder", prompt_builder)

    response = TestClient(app_module.app).post(
        "/api/dialogue/test",
        json={
            **ROOT_PAYLOAD,
            "provider": "cloud",
            "compactPrompt": True,
        },
    )

    assert response.status_code == 200
    assert prompt_builder.compact is True
    assert prompt_builder.runtime_compact is True


def test_compact_prompt_omits_structured_game_state_message_for_cloud_relay() -> None:
    context = ContextBuilder().build(ROOT_PAYLOAD)
    context["_runtime_compact"] = True

    messages = PromptBuilder().build(
        context,
        ROOT_PAYLOAD["message"],
        compact=True,
    )

    assert all(message.get("name") != "game_state" for message in messages)


def test_regular_compact_prompt_keeps_game_state_for_quality_evaluation() -> None:
    context = ContextBuilder().build(ROOT_PAYLOAD)

    messages = PromptBuilder().build(
        context,
        ROOT_PAYLOAD["message"],
        compact=True,
    )

    assert any(message.get("name") == "game_state" for message in messages)


def test_runtime_compact_prompt_omits_large_interaction_cards_for_cloud_relay() -> None:
    context = ContextBuilder().build(
        {
            **ROOT_PAYLOAD,
            "channel": "remote",
            "compactPrompt": True,
        }
    )
    context["_runtime_compact"] = True

    messages = PromptBuilder().build(
        context,
        ROOT_PAYLOAD["message"],
        compact=True,
    )
    names = {message.get("name") for message in messages}

    assert "interaction" not in names
    assert "conversation_lead" not in names


def test_topic_dialogue_does_not_pass_internal_topic_prompt_as_player_input(
    monkeypatch: Any,
) -> None:
    app_module = importlib.import_module("stardew_ai_bridge.app")
    router = RecordingRouter()
    monkeypatch.setattr(app_module, "provider_router", router)

    response = TestClient(app_module.app).post(
        "/api/dialogue/test",
        json={
            "npcId": "Wizard",
            "intent": "topic",
            "message": "请主动找一个自然的话题。",
            "provider": "cloud",
        },
    )

    assert response.status_code == 200
    assert router.messages is not None
    topic_triggers = [
        message
        for message in router.messages
        if message["name"] == "topic_trigger"
    ]
    assert topic_triggers == [
        {"role": "user", "name": "topic_trigger", "content": ""}
    ]
    assert all(
        "请主动找一个自然的话题。" not in message["content"]
        for message in router.messages
    )


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
