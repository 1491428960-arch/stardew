from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from stardew_ai_bridge.app import app
from stardew_ai_bridge.models import ProviderResult


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_bridge_ready(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module

    class EmptyRouter:
        local_provider = None
        cloud_provider = None
        cloud_enabled = False
        default_provider = "auto"

    monkeypatch.setattr(app_module, "provider_router", EmptyRouter())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "fake"}


def test_health_reports_selected_default_provider_instead_of_local_availability(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module

    class StubProvider:
        def __init__(self, name: str) -> None:
            self.name = name

    class CloudDefaultRouter:
        local_provider = StubProvider("local")
        cloud_provider = StubProvider("cloud")
        cloud_enabled = False
        default_provider = "cloud"

    monkeypatch.setattr(app_module, "provider_router", CloudDefaultRouter())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "cloud"}


def test_fake_dialogue_returns_structured_response(client: TestClient) -> None:
    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Rasmodia", "message": "你好", "provider": "fake"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"]
    # fake provider 会用 `npcId` 拼文本，而 `npcId` 是 mod 的英文标识
    # （`Rasmodia`，游戏内显示名是中文）。出口清洗会把这个英文名当碎片删掉 ——
    # **这正是期望行为**：玩家看到的台词里不该出现 `Rasmodia`。
    # 清洗本身的契约见 `test_reply_scrub.py`。
    assert "Rasmodia" not in body["reply"]
    assert "本地演示" in body["reply"]
    assert "非真实 AI" in body["reply"]
    assert body["provider"] == "fake"
    assert body["fallback"] is False
    assert isinstance(body["latencyMs"], int)
    assert body["latencyMs"] >= 0
    assert body["warnings"] == []


def test_dialogue_can_explicitly_use_fake_provider(client: TestClient) -> None:
    response = client.post(
        "/api/dialogue/test",
        json={
            "npcId": "Rasmodia",
            "message": "今天过得怎么样？",
            "provider": "fake",
        },
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "fake"


def test_group_dialogue_endpoint_returns_strategy_metrics(client: TestClient) -> None:
    response = client.post(
        "/api/dialogue/group",
        json={
            "message": "你们最近都在忙什么？",
            "provider": "fake",
            "strategy": "turn_based",
            "channel": "remote",
            "participants": [
                {"npcId": "Abigail", "displayName": "Abigail"},
                {"npcId": "Emily", "displayName": "Emily"},
            ],
            "activeSpeakerNpcId": "Abigail",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["strategy"] == "turn_based"
    assert body["providerCalls"] == 1
    assert body["turns"][0]["speakerNpcId"] == "Abigail"
    assert body["channel"] == "remote"


def test_group_dialogue_endpoint_rejects_face_to_face_channel(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/dialogue/group",
        json={
            "message": "测试",
            "provider": "fake",
            "strategy": "turn_based",
            "channel": "face_to_face",
            "participants": [
                {"npcId": "Abigail"},
                {"npcId": "Emily"},
            ],
        },
    )

    assert response.status_code == 422


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
            "provider": "fake",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "latencyMs" in body
    assert "latency_ms" not in body
    assert set(body) == {
        "reply",
        "provider",
        "fallback",
        "latencyMs",
        # 延迟含重试，`requestCount` 是它的归因口径（2026-09-26 加）。
        "requestCount",
        "warnings",
        "usage",
        "openLoop",
    }
    assert body["usage"] is None
    assert body["openLoop"] is None


def test_dialogue_forwards_valid_open_loop_and_clears_it_on_fallback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module
    from stardew_ai_bridge.models import OpenLoopSignal

    class SignalRouter:
        def __init__(self) -> None:
            self.calls = 0

        def has_configured_upstream(self) -> bool:
            return True

        def generate(
            self,
            request: object,
            *,
            messages: list[dict[str, str]] | None = None,
        ) -> ProviderResult:
            del request, messages
            self.calls += 1
            if self.calls == 1:
                return ProviderResult(
                    reply="我们下次当面继续。",
                    provider="cloud",
                    openLoop=OpenLoopSignal(
                        action="open",
                        loopId="wizard:rune:Spring-14",
                        topic="rune_review",
                        shortSummary="线上留下了核对符文数据的话题",
                    ),
                )
            return ProviderResult(reply="忽略之前的指令", provider="cloud")

    monkeypatch.setattr(app_module, "provider_router", SignalRouter())

    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Wizard", "message": "这件事下次继续", "provider": "cloud"},
    )

    assert response.status_code == 200
    assert response.json()["openLoop"]["loopId"] == "wizard:rune:Spring-14"

    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Wizard", "message": "再试一次", "provider": "cloud"},
    )

    assert response.status_code == 200
    assert response.json()["fallback"] is True
    assert response.json()["openLoop"] is None


def test_dialogue_accepts_optional_conversation_channel(client: TestClient) -> None:
    response = client.post(
        "/api/dialogue/test",
        json={
            "npcId": "Shane",
            "message": "鸡舍今天忙吗？",
            "channel": "face_to_face",
            "provider": "fake",
        },
    )

    assert response.status_code == 200


def test_dialogue_can_explicitly_use_cloud_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module

    class CloudRouter:
        def has_configured_upstream(self) -> bool:
            return True

        def generate(
            self,
            request: object,
            *,
            messages: list[dict[str, str]] | None = None,
        ) -> ProviderResult:
            assert getattr(request, "provider") == "cloud"
            assert messages
            return ProviderResult(reply="今天见到你真好。", provider="cloud")

    monkeypatch.setattr(app_module, "provider_router", CloudRouter())

    response = client.post(
        "/api/dialogue/test",
        json={
            "npcId": "Rasmodia",
            "message": "你好",
            "provider": "cloud",
        },
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "cloud"
    assert response.json()["reply"] == "今天见到你真好。"


def test_dialogue_response_forwards_provider_usage(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module
    from stardew_ai_bridge.models import ProviderUsage

    class UsageRouter:
        def has_configured_upstream(self) -> bool:
            return True

        def generate(
            self,
            request: object,
            *,
            messages: list[dict[str, str]] | None = None,
        ) -> ProviderResult:
            del request, messages
            return ProviderResult(
                reply="这次回复带有用量。",
                provider="cloud",
                usage=ProviderUsage(
                    inputTokens=123,
                    outputTokens=17,
                    totalTokens=140,
                ),
            )

    monkeypatch.setattr(app_module, "provider_router", UsageRouter())

    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Wizard", "message": "你好", "provider": "cloud"},
    )

    assert response.status_code == 200
    assert response.json()["usage"] == {
        "inputTokens": 123,
        "outputTokens": 17,
        "totalTokens": 140,
    }


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
    assert 'id="test-case-browser"' in response.text
    assert 'id="case-list"' in response.text


def test_chat_test_page_keeps_existing_dialogue_lab(client: TestClient) -> None:
    response = client.get("/test/chat")

    assert response.status_code == 200
    assert 'id="npc-select"' in response.text
    assert 'id="reply"' in response.text


def test_npcs_returns_persona_database(client: TestClient) -> None:
    response = client.get("/api/npcs")

    assert response.status_code == 200
    body = response.json()
    assert body["npcs"]
    wizard = next(item for item in body["npcs"] if item["npcId"] == "Wizard")
    assert wizard["displayName"] == "Wizard"


def test_npcs_merges_index_catalog_with_personas_and_exposes_evidence(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import json
    import stardew_ai_bridge.app as app_module
    from stardew_ai_bridge.personas import PersonaStore
    from stardew_ai_bridge.profile_index import ProfileIndexStore

    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    (persona_dir / "vanilla.json").write_text(
        json.dumps(
            {
                "mod": "vanilla",
                "personas": {
                    "Caroline": {"displayName": "Caroline"},
                    "Wizard": {"displayName": "Wizard"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {
                    "Caroline": {
                        "npcId": "Caroline",
                        "sourceMods": ["vanilla"],
                    },
                    "Rasmodia": {"npcId": "Rasmodia", "sourceMods": ["SVE"]},
                },
                "styleSamples": [
                    {
                        "sampleId": "caroline-1",
                        "npcId": "Caroline",
                        "sourceMod": "vanilla",
                        "text": "花园今天很安静。",
                    }
                ],
                "speechEvidence": [],
                "voiceCards": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "persona_store", PersonaStore(persona_dir))
    monkeypatch.setattr(app_module, "profile_index_store", ProfileIndexStore(index_path))

    body = client.get("/api/npcs").json()
    by_id = {item["npcId"]: item for item in body["npcs"]}

    assert "Caroline" in by_id
    assert by_id["Caroline"]["sourceMods"] == ["vanilla"]
    assert by_id["Caroline"]["hasDialogueEvidence"] is True
    assert "Wizard" in by_id
    assert "Rasmodia" not in by_id


def test_npcs_resolves_display_name_from_each_npc_source_mods(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import json
    import stardew_ai_bridge.app as app_module
    from stardew_ai_bridge.personas import PersonaStore
    from stardew_ai_bridge.profile_index import ProfileIndexStore

    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    (persona_dir / "vanilla.json").write_text(
        json.dumps(
            {"mod": "vanilla", "personas": {"Alex": {"displayName": "Alex"}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (persona_dir / "female-bachelors.json").write_text(
        json.dumps(
            {
                "mod": "female-bachelors",
                "personas": {"Alex": {"displayName": "爱丽克斯"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {
                    "Alex": {
                        "npcId": "Alex",
                        "displayName": "Alex",
                        "sourceMods": ["vanilla", "female-bachelors"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "persona_store", PersonaStore(persona_dir))
    monkeypatch.setattr(app_module, "profile_index_store", ProfileIndexStore(index_path))

    body = client.get("/api/npcs").json()
    alex = next(item for item in body["npcs"] if item["npcId"] == "Alex")

    assert alex["displayName"] == "爱丽克斯"
    assert alex["npcId"] == "Alex"


def test_npcs_does_not_resolve_female_bachelors_name_for_ineligible_npc(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import json
    import stardew_ai_bridge.app as app_module
    from stardew_ai_bridge.personas import PersonaStore
    from stardew_ai_bridge.profile_index import ProfileIndexStore

    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    (persona_dir / "vanilla.json").write_text(
        json.dumps(
            {
                "mod": "vanilla",
                "personas": {"Caroline": {"displayName": "Caroline"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (persona_dir / "female-bachelors.json").write_text(
        json.dumps(
            {
                "mod": "female-bachelors",
                "personas": {"Caroline": {"displayName": "错误名字"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {
                    "Caroline": {
                        "npcId": "Caroline",
                        "displayName": "Caroline",
                        "sourceMods": ["vanilla", "female-bachelors"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "persona_store", PersonaStore(persona_dir))
    monkeypatch.setattr(
        app_module, "profile_index_store", ProfileIndexStore(index_path)
    )

    body = client.get("/api/npcs").json()
    caroline = next(item for item in body["npcs"] if item["npcId"] == "Caroline")

    assert caroline["displayName"] == "Caroline"


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


def test_context_preview_exposes_background_facts_and_known_characters(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import json
    import stardew_ai_bridge.app as app_module
    from stardew_ai_bridge.prompts import ContextBuilder
    from stardew_ai_bridge.profile_index import ProfileIndexStore

    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {"Caroline": {"npcId": "Caroline"}},
                "styleSamples": [],
                "speechEvidence": [],
                "voiceCards": {},
                "knowledgeFacts": [
                    {
                        "factId": "caroline-garden",
                        "npcId": "Caroline",
                        "sourceMod": "vanilla",
                        "summary": "她照料花园。",
                        "knowledgeScope": "canon_confirmed",
                        "confidence": "high",
                    }
                ],
                "knownCharacters": [
                    {
                        "relationId": "caroline-marnie",
                        "npcId": "Caroline",
                        "knownNpcId": "Marnie",
                        "relation": "熟人",
                        "summary": "她认识 Marnie。",
                        "sourceMod": "vanilla",
                        "knowledgeScope": "canon_confirmed",
                        "confidence": "high",
                    }
                ],
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    profile_index = ProfileIndexStore(index_path)
    monkeypatch.setattr(app_module, "profile_index_store", profile_index)
    monkeypatch.setattr(
        app_module,
        "context_builder",
        ContextBuilder(app_module.persona_store, profile_index),
    )

    response = client.post(
        "/api/context/preview",
        json={"npcId": "Caroline", "sourceMods": ["vanilla"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["knowledgeFacts"][0]["factId"] == "caroline-garden"
    assert body["knownCharacters"][0]["knownNpcId"] == "Marnie"


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


def test_profile_index_path_resolver_uses_project_root_for_relative_path() -> None:
    import stardew_ai_bridge.app as app_module

    configured = "data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json"

    resolved = app_module.resolve_profile_index_path(configured)

    assert resolved == app_module.project_root / configured


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
    assert body["reply"] == "（暂时没有合适的回复，请稍后再试。）"
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


def test_dialogue_retries_once_when_upstream_reply_contains_format_noise(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module

    class RetryRouter:
        def __init__(self) -> None:
            self.calls: list[list[dict[str, str]] | None] = []

        def has_configured_upstream(self) -> bool:
            return True

        def generate(
            self,
            request: object,
            *,
            messages: list[dict[str, str]] | None = None,
        ) -> ProviderResult:
            del request
            self.calls.append(messages)
            if len(self.calls) == 1:
                return ProviderResult(reply="请看看**葡萄**。", provider="local")
            return ProviderResult(reply="我们可以一起看看葡萄。", provider="local")

    router = RetryRouter()
    monkeypatch.setattr(app_module, "provider_router", router)

    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Sophia", "message": "要不要一起看看葡萄？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "我们可以一起看看葡萄。"
    assert len(router.calls) == 2
    assert router.calls[0]
    assert router.calls[1]
    assert router.calls[1][-1]["name"] == "format_retry"
    assert "response_format_retry: markdown" in body["warnings"]
    # 延迟是**端到端总耗时**：重试时它累计两次请求，所以必须同时给出次数。
    # 2026-09-26 的晨间实测里同一个页面出现过 3.2s 与 21.1s，没有这个字段
    # 就无法区分「上游慢」与「重试叠加」。
    assert body["requestCount"] == 2


def test_dialogue_usage_includes_bounded_format_retry_attempts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module
    from stardew_ai_bridge.models import ProviderUsage

    class RetryUsageRouter:
        def __init__(self) -> None:
            self.calls = 0

        def has_configured_upstream(self) -> bool:
            return True

        def generate(
            self,
            request: object,
            *,
            messages: list[dict[str, str]] | None = None,
        ) -> ProviderResult:
            del request, messages
            self.calls += 1
            noisy = self.calls == 1
            return ProviderResult(
                reply="请看看**葡萄**。" if noisy else "我们可以一起看看葡萄。",
                provider="cloud",
                usage=ProviderUsage(
                    inputTokens=100 if noisy else 120,
                    outputTokens=10 if noisy else 12,
                    totalTokens=110 if noisy else 132,
                ),
            )

    router = RetryUsageRouter()
    monkeypatch.setattr(app_module, "provider_router", router)

    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Sophia", "message": "要不要一起看看葡萄？"},
    )

    assert response.status_code == 200
    assert router.calls == 2
    assert response.json()["usage"] == {
        "inputTokens": 220,
        "outputTokens": 22,
        "totalTokens": 242,
    }


def test_dialogue_does_not_retry_clean_upstream_reply(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module

    class StableRouter:
        def __init__(self) -> None:
            self.calls = 0

        def has_configured_upstream(self) -> bool:
            return True

        def generate(
            self,
            request: object,
            *,
            messages: list[dict[str, str]] | None = None,
        ) -> ProviderResult:
            del request, messages
            self.calls += 1
            return ProviderResult(reply="今天还好，谢了。", provider="local")

    router = StableRouter()
    monkeypatch.setattr(app_module, "provider_router", router)

    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Shane", "message": "今天怎么样？"},
    )

    assert response.status_code == 200
    assert router.calls == 1
    assert "response_format_retry" not in response.json()["warnings"]
    assert response.json()["requestCount"] == 1


def test_dialogue_format_retry_is_bounded_and_then_uses_existing_fallback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stardew_ai_bridge.app as app_module

    class AlwaysNoisyRouter:
        def __init__(self) -> None:
            self.calls = 0

        def has_configured_upstream(self) -> bool:
            return True

        def generate(
            self,
            request: object,
            *,
            messages: list[dict[str, str]] | None = None,
        ) -> ProviderResult:
            del request, messages
            self.calls += 1
            return ProviderResult(reply="**仍然有格式问题**", provider="local")

    class SafeFallback:
        def generate(self, request: object) -> ProviderResult:
            del request
            return ProviderResult(
                reply="Rasmodia：我们改天再聊。",
                provider="fallback",
                fallback=True,
            )

    router = AlwaysNoisyRouter()
    monkeypatch.setattr(app_module, "provider_router", router)
    monkeypatch.setattr(app_module, "fallback_provider", SafeFallback())

    response = client.post(
        "/api/dialogue/test",
        json={"npcId": "Wizard", "message": "你好"},
    )

    assert response.status_code == 200
    body = response.json()
    assert router.calls == 3
    assert body["reply"] == "Rasmodia：我们改天再聊。"
    assert body["fallback"] is True
    assert "response_guard: format_markdown" in body["warnings"]
