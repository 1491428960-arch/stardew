from __future__ import annotations

import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Protocol, runtime_checkable

import httpx

from .config import BridgeSettings, ProviderSettings
from .models import DialogueTestRequest, ProviderResult


class ProviderError(RuntimeError):
    """Provider 调用失败，消息不包含请求凭据。"""


@runtime_checkable
class Provider(Protocol):
    @property
    def name(self) -> str:
        """返回 Provider 的稳定标识。"""

    def generate(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        """根据一次测试请求生成结构化回复。"""


class FakeProvider(Provider):
    """不联网的确定性演示 Provider；它不是语言模型。"""

    DEMO_MARKER = "【本地演示·非真实 AI】"

    _NPC_LABELS = {
        "rasmodia": "Rasmodia",
        "wizard": "Rasmodia",
        "stardewai_npc_test": "Rasmodia（测试）",
    }

    _SEASONS = {
        "spring": "春天",
        "summer": "夏天",
        "fall": "秋天",
        "autumn": "秋天",
        "winter": "冬天",
        "春": "春天",
        "夏": "夏天",
        "秋": "秋天",
        "冬": "冬天",
    }
    _WEATHER = {
        "sunny": "晴天",
        "sun": "晴天",
        "rain": "雨天",
        "rainy": "雨天",
        "storm": "雷雨天",
        "wind": "有风的天气",
        "snow": "雪天",
        "festival": "节日天气",
        "晴": "晴天",
        "雨": "雨天",
        "雷": "雷雨天",
        "雪": "雪天",
    }
    _RELATIONSHIP_LABELS = {
        "stranger": "初识",
        "acquaintance": "熟悉",
        "friend": "朋友",
        "close": "亲近",
        "dating": "恋爱",
        "married": "婚后",
        "parent": "育儿",
    }

    @property
    def name(self) -> str:
        return "fake"

    def generate(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        del messages
        return ProviderResult(
            reply=self._build_demo_reply(request),
            provider=self.name,
            fallback=False,
            latencyMs=0,
            warnings=[],
        )

    def _build_demo_reply(self, request: DialogueTestRequest) -> str:
        # Fake mode is reachable without an upstream model, so never reflect
        # request-controlled identity, message, fact, or item text. Only exact
        # known IDs are mapped to fixed labels.
        display_name = self._NPC_LABELS.get(request.npc_id.strip().lower(), "NPC")
        state = request.game_state
        context_parts: list[str] = []
        if state is not None:
            season = self._normalise_context(state.season, self._SEASONS)
            weather = self._normalise_context(state.weather, self._WEATHER)
            if season:
                context_parts.append(season)
            if weather:
                context_parts.append(weather)
            time_label = self._time_label(state.time)
            if time_label:
                context_parts.append(time_label)

        context_text = "、".join(context_parts)
        relationship_stage = self._relationship_stage(state)
        relationship_label = self._RELATIONSHIP_LABELS[relationship_stage]
        history_count = self._history_count(request.history)
        history_text = (
            f"我们已经聊过 {history_count} 条消息"
            if history_count
            else "这是本次对话的开场"
        )
        if request.intent == "topic":
            body = (
                f"我来主动找话题：现在是{context_text or '今天'}，"
                f"我们处在{relationship_label}阶段。"
                "你最近有什么想聊的日常吗？"
            )
        elif request.intent == "item" and request.item_context is not None:
            action = {
                "display": "拿出来给我看",
                "share": "和我分享",
                "gift": "准备送给我",
            }[request.item_context.action]
            body = (
                f"我们处在{relationship_label}阶段，我看到你把这件物品{action}了。"
                "这个版本只按物品字段选择预设话术。"
            )
        elif "天气" in request.message or "下雨" in request.message:
            body = (
                f"{context_text or '当前天气'}确实会改变一天的安排。"
                f"我们处在{relationship_label}阶段，"
                "这句回复来自游戏时间与天气字段。"
            )
        elif any(word in request.message for word in ("关系", "好感", "心")):
            hearts = state.friendship_hearts if state is not None else None
            body = (
                f"当前关系记录是 {hearts} 颗心，阶段是{relationship_label}。"
                if hearts is not None
                else f"当前请求里没有可用的关系心级，暂按{relationship_label}阶段演示。"
            )
        elif request.recent_facts:
            body = (
                f"我们处在{relationship_label}阶段，收到了最近 "
                f"{len(request.recent_facts)} 条事实记录，"
                "但演示模式不会自行补写剧情。"
            )
        else:
            prefix = f"现在是{context_text}。" if context_text else ""
            body = (
                f"{prefix}我们处在{relationship_label}阶段，{history_text}。"
                "我收到了你的话，"
                "这里只会按少量游戏字段选择预设回复。"
            )

        return f"{self.DEMO_MARKER}{display_name}：{body}"

    @staticmethod
    def _normalise_context(
        value: str | None,
        mapping: dict[str, str],
    ) -> str | None:
        if not value:
            return None
        normalized = value.strip().lower()
        if normalized in mapping:
            return mapping[normalized]
        for marker, label in mapping.items():
            if marker in normalized:
                return label
        return None

    @staticmethod
    def _time_label(time_value: int | None) -> str | None:
        if time_value is None:
            return None
        if time_value < 1200:
            return "早上"
        if time_value < 1800:
            return "下午"
        return "晚上"

    @classmethod
    def _relationship_stage(cls, state: NpcGameState | None) -> str:
        if state is None:
            return "stranger"
        if state.children_count is not None and state.children_count > 0:
            return "parent"
        marriage = (state.marriage_status or "").strip().casefold()
        if marriage in {"married", "spouse", "partner", "roommate"}:
            return "married"
        relationship = (state.relationship or "").strip().casefold()
        if relationship in {
            "dating",
            "engaged",
            "fiance",
            "fiancé",
            "girlfriend",
            "boyfriend",
        }:
            return "dating"
        hearts = state.friendship_hearts or 0
        if hearts >= 8:
            return "close"
        if hearts >= 6:
            return "friend"
        if hearts >= 3:
            return "acquaintance"
        return "stranger"

    @staticmethod
    def _history_count(history: list[dict[str, object]]) -> int:
        return sum(
            1
            for item in history
            if isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
            and bool(item["content"].strip())
        )


class OpenAICompatibleProvider:
    """调用 OpenAI-compatible chat completions 接口的同步 Provider。"""

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    @property
    def name(self) -> str:
        return self.settings.name

    def generate(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        started_at = perf_counter()
        response = _run_async(self._generate_async(request, messages=messages))
        return response.model_copy(
            update={
                "latency_ms": max(
                    response.latency_ms,
                    int((perf_counter() - started_at) * 1000),
                )
            }
        )

    async def _generate_async(
        self,
        request: DialogueTestRequest,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        if not self.settings.enabled or not self.settings.url:
            raise ProviderError(f"{self.name} provider is disabled")
        if not self.settings.model:
            raise ProviderError(f"{self.name} provider model is not configured")

        headers: dict[str, str] = {"content-type": "application/json"}
        if self.settings.api_key:
            headers["authorization"] = f"Bearer {self.settings.api_key}"
        payload = {
            "model": self.settings.model,
            "messages": messages or [
                {
                    "role": "system",
                    "content": (
                        f"你正在扮演 {request.display_name or request.npc_id}。"
                        "请用简洁、自然的中文回复。"
                    ),
                },
                {"role": "user", "content": request.message},
            ],
        }
        started_at = perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    self.settings.url,
                    headers=headers,
                    json=payload,
                )
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            raise ProviderError(f"{self.name} request failed") from exc

        if response.is_error:
            raise ProviderError(f"{self.name} returned HTTP {response.status_code}")

        try:
            body = response.json()
            reply = body["choices"][0]["message"]["content"]
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("empty content")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(f"{self.name} returned an invalid response") from exc

        return ProviderResult(
            reply=reply.strip(),
            provider=self.name,
            fallback=False,
            latencyMs=int((perf_counter() - started_at) * 1000),
            warnings=[],
        )


def _run_async(coroutine):  # type: ignore[no-untyped-def]
    """在同步接口中运行协程；若调用方已有事件循环则隔离到线程。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


class ProviderRouter:
    """本地优先、云端降级、预设回复兜底的 Provider 路由器。"""

    def __init__(
        self,
        local_provider: Provider | None = None,
        cloud_provider: Provider | None = None,
        fallback_provider: Provider | None = None,
        *,
        fake_provider: Provider | None = None,
        cloud_enabled: bool = False,
    ) -> None:
        if fallback_provider is None:
            from .fallback import FallbackProvider

            fallback_provider = FallbackProvider()
        self.local_provider = local_provider
        self.cloud_provider = cloud_provider
        self.fallback_provider = fallback_provider
        self.fake_provider = fake_provider or FakeProvider()
        self.cloud_enabled = cloud_enabled

    @classmethod
    def from_settings(
        cls,
        settings: BridgeSettings,
        *,
        fake_provider: Provider | None = None,
        fallback_provider: Provider | None = None,
    ) -> "ProviderRouter":
        local = (
            OpenAICompatibleProvider(settings.local)
            if settings.local.enabled and settings.local.url
            else None
        )
        cloud = (
            OpenAICompatibleProvider(settings.cloud)
            if settings.cloud.enabled and settings.cloud.url
            else None
        )
        if fallback_provider is None:
            from .fallback import FallbackProvider

            fallback_provider = FallbackProvider(settings.fallback_reply)
        return cls(
            local_provider=local,
            cloud_provider=cloud,
            fallback_provider=fallback_provider,
            fake_provider=fake_provider,
            cloud_enabled=settings.cloud_enabled,
        )

    @classmethod
    def from_env(
        cls,
        *,
        fake_provider: Provider | None = None,
        fallback_provider: Provider | None = None,
    ) -> "ProviderRouter":
        return cls.from_settings(
            BridgeSettings.from_env(),
            fake_provider=fake_provider,
            fallback_provider=fallback_provider,
        )

    def has_configured_upstream(self) -> bool:
        return self.local_provider is not None or (
            self.cloud_enabled and self.cloud_provider is not None
        )

    def generate(
        self,
        request: DialogueTestRequest,
        provider: str | None = None,
        *,
        messages: list[dict[str, str]] | None = None,
    ) -> ProviderResult:
        explicit_provider = provider or self._explicit_request_provider(request)
        if explicit_provider == "fake":
            return self.fake_provider.generate(request)

        warnings: list[str] = []
        started_at = perf_counter()
        for candidate in self._candidates():
            try:
                result = self._generate_candidate(candidate, request, messages)
            except Exception as exc:  # noqa: BLE001 - 路由必须隔离单个上游故障
                warnings.append(self._warning(candidate, exc))
                continue
            return self._with_metadata(
                result,
                warnings=warnings,
                elapsed_ms=int((perf_counter() - started_at) * 1000),
            )

        result = self.fallback_provider.generate(request)
        return self._with_metadata(
            result,
            fallback=True,
            warnings=warnings,
            elapsed_ms=int((perf_counter() - started_at) * 1000),
        )

    @staticmethod
    def _generate_candidate(
        candidate: Provider,
        request: DialogueTestRequest,
        messages: list[dict[str, str]] | None,
    ) -> ProviderResult:
        if messages is None:
            return candidate.generate(request)

        parameters = inspect.signature(candidate.generate).parameters
        accepts_messages = "messages" in parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        if accepts_messages:
            return candidate.generate(request, messages=messages)
        return candidate.generate(request)

    def _candidates(self) -> list[Provider]:
        candidates: list[Provider] = []
        if self.local_provider is not None:
            candidates.append(self.local_provider)
        if self.cloud_enabled and self.cloud_provider is not None:
            candidates.append(self.cloud_provider)
        return candidates

    @staticmethod
    def _explicit_request_provider(request: DialogueTestRequest) -> str | None:
        fields_set = getattr(request, "model_fields_set", set())
        return request.provider if "provider" in fields_set else None

    @staticmethod
    def _warning(provider: Provider, error: Exception) -> str:
        del error
        return f"{provider.name} provider failed"

    @staticmethod
    def _with_metadata(
        result: ProviderResult,
        *,
        warnings: list[str],
        elapsed_ms: int,
        fallback: bool | None = None,
    ) -> ProviderResult:
        return result.model_copy(
            update={
                "fallback": result.fallback if fallback is None else fallback,
                "latency_ms": max(result.latency_ms, elapsed_ms),
                "warnings": [*warnings, *result.warnings],
            }
        )
