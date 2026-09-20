from __future__ import annotations

from collections.abc import Iterable, Mapping
import os
from pathlib import Path
import tempfile
from time import perf_counter

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from .config import DEFAULT_FALLBACK_REPLY, BridgeSettings, load_local_env
from .character_quality_eval import quality_case_catalog
from .fallback import FallbackProvider
from .guard import ResponseGuard, retry_for_format_noise
from .models import (
    DialogueResponse,
    DialogueTestRequest,
    HealthResponse,
    ProviderResult,
    ProviderUsage,
)
from .personas import (
    PersonaStore,
    canonical_npc_id,
    is_female_bachelor_eligible,
)
from .profile_index import ProfileIndexStore
from .providers import FakeProvider, ProviderRouter
from .prompts import ContextBuilder, PromptBuilder, build_group_voice_cards
from .quality_results import SAFE_SUITE_IDS, load_latest_quality_run
from .dialogue_lab_page import (
    integrated_dialogue_lab_page,
)
from .dialogue_lab_session import DialogueLabSessionStore, normalize_session
from .group_conversation import GroupConversationService
from .group_dialogue_lab_page import group_dialogue_lab_page
from .group_dialogue_review_page import group_dialogue_review_page
from .ui_preview_page import ui_preview_page
from .ui_preview_redesign_page import ui_preview_redesign_page
from .models import GroupDialogueRequest, GroupDialogueResponse


app = FastAPI(title="Stardew AI NPC Bridge")
fake_provider = FakeProvider()
load_local_env()
settings = BridgeSettings.from_env()
fallback_provider = FallbackProvider(settings.fallback_reply)
provider_router = ProviderRouter.from_settings(
    settings,
    fake_provider=fake_provider,
    fallback_provider=fallback_provider,
)
persona_store = PersonaStore()
project_root = Path(__file__).resolve().parents[3]


def resolve_profile_index_path(configured_path: str | None) -> Path:
    """解析索引配置；相对路径固定相对于项目根目录，避免依赖启动 cwd。"""
    if configured_path and configured_path.strip():
        configured = Path(configured_path.strip()).expanduser()
        if not configured.is_absolute():
            configured = project_root / configured
        return configured
    return project_root / "data" / "generated" / "profile-index.json"


def resolve_dialogue_session_path(configured_path: str | None) -> Path:
    """解析本地会话路径；默认使用本机临时数据目录，避开仓库只读目录。"""
    if configured_path and configured_path.strip():
        return Path(configured_path.strip()).expanduser()
    return Path(tempfile.gettempdir()) / "StardewAI.NPC" / "dialogue-lab-session.json"


profile_index_path = resolve_profile_index_path(settings.profile_index_path)
quality_artifact_root = project_root / "artifacts" / "character-quality-eval"
profile_index_store = ProfileIndexStore(profile_index_path)
context_builder = ContextBuilder(persona_store, profile_index_store)
prompt_builder = PromptBuilder()
response_guard = ResponseGuard()
def _group_voice_cards(participants: list[object]) -> dict[str, dict[str, object]]:
    """把群聊参与者映射成声线卡请求，复用单 NPC 的 persona / 索引管线。"""

    return build_group_voice_cards(
        context_builder,
        [
            {
                "npcId": getattr(item, "npc_id", ""),
                "displayName": getattr(item, "display_name", ""),
                "sourceMods": list(getattr(item, "source_mods", ()) or ()),
            }
            for item in participants
        ],
    )


def _group_participant_prompts(
    participants: list[object],
    request: object,
) -> dict[str, list[dict[str, str]]]:
    """为每个参与者生成与私聊同源的角色卡（走同一个 PromptBuilder）。"""

    prompts: dict[str, list[dict[str, str]]] = {}
    for item in participants:
        npc_id = getattr(item, "npc_id", "")
        if not npc_id:
            continue
        payload: dict[str, object] = {
            "npcId": npc_id,
            "message": getattr(request, "message", ""),
            "sourceMods": list(getattr(item, "source_mods", ()) or ()),
            "channel": getattr(request, "channel", "remote"),
        }
        game_state = getattr(item, "game_state", None) or getattr(
            request, "game_state", None
        )
        if game_state is not None:
            payload["gameState"] = game_state.model_dump(
                by_alias=True, exclude_none=True
            )
        _, messages = _build_context(payload)
        prompts[npc_id] = messages
    return prompts


group_conversation_service = GroupConversationService(
    provider_router,
    voice_card_provider=_group_voice_cards,
    prompt_provider=_group_participant_prompts,
)
dialogue_lab_session_store = DialogueLabSessionStore(
    resolve_dialogue_session_path(os.environ.get("BRIDGE_DIALOGUE_SESSION_PATH"))
)
# 安全兜底文案只有 config 一个来源（2026-09-20 语义层审计 P3 第 47 条）；
# 这个别名保留是为了不动既有调用点与测试。
_SAFE_FALLBACK_REPLY = DEFAULT_FALLBACK_REPLY
_WARNING_LIMIT = 20
_DIALOGUE_FIELDS = {
    "npcId",
    "message",
    "provider",
    "displayName",
    "sourceMods",
    "recentFacts",
    "history",
    "gameState",
    "intent",
    "compactPrompt",
    "channel",
    "itemContext",
    "relationshipWorld",
}


def _limit_warnings(warnings: Iterable[str]) -> list[str]:
    values = list(warnings)
    guard_indices = [
        index
        for index, warning in enumerate(values)
        if warning.startswith(("response_guard:", "fallback_guard:"))
    ]
    selected = set(guard_indices[-_WARNING_LIMIT:])
    for index in range(len(values) - 1, -1, -1):
        if len(selected) >= _WARNING_LIMIT:
            break
        selected.add(index)
    return [values[index] for index in sorted(selected)]


def _merge_provider_usages(
    usages: Iterable[ProviderUsage | None],
) -> ProviderUsage | None:
    """合计同一轮内所有真实上游请求的用量。

    保守口径：只要有一个 chunk 没报某个字段，该字段就留空。
    2026-09-20（语义层审计）统一——此前私聊逐字段累加、群聊保守，
    同一上游两条路径给出不同结果。token 用量用于成本统计，
    「缺失」比「偏小」安全，调用方能从 None 看出数据不全。
    """

    present = [usage for usage in usages if usage is not None]
    if not present:
        return None

    def total(field_name: str) -> int | None:
        values = [getattr(usage, field_name) for usage in present]
        return sum(values) if all(value is not None for value in values) else None

    return ProviderUsage(
        input_tokens=total("input_tokens"),
        output_tokens=total("output_tokens"),
        total_tokens=total("total_tokens"),
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    default_provider = getattr(provider_router, "default_provider", "auto")
    selected_provider = getattr(provider_router, f"{default_provider}_provider", None)
    if selected_provider is not None:
        provider_name = selected_provider.name
    elif default_provider == "auto" and provider_router.local_provider is not None:
        provider_name = provider_router.local_provider.name
    elif (
        default_provider == "auto"
        and provider_router.cloud_enabled
        and provider_router.cloud_provider is not None
    ):
        provider_name = provider_router.cloud_provider.name
    else:
        provider_name = fake_provider.name
    return HealthResponse(status="ok", provider=provider_name)


@app.get("/test", response_class=HTMLResponse)
def test_page() -> str:
    return integrated_dialogue_lab_page("cases")


@app.get("/test/chat", response_class=HTMLResponse)
def chat_test_page() -> str:
    return integrated_dialogue_lab_page("chat")


@app.get("/raw", response_class=HTMLResponse)
def raw_dialogue_reference_page() -> str:
    return integrated_dialogue_lab_page("raw")


@app.get("/api/npcs")
def list_npcs() -> dict[str, list[dict[str, object]]]:
    merged: dict[str, dict[str, object]] = {}

    def ensure(npc_id: object) -> dict[str, object] | None:
        canonical_id = canonical_npc_id(npc_id)
        if not canonical_id.strip():
            return None
        key = canonical_id.casefold()
        return merged.setdefault(
            key,
            {
                "npcId": canonical_id,
                "displayName": canonical_id,
                "sourceMods": [],
                "hasDialogueEvidence": False,
            },
        )

    for item in profile_index_store.npc_catalog():
        entry = ensure(item.get("npcId"))
        if entry is None:
            continue
        for field in ("displayName", "hasDialogueEvidence"):
            if field in item and item[field] not in (None, ""):
                entry[field] = item[field]
        source_mods = entry["sourceMods"]
        if isinstance(source_mods, list):
            for source_mod in item.get("sourceMods", []):
                if source_mod not in source_mods:
                    source_mods.append(source_mod)

    for npc_id in sorted(persona_store._personas, key=str.casefold):
        persona = persona_store.get_persona(npc_id)
        entry = ensure(persona.get("npcId", npc_id))
        if entry is None:
            continue
        display_name = persona.get("displayName")
        if isinstance(display_name, str) and display_name.strip():
            entry["displayName"] = display_name.strip()
        overlays = persona.get("modOverlay", {})
        if isinstance(overlays, Mapping) and isinstance(entry["sourceMods"], list):
            for source_mod in overlays:
                if source_mod not in entry["sourceMods"]:
                    entry["sourceMods"].append(source_mod)

    for entry in merged.values():
        npc_id = entry.get("npcId")
        source_mods = entry.get("sourceMods", [])
        if not isinstance(npc_id, str) or not isinstance(source_mods, list):
            continue
        if not any(
            isinstance(source_mod, str)
            and source_mod.strip().casefold() == "female-bachelors"
            for source_mod in source_mods
        ):
            continue
        if not is_female_bachelor_eligible(npc_id):
            continue
        resolved_persona = persona_store.get_persona(npc_id, ["female-bachelors"])
        display_name = resolved_persona.get("displayName")
        if isinstance(display_name, str) and display_name.strip():
            entry["displayName"] = display_name.strip()

    npcs = sorted(
        merged.values(),
        key=lambda item: (
            str(item.get("displayName", "")).casefold(),
            str(item.get("npcId", "")).casefold(),
        ),
    )
    return {"npcs": npcs}


@app.get("/api/quality/cases")
def list_quality_cases(suite: str = "default") -> dict[str, object]:
    normalized_suite = suite.strip().casefold()
    try:
        cases = quality_case_catalog(normalized_suite)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    source_by_suite = {
        "default": "character_quality_eval.DEFAULT_CASES",
        "conversation-lead": "character_quality_eval.CONVERSATION_LEAD_CASES",
        "topic-start-intimacy": "topic_start_intimacy_cases.TOPIC_START_INTIMACY_CASES",
        "topic-start-adaptive": "topic_start_adaptive_cases.TOPIC_START_ADAPTIVE_CASES",
        "affection-pacing": "affection_pacing_cases.AFFECTION_PACING_SUITE",
        "relationship-world": "relationship_world_cases.RELATIONSHIP_WORLD_SUITE",
        "deep-flirt": "deep_flirt_cases.DEEP_FLIRT_SUITE",
        "deep-flirt-intimate": (
            "deep_flirt_intimate_cases.DEEP_FLIRT_INTIMATE_SUITE"
        ),
        "topic-start-event-impact": "event_impact_cases.EVENT_IMPACT_CASES",
        "relationship-stage-gating": (
            "relationship_gating_cases.RELATIONSHIP_GATING_CASES"
        ),
    }
    return {
        "schemaVersion": 1,
        "suite": normalized_suite,
        "source": source_by_suite[normalized_suite],
        "cases": cases,
    }


@app.get("/api/quality/results")
def list_quality_results(suite: str | None = None) -> dict[str, object]:
    """给案例浏览器读取最新脱敏评测结果，不暴露原始请求内容。"""

    normalized_suite = suite.strip().casefold() if suite else None
    if normalized_suite and normalized_suite not in SAFE_SUITE_IDS:
        raise HTTPException(status_code=400, detail="未知质量评测套件")
    return {
        "source": "artifacts/character-quality-eval",
        **load_latest_quality_run(quality_artifact_root, normalized_suite),
    }


@app.get("/api/dialogue/session")
def get_dialogue_session() -> dict[str, object]:
    return dialogue_lab_session_store.load()


@app.put("/api/dialogue/session")
def save_dialogue_session(payload: dict[str, object]) -> dict[str, object]:
    safe_session = normalize_session(payload)
    stored = dialogue_lab_session_store.save(safe_session)
    return stored if isinstance(stored, dict) else safe_session


@app.delete("/api/dialogue/session")
def clear_dialogue_session() -> dict[str, str]:
    dialogue_lab_session_store.clear()
    return {"status": "cleared"}


@app.get("/api/dialogue/raw")
def get_raw_dialogue(npcId: str = "") -> dict[str, object]:
    """给网页人工复核使用的只读原文参照，不进入模型请求。"""

    return profile_index_store.dialogue_reference(npcId)


def _build_context(
    payload: Mapping[str, object],
    *,
    compact_prompt: bool | None = None,
) -> tuple[
    dict[str, object], list[dict[str, str]]
]:
    context_payload = dict(payload)
    is_topic_request = (
        isinstance(payload.get("intent"), str)
        and payload["intent"].strip().casefold() == "topic"
    )
    if is_topic_request:
        # topic 是 NPC 主动开口；清掉旧客户端可能传来的内部提示，
        # 防止它进入资料检索、上下文摘要或最终 Prompt。
        context_payload["message"] = ""
    context = context_builder.build(context_payload)
    player_input = payload.get("message", "")
    if is_topic_request:
        player_input = ""
    runtime_compact = (
        compact_prompt
        if compact_prompt is not None
        else payload.get("compactPrompt") is True
    )
    if runtime_compact:
        # 这是给游戏端云端请求的内部标记，不进入模型上下文；质量评测的
        # compact=True 仍沿用完整的评测卡片组合。
        context["_runtime_compact"] = True
    prompt = prompt_builder.build(
        context,
        player_input if isinstance(player_input, str) else "",
        compact=runtime_compact,
    )
    return context, prompt


def _retry_for_format_noise(
    request: DialogueTestRequest,
    prompt: list[dict[str, str]],
    result: ProviderResult,
    *,
    attempts: list[ProviderResult] | None = None,
) -> ProviderResult:
    def generate(retry_messages: list[dict[str, str]]) -> ProviderResult:
        retried = provider_router.generate(
            request,
            messages=retry_messages,
        )
        if attempts is not None:
            attempts.append(retried)
        return retried

    return retry_for_format_noise(
        result,
        prompt,
        generate,
        skip=result.provider == fake_provider.name,
    )


@app.post("/api/context/preview")
def preview_context(payload: dict[str, object]) -> dict[str, object]:
    context, prompt = _build_context(payload)
    identity = context["npcIdentity"]
    response: dict[str, object] = {
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
    if "interaction" in context:
        response["interaction"] = context["interaction"]
    if "relationshipWorld" in context:
        response["relationshipWorld"] = context["relationshipWorld"]
    for key in (
        "styleSamples",
        "speechEvidence",
        "behaviorExamples",
        "knowledgeFacts",
        "knownCharacters",
        "storyEvents",
    ):
        if key in context:
            response[key] = context[key]
    return response


def _validate_dialogue_request(payload: Mapping[str, object]) -> DialogueTestRequest:
    filtered = {
        key: payload[key]
        for key in _DIALOGUE_FIELDS
        if key in payload
    }
    try:
        request = DialogueTestRequest.model_validate(filtered)
        if request.intent == "topic":
            # API 入口也做一次归一化，避免 Provider 的无 Prompt 默认路径
            # 重新看到旧版客户端携带的“请主动找话题”文本。
            return request.model_copy(update={"message": ""})
        return request
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


def _validate_group_dialogue_request(
    payload: Mapping[str, object],
) -> GroupDialogueRequest:
    try:
        return GroupDialogueRequest.model_validate(payload)
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
    _, prompt = _build_context(payload, compact_prompt=request.compact_prompt)
    started_at = perf_counter()
    if (
        not provider_router.has_configured_upstream()
        and "provider" not in request.model_fields_set
    ):
        result = fake_provider.generate(request)
    else:
        result = provider_router.generate(request, messages=prompt)

    attempts = [result]
    result = _retry_for_format_noise(
        request,
        prompt,
        result,
        attempts=attempts,
    )

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
                    "open_loop": None,
                    "warnings": warnings,
                }
            )
        else:
            result = fallback.model_copy(
                update={
                    "reply": _SAFE_FALLBACK_REPLY,
                    "fallback": True,
                    "open_loop": None,
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
        warnings=_limit_warnings(result.warnings),
        usage=_merge_provider_usages(item.usage for item in attempts),
        openLoop=result.open_loop if not result.fallback else None,
    )


@app.post("/api/dialogue/group", response_model=GroupDialogueResponse)
def group_dialogue(payload: dict[str, object]) -> GroupDialogueResponse:
    request = _validate_group_dialogue_request(payload)
    return group_conversation_service.generate(request)


@app.get("/test/group", response_class=HTMLResponse)
def group_dialogue_lab() -> str:
    return group_dialogue_lab_page()


@app.get("/test/group/review", response_class=HTMLResponse)
def group_dialogue_review(batch: str | None = None) -> str:
    return group_dialogue_review_page(quality_artifact_root, batch=batch)


@app.get("/test/ui", response_class=HTMLResponse)
def ui_preview() -> str:
    """三个游戏内聊天界面的浏览器复刻稿（不读运行数据，纯静态渲染）。"""

    return ui_preview_page()


@app.get("/test/ui-redesign", response_class=HTMLResponse)
def ui_preview_redesign() -> str:
    """三个游戏内聊天界面的「外壳重构」设计稿，可与 /test/ui 并排比对。"""

    return ui_preview_redesign_page()


@app.get("/test/bubble-colors", response_class=HTMLResponse)
def bubble_colors() -> str:
    """46 个角色的气泡底色核对：现方案（彩色木框）vs 备选（去色面板）。

    页面**自身零依赖**（贴图的 PNG 解码与 tint 预乘走标准库，见 ``png_rgba``），
    但这里的惰性导入保留 —— 它是「一个页面的 import 不该拖垮整个 Bridge」的护栏：
    2026-09-21 与 2026-09-20 各发生过一次（`from PIL import Image` 缺失 /
    `group_dialogue_review_page` 的错误 import）→ `import stardew_ai_bridge.app` 直接失败，
    Bridge 一重启就挂。现在最坏情况只是这一个路由 503，其余路由与 Bridge 本体不受影响。
    """

    try:
        from .bubble_color_page import bubble_color_page
    except ModuleNotFoundError as error:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail=(
                f"页面模块加载失败：当前 Bridge 环境缺少 {error.name}；"
                "Bridge 本体与其余路由不受影响。"
            ),
        ) from error

    return bubble_color_page()
