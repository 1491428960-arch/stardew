from __future__ import annotations

import asyncio
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

    def generate(self, request: DialogueTestRequest) -> ProviderResult:
        """根据一次测试请求生成结构化回复。"""


class FakeProvider(Provider):
    REPLY = "Rasmodia：你好，这是一条固定的 Fake Provider 测试回复。"

    @property
    def name(self) -> str:
        return "fake"

    def generate(self, request: DialogueTestRequest) -> ProviderResult:
        return ProviderResult(
            reply=self.REPLY,
            provider=self.name,
            fallback=False,
            latencyMs=0,
            warnings=[],
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

    def generate(self, request: DialogueTestRequest) -> ProviderResult:
        started_at = perf_counter()
        response = _run_async(self._generate_async(request))
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
            "messages": [
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
    ) -> ProviderResult:
        explicit_provider = provider or self._explicit_request_provider(request)
        if explicit_provider == "fake":
            return self.fake_provider.generate(request)

        warnings: list[str] = []
        started_at = perf_counter()
        for candidate in self._candidates():
            try:
                result = candidate.generate(request)
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
