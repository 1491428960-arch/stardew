from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from .config import BridgeSettings
from .fallback import FallbackProvider
from .guard import ResponseGuard
from .models import DialogueResponse, DialogueTestRequest, HealthResponse
from .personas import PersonaStore
from .providers import FakeProvider, ProviderRouter
from .prompts import ContextBuilder, PromptBuilder
from .test_page import TEST_PAGE_HTML


app = FastAPI(title="Stardew AI NPC Bridge")
fake_provider = FakeProvider()
settings = BridgeSettings.from_env()
fallback_provider = FallbackProvider(settings.fallback_reply)
provider_router = ProviderRouter.from_settings(
    settings,
    fake_provider=fake_provider,
    fallback_provider=fallback_provider,
)
persona_store = PersonaStore()
context_builder = ContextBuilder(persona_store)
prompt_builder = PromptBuilder()
response_guard = ResponseGuard()
_SAFE_FALLBACK_REPLY = "Rasmodia：暂时没有合适的回复，请稍后再试。"

_DIALOGUE_FIELDS = {
    "npcId",
    "message",
    "provider",
    "displayName",
    "sourceMods",
    "recentFacts",
    "history",
    "gameState",
}


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if provider_router.local_provider is not None:
        provider_name = provider_router.local_provider.name
    else:
        provider_name = fake_provider.name
    return HealthResponse(status="ok", provider=provider_name)


@app.get("/test", response_class=HTMLResponse)
def test_page() -> str:
    return TEST_PAGE_HTML


@app.get("/api/npcs")
def list_npcs() -> dict[str, list[dict[str, object]]]:
    npcs: list[dict[str, object]] = []
    for npc_id in sorted(persona_store._personas, key=str.casefold):
        persona = persona_store.get_persona(npc_id)
        npcs.append(
            {
                "npcId": persona.get("npcId", npc_id),
                "displayName": persona.get("displayName", npc_id),
            }
        )
    return {"npcs": npcs}


def _build_context(payload: Mapping[str, object]) -> tuple[
    dict[str, object], list[dict[str, str]]
]:
    context = context_builder.build(payload)
    player_input = payload.get("message", "")
    prompt = prompt_builder.build(
        context,
        player_input if isinstance(player_input, str) else "",
    )
    return context, prompt


@app.post("/api/context/preview")
def preview_context(payload: dict[str, object]) -> dict[str, object]:
    context, prompt = _build_context(payload)
    identity = context["npcIdentity"]
    return {
        "npcId": identity["npcId"],
        "personaSummary": identity,
        "gameState": context["gameState"],
        "modSources": context["modSources"],
        "recentFacts": context["recentFacts"],
        "history": context["history"],
        "promptSummary": [
            {"role": message["role"], "name": message["name"]}
            for message in prompt
        ],
    }


def _validate_dialogue_request(payload: Mapping[str, object]) -> DialogueTestRequest:
    filtered = {
        key: payload[key]
        for key in _DIALOGUE_FIELDS
        if key in payload
    }
    try:
        return DialogueTestRequest.model_validate(filtered)
    except ValidationError as exc:
        detail = [
            {
                "loc": error["loc"],
                "msg": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        raise HTTPException(status_code=422, detail=detail) from exc


@app.post("/api/dialogue/test", response_model=DialogueResponse)
def test_dialogue(payload: dict[str, object]) -> DialogueResponse:
    request = _validate_dialogue_request(payload)
    _, prompt = _build_context(payload)
    started_at = perf_counter()
    if (
        not provider_router.has_configured_upstream()
        and "provider" not in request.model_fields_set
    ):
        result = fake_provider.generate(request)
    else:
        result = provider_router.generate(request, messages=prompt)

    guarded = response_guard.check(result.reply)
    if not guarded.accepted:
        fallback = fallback_provider.generate(request)
        fallback_guarded = response_guard.check(fallback.reply)
        warnings = [
            *result.warnings,
            f"response_guard: {guarded.reason}",
            *fallback.warnings,
        ]
        if fallback_guarded.accepted:
            result = fallback.model_copy(
                update={
                    "reply": fallback_guarded.text,
                    "fallback": True,
                    "warnings": warnings,
                }
            )
        else:
            result = fallback.model_copy(
                update={
                    "reply": _SAFE_FALLBACK_REPLY,
                    "fallback": True,
                    "warnings": [
                        *warnings,
                        f"fallback_guard: {fallback_guarded.reason}",
                    ],
                }
            )
    elif guarded.text != result.reply:
        result = result.model_copy(update={"reply": guarded.text})

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
