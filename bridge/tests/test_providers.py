from __future__ import annotations

from dataclasses import dataclass
import json

import httpx
import pytest

from stardew_ai_bridge.config import BridgeSettings, ProviderSettings
from stardew_ai_bridge.models import (
    DialogueTestRequest,
    ItemConversationContext,
    NpcGameState,
    ProviderResult,
)
from stardew_ai_bridge.providers import (
    FakeProvider,
    OllamaNativeProvider,
    OpenAICompatibleProvider,
    Provider,
    ProviderError,
    ProviderRouter,
    _default_provider_messages,
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
    # 演示文案用 `scene.time_of_day_label(..., include_clock=False)` 的短形式。
    # 此前这里是粗粒度的「早上」（<1200 一律叫早上），8:30 被说成"早上"并不准确；
    # 时段细化后 830 落在「上午」。
    assert "上午" in result.reply
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


def test_default_provider_messages_use_hidden_topic_trigger() -> None:
    messages = _default_provider_messages(
        DialogueTestRequest(npcId="Wizard", intent="topic")
    )

    assert messages[-1] == {
        "role": "user",
        "name": "topic_trigger",
        "content": "",
    }


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


def test_router_uses_explicit_cloud_provider_without_calling_local() -> None:
    local = StubProvider("local", error=AssertionError("不应调用本地"))
    cloud = StubProvider("cloud", reply="Terra 云端回复")
    fallback = StubProvider("fallback", error=AssertionError("不应调用兜底"))
    router = ProviderRouter(
        local_provider=local,
        cloud_provider=cloud,
        fallback_provider=fallback,
        cloud_enabled=False,
        cloud_only=True,
    )
    request = DialogueTestRequest(
        npcId="Rasmodia",
        message="你好",
        provider="cloud",
    )

    result = router.generate(request)

    assert result.reply == "Terra 云端回复"
    assert result.provider == "cloud"
    assert result.fallback is False
    assert result.warnings == []


def test_cloud_only_auto_route_uses_only_gemini_candidate() -> None:
    local = StubProvider("local", reply="不应调用 Qwen")
    cloud = StubProvider("cloud", reply="Gemini 回复")
    router = ProviderRouter(
        local_provider=local,
        cloud_provider=cloud,
        cloud_enabled=True,
        cloud_only=True,
    )

    candidates = router._candidates("auto")

    assert candidates == [cloud]


def test_cloud_only_gemini_failure_uses_fallback_without_calling_local() -> None:
    local = StubProvider("local", error=AssertionError("cloud-only 不应调用 Qwen"))
    cloud = StubProvider("cloud", error=RuntimeError("Gemini 429"))
    fallback = StubProvider("fallback", reply="安全兜底")
    router = ProviderRouter(
        local_provider=local,
        cloud_provider=cloud,
        fallback_provider=fallback,
        cloud_enabled=True,
        cloud_only=True,
    )

    result = router.generate(REQUEST)

    assert result.provider == "fallback"
    assert result.reply == "安全兜底"
    assert result.fallback is True
    assert result.warnings == ["cloud provider failed"]


def test_cloud_only_keeps_explicit_local_as_manual_ab_path() -> None:
    local = StubProvider("local", reply="Qwen A/B 回复")
    cloud = StubProvider("cloud", error=AssertionError("显式 local 不应调用 Gemini"))
    router = ProviderRouter(
        local_provider=local,
        cloud_provider=cloud,
        cloud_enabled=True,
        cloud_only=True,
    )

    result = router.generate(REQUEST.model_copy(update={"provider": "local"}))

    assert result.provider == "local"
    assert result.reply == "Qwen A/B 回复"
    assert result.fallback is False


def test_settings_keep_cloud_available_for_explicit_request_when_auto_disabled() -> None:
    settings = BridgeSettings(
        local=ProviderSettings(name="local", enabled=False),
        cloud=ProviderSettings(
            name="cloud",
            url="https://cloud.invalid/v1/chat/completions",
            model="cloud-model",
            api_key="test-key",
            enabled=False,
        ),
        cloud_enabled=False,
    )

    router = ProviderRouter.from_settings(settings)

    assert isinstance(router.cloud_provider, OpenAICompatibleProvider)
    assert router.cloud_provider.settings.enabled is True
    assert router.cloud_enabled is False


def test_configured_cloud_is_default_for_requests_without_provider() -> None:
    settings = BridgeSettings(
        local=ProviderSettings(name="local", enabled=False),
        cloud=ProviderSettings(
            name="cloud",
            url="https://cloud.invalid/v1/chat/completions",
            model="cloud-model",
            api_key="test-key",
            enabled=False,
        ),
        cloud_enabled=False,
    )

    router = ProviderRouter.from_settings(settings)

    assert router.default_provider == "cloud"
    assert router._candidates(router.default_provider) == [router.cloud_provider]
    router.cloud_provider = StubProvider("cloud", reply="默认云端回复")

    result = router.generate(REQUEST)

    assert result.provider == "cloud"
    assert result.reply == "默认云端回复"


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
    monkeypatch.setenv("BRIDGE_LOCAL_API_MODE", "ollama")
    monkeypatch.setenv("BRIDGE_LOCAL_TIMEOUT", "1.5")
    monkeypatch.setenv("BRIDGE_CLOUD_ENABLED", "true")
    monkeypatch.setenv("BRIDGE_CLOUD_ONLY", "true")
    monkeypatch.setenv("BRIDGE_CLOUD_URL", "https://cloud.invalid/v1/chat/completions")
    monkeypatch.setenv("BRIDGE_CLOUD_MODEL", "cloud-model")
    monkeypatch.setenv("BRIDGE_CLOUD_API_KEY", "secret-key")

    settings = BridgeSettings.from_env()

    assert settings.local.url == "http://127.0.0.1:11434/v1/chat/completions"
    assert settings.local.model == "local-model"
    assert settings.local.api_mode == "ollama"
    assert settings.local.timeout == 1.5
    assert settings.cloud_enabled is True
    assert settings.cloud_only is True
    assert settings.cloud.url == "https://cloud.invalid/v1/chat/completions"
    assert settings.cloud.model == "cloud-model"
    assert settings.cloud.api_key == "secret-key"


def test_bridge_settings_read_profile_index_path_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "BRIDGE_PROFILE_INDEX",
        "data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json",
    )

    settings = BridgeSettings.from_env()

    assert settings.profile_index_path == (
        "data/generated/vanilla-sve-rasmodia-profile-index-zh-CN.json"
    )


def test_bridge_settings_allow_time_for_local_model_cold_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BRIDGE_LOCAL_TIMEOUT", raising=False)

    settings = BridgeSettings.from_env()

    assert settings.local.timeout == 45.0


def test_openai_compatible_provider_uses_async_http_without_exposing_api_key() -> None:
    received: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["authorization"] = request.headers.get("authorization")
        received["body"] = request.read()
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                "data: {\"choices\":[{\"delta\":{\"content\":\"本地\"}}]}\n\n"
                "data: {\"choices\":[{\"delta\":{\"content\":\"模型回复\"}}],"
                "\"usage\":{\"prompt_tokens\":3,\"completion_tokens\":2,\"total_tokens\":5}}\n\n"
                "data: [DONE]\n\n"
            ).encode("utf-8"),
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
    assert result.usage is not None
    assert result.usage.total_tokens == 5
    assert "secret-key" not in repr(result)
    assert received["authorization"] == "Bearer secret-key"
    assert b"secret-key" not in received["body"]
    request_payload = json.loads(received["body"])
    assert request_payload["stream"] is True
    # 单轮预算必须容得下她写完「物品 + 反应 + 动作」一整句。
    # 160 是为 DeepSeek 系定的（reasoning 会吃掉预算），而现行云端是不带推理的
    # Kimi-K2.5：中文 160 token 只有约 100 字，物品场景实测一个晚上撞线两次
    # （2026-09-23，finish_reason=length ⇒ 整轮变成「暂时联系不上她」）。
    assert request_payload["max_tokens"] == 240


def test_temperature_is_only_sent_when_configured() -> None:
    """`temperature` 不配就一个字节都不发 —— 既有 A/B 的可比性不能被改变。

    2026-10-01 实测的噪音底噪（同一 prompt 连发 5 次）：默认温度下两两相似度
    中位数 0.222，而 K=1/K=4 那次 198 轮对照的观测值是 **0.203** —— 比纯噪音
    还小，所以那个 null 结果零信息量。结论是采样参数必须可设，
    但默认行为必须与加这个字段之前逐字节一致。
    """
    from stardew_ai_bridge.config import ProviderSettings

    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
                "data: [DONE]\n\n"
            ).encode("utf-8"),
        )

    def payload_for(temperature: float | None) -> dict[str, object]:
        provider = OpenAICompatibleProvider(
            ProviderSettings(
                name="cloud",
                url="https://cloud.invalid/v1/chat/completions",
                model="cloud-model",
                api_key="secret-key",
                timeout=2.0,
                temperature=temperature,
            ),
            transport=httpx.MockTransport(handler),
        )
        provider.generate(REQUEST)
        return seen[-1]

    # 不设 ⇒ 键根本不存在（而不是发了个 null）。
    assert "temperature" not in payload_for(None)
    # 0.0 是 falsy，必须能区分「没发」和「发了 0」。
    assert payload_for(0.0)["temperature"] == 0.0
    assert payload_for(0.7)["temperature"] == 0.7


def test_multi_turn_group_requests_get_a_larger_output_budget() -> None:
    from stardew_ai_bridge import providers as providers_module

    single = DialogueTestRequest(npcId="Rasmodia", message="你好")
    group = DialogueTestRequest(
        npcId="Shane",
        message="我最近总是睡不好。",
        groupStrategy="multi_turn",
        groupParticipantIds=["Shane", "Harvey"],
        groupTurnCount=3,
    )

    assert providers_module._max_tokens_for(single) == 240
    # multi_turn 一次要写 3～4 条对白：只断言 `> 160` 时改成 161 也能通过，
    # 而那样第二条就会被截断——这正是 09-19 之前回合数长期只有 1～3 的根因。
    assert providers_module._max_tokens_for(group) >= 900


def test_openai_compatible_provider_sends_raised_budget_for_group_multi_turn() -> None:
    received: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["body"] = request.read()
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"choices":[{"delta":{"content":"{}"}}]}\n\n'
                "data: [DONE]\n\n"
            ).encode("utf-8"),
        )

    provider = OpenAICompatibleProvider(
        ProviderSettings(
            name="cloud",
            url="https://cloud.invalid/v1/chat/completions",
            model="cloud-model",
            api_key="secret-key",
            timeout=2.0,
        ),
        transport=httpx.MockTransport(handler),
    )

    provider.generate(
        DialogueTestRequest(
            npcId="Shane",
            message="我最近总是睡不好。",
            groupStrategy="multi_turn",
            groupParticipantIds=["Shane", "Harvey"],
            groupTurnCount=3,
        )
    )

    payload = json.loads(received["body"])
    # 与 _max_tokens_for 的口径一致：multi_turn 的预算必须真的够写多条对白。
    assert payload["max_tokens"] >= 900


def test_openai_compatible_provider_rejects_truncated_stream() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"choices":[{"delta":{"content":"半句"}}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
                "data: [DONE]\n\n"
            ).encode("utf-8"),
        )

    provider = OpenAICompatibleProvider(
        ProviderSettings(
            name="cloud",
            url="https://relay.invalid/v1/chat/completions",
            model="gemini-3.7-flash",
            timeout=2.0,
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError, match="finish_reason=length"):
        provider.generate(REQUEST)


def test_truncated_stream_keeps_a_whole_sentence_instead_of_dropping_the_turn() -> None:
    """截断只说明她说得比预算长，不代表这一轮没救。

    2026-09-23 实机：物品场景里她要把「物品 + 反应 + 动作」一口气写完，
    输出正好撞上预算 ⇒ finish_reason=length ⇒ 整轮被丢成「暂时联系不上她」。
    可已经到手的往往是一句完整的话。半句仍然要拒（见上一条测试），
    完整句子没有理由跟着陪葬 —— 那等于把「话说长了一点」升级成「联系不上」。
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"choices":[{"delta":{"content":"这个分你一点，我很喜欢。"}}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
                "data: [DONE]\n\n"
            ).encode("utf-8"),
        )

    provider = OpenAICompatibleProvider(
        ProviderSettings(
            name="cloud",
            url="https://relay.invalid/v1/chat/completions",
            model="moonshotai/Kimi-K2.5",
            timeout=2.0,
        ),
        transport=httpx.MockTransport(handler),
    )

    assert provider.generate(REQUEST).reply == "这个分你一点，我很喜欢。"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("这个分你一点，我很喜欢。", True),
        ("我想画下来！」", True),  # 收尾的成对符号要剥掉再看
        ("这个分你一点，", False),  # 逗号收尾就是半句
        ("……原来真的会发光", False),
        ("", False),
        ("   ", False),
    ],
)
def test_whole_sentence_detection_only_accepts_sentence_endings(
    text: str,
    expected: bool,
) -> None:
    """只有句末标点收尾才算「话说完了」—— 逗号、顿号、半截词都不算。"""

    from stardew_ai_bridge.providers import _ends_like_a_whole_sentence

    assert _ends_like_a_whole_sentence(text) is expected


def test_openai_compatible_provider_rejects_embedded_sse_error_without_leaking_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"error":{"message":"sensitive upstream detail",'
                '"type":"upstream_error","code":"rate_limit"}}\n\n'
            ).encode("utf-8"),
        )

    provider = OpenAICompatibleProvider(
        ProviderSettings(
            name="cloud",
            url="https://relay.invalid/v1/chat/completions",
            model="gemini-3.7-flash",
            timeout=2.0,
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError, match="embedded provider error") as exc_info:
        provider.generate(REQUEST)

    assert "sensitive upstream detail" not in str(exc_info.value)


def test_openai_compatible_provider_parses_valid_open_loop_metadata() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "下次当面继续。"}}],
                "openLoop": {
                    "action": "open",
                    "loopId": "wizard:rune:Spring-14",
                    "topic": "rune_review",
                    "shortSummary": "线上留下了核对符文数据的话题",
                },
            },
        )

    provider = OpenAICompatibleProvider(
        ProviderSettings(
            name="cloud",
            url="https://cloud.invalid/v1/chat/completions",
            model="cloud-model",
            timeout=2.0,
        ),
        transport=httpx.MockTransport(handler),
    )

    result = provider.generate(REQUEST)

    assert result.open_loop is not None
    assert result.open_loop.action == "open"
    assert result.warnings == []


def test_ollama_native_provider_discards_invalid_open_loop_metadata() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "普通回复。"},
                "openLoop": {
                    "action": "open",
                    "loopId": "wizard:rune:Spring-14",
                    "topic": "rune_review",
                    "shortSummary": "核对符文",
                    "location": "WizardTower",
                },
            },
        )

    provider = OllamaNativeProvider(
        ProviderSettings(
            name="local",
            url="http://127.0.0.1:11434/api/chat",
            model="qwen3.5:9b",
            timeout=2.0,
            api_mode="ollama",
        ),
        transport=httpx.MockTransport(handler),
    )

    result = provider.generate(REQUEST)

    assert result.reply == "普通回复。"
    assert result.open_loop is None
    assert any("openLoop" in warning for warning in result.warnings)


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


def test_openai_compatible_provider_normalizes_api_usage_without_secrets() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "带用量的回复"}}],
                "usage": {
                    "prompt_tokens": 37,
                    "completion_tokens": 19,
                    "total_tokens": 56,
                },
            },
        )

    from stardew_ai_bridge.config import ProviderSettings

    provider = OpenAICompatibleProvider(
        ProviderSettings(
            name="cloud",
            url="https://dashscope.invalid/compatible-mode/v1/chat/completions",
            model="qwen-plus-character",
            api_key="test-secret-key",
            timeout=2.0,
        ),
        transport=httpx.MockTransport(handler),
    )

    result = provider.generate(REQUEST)

    assert result.usage is not None
    assert result.usage.input_tokens == 37
    assert result.usage.output_tokens == 19
    assert result.usage.total_tokens == 56
    assert "test-secret-key" not in repr(result)


def test_ollama_native_provider_normalizes_eval_counts() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "本地带用量的回复"},
                "prompt_eval_count": 23,
                "eval_count": 11,
            },
        )

    from stardew_ai_bridge.config import ProviderSettings

    provider = OllamaNativeProvider(
        ProviderSettings(
            name="local",
            url="http://127.0.0.1:11435/api/chat",
            model="qwen3.5:9b",
            timeout=2.0,
            api_mode="ollama",
        ),
        transport=httpx.MockTransport(handler),
    )

    result = provider.generate(REQUEST)

    assert result.usage is not None
    assert result.usage.input_tokens == 23
    assert result.usage.output_tokens == 11
    assert result.usage.total_tokens == 34


def test_ollama_native_provider_disables_thinking_and_streaming() -> None:
    received: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["body"] = request.read()
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "原生 Ollama 回复"}},
        )

    from stardew_ai_bridge.config import ProviderSettings

    provider = OllamaNativeProvider(
        ProviderSettings(
            name="local",
            url="http://127.0.0.1:11434/api/chat",
            model="qwen3.5:4b",
            timeout=2.0,
            api_mode="ollama",
        ),
        transport=httpx.MockTransport(handler),
    )
    messages = [
        {"role": "system", "content": "你正在扮演 Rasmodia"},
        {"role": "user", "content": "你好"},
    ]

    result = provider.generate(REQUEST, messages=messages)

    assert result.reply == "原生 Ollama 回复"
    assert result.provider == "local"
    payload = json.loads(received["body"])  # type: ignore[arg-type]
    assert payload == {
        "model": "qwen3.5:4b",
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"num_predict": 240},
    }


def test_router_builds_ollama_native_provider_from_settings() -> None:
    from stardew_ai_bridge.config import ProviderSettings

    settings = BridgeSettings(
        local=ProviderSettings(
            name="local",
            url="http://127.0.0.1:11434/api/chat",
            model="qwen3.5:4b",
            api_mode="ollama",
        )
    )

    router = ProviderRouter.from_settings(settings)

    assert isinstance(router.local_provider, OllamaNativeProvider)
