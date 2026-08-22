from __future__ import annotations

from time import perf_counter

from fastapi import FastAPI

from .config import BridgeSettings
from .fallback import FallbackProvider
from .models import DialogueResponse, DialogueTestRequest, HealthResponse
from .providers import FakeProvider, ProviderRouter


app = FastAPI(title="Stardew AI NPC Bridge")
fake_provider = FakeProvider()
settings = BridgeSettings.from_env()
fallback_provider = FallbackProvider(settings.fallback_reply)
provider_router = ProviderRouter.from_settings(
    settings,
    fake_provider=fake_provider,
    fallback_provider=fallback_provider,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if provider_router.local_provider is not None:
        provider_name = provider_router.local_provider.name
    else:
        provider_name = fake_provider.name
    return HealthResponse(status="ok", provider=provider_name)


@app.post("/api/dialogue/test", response_model=DialogueResponse)
def test_dialogue(request: DialogueTestRequest) -> DialogueResponse:
    started_at = perf_counter()
    if (
        not provider_router.has_configured_upstream()
        and "provider" not in request.model_fields_set
    ):
        result = fake_provider.generate(request)
    else:
        result = provider_router.generate(request)
    latency_ms = max(
        result.latency_ms,
        int((perf_counter() - started_at) * 1000),
    )

    return DialogueResponse(
        reply=result.reply,
        provider=result.provider,
        fallback=result.fallback,
        latencyMs=latency_ms,
        warnings=result.warnings,
    )
