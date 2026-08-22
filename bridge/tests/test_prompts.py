from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from stardew_ai_bridge.personas import PersonaStore, merge_persona
    from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder
except ModuleNotFoundError:
    class _MissingImplementation:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def __getattr__(self, name: str) -> object:
            del name
            pytest.fail("Task 4 人物与提示词模块尚未实现")

    PersonaStore = _MissingImplementation  # type: ignore[misc,assignment]
    ContextBuilder = _MissingImplementation  # type: ignore[misc,assignment]
    PromptBuilder = _MissingImplementation  # type: ignore[misc,assignment]

    def merge_persona(*args: object, **kwargs: object) -> object:
        del args, kwargs
        pytest.fail("Task 4 人物合并模块尚未实现")


PERSONAS_DIR = Path(__file__).parents[2] / "data" / "personas"


def test_persona_store_loads_required_json_datasets() -> None:
    store = PersonaStore(PERSONAS_DIR)

    assert store.get_persona("Wizard")["displayName"] == "Wizard"
    assert {"vanilla.json", "sve.json", "female-bachelors.json", "rasmodia.json"} <= {
        path.name for path in PERSONAS_DIR.glob("*.json")
    }


def test_sve_overlay_requires_sve_source_mod() -> None:
    store = PersonaStore(PERSONAS_DIR)

    vanilla = store.get_persona("Wizard", source_mods=[])
    sve = store.get_persona("Wizard", source_mods=["SVE"])

    assert vanilla["displayName"] == "Wizard"
    assert vanilla["modOverlay"] == {}
    assert sve["displayName"] != vanilla["displayName"]
    assert "SVE" in sve["modOverlay"]


def test_rasmodia_overlay_changes_display_name_pronouns_and_addressing() -> None:
    store = PersonaStore(PERSONAS_DIR)

    rasmodia = store.get_persona(
        "Wizard", source_mods=["Romanceable Rasmodius"]
    )

    assert rasmodia["displayName"] == "Rasmodia"
    assert rasmodia["pronouns"]["subject"] == "she"
    assert rasmodia["addressing"]["player"] == "traveler"


def test_female_bachelors_overlay_supports_female_shane() -> None:
    store = PersonaStore(PERSONAS_DIR)

    shane = store.get_persona("Shane", source_mods=["female-bachelors"])

    assert shane["pronouns"]["subject"] == "she"
    assert shane["addressing"]["player"]


def test_merge_persona_applies_only_matching_source_mod_overlays() -> None:
    base = {
        "npcId": "Wizard",
        "displayName": "Wizard",
        "pronouns": {"subject": "he"},
        "modOverlay": {
            "SVE": {"displayName": "Magnus"},
            "Rasmodia": {"displayName": "Rasmodia"},
        },
    }

    merged = merge_persona(base, source_mods=["SVE"])

    assert merged["displayName"] == "Magnus"
    assert base["displayName"] == "Wizard"


def test_persona_json_does_not_store_complete_story_text() -> None:
    for path in PERSONAS_DIR.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "story" not in json.dumps(payload, ensure_ascii=False).lower()


def test_context_builder_keeps_allowed_state_and_limits_history() -> None:
    builder = ContextBuilder(PersonaStore(PERSONAS_DIR))
    history = [
        {"role": "user", "content": f"第 {index} 轮"}
        for index in range(8)
    ]
    history[0]["unknown"] = "不得进入上下文"

    context = builder.build(
        npc_id="Wizard",
        source_mods=["SVE"],
        date="春 1 日",
        weather="晴",
        location="法师塔",
        friendship=128,
        relationship="朋友",
        recent_facts=["玩家刚刚拜访法师塔"],
        history=history,
        unknown_field="secret-value",
    )

    assert set(context) == {
        "npcIdentity",
        "modSources",
        "gameState",
        "recentFacts",
        "history",
    }
    assert set(context["gameState"]) == {
        "date",
        "weather",
        "location",
        "friendship",
        "relationship",
    }
    assert len(context["history"]) == 6
    assert [item["content"] for item in context["history"]] == [
        f"第 {index} 轮" for index in range(2, 8)
    ]
    assert "unknown" not in context["history"][0]
    assert "unknown_field" not in json.dumps(context, ensure_ascii=False)
    assert all(len(item["content"]) <= 240 for item in context["history"])


def test_prompt_message_order_is_fixed_and_excludes_secrets() -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        npc_id="Wizard",
        source_mods=["SVE"],
        date="春 1 日",
        weather="晴",
        location="法师塔",
        friendship=128,
        relationship="朋友",
        recent_facts=["玩家刚刚拜访法师塔"],
        history=[{"role": "assistant", "content": "欢迎。"}],
        api_key="secret-api-key",
    )

    messages = PromptBuilder().build(context, "你好")

    assert [message["role"] for message in messages] == [
        "system",
        "system",
        "system",
        "system",
        "assistant",
        "user",
    ]
    assert [message["name"] for message in messages] == [
        "safety_rules",
        "persona_core",
        "mod_overlay",
        "game_state",
        "conversation_history",
        "player_input",
    ]
    rendered = json.dumps(messages, ensure_ascii=False)
    assert "secret-api-key" not in rendered
    assert "api_key" not in rendered
    assert messages[-1]["content"] == "你好"


def test_context_and_prompt_redact_sensitive_values_in_allowed_strings() -> None:
    context = ContextBuilder(PersonaStore(PERSONAS_DIR)).build(
        npc_id="Wizard",
        location="WizardTower apiKey=location-key",
        recent_facts=["token: fact-token"],
        history=[
            {
                "role": "assistant",
                "content": "secret: history-secret; authorization: Bearer history-auth",
            }
        ],
    )

    messages = PromptBuilder().build(context, "authorization: Bearer player-key")
    rendered = json.dumps(messages, ensure_ascii=False)
    context_rendered = json.dumps(context, ensure_ascii=False)

    for secret in (
        "location-key",
        "fact-token",
        "history-secret",
        "history-auth",
        "player-key",
    ):
        assert secret not in context_rendered
        assert secret not in rendered
