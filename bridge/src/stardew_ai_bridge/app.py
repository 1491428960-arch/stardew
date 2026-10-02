from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
import json
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
    MorningMessagePlan,
    MorningPlanRequest,
    MorningPlanResponse,
    MorningScenarioListResponse,
    MorningScenarioView,
    ProviderResult,
    ProviderUsage,
)
from .morning_scenario import MorningScenarioStore, match_scenario_by_history
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
# 晨间预设是**可选内容**：文件不存在时是空库而不是错误，
# 整条链路应退化成「没有人在早上主动开口」，也就是加这个功能之前的行为。
morning_scenario_store = MorningScenarioStore.load(
    project_root / "data" / "scenarios" / "morning.json"
)


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
    # 跨窗口的"她最近说过什么"（2026-09-23）：漏进这份白名单就是**静默吞字段**
    # —— 本项目在同类白名单上记过多次（`_compact_stage_policy`、`_STATE_FIELDS`）。
    "recentReplies",
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


@app.get("/test/morning", response_class=HTMLResponse)
def morning_test_page() -> str:
    """晨间预设的**游戏外**审阅页：看文本、试着接一句。

    **为什么要有它**：预设的价值全在措辞上，而它只在某一天的早上出现一次，
    靠开游戏来审等于每次都要过一整天的存档。这个页面把「看文本」和「试一句」
    搬到浏览器里；真正只能靠游戏验的，只剩「`DayStarted` 会不会触发」。
    """
    return integrated_dialogue_lab_page("morning")


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


def _request_compact_flag(payload: Mapping[str, object]) -> bool:
    """请求体的紧凑路径标记——按 `DialogueTestRequest` 的同一个字段口径解析。

    `/api/dialogue/test` 与 `/api/context/preview` 都从这里取值，保证
    「上下文预览显示的路径」就是「实际发给模型的那条路径」。
    参数不合法时返回 False：那种请求在 `/api/dialogue/test` 上会直接 422，
    根本走不到发 prompt，因此预览按完整路径显示不会掩盖任何真实请求。
    """

    filtered = {
        key: payload[key]
        for key in _DIALOGUE_FIELDS
        if key in payload
    }
    try:
        return DialogueTestRequest.model_validate(filtered).compact_prompt
    except ValidationError:
        return False


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
    context = context_builder.build(
        context_payload,
        # 「这段对话是不是某条晨间预设的后续」在这里判、以**显式参数**传下去，
        # 不塞进 context_payload：payload 是被 `_sanitize_value` 之类整体处理的，
        # 混一个内部键进去有泄漏到 prompt 里的风险。
        morning_scenario=match_scenario_by_history(
            morning_scenario_store,
            context_payload.get("history"),
        ),
    )
    player_input = payload.get("message", "")
    if is_topic_request:
        player_input = ""
    # 调用方显式传入时以它为准（`/api/dialogue/test` 传的是校验后的
    # `DialogueTestRequest.compact_prompt`）；不传的调用方目前只有群聊，
    # 它的内部 payload 不带这个键，因此固定走完整卡组——与游戏端群聊一致。
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


def _stage_from_context(context: object) -> str | None:
    """取当前轮的关系阶段，供按阶段放宽长度阈值使用。

    取不到就返回 None（退回全局阈值）—— **不要猜**。context 的形状由
    `prompts.py` 决定，这里只做防御性读取，不复制它的阶段推导逻辑，
    否则两处会各自漂移。
    """

    try:
        stage = context["npcIdentity"]["stageProfile"]["stage"]  # type: ignore[index]
    except (TypeError, KeyError, IndexError):
        return None
    return stage if isinstance(stage, str) and stage.strip() else None


def _retry_for_format_noise(
    request: DialogueTestRequest,
    prompt: list[dict[str, str]],
    result: ProviderResult,
    *,
    attempts: list[ProviderResult] | None = None,
    stage: str | None = None,
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
        stage=stage,
    )


@app.post("/api/context/preview")
def preview_context(payload: dict[str, object]) -> dict[str, object]:
    compact_prompt = _request_compact_flag(payload)
    context, prompt = _build_context(payload, compact_prompt=compact_prompt)
    identity = context["npcIdentity"]
    response: dict[str, object] = {
        "npcId": identity["npcId"],
        "personaSummary": identity,
        "gameState": context["gameState"],
        "modSources": context["modSources"],
        "recentFacts": context["recentFacts"],
        "history": context["history"],
        # 回显本轮预览走的是哪条路径：页面与人工复核都靠它确认
        # 「预览的那份 prompt」与「实发的那份 prompt」同源。
        "compactPrompt": compact_prompt,
        "promptSummary": [
            {"role": message["role"], "name": message["name"]}
            for message in prompt
        ],
    }
    # 这一轮的历史首条如果命中某条晨间预设的开场白，就把它的 id 回显出来。
    #
    # **为什么要单独回显**：认人靠逐字比对（见 `match_scenario_by_history`），
    # 而它对失败是**静默**的——没认出时只是少一层方向约束，回复照样正常生成。
    # 测试页必须能一眼看出「这次到底认出来了没有」，否则试聊的效果无从归因，
    # 正是本项目反复记的那类「数据写对但永不生效」。
    matched_morning = match_scenario_by_history(
        morning_scenario_store, payload.get("history")
    )
    response["morningScenarioId"] = matched_morning.id if matched_morning else None
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


def _record_dialogue(
    payload: Mapping[str, object],
    response: DialogueResponse,
) -> None:
    """把一次**真实**对话追加到 `artifacts/dialogue-log/<日期>.jsonl`。

    **为什么要有它**：SMAPI 日志只记目标／频道／延迟／`fallback`，**回复正文不落盘**；
    存档里的聊天记录只在**保存游戏**时写入。于是「刚才那句她到底说了什么」在两边都查不到
    —— 2026-09-26 实机验证时就卡在这里。这个文件补的就是这一段。

    **只写不改行为**：任何异常都被吞掉（含目录不可写、磁盘满），
    对话本身绝不会因为记日志失败而失败。用 `BRIDGE_DIALOGUE_LOG=0` 关掉。
    """
    if os.environ.get("BRIDGE_DIALOGUE_LOG", "1") == "0":
        return
    try:
        root = Path(__file__).resolve().parents[3]
        log_dir = root / "artifacts" / "dialogue-log"
        log_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            # ⚠ 键名是 **HTTP 层**的名字，不是模型的 Python 字段名：
            # `npc_id` 的 alias 是 `npcId`、`display_name` 的是 `displayName`，
            # 而 `message`/`intent`/`channel`/`history` 没有 alias、保持原名。
            # 这一处我猜错过两次（先按 camelCase 猜 message、又照 model_fields 改成 snake_case），
            # 判据只有一条：`DialogueTestRequest.model_fields[...].alias`。
            "npcId": payload.get("npcId"),
            "displayName": payload.get("displayName"),
            "playerText": payload.get("message"),
            "intent": payload.get("intent"),
            "channel": payload.get("channel"),
            "reply": response.reply,
            "provider": response.provider,
            "fallback": response.fallback,
            # ⚠ 这里是 **Python 属性名**（snake_case），不是 HTTP 别名：
            # `latencyMs` 只是 `latency_ms` 的 alias，读属性用 alias 会 AttributeError。
            # 与上面 payload 那一段正好相反——那边取的是原始 HTTP dict。
            "latencyMs": response.latency_ms,
            "warnings": list(response.warnings),
            # 历史长度是「这一轮到底有没有上下文」的唯一判据：
            # 探针那次「发了历史却被静默丢弃」就是靠它才发现的。
            "historyLen": len(payload.get("history") or ()),
        }
        path = log_dir / f"{datetime.now():%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 —— 记日志绝不影响对话
        return


# 游戏端送进来的是 `Game1.Date.TotalDays`（第 1 年春季第 1 天 = 0），
# 而 `data/scenarios/morning.json` 的 `absoluteDay.dayIndex` 写的是人话「第几天」。
# 两者差 1。**2026-09-26 实机踩到**：预设挂在「第 2 天」、玩家也真的过到了第 2 天、
# Bridge 也真的被调用了两次（`POST /api/morning/plan` → 200 OK），
# 但游戏里一条消息都没有 —— 送进来的是 1、配置等的是 2，永远匹配不上。
# 换算只在这一处做：`for_day()` 保持「按配置里的天数取」的纯语义，
# 由端点负责把 API 的 0 基计数器翻成人话天数。
_MORNING_DAY_OFFSET = 1


@app.post("/api/morning/plan", response_model=MorningPlanResponse)
def morning_plan(request: MorningPlanRequest) -> MorningPlanResponse:
    """游戏端在 `DayStarted` 时来问：今天早上有没有人要主动开口。

    **为什么是「问」而不是把内容编进 DLL**：预设内容会反复调整
    （措辞、边界、该由谁说），编进 DLL 就意味着每改一个字都要重新编译部署。
    放在 Bridge 侧的数据文件里，改完重启 Bridge 即可。

    **为什么返回值里带 `opening` 全文而不是只给 id**：游戏端拿到就写进聊天记录，
    不需要再回一次；而且 `opening` 必须与 `morning.json` 里的**逐字一致**——
    `prompts.py` 是靠「历史首条 == 某条 opening」来认出「这是晨间对话的后续」的，
    两端一旦不一致，方向约束就会静默失效（这正是 ㉑ 那类「数据写对但永不生效」）。
    """
    # 测试期诊断（2026-09-27）：`recentEventIds` 是事件型预设的唯一输入，而它从 DLL
    # 走到这里要经过「跨天差异 → 序列化 → HTTP」三段，任何一段断了**症状都一样**：
    # 今天早上没人发消息。把它打出来，日志才能指出断在哪一段。
    #
    # ⚠ `model_fields_set` 里放的是**字段名**（`recent_event_ids`），不是 alias
    # （`recentEventIds`）—— 2026-09-27 实测踩到：只查 alias 会让「已送达」永远
    # 显示成「未送达」，把一条好链路误诊成断的。两个都查，因为这点跨 pydantic 版本不保证。
    #
    # 用英文而不是中文：Bridge 的输出常被重定向到文件，那种场景下中文会变成乱码
    # （实测 `<未送达>` 显示成 `<δ�ʹ�>`），而日志看不懂就等于没有。
    _field_arrived = bool(
        {"recentEventIds", "recent_event_ids"} & set(request.model_fields_set)
    )
    print(
        f"[morning] dayIndex={request.day_index}"
        f" recentEventIds={'<NOT-SENT>' if not _field_arrived else list(request.recent_event_ids)}"
        f" knownNpcIds={len(request.known_npc_ids)}",
        flush=True,
    )

    scenario = morning_scenario_store.for_day(
        request.day_index + _MORNING_DAY_OFFSET,
        recent_event_ids=request.recent_event_ids,
    )
    if scenario is None:
        # 空数组而不是 404：绝大多数日子本来就没有预设消息，
        # 「今天没人发」是正常结果，不是错误。
        return MorningPlanResponse()
    return MorningPlanResponse(
        messages=[
            MorningMessagePlan(
                npc_id=scenario.npc_id,
                display_name=scenario.display_name,
                scenario_id=scenario.id,
                opening=scenario.opening,
            )
        ]
    )


@app.get("/api/morning/scenarios", response_model=MorningScenarioListResponse)
def morning_scenarios() -> MorningScenarioListResponse:
    """列出全部晨间预设的**完整文本**，供 `/test/morning` 审阅。

    **为什么不再读一次文件**：内容只有一个来源（`morning_scenario_store`），
    页面上看到的就是游戏端会收到的。真去读第二遍文件，两处就会各自漂移——
    而这个功能最怕的正是「页面看到的和游戏里发的不是同一句」。
    """
    return MorningScenarioListResponse(
        scenarios=[
            MorningScenarioView(
                scenario_id=scenario.id,
                npc_id=scenario.npc_id,
                display_name=scenario.display_name,
                day_index=scenario.day_index,
                opening=scenario.opening,
                opening_source=scenario.opening_source,
                direction=scenario.direction,
                boundaries=list(scenario.boundaries),
                closing_hook=scenario.closing_hook,
                allowed_kinds=list(scenario.allowed_kinds),
            )
            for scenario in morning_scenario_store.scenarios
        ]
    )


@app.post("/api/dialogue/test", response_model=DialogueResponse)
def test_dialogue(payload: dict[str, object]) -> DialogueResponse:
    request = _validate_dialogue_request(payload)
    context, prompt = _build_context(payload, compact_prompt=request.compact_prompt)
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
        stage=_stage_from_context(context),
    )

    guarded = response_guard.check(result.reply)
    if not guarded.accepted:
        fallback = fallback_provider.generate(request)
        # ⚠ **默认配置下 `fallback_guarded.accepted` 恒为 False**，所以每次都走下面的
        # `else`，warning 里也必然出现 `fallback_guard: stage_direction`。
        #
        # 原因**不是守卫失败**，是形态对撞：`FallbackProvider` 返回的就是
        # `settings.fallback_reply`（`DEFAULT_FALLBACK_REPLY`），**和 `_SAFE_FALLBACK_REPLY`
        # 是同一个字符串**，而它用全角括号包裹 —— `ResponseGuard` 的 `_stage_direction`
        # 判据（括号动作旁白）必然命中它。
        #
        # **括号是有意的，不要去改**：2026-09-26 特意从「Rasmodia：暂时没有合适的回复，
        # 请稍后再试。」改成这个形态，为的是让兜底文案在**形状上**跟角色台词分开
        # （兜底哪个 NPC 都可能触发，署名或写成台词形状会让玩家以为是某个角色在说话）。
        # 去掉括号就退回了那次要修的坑。详见 `config.py` 里 `DEFAULT_FALLBACK_REPLY` 的注释。
        #
        # 所以：看到这条 warning 不等于「守卫拦下了一条坏回复」，只是**兜底文案的形态**。
        # 下面这一支检查留着，是为了兜住 `BRIDGE_FALLBACK_REPLY` 被配成别的文案的情况。
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

    response = DialogueResponse(
        reply=result.reply,
        provider=result.provider,
        fallback=result.fallback,
        latencyMs=latency_ms,
        # 延迟是**含重试的总耗时**，所以必须同时说出「发了几次」——
        # 否则审阅页上看到的 3.2s 与 21.1s 无法区分是上游慢还是重试叠加。
        requestCount=len(attempts),
        warnings=_limit_warnings(result.warnings),
        usage=_merge_provider_usages(item.usage for item in attempts),
        openLoop=result.open_loop if not result.fallback else None,
    )
    _record_dialogue(payload, response)
    return response


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
