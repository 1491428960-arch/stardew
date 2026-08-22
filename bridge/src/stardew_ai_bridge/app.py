from __future__ import annotations

from time import perf_counter

from fastapi import FastAPI

from .models import DialogueResponse, DialogueTestRequest, HealthResponse
from .providers import FakeProvider


app = FastAPI(title="Stardew AI NPC Bridge")
fake_provider = FakeProvider()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", provider=fake_provider.name)


@app.post("/api/dialogue/test", response_model=DialogueResponse)
def test_dialogue(request: DialogueTestRequest) -> DialogueResponse:
    started_at = perf_counter()
    result = fake_provider.generate(request)
    latency_ms = max(0, int((perf_counter() - started_at) * 1000))

    return DialogueResponse(
        reply=result.reply,
        provider=result.provider,
        fallback=result.fallback,
        latencyMs=latency_ms,
        warnings=result.warnings,
    )
