from __future__ import annotations

import argparse
from datetime import datetime
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import sys
from time import perf_counter
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bridge" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stardew_ai_bridge.character_quality_eval import (  # noqa: E402
    DEFAULT_CASES,
    QUALITY_SUITE_IDS,
    CharacterQualityCase,
    CharacterQualityTurn,
    diagnose_affection_initiative,
    quality_cases_for_suite,
    score_affection_pacing,
    score_affection_variation,
    score_conversation_lead_variation,
    score_dialogue_progression,
    score_character_reply,
    score_generated_player_input,
    _turn_intent,
    _turn_for_plan_scoring,
    quality_case_display_name,
    validate_quality_cases,
    relationship_turn_metadata,
)
from stardew_ai_bridge.artifact_paths import stable_artifact_path  # noqa: E402
from stardew_ai_bridge.config import ProviderSettings, load_local_env  # noqa: E402
from stardew_ai_bridge.reply_scrub import scrub_reply  # noqa: E402
from stardew_ai_bridge.models import (  # noqa: E402
    DialogueTestRequest,
    ProviderResult,
    ProviderUsage,
)
from stardew_ai_bridge.profile_index import ProfileIndexStore  # noqa: E402
from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: E402
from stardew_ai_bridge.personas import canonical_npc_id  # noqa: E402
from stardew_ai_bridge.relationship_world import (  # noqa: E402
    project_relationship_context,
    project_relationship_request,
)
from stardew_ai_bridge.providers import (  # noqa: E402
    FakeProvider,
    OllamaNativeProvider,
    OpenAICompatibleProvider,
)
from stardew_ai_bridge.behavior_quality import sanitize_quality_artifact  # noqa: E402
from stardew_ai_bridge.dialogue_style_quality import (  # noqa: E402
    analyze_dialogue_style,
)
from stardew_ai_bridge.evaluation_budget import (  # noqa: E402
    EvaluationBudget,
    EvaluationBudgetExceeded,
    EvaluationBudgetTracker,
)
from stardew_ai_bridge.guard import ResponseGuard, retry_for_format_noise  # noqa: E402


DEFAULT_PROFILE_INDEX = (
    ROOT
    / "data"
    / "generated"
    / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)
DEFAULT_ENDPOINT = "http://127.0.0.1:11435/api/chat"
DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_CLOUD_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
)
DEFAULT_CLOUD_MODEL = "gemini-3.7-flash"


_TURN_PLAN_MODES = {
    "answer_only",
    "answer_plus_detail",
    "answer_plus_lead",
    "answer_plus_warmth",
    "boundary_close",
    "explicit_intimacy",
}
_TURN_PLAN_INTENSITIES = {"none", "light", "direct", "explicit"}
_TURN_PLAN_CLOSE_MARKERS = (
    "先不说了",
    "先休息",
    "先这样",
    "下次再聊",
    "改天再聊",
    "我先走了",
    "不想聊",
    "没心情",
    "别逼我",
)
_TURN_PLAN_INTIMACY_MARKERS = (
    "更亲密",
    "亲密一点",
    "接吻",
    "亲一下",
    "抱我",
    "摸我",
    "想和你睡",
    "一起睡",
    "发生关系",
    "脱掉",
)
_TURN_PLAN_LEAD_KINDS = {
    "specific_plan",
    "companionship",
    "creative_share",
    "playful_tease",
    "shared_evening",
    "care_action",
}


def _turn_plan(
    case: CharacterQualityCase,
    turn: object | None,
    *,
    message: str,
    intent: str | None,
) -> dict[str, object]:
    """为评测回合生成唯一目标，并保持与 PromptBuilder 的字段契约一致。

    评测脚本需要把该目标同时放进 ``qualityContext`` 和结果记录。这里不把
    ``evaluation_focus`` 等仅供评测者阅读的字段传给模型，只保留模式和关系
    强度，避免把评分意图泄漏到对白提示中。
    """

    explicit_mode = getattr(turn, "turn_plan_mode", "")
    if not isinstance(explicit_mode, str):
        explicit_mode = ""
    mode = explicit_mode.strip().casefold()

    effective_intent = intent or getattr(turn, "intent", None) or case.intent
    if not isinstance(effective_intent, str):
        effective_intent = case.intent
    effective_intent = effective_intent.strip().casefold()
    expectation = getattr(turn, "initiative_expectation", "none")
    if not isinstance(expectation, str):
        expectation = "none"
    expectation = expectation.strip().casefold()
    initiative_kind = getattr(turn, "initiative_kind", "none")
    if not isinstance(initiative_kind, str):
        initiative_kind = "none"
    initiative_kind = initiative_kind.strip().casefold()
    intensity = case.flirt_intensity.strip().casefold()
    player_text = message.strip()
    natural_adaptive_topic = (
        case.follow_up_mode == "adaptive" and case.intent == "topic"
    )

    if mode not in _TURN_PLAN_MODES:
        # 收口优先级最高：即使案例仍带有亲密关系字段，也不能因评分契约
        # 把玩家明确结束的话题重新升级。
        if initiative_kind == "conversation_exit" or any(
            marker in player_text for marker in _TURN_PLAN_CLOSE_MARKERS
        ):
            mode = "boundary_close"
        elif (
            any(marker in player_text for marker in _TURN_PLAN_INTIMACY_MARKERS)
            and intensity == "explicit"
            and case.adult_consensual is True
            and _case_romance_eligible(case) is not False
        ):
            mode = "explicit_intimacy"
        elif effective_intent == "topic":
            mode = "answer_only" if natural_adaptive_topic else "answer_plus_lead"
        elif expectation == "proactive" and initiative_kind in _TURN_PLAN_LEAD_KINDS:
            mode = "answer_plus_lead"
        elif expectation == "proactive" and initiative_kind == "affection_signal":
            mode = "answer_plus_warmth"
        elif expectation == "guarded":
            mode = "answer_only"
        elif expectation == "responsive" or initiative_kind == "none":
            mode = "answer_only" if natural_adaptive_topic else (
                "answer_plus_detail" if player_text else "answer_only"
            )
        else:
            mode = "answer_only"

    plan: dict[str, object] = {"mode": mode}
    if intensity in _TURN_PLAN_INTENSITIES:
        plan["intensity"] = intensity
    return plan


def _relationship_hearts(stage: str) -> int:
    return {
        "stranger": 0,
        "acquaintance": 2,
        "friend": 6,
        "close": 8,
        "dating": 8,
        "married": 10,
        "parent": 10,
    }.get(stage, 0)


def _canonical_case_npc_id(case: CharacterQualityCase) -> str:
    return canonical_npc_id(case.npc_id)


def _case_romance_eligible(case: CharacterQualityCase) -> bool:
    if case.romance_eligible is not None:
        return case.romance_eligible
    return _canonical_case_npc_id(case) in {
        "Wizard",
        "Sophia",
        "Shane",
        "Sebastian",
        "Alex",
    }


def _resolve_index(value: ProfileIndexStore | Path | str) -> ProfileIndexStore:
    if isinstance(value, ProfileIndexStore):
        return value
    return ProfileIndexStore(Path(value))


def _case_game_state(case: CharacterQualityCase) -> dict[str, object]:
    """案例的 `gameState`，**始终**显式声明事件状态。

    ⚠ `CharacterQualityCase.completed_event_ids` 默认是空元组，它表示
    「该案例确认尚未完成任何事件」= **显式空集**，而不是「调用方没提供状态」。
    早先这里是 `if case.completed_event_ids:` —— 空元组时不写这个键，于是
    `prompts.py:1693` 的 `completed_event_ids_known` 为 `False`，
    `relationship_gating.py:292` 按「不能推断为没有完成事件」跳过事件锁，
    已完成事件的对白因此漏进初识阶段的 prompt（Alex 说出海滩事件台词即此）。
    评分侧 `character_quality_eval._event_gate_payload` 一直按「未完成」处理，
    两边口径由此一致；运行时 SMAPI 也总是随存档带上这个字段。
    """
    game_state = dict(case.game_state)
    game_state.setdefault("friendshipHearts", _relationship_hearts(case.relationship_stage))
    game_state["sourceMods"] = list(case.source_mods)
    game_state["completedEventIds"] = list(case.completed_event_ids)
    return game_state


def _build_request(
    case: CharacterQualityCase,
    *,
    message: str | None = None,
    history: list[dict[str, object]] | None = None,
    intent: str | None = None,
) -> DialogueTestRequest:
    game_state = _case_game_state(case)
    relationship_world = None
    if case.relationship_world is not None:
        relationship_world = project_relationship_request(
            _canonical_case_npc_id(case),
            case.relationship_world,
        )
    return DialogueTestRequest(
        npcId=_canonical_case_npc_id(case),
        displayName=quality_case_display_name(case),
        sourceMods=list(case.source_mods),
        recentFacts=[case.story_progress] if case.story_progress else [],
        history=[dict(item) for item in (case.history if history is None else history)],
        message=case.message if message is None else message,
        intent=case.intent if intent is None else intent,
        channel=case.channel,
        gameState=game_state,
        relationshipWorld=relationship_world,
    )


def _build_context(
    builder: ContextBuilder,
    case: CharacterQualityCase,
    *,
    message: str | None = None,
    history: list[dict[str, object]] | None = None,
    turn: object | None = None,
    intent: str | None = None,
) -> dict[str, Any]:
    game_state = _case_game_state(case)
    game_state["relationshipStage"] = case.relationship_stage
    quality_context: dict[str, object] = {
        "flirtIntensity": case.flirt_intensity,
        "adultConsensual": case.adult_consensual,
        "romanceEligible": (
            _case_romance_eligible(case)
        ),
        "relationshipContext": case.relationship_context or case.story_progress,
        "genderPresentation": case.gender_presentation,
    }
    relationship_gating_case = case.case_id.startswith("relationship-gate-")
    if (
        case.case_id.startswith("deep-flirt-")
        or relationship_gating_case
        or (
            case.follow_up_mode == "adaptive"
            and case.intent == "topic"
        )
    ):
        # deep-flirt、关系事件锁和 NPC 主动找话题的 adaptive 输入都按自然对白处理；
        # 关系事件锁只比较权限前后，不能让旧评测腔或硬性回显规则改变角色声线。
        # 其他套件保持旧契约，避免改变既有评测边界。
        quality_context["naturalMode"] = True
        if (
            case.follow_up_mode == "adaptive"
            and case.intent == "topic"
            and _canonical_case_npc_id(case).casefold() == "elliott"
        ) or (
            relationship_gating_case
            and _canonical_case_npc_id(case).casefold() == "elliott"
        ):
            quality_context["styleCalibration"] = "elliott_original_rhythm"
    if case.topic_seed:
        quality_context["topicSeed"] = case.topic_seed
    if case.topic_keywords:
        quality_context["topicKeywords"] = list(case.topic_keywords)
    if case.continuation_mode:
        quality_context["continuationMode"] = case.continuation_mode
    initiative_expectation = getattr(turn, "initiative_expectation", "none")
    initiative_kind = getattr(turn, "initiative_kind", "none")
    if isinstance(initiative_expectation, str):
        quality_context["initiativeExpectation"] = initiative_expectation
    if isinstance(initiative_kind, str):
        quality_context["initiativeKind"] = initiative_kind
    relationship_focus = getattr(turn, "relationship_focus", "")
    if isinstance(relationship_focus, str) and relationship_focus.strip():
        quality_context["relationshipFocus"] = relationship_focus.strip().casefold()
    quality_context["turnPlan"] = _turn_plan(
        case,
        turn,
        message=case.message if message is None else message,
        intent=case.intent if intent is None else intent,
    )
    payload: dict[str, object] = {
            "npcId": _canonical_case_npc_id(case),
            "displayName": quality_case_display_name(case),
            "sourceMods": list(case.source_mods),
            "recentFacts": [case.story_progress] if case.story_progress else [],
            "message": case.message if message is None else message,
            "intent": case.intent if intent is None else intent,
            "channel": case.channel,
            "qualityContext": quality_context,
            "history": [dict(item) for item in (case.history if history is None else history)],
            "gameState": game_state,
        }
    if case.relationship_world is not None:
        payload["relationshipWorld"] = case.relationship_world
    return builder.build(payload)


def _safe_record(record: dict[str, object]) -> dict[str, object]:
    return dict(sanitize_quality_artifact(record))  # type: ignore[arg-type]


def _safe_error_message(exc: BaseException, *, limit: int = 400) -> str:
    """把异常 message 收敛成可审计的一行。

    只存类名查不出病根（见 turn_records 里的注释），但 message 可能夹带
    端点或凭据片段，所以按已加载的密钥做一次精确替换，再截断。
    """

    text = str(exc)
    for name in ("BRIDGE_CLOUD_API_KEY", "CMD_API_KEY", "CMD_API_KEY_2", "CMD_API_KEY_3"):
        secret = os.environ.get(name, "")
        if secret:
            text = text.replace(secret, "<redacted>")
    text = " ".join(text.split())
    return text[:limit]


def _usage_dict(usage: ProviderUsage | None) -> dict[str, int] | None:
    if usage is None:
        return None
    values = {
        key: value
        for key, value in usage.model_dump(by_alias=True, exclude_none=True).items()
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    }
    return values or None


def _merge_usages(usages: Iterable[ProviderUsage | None]) -> dict[str, int] | None:
    values = [usage for usage in (_usage_dict(item) for item in usages) if usage]
    if not values:
        return None
    totals: dict[str, int] = {}
    for value in values:
        for key in ("inputTokens", "outputTokens", "totalTokens"):
            if key in value:
                totals[key] = totals.get(key, 0) + value[key]
    if "totalTokens" not in totals and {
        "inputTokens",
        "outputTokens",
    }.issubset(totals):
        totals["totalTokens"] = totals["inputTokens"] + totals["outputTokens"]
    return totals or None


def _non_negative_price(value: float | str | None) -> float | None:
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price >= 0 else None


def _resolve_price(value: float | None, env_name: str) -> float | None:
    return _non_negative_price(value) if value is not None else _non_negative_price(os.getenv(env_name))


def _estimated_cost(
    usage: Mapping[str, int],
    *,
    input_price_per_million: float | None,
    output_price_per_million: float | None,
) -> dict[str, object] | None:
    if input_price_per_million is None or output_price_per_million is None:
        return None
    amount = (
        usage.get("inputTokens", 0) * input_price_per_million
        + usage.get("outputTokens", 0) * output_price_per_million
    ) / 1_000_000
    return {
        "currency": "CNY",
        "inputPricePerMillion": input_price_per_million,
        "outputPricePerMillion": output_price_per_million,
        "amount": round(amount, 8),
    }


def _write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(_safe_record(record), ensure_ascii=False, sort_keys=True)
            )
            handle.write("\n")


def _last_assistant_reply(history: Iterable[Mapping[str, object]]) -> str:
    for item in reversed(list(history)):
        if item.get("role") == "assistant" and isinstance(item.get("content"), str):
            text = item["content"].strip()
            if text:
                return text
    return ""


def _player_simulator_messages(
    case: CharacterQualityCase,
    *,
    previous_reply: str,
    history: list[dict[str, str]],
    turn_number: int,
) -> list[dict[str, str]]:
    display_name = quality_case_display_name(case)
    transcript = "\n".join(
        f"{item.get('role', 'unknown')}: {str(item.get('content', ''))[:500]}"
        for item in history[-6:]
    )
    style = case.player_simulation_style or "自然回应上一条 NPC 回复"
    expression_card = case.player_expression_card
    intimacy_boundary = (
        "这是高亲密关系案例，可以回应亲密信号，但不要凭空添加未发生的动作。"
        if case.flirt_intensity != "none"
        else "这是普通熟人或朋友对照案例，只保持日常聊天，不调情、不升级关系。"
    )
    card_instruction = ""
    if expression_card is not None:
        card_instruction = (
            "玩家表达卡（只用来保持口吻，不要逐条复述）："
            f"关系姿态：{expression_card.relationship_stance}；"
            f"说话习惯：{expression_card.language_texture}；"
            f"遇到状况时：{expression_card.helping_impulse}；"
            f"距离感：{expression_card.distance_pattern}；"
            f"自我修正：{expression_card.self_correction}。"
        )
    return [
        {
            "role": "system",
            "name": "player_simulator",
            "content": (
                "你就是玩家本人，像熟人随口接话，也像熟人随手回一句，不是 NPC，也不是旁观者。"
                "只发一条简体中文消息，一条消息就够；不解释，不加引号。"
                "看最近一条 NPC 回复，抓住一个点说自己的第一反应；"
                "选最顺的一种说法就好：短答、半句、轻轻打趣或一个自然问题，必要时把话头留给 NPC。"
                "不要复述 NPC 原句，不要把 NPC 的整句话搬回来，不能只摘抄一个词，也不要使用‘你刚才提到的……后来怎么样了’这种固定句式。"
                "不要替 NPC 补事实，不要凭空安排时间、见面或下一步；除非上一条明确需要确认，否则不要连续问两个问题，也不要连续追问。"
                "消息短一点，大多数时候一小句，只有确实需要才补第二句，最多 60 个汉字；"
                "不要写成告白、情书或小诗。"
                "像手机上临时想到就发的一小句普通话，落在一个具体反应；"
                "不用追求机灵、暧昧或文采，也不要把感受总结完整。"
                "对方说到作品、句子或景色时，文学分享时优先用日常口语接话；不要分析文学手法，"
                "不要复述对方完整比喻，不要接着写景或改写意象，无论 NPC 多文学，玩家都用普通口语。"
                "遇到比喻、句子或作品，不要替它下结论；先问具体内容或说第一反应。"
                "不要把一句话总结成‘什么都说了’或‘更有分量’，不要写成文学评论或普遍道理。"
                "允许‘嗯’‘那行’‘好吧’这类口头停顿，别为了完整而补解释性收束。"
                "不要出现规则、任务、评分、模型或提示词等旁观者用语。"
                f"{intimacy_boundary}{card_instruction}玩家这次的说话感觉：{style}。"
            ),
        },
        {
            "role": "user",
            "name": "npc_reply",
            "content": (
                f"NPC（{display_name}）刚才的回复：\n{previous_reply[:1600]}\n\n"
                f"已有对话记录：\n{transcript or '无'}\n\n"
                "只根据最近一条 NPC 回复生成下一句玩家消息；不要根据案例标题或预期词猜话题，"
                "不要把最近一条回复整句搬进玩家消息。"
            ),
        },
    ]


def _player_simulator_request(
    case: CharacterQualityCase,
    *,
    history: list[dict[str, str]],
) -> DialogueTestRequest:
    game_state = dict(case.game_state)
    game_state.setdefault("friendshipHearts", _relationship_hearts(case.relationship_stage))
    game_state["sourceMods"] = list(case.source_mods)
    return DialogueTestRequest(
        npcId=case.npc_id,
        displayName="玩家",
        sourceMods=[],
        history=[dict(item) for item in history],
        message="请根据 NPC 的上一条回复生成玩家的自然承接。",
        intent="chat",
        channel=case.channel,
        gameState=game_state,
    )


def _fake_player_input(case: CharacterQualityCase, previous_reply: str) -> str:
    """Fake 模式只用于离线冒烟，但玩家输入仍从上一条回复取具体锚点。"""

    compact = "".join(previous_reply.strip().split())
    anchor = next(
        (
            keyword
            for keyword in case.topic_keywords
            if isinstance(keyword, str)
            and len(keyword.strip()) >= 2
            and keyword.strip() in compact
        ),
        "",
    )
    if not anchor:
        match = re.search(r"[\u4e00-\u9fff]{2,8}", compact)
        anchor = match.group(0) if match else "刚才那件事"
    if case.continuation_mode == "pressure":
        return f"{anchor}让我有点在意，你还想继续说吗？"
    return f"我对{anchor}有点好奇，你最在意哪一点？"


def run_evaluation(
    *,
    profile_index: ProfileIndexStore | Path | str,
    output_dir: Path | str,
    cases: Iterable[CharacterQualityCase] = DEFAULT_CASES,
    endpoint: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
    provider: str = "local",
    suite: str = "default",
    input_price_per_million: float | None = None,
    output_price_per_million: float | None = None,
    budget: EvaluationBudget | None = None,
    truncated: bool = False,
) -> dict[str, object]:
    """使用实际 ContextBuilder/PromptBuilder 对固定角色场景做脱敏评测。

    ``truncated`` 标记「本批被 ``--max-requests`` 人为截断」。它必须落进
    ``summary.json``：截断意味着**覆盖到的问题集与完整跑不同**，
    两份工件的对比因此无效（规范见 ``docs/eval-runbook-2026-09-28.md`` §四.1）。
    这不是一条警告，而是**可比性判决** —— 下游按它决定能不能把两批放进同一张表。
    """

    normalized_suite = suite.strip().casefold()
    if normalized_suite not in QUALITY_SUITE_IDS:
        raise ValueError(f"unsupported evaluation suite: {suite}")
    index_store = _resolve_index(profile_index)
    context_builder = ContextBuilder(profile_index=index_store)
    prompt_builder = PromptBuilder()
    upstream = _build_provider(
        provider,
        endpoint=endpoint,
        model=model,
        timeout=timeout,
    )
    evaluation_budget = budget or EvaluationBudget()
    selected_cases = list(cases)
    if evaluation_budget.max_cases is not None:
        selected_cases = selected_cases[: evaluation_budget.max_cases]
    case_numbers = {
        case.case_id: case_number
        for case_number, case in enumerate(selected_cases, start=1)
    }
    validation_errors = validate_quality_cases(selected_cases)
    if validation_errors:
        raise ValueError("角色质量案例校验失败：" + "; ".join(validation_errors))
    records: list[dict[str, object]] = []
    request_count = 0
    npc_request_count = 0
    player_input_request_count = 0
    player_input_generation_count = 0
    player_input_valid_count = 0
    player_input_invalid_count = 0
    player_input_quality_tags: set[str] = set()
    mechanical_restatement_count = 0
    npc_retry_count = 0
    player_input_retry_count = 0
    successful_turns = 0
    failed_turns = 0
    all_usages: list[ProviderUsage | None] = []
    usage_returned_turns = 0
    player_input_usage_returned = 0
    relationship_focus_counts: dict[str, int] = {}
    relationship_tag_counts: dict[str, int] = {}
    budget_tracker = EvaluationBudgetTracker(evaluation_budget)

    def reserve_request(kind: str) -> None:
        nonlocal request_count, npc_request_count, player_input_request_count
        budget_tracker.reserve_request()
        request_count += 1
        if kind == "npc":
            npc_request_count += 1
        elif kind == "player_input":
            player_input_request_count += 1

    started_at = perf_counter()
    for case in selected_cases:
        case_started_at = perf_counter()
        conversation_history = [dict(item) for item in case.history]
        turn_records: list[dict[str, object]] = []
        for turn_index, turn in enumerate(case.dialogue_turns()):
            turn_started_at = perf_counter()
            current_intent = _turn_intent(case, turn)
            actual_message = turn.message
            player_input_source = "fixed"
            player_input_quality: dict[str, object] | None = None
            player_input_provider: str | None = None
            player_input_latency_ms: int | None = None
            player_input_usage: dict[str, int] | None = None
            player_input_error: str | None = None
            if (
                case.follow_up_mode == "adaptive"
                and turn_index > 0
                and not evaluation_budget.dynamic_player_input
            ):
                # 经济模式把自适应玩家输入替换为固定短句，保留三轮 NPC
                # 评测语义，同时省掉每个案例额外的两次模型请求。
                player_input_source = "fixed_economical"
                actual_message = turn.message or "嗯，你继续说。"
            if (
                case.follow_up_mode == "adaptive"
                and turn_index > 0
                and evaluation_budget.dynamic_player_input
            ):
                player_input_source = "generated"
                player_input_generation_count += 1
                previous_reply = _last_assistant_reply(conversation_history)
                if provider == "fake":
                    actual_message = _fake_player_input(case, previous_reply)
                    player_input_provider = "fake"
                    player_input_quality = score_generated_player_input(
                        case,
                        actual_message,
                        previous_reply=previous_reply,
                    )
                else:
                    player_request = _player_simulator_request(
                        case,
                        history=conversation_history,
                    )
                    player_messages = _player_simulator_messages(
                        case,
                        previous_reply=previous_reply,
                        history=conversation_history,
                        turn_number=turn_index + 1,
                    )
                    try:
                        reserve_request("player_input")
                        player_result = upstream.generate(
                            player_request,
                            messages=player_messages,
                        )
                    except EvaluationBudgetExceeded:
                        # 达到批次预算时直接停止当前批次，不把它记成模型错误。
                        break
                    except Exception as exc:  # noqa: BLE001 - 保留输入链路诊断
                        player_input_error = type(exc).__name__
                        player_input_quality = score_generated_player_input(
                            case,
                            "",
                            previous_reply=previous_reply,
                        )
                    else:
                        player_input_provider = player_result.provider
                        player_input_latency_ms = player_result.latency_ms
                        player_input_usage = _usage_dict(player_result.usage)
                        budget_tracker.record_usage(player_result.usage)
                        all_usages.append(player_result.usage)
                        if player_result.usage is not None:
                            player_input_usage_returned += 1
                        actual_message = player_result.reply
                        player_input_quality = score_generated_player_input(
                            case,
                            actual_message,
                            previous_reply=previous_reply,
                        )
                if player_input_quality is not None:
                    if player_input_quality.get("valid") is True:
                        player_input_valid_count += 1
                    elif player_input_quality.get("valid") is False:
                        player_input_invalid_count += 1
                    player_input_quality_tags.update(
                        str(tag)
                        for tag in player_input_quality.get("tags", [])
                        if isinstance(tag, str)
                    )
                if budget_tracker.stop_reason is not None:
                    break
                if player_input_error:
                    failed_turns += 1
                    turn_records.append(
                        {
                            "turnId": turn.turn_id,
                            "intent": current_intent,
                            "turnPlan": _turn_plan(
                                case,
                                turn,
                                message=actual_message,
                                intent=current_intent,
                            ),
                            "playerInput": "",
                            "playerInputSource": player_input_source,
                            "playerInputError": player_input_error,
                            "playerInputQuality": player_input_quality,
                            "error": "PlayerInputGenerationError",
                            "elapsedMs": int((perf_counter() - turn_started_at) * 1000),
                        }
                    )
                    # 自适应链路一旦断裂，后续轮次没有可靠的“上一条回复”，
                    # 直接结束当前案例，避免把级联失败误算成 NPC 输出失败。
                    break
            turn_plan = _turn_plan(
                case,
                turn,
                message=actual_message,
                intent=current_intent,
            )
            # 评分必须消费与 Prompt、Guard 完全相同的回合计划；否则生成侧
            # 已允许自然接话，评分侧仍会按旧的主动亲密规则判失败。
            scoring_turn = turn
            turn_plan_mode = turn_plan.get("mode")
            if (
                isinstance(turn_plan_mode, str)
                and isinstance(turn, CharacterQualityTurn)
                and (
                    turn_plan_mode != "answer_plus_detail"
                    or turn.initiative_expectation != "none"
                    or turn.initiative_kind != "none"
                    or current_intent == "topic"
                )
            ):
                scoring_turn = replace(
                    turn,
                    turn_plan_mode=turn_plan_mode,
                )
            context = _build_context(
                context_builder,
                case,
                message=actual_message,
                history=conversation_history,
                turn=turn,
                intent=current_intent,
            )
            messages = prompt_builder.build(
                context,
                actual_message,
                compact=evaluation_budget.compact_prompt,
            )
            request = _build_request(
                case,
                message=actual_message,
                history=conversation_history,
                intent=current_intent,
            )
            attempt_usages: list[ProviderUsage | None] = []
            npc_requests_before = npc_request_count

            def generate_attempt(
                prompt_messages: list[dict[str, str]],
            ) -> ProviderResult:
                reserve_request("npc")
                result = upstream.generate(request, messages=prompt_messages)
                budget_tracker.record_usage(result.usage)
                attempt_usages.append(result.usage)
                return result

            try:
                result = generate_attempt(messages)
            except EvaluationBudgetExceeded:
                break
            except Exception as exc:  # noqa: BLE001 - 单轮失败不阻断其他轮次
                failed_turns += 1
                relationship_fields = (
                    relationship_turn_metadata(case)
                    if normalized_suite == "relationship-world"
                    else {}
                )
                turn_records.append(
                    {
                        "turnId": turn.turn_id,
                        "intent": current_intent,
                        "turnPlan": turn_plan,
                        "playerInput": actual_message,
                        "playerInputSource": player_input_source,
                        "playerInputQuality": player_input_quality,
                        "playerInputProvider": player_input_provider,
                        "playerInputLatencyMs": player_input_latency_ms,
                        "playerInputUsage": player_input_usage,
                        **relationship_fields,
                        **(
                            {"relationshipTags": ["provider_error"]}
                            if normalized_suite == "relationship-world"
                            else {}
                        ),
                        "error": type(exc).__name__,
                        # 2026-09-29：原来只存类名，导致一次真实故障查不出来。
                        # 批次 20260929-070405 里 wizard turn-2 记录为
                        # `ProviderError`、elapsedMs 5022、正文为空，而
                        # `providers.py` 里有四处会抛 ProviderError：
                        #   · provider disabled（482）/ model 未配置（484）
                        #   · HTTP 非 2xx（512）
                        #   · 响应不是合法 JSON，通常意味着流被截断（536）
                        #   · 响应体内嵌 error 对象（542）
                        # 只凭类名无法区分，只能重跑。存下 message 才能直接判定。
                        "errorMessage": _safe_error_message(exc),
                        "elapsedMs": int((perf_counter() - turn_started_at) * 1000),
                    }
                )
                continue

            if provider != "fake":
                if evaluation_budget.max_npc_retries is None:
                    # 兼容既有调用方和测试替身：未显式限制时保持旧的三参数契约。
                    result = retry_for_format_noise(
                        result,
                        messages,
                        generate_attempt,
                    )
                else:
                    result = retry_for_format_noise(
                        result,
                        messages,
                        generate_attempt,
                        max_retries=evaluation_budget.max_npc_retries,
                    )
            turn_request_count = npc_request_count - npc_requests_before
            turn_retry_count = max(0, turn_request_count - 1)
            npc_retry_count += turn_retry_count
            usage = _merge_usages(attempt_usages)
            all_usages.extend(attempt_usages)
            if usage is not None:
                usage_returned_turns += 1
            successful_turns += 1
            score = score_character_reply(
                case,
                result.reply,
                turn=scoring_turn,
                history=conversation_history,
                player_input=actual_message,
            )
            format_issue = ResponseGuard.format_issue(result.reply)
            if format_issue:
                score["tags"] = {
                    *score.get("tags", set()),
                    "format_noise",
                }
                score["passed"] = False
            score["tags"] = sorted(str(tag) for tag in score.get("tags", set()))
            style_quality = analyze_dialogue_style(
                result.reply,
                history=conversation_history,
            )
            initiative_diagnostic = diagnose_affection_initiative(
                case,
                _turn_for_plan_scoring(scoring_turn, actual_message),
                result.reply,
                player_input=actual_message,
            )
            relationship_fields = (
                relationship_turn_metadata(case)
                if normalized_suite == "relationship-world"
                else {}
            )
            relationship_tags = [
                str(tag)
                for tag in score.get("relationshipTags", [])
                if isinstance(tag, str)
            ]
            if normalized_suite == "relationship-world":
                focus = turn.relationship_focus
                if focus:
                    relationship_focus_counts[focus] = (
                        relationship_focus_counts.get(focus, 0) + 1
                    )
                for tag in relationship_tags:
                    relationship_tag_counts[tag] = (
                        relationship_tag_counts.get(tag, 0) + 1
                    )
            if initiative_diagnostic["mechanicalRestatement"] is True:
                mechanical_restatement_count += 1
            if case.topic_seed:
                initiative_failure_tags = {
                    "missing_proactive_affection",
                    "flirt_stage_mismatch",
                    "romance_boundary_violation",
                    "romance_channel_mismatch",
                }
                if initiative_failure_tags.intersection(
                    initiative_diagnostic["initiativeTags"]
                ):
                    score["tags"] = sorted({
                        *(str(tag) for tag in score.get("tags", [])),
                        *initiative_failure_tags.intersection(
                            initiative_diagnostic["initiativeTags"]
                        ),
                    })
                    score["passed"] = False
            turn_records.append(
                {
                    "turnId": turn.turn_id,
                    "intent": current_intent,
                    "turnPlan": turn_plan,
                    "playerInput": actual_message,
                    "playerInputSource": player_input_source,
                    "playerInputQuality": player_input_quality,
                    "playerInputProvider": player_input_provider,
                    "playerInputLatencyMs": player_input_latency_ms,
                    "playerInputUsage": player_input_usage,
                    "reply": result.reply,
                    # 处方 C（2026-09-28）：`reply` 是 **ProviderResult**，即**模型原始输出**；
                    # 玩家实际看到的是过 `scrub_reply` 之后的文本（只有对外的 DialogueResponse 才清洗）。
                    # 这个分层是 models.py 故意设计的，但后果是评测里所有
                    # 「英文残留 / 格式噪音」类数字都在量一个**玩家看不见**的东西。
                    # 同一 case 同时记两份，才能分清「模型给了什么」与「玩家看到什么」。
                    "scrubbedReply": scrub_reply(result.reply),
                    "scrubChanged": scrub_reply(result.reply) != result.reply,
                    "provider": result.provider,
                    "fallback": result.fallback,
                    "latencyMs": result.latency_ms,
                    "warnings": list(result.warnings),
                    # 重试择优结果（2026-09-28 加）：`warnings` 只记「触发过重试」，
                    # **不记「重试有没有用」** ⇒ 全库 480 次 `response_affection_retry`
                    # （占重试 54%）没法归因。`None` = 本回合没比较过。
                    "retryImproved": result.retry_improved,
                    "elapsedMs": int((perf_counter() - turn_started_at) * 1000),
                    "usage": usage,
                    "requestCount": turn_request_count,
                    "retryCount": turn_retry_count,
                    "score": score,
                    "styleQuality": style_quality,
                    "initiativeExpectation": turn.initiative_expectation,
                    "initiativeKind": turn.initiative_kind,
                    "detectedInitiativeKind": initiative_diagnostic["initiativeKind"],
                    "initiativeDetected": initiative_diagnostic[
                        "initiativeDetected"
                    ],
                    "initiativeTags": initiative_diagnostic["initiativeTags"],
                    "mechanicalRestatement": initiative_diagnostic[
                        "mechanicalRestatement"
                    ],
                    "personalAffectionDetected": initiative_diagnostic[
                        "personalAffectionDetected"
                    ],
                    "companionshipDetected": initiative_diagnostic[
                        "companionshipDetected"
                    ],
                    "specificPlanDetected": initiative_diagnostic[
                        "specificPlanDetected"
                    ],
                    "affectionEvidence": initiative_diagnostic["affectionEvidence"],
                    "affectionShape": initiative_diagnostic["affectionShape"],
                    "affectionIntensity": initiative_diagnostic[
                        "affectionIntensity"
                    ],
                    "strongAffectionDetected": initiative_diagnostic[
                        "strongAffectionDetected"
                    ],
                    "affectionSemanticFamilies": initiative_diagnostic[
                        "affectionSemanticFamilies"
                    ],
                    "explicitRequest": initiative_diagnostic["explicitRequest"],
                    "answeredCurrentTopic": score.get("answeredCurrentTopic"),
                    "conversationLeadDetected": score.get("conversationLeadDetected"),
                    "conversationLeadKind": score.get("conversationLeadKind"),
                    "conversationLeadEvidence": score.get("conversationLeadEvidence", []),
                     "conversationLeadTags": score.get("conversationLeadTags", []),
                     **relationship_fields,
                     **(
                         {"relationshipTags": relationship_tags}
                         if normalized_suite == "relationship-world"
                         else {}
                     ),
                 }
             )
            if actual_message:
                conversation_history.append(
                    {
                        "role": "user",
                        "content": actual_message,
                        "intent": current_intent,
                        "relationshipStage": case.relationship_stage,
                    }
                )
            conversation_history.append(
                {
                    "role": "assistant",
                    "content": result.reply,
                    "intent": current_intent,
                    "relationshipStage": case.relationship_stage,
                }
            )
            if budget_tracker.stop_reason is not None:
                break

        if budget_tracker.stop_reason is not None and not turn_records:
            break

        case_turns = case.dialogue_turns()
        progression_scores = score_dialogue_progression(
            [
                record.get("reply", "") if isinstance(record, dict) else ""
                for record in turn_records
            ],
            case_turns,
        )
        affection_variation_scores = score_affection_variation(
            [
                record.get("reply", "") if isinstance(record, dict) else ""
                for record in turn_records
            ],
            case_turns,
            turn_records,
        )
        conversation_lead_variation_scores = score_conversation_lead_variation(
            [
                record.get("reply", "") if isinstance(record, dict) else ""
                for record in turn_records
            ],
            case_turns,
            [
                record.get("score", {}) if isinstance(record, dict) else {}
                for record in turn_records
            ],
            case=case,
        )
        affection_pacing_scores = score_affection_pacing(
            [
                record.get("reply", "") if isinstance(record, dict) else ""
                for record in turn_records
            ],
            case_turns,
            [
                record if isinstance(record, dict) else {}
                for record in turn_records
            ],
            case=case,
        )
        progression_tags: set[str] = set()
        novel_expected_terms: list[str] = []
        max_overlap = 0.0
        for index, progression in enumerate(progression_scores):
            if isinstance(progression, dict):
                progression_tags.update(
                    str(tag) for tag in progression.get("tags", [])
                )
                overlap = progression.get("overlap")
                if isinstance(overlap, (int, float)) and not isinstance(overlap, bool):
                    max_overlap = max(max_overlap, float(overlap))
                for term in progression.get("novelExpectedTerms", []):
                    if isinstance(term, str) and term not in novel_expected_terms:
                        novel_expected_terms.append(term)
            if index >= len(turn_records):
                continue
            turn_record = turn_records[index]
            if "reply" not in turn_record or not isinstance(progression, dict):
                continue
            turn_record["progression"] = progression
            score = turn_record.get("score")
            if not isinstance(score, dict):
                continue
            if progression.get("repeated") is True:
                score["tags"] = sorted({
                    *(str(tag) for tag in score.get("tags", [])),
                    "repeated_turn_content",
                })
                score["passed"] = False

        for index, variation in enumerate(affection_variation_scores):
            if index >= len(turn_records):
                continue
            turn_record = turn_records[index]
            if "reply" not in turn_record or not isinstance(variation, dict):
                continue
            turn_record["affectionVariation"] = variation
            variation_tags = {
                str(tag) for tag in variation.get("tags", []) if isinstance(tag, str)
            }
            progression_tags.update(variation_tags)
            score = turn_record.get("score")
            if not isinstance(score, dict) or variation.get("mechanical") is not True:
                continue
            score["tags"] = sorted({
                *(str(tag) for tag in score.get("tags", [])),
                *variation_tags,
            })
            score["passed"] = False

        for index, variation in enumerate(conversation_lead_variation_scores):
            if index >= len(turn_records):
                continue
            turn_record = turn_records[index]
            if "reply" not in turn_record or not isinstance(variation, dict):
                continue
            turn_record["conversationLeadVariation"] = variation
            variation_tags = {
                str(tag) for tag in variation.get("tags", []) if isinstance(tag, str)
            }
            progression_tags.update(variation_tags)
            score = turn_record.get("score")
            if not isinstance(score, dict) or variation.get("mechanical") is not True:
                continue
            score["tags"] = sorted({
                *(str(tag) for tag in score.get("tags", [])),
                *variation_tags,
            })
            score["passed"] = False

        affection_pacing_tags: set[str] = set()
        for index, pacing in enumerate(affection_pacing_scores):
            if index >= len(turn_records) or not isinstance(pacing, dict):
                continue
            turn_record = turn_records[index]
            if "reply" not in turn_record:
                continue
            turn_record["affectionPacing"] = pacing
            pacing_tags = {
                str(tag)
                for tag in pacing.get("tags", [])
                if isinstance(tag, str)
            }
            affection_pacing_tags.update(pacing_tags)
            score = turn_record.get("score")
            if not isinstance(score, dict):
                continue
            if pacing_tags.intersection(
                {
                    "strong_affection_over_budget",
                    "repeated_strong_affection_family",
                }
            ):
                score["tags"] = sorted({
                    *(str(tag) for tag in score.get("tags", [])),
                    *pacing_tags,
                })
                score["passed"] = False
        progression_tags.update(affection_pacing_tags)

        progression_record: dict[str, object] = {
            "passed": bool(turn_records)
            and len(turn_records) == len(case_turns)
            and all(
                isinstance(progression, dict)
                and progression.get("repeated") is not True
                and (
                    index >= len(affection_variation_scores)
                    or affection_variation_scores[index].get("mechanical") is not True
                )
                and (
                    index >= len(conversation_lead_variation_scores)
                    or conversation_lead_variation_scores[index].get("mechanical") is not True
                )
                and "reply" in turn_records[index]
                for index, progression in enumerate(progression_scores)
                if index < len(turn_records)
            ),
            "tags": sorted(progression_tags),
            "overlap": round(max_overlap, 4),
            "novelExpectedTerms": novel_expected_terms[:20],
        }
        passed_turn_count = sum(
            1
            for record in turn_records
            if isinstance(record.get("score"), dict)
            and record["score"].get("passed") is True
        )
        failed_turn_count = max(0, len(case_turns) - passed_turn_count)
        case_passed = (
            len(turn_records) == len(case_turns)
            and len(turn_records) > 0
            and all(
                "reply" in record
                and isinstance(record.get("score"), dict)
                and record["score"].get("passed") is True
                for record in turn_records
            )
        )
        first_result = next((item for item in turn_records if "reply" in item), None)
        first_initiative = next(
            (item for item in turn_records if "initiativeDetected" in item),
            None,
        )
        initiative_tags = sorted({
            str(tag)
            for item in turn_records
            for tag in item.get("initiativeTags", [])
            if isinstance(item, dict) and isinstance(tag, str)
        })[:20]
        case_mechanical_restatement_count = sum(
            1
            for item in turn_records
            if isinstance(item, dict)
            and item.get("mechanicalRestatement") is True
        )
        affection_pacing_record: dict[str, object] = {
            "eligibleTurns": sum(
                not bool(item.get("skipped"))
                for item in affection_pacing_scores
                if isinstance(item, dict)
            ),
            "skippedTurns": sum(
                bool(item.get("skipped"))
                for item in affection_pacing_scores
                if isinstance(item, dict)
            ),
            "strongAffectionTurns": sum(
                bool(item.get("strongAffection"))
                for item in affection_pacing_scores
                if isinstance(item, dict)
            ),
            "overBudgetCount": sum(
                bool(item.get("overBudget"))
                for item in affection_pacing_scores
                if isinstance(item, dict)
            ),
            "repeatedStrongFamilyCount": sum(
                "repeated_strong_affection_family" in item.get("tags", [])
                for item in affection_pacing_scores
                if isinstance(item, dict)
            ),
            "tags": sorted(affection_pacing_tags),
            "passed": not bool(
                affection_pacing_tags.intersection(
                    {
                        "strong_affection_over_budget",
                        "repeated_strong_affection_family",
                    }
                )
            ),
        }
        case_record: dict[str, object] = {
            "caseId": case.case_id,
            "caseNumber": case_numbers.get(case.case_id),
            "suite": normalized_suite,
            "profileKey": case.profile_key,
            "npcId": _canonical_case_npc_id(case),
            "displayName": quality_case_display_name(case),
            "channel": case.channel,
            "friendshipHearts": (
                dict(case.game_state).get("friendshipHearts", case.friendship_hearts)
            ),
            "flirtIntensity": case.flirt_intensity,
            "adultConsensual": case.adult_consensual,
            "romanceEligible": _case_romance_eligible(case),
            "relationshipContext": case.relationship_context or case.story_progress,
            "relationshipStage": case.relationship_stage,
            "gameState": dict(case.game_state),
            "storyProgress": case.story_progress,
            "completedEventIds": list(case.completed_event_ids),
            "eventPairId": case.event_pair_id,
            "eventId": case.event_id,
            "eventCondition": case.event_condition,
            "eventSummary": case.event_summary,
            "eventSourceStatus": case.event_source_status,
            "eventEvidence": list(case.event_evidence),
            "genderPresentation": case.gender_presentation,
            "topicSeed": case.topic_seed,
            "topicKeywords": list(case.topic_keywords),
            "continuationMode": case.continuation_mode,
            "followUpMode": case.follow_up_mode,
            "playerSimulationStyle": case.player_simulation_style,
            "turnCount": len(case_turns),
            "passedTurnCount": passed_turn_count,
            "failedTurnCount": failed_turn_count,
            "casePassed": case_passed,
            "progression": progression_record,
            "affectionPacing": affection_pacing_record,
            "turns": turn_records,
            "initiativeExpectation": (
                first_initiative.get("initiativeExpectation", "none")
                if first_initiative
                else "none"
            ),
            "initiativeKind": (
                first_initiative.get("initiativeKind", "none")
                if first_initiative
                else "none"
            ),
            "initiativeDetected": (
                first_initiative.get("initiativeDetected", False)
                if first_initiative
                else False
            ),
            "initiativeTags": initiative_tags,
            "mechanicalRestatement": case_mechanical_restatement_count > 0,
            "mechanicalRestatementCount": case_mechanical_restatement_count,
            "personalAffectionDetected": (
                first_initiative.get("personalAffectionDetected", False)
                if first_initiative
                else False
            ),
            "companionshipDetected": (
                first_initiative.get("companionshipDetected", False)
                if first_initiative
                else False
            ),
            "specificPlanDetected": (
                first_initiative.get("specificPlanDetected", False)
                if first_initiative
                else False
            ),
            "affectionEvidence": (
                first_initiative.get("affectionEvidence", [])
                if first_initiative
                else []
            ),
            "affectionShape": (
                first_initiative.get("affectionShape", "")
                if first_initiative
                else ""
            ),
            "answeredCurrentTopic": (
                first_result.get("answeredCurrentTopic", False)
                if first_result
                else False
            ),
            "conversationLeadDetected": (
                first_result.get("conversationLeadDetected", False)
                if first_result
                else False
            ),
            "conversationLeadKind": (
                first_result.get("conversationLeadKind", "")
                if first_result
                else ""
            ),
            "conversationLeadEvidence": (
                first_result.get("conversationLeadEvidence", [])
                if first_result
                else []
            ),
            "conversationLeadTags": (
                first_result.get("conversationLeadTags", [])
                if first_result
                else []
            ),
            "elapsedMs": int((perf_counter() - case_started_at) * 1000),
        }
        if first_result is not None:
            case_record.update(
                {
                    "reply": first_result.get("reply"),
                    "provider": first_result.get("provider"),
                    "fallback": first_result.get("fallback"),
                    "latencyMs": first_result.get("latencyMs"),
                    "warnings": first_result.get("warnings", []),
                    "usage": first_result.get("usage"),
                    "score": first_result.get("score"),
                    "styleQuality": first_result.get("styleQuality"),
                }
            )
        elif turn_records:
            case_record["error"] = turn_records[0].get("error", "ProviderError")
        records.append(case_record)
        if budget_tracker.stop_reason is not None:
            break

    successful = sum("reply" in record for record in records)
    usage_totals = _merge_usages(all_usages)
    usage_summary: dict[str, object] = {
        "inputTokens": usage_totals.get("inputTokens", 0) if usage_totals else 0,
        "outputTokens": usage_totals.get("outputTokens", 0) if usage_totals else 0,
        "totalTokens": usage_totals.get("totalTokens", 0) if usage_totals else 0,
        "usageReturnedTurns": usage_returned_turns,
        "missingUsageTurns": successful_turns - usage_returned_turns,
    }
    affection_pacing_summary: dict[str, object] = {
        "eligibleTurns": sum(
            int(record.get("affectionPacing", {}).get("eligibleTurns", 0))
            for record in records
            if isinstance(record.get("affectionPacing"), dict)
        ),
        "skippedTurns": sum(
            int(record.get("affectionPacing", {}).get("skippedTurns", 0))
            for record in records
            if isinstance(record.get("affectionPacing"), dict)
        ),
        "strongAffectionTurns": sum(
            int(record.get("affectionPacing", {}).get("strongAffectionTurns", 0))
            for record in records
            if isinstance(record.get("affectionPacing"), dict)
        ),
        "overBudgetCount": sum(
            int(record.get("affectionPacing", {}).get("overBudgetCount", 0))
            for record in records
            if isinstance(record.get("affectionPacing"), dict)
        ),
        "repeatedStrongFamilyCount": sum(
            int(record.get("affectionPacing", {}).get("repeatedStrongFamilyCount", 0))
            for record in records
            if isinstance(record.get("affectionPacing"), dict)
        ),
        "tags": sorted({
            str(tag)
            for record in records
            for tag in record.get("affectionPacing", {}).get("tags", [])
            if isinstance(record.get("affectionPacing"), dict)
            and isinstance(tag, str)
        }),
    }
    relationship_summary: dict[str, object] | None = None
    if normalized_suite == "relationship-world":
        relationship_summary = {
            "focusedTurnCount": sum(relationship_focus_counts.values()),
            "focusCounts": dict(sorted(relationship_focus_counts.items())),
            "tagCounts": dict(sorted(relationship_tag_counts.items())),
            "tags": sorted(relationship_tag_counts),
        }
    resolved_input_price = _resolve_price(
        input_price_per_million,
        "BRIDGE_CLOUD_INPUT_PRICE_PER_MILLION",
    )
    resolved_output_price = _resolve_price(
        output_price_per_million,
        "BRIDGE_CLOUD_OUTPUT_PRICE_PER_MILLION",
    )
    summary: dict[str, object] = {
        "schemaVersion": 2,
        "suite": normalized_suite,
        "caseCount": len(selected_cases),
        "processedCaseCount": len(records),
        "processedTurnCount": sum(
            len(record.get("turns", []))
            for record in records
            if isinstance(record.get("turns", []), list)
        ),
        "successful": successful,
        "errors": len(records) - successful,
        "turnCount": sum(len(case.dialogue_turns()) for case in selected_cases),
        "requestCount": request_count,
        "npcRequestCount": npc_request_count,
        "playerInputRequestCount": player_input_request_count,
        "playerInputGenerationCount": player_input_generation_count,
        "playerInputValidCount": player_input_valid_count,
        "playerInputInvalidCount": player_input_invalid_count,
        "playerInputQualityTags": sorted(player_input_quality_tags)[:20],
        "successfulTurns": successful_turns,
        "failedTurns": failed_turns,
        "playerInputUsageReturned": player_input_usage_returned,
        "npcRetryCount": npc_retry_count,
        "playerInputRetryCount": player_input_retry_count,
        "affectionPacing": affection_pacing_summary,
        "budget": evaluation_budget.as_dict(),
        "budgetStopReason": budget_tracker.stop_reason,
        # `--max-requests` 截断 ⇒ 本批与完整跑覆盖不同，**不可跨批比较**。
        "truncated": truncated,
        "truncatedReason": "max_requests" if truncated else None,
        "passed": sum(
            record.get("casePassed") is True
            for record in records
        ),
        "passedCases": sum(
            record.get("casePassed") is True for record in records
        ),
        "passedTurns": sum(
            int(record.get("passedTurnCount", 0))
            for record in records
            if isinstance(record.get("passedTurnCount", 0), int)
            and not isinstance(record.get("passedTurnCount", 0), bool)
        ),
        "turnPassRate": (
            sum(
                int(record.get("passedTurnCount", 0))
                for record in records
                if isinstance(record.get("passedTurnCount", 0), int)
                and not isinstance(record.get("passedTurnCount", 0), bool)
            )
            / sum(len(case.dialogue_turns()) for case in selected_cases)
            if sum(len(case.dialogue_turns()) for case in selected_cases)
            else 0.0
        ),
        "casePassRate": (
            sum(record.get("casePassed") is True for record in records)
            / len(selected_cases)
            if selected_cases
            else 0.0
        ),
        "initiativeDetected": sum(
            1
            for record in records
            for turn in record.get("turns", [])
            if isinstance(turn, dict) and turn.get("initiativeDetected") is True
        ),
        "initiativeTags": sorted({
            str(tag)
            for record in records
            for tag in record.get("initiativeTags", [])
            if isinstance(tag, str)
        })[:20],
        "mechanicalRestatementCount": mechanical_restatement_count,
        "usage": usage_summary,
        "estimatedCost": _estimated_cost(
            usage_summary,
            input_price_per_million=resolved_input_price,
            output_price_per_million=resolved_output_price,
        ),
        "elapsedMs": int((perf_counter() - started_at) * 1000),
        "profileIndex": stable_artifact_path(index_store.index_path, root=ROOT),
    }
    if relationship_summary is not None:
        summary["relationshipDiagnostics"] = relationship_summary
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    _write_jsonl(destination / "results.jsonl", records)
    (destination / "summary.json").write_text(
        json.dumps(_safe_record(summary), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return summary


def _build_provider(
    provider: str,
    *,
    endpoint: str | None,
    model: str | None,
    timeout: float | None,
):
    if provider == "fake":
        return FakeProvider()
    if provider == "local":
        return OllamaNativeProvider(
            ProviderSettings(
                name="local",
                url=endpoint or os.getenv("BRIDGE_LOCAL_URL") or DEFAULT_ENDPOINT,
                model=model or os.getenv("BRIDGE_LOCAL_MODEL") or DEFAULT_MODEL,
                timeout=timeout or _env_timeout("BRIDGE_LOCAL_TIMEOUT", 45.0),
                enabled=True,
                api_mode="ollama",
            )
        )
    if provider == "cloud":
        cloud_settings = ProviderSettings.from_env(
            "BRIDGE_CLOUD",
            name="cloud",
            default_timeout=15.0,
        )
        return OpenAICompatibleProvider(
            ProviderSettings(
                name="cloud",
                url=endpoint or cloud_settings.url or DEFAULT_CLOUD_ENDPOINT,
                model=model or cloud_settings.model or DEFAULT_CLOUD_MODEL,
                api_key=cloud_settings.api_key,
                timeout=timeout or cloud_settings.timeout,
                enabled=True,
                api_mode="openai",
            )
        )
    raise ValueError(f"unsupported evaluation provider: {provider}")


def _env_timeout(name: str, default: float) -> float:
    value = os.getenv(name, str(default))
    try:
        timeout = float(value)
    except ValueError:
        return default
    return timeout if timeout > 0 else default


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行五个角色的固定质量评测")
    parser.add_argument("--profile-index", type=Path, default=DEFAULT_PROFILE_INDEX)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT
        / "artifacts"
        / "character-quality-eval"
        / datetime.now().strftime("%Y%m%d-%H%M%S"),
    )
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument(
        "--provider",
        choices=("local", "cloud", "fake"),
        default="local",
    )
    parser.add_argument(
        "--confirm-cloud",
        action="store_true",
        help="确认消耗云端 Token；不传且 --provider cloud 时只打印计划（dry-run）",
    )
    parser.add_argument("--input-price-per-million", type=float, default=None)
    parser.add_argument("--output-price-per-million", type=float, default=None)
    parser.add_argument("--suite", choices=QUALITY_SUITE_IDS, default="default")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--economical",
        action="store_true",
        help="只跑少量案例、使用 compact Prompt，并限制重试与预算",
    )
    parser.add_argument(
        "--compact-prompt",
        action="store_true",
        default=None,
        help=(
            "用线上口径构造 prompt（compactPrompt=true），与 --economical 解耦。"
            "默认沿历史行为走 false —— 那条评测路径比游戏端大约 74%% 字符，"
            "每条话题素材的出现次数只有线上的一半，"
            "所以「离线测不出差异」不能直接推成「线上没差异」"
        ),
    )
    parser.add_argument("--max-requests", type=int, default=None)
    parser.add_argument("--max-total-tokens", type=int, default=None)
    parser.add_argument(
        "--dynamic-player-input",
        action="store_true",
        default=None,
        help="在经济模式下显式启用模型生成的后续玩家输入",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="跑前闸门：打印三问 + 预算预估并退出，**零请求**（规范 §二/§四）",
    )
    parser.add_argument(
        "--stage",
        default=None,
        help=(
            "按关系阶段筛例（逗号分隔，如 stranger,parent）。"
            "⚠ --limit 只能取前 N 个，够不到追加在末尾的新 case"
        ),
    )
    return parser.parse_args(argv)


# 合法关系阶段。与 `character_quality_eval._STAGE_TO_GATE` 的档位一致，
# 但**多一个 stranger** —— 它在关系门之前，所以不在门表里（见 active-work 2026-09-28）。
RELATIONSHIP_STAGES: tuple[str, ...] = (
    "acquaintance",
    "friend",
    "close",
    "dating",
    "married",
    "parent",
    "stranger",
)


def _parse_stages(raw: str | None) -> list[str] | None:
    """解析 `--stage a,b,a`：去重、保序、校验档名。

    ⚠ 档名写错必须报错：静默跑 0 个 case 会被读成「跑了但没问题」，
    那比报错坏得多。
    """
    if raw is None:
        return None
    stages: list[str] = []
    for part in raw.split(","):
        name = part.strip()
        if not name:
            continue
        if name not in RELATIONSHIP_STAGES:
            raise ValueError(
                f"未知关系阶段 {name!r}；可选：{', '.join(RELATIONSHIP_STAGES)}"
            )
        if name not in stages:
            stages.append(name)
    return stages or None


def _select_cases(
    suite_cases: list,
    *,
    max_cases: int | None,
    stages: list[str] | None = None,
) -> list:
    """选例的**唯一**实现 —— `main()` 与 `_print_plan()` 必须走同一条路。

    顺序要紧：**先按阶段筛，再截断**。反过来的话
    `--stage stranger --limit 5` 会先取前 5 个（全是别的阶段）再筛成空集。
    """
    cases = list(suite_cases)
    if stages:
        wanted = set(stages)
        cases = [case for case in cases if case.relationship_stage in wanted]
    if max_cases is not None:
        cases = cases[: max(0, max_cases)]
    return cases


def _print_plan(args: argparse.Namespace, stages: list[str] | None) -> int:
    """跑前闸门：零请求地把「该不该跑」摊在屏幕上。

    ⭐ 为什么做成代码，而不是只写在 `docs/eval-runbook-2026-09-28.md` 里：
    文档里的规则**跑起来照样能违反**（审计里就有批次在统计上无法判定）。
    做成 `--plan` 之后，三问、不可比警告、预算预估是每次开跑前都会被打印的。
    """
    default_budget = (
        EvaluationBudget.economical() if args.economical else EvaluationBudget()
    )
    # 选例走 _select_cases() —— 与 main() 同一份实现，不可能漂移。
    max_cases = args.limit if args.limit is not None else default_budget.max_cases
    suite_cases = quality_cases_for_suite(args.suite)
    limit = len(suite_cases) if max_cases is None else max_cases
    cases = _select_cases(suite_cases, max_cases=limit, stages=stages)
    turn_count = sum(len(case.dialogue_turns()) for case in cases)
    # 重试余量取 20%：实测全库 24.7% 的 case 发生过重试，20% 是保守下界。
    # `(n * 6 + 4) // 5` 就是 ceil(n × 1.2)，避免为一个除法引入新 import。
    estimated_requests = (turn_count * 6 + 4) // 5
    # ⚠ 每次请求的 token 量按模式分开，**不要取一个折中平均**：
    #   · compact Prompt（--economical）：全库均值 ≈ 5,000
    #   · 完整 Prompt：实测 20260928-211944 批次 = 7,820（23 请求 / 179,867 token）
    # 两者差 56%，用错模式估出来的预算会差一倍。
    estimated_tokens = estimated_requests * (5000 if args.economical else 7800)
    # 美元按**实测单价**估：20260928-211944 批次 23 请求吃掉池 1 周额度的 2.2%
    #（$35 × 2.2% ≈ $0.77）⇒ ≈ $0.033/请求。
    # ⚠ economical 那个数按 token 比例折算而来，**没有实测过**，只给量级。
    estimated_cost_usd = round(
        estimated_requests * (0.021 if args.economical else 0.033), 2
    )

    warnings: list[str] = []
    if args.max_requests is not None:
        warnings.append(
            "⛔ 用了 --max-requests：它只让本批覆盖前若干个请求 "
            "⇒ 与完整跑的问题集不同 ⇒ **不可比**，两批放进同一张表会得出错误结论，"
            "而且最终往往要重跑一次（更贵）。要压规模请改用 --limit。"
        )
    if args.max_total_tokens is not None:
        warnings.append(
            "⚠ 用了 --max-total-tokens：预算触顶的批次会被标记为不完整，不参与对比。"
        )
    if stages and not cases:
        warnings.append(
            f"⛔ --stage {'/'.join(stages)} 在 suite {args.suite} 里一个 case 都没匹配上 —— "
            "别把它读成「跑了但没问题」。"
        )
    if turn_count and turn_count < 36:
        warnings.append(
            f"⚠ 本批 {turn_count} 轮 < 36 轮：按实测 σ ≈ 24 字，这个规模 "
            "**只能走 L1 人读档**（只陈述样例，不做统计声明）。"
        )

    print(
        json.dumps(
            {
                "plan": True,
                "suite": args.suite,
                "stages": stages or [],
                "caseIds": [case.case_id for case in cases],
                "caseCount": len(cases),
                "turnCount": turn_count,
                "estimatedRequests": estimated_requests,
                "estimatedTokens": estimated_tokens,
                "estimatedCostUsd": estimated_cost_usd,
                "gate": {
                    "question": "① 这次要回答哪一个问题？（写一句；写不出来就不该跑）",
                    "expectedEffect": (
                        "② 预期效应多大？< 17 字 ⇒ 只能走 L1 人读档；"
                        "要数值结论须先用 scripts/analyze_ab_power.py 算样本量"
                    ),
                    "budget": (
                        "③ 预算是否可接受？见 estimatedRequests / estimatedTokens；"
                        "开工前查池余量 node E:\\workspace\\hub\\scripts\\_cc_pools.mjs"
                    ),
                },
                "warnings": warnings,
                "note": (
                    "未发起任何请求。这是**跑前闸门**，不是许可 —— "
                    "三问答完再决定跑不跑。"
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    args = _parse_args(argv)
    try:
        stages = _parse_stages(args.stage)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.plan:
        # 放在 cloud 的 dry-run **之前**：`--plan` 对**所有** provider 都该生效，
        # 它回答的是「该不该跑」，而不是「云端要不要确认」。
        return _print_plan(args, stages)
    if args.provider == "cloud" and not args.confirm_cloud:
        # 成本护栏（与 run_group_dialogue_cloud_batch.py 同一约定）：云端是本项目最贵的入口，
        # 不传 --confirm-cloud 时只输出计划并退出，绝不静默联网消耗 Token。
        print(
            json.dumps(
                {
                    "dryRun": True,
                    "provider": "cloud",
                    "suite": args.suite,
                    "limit": args.limit,
                    "maxRequests": args.max_requests,
                    "maxTotalTokens": args.max_total_tokens,
                    "outputDir": str(args.output_dir),
                    "note": "未发起任何云端请求；确认后加 --confirm-cloud 重跑。",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    default_budget = (
        EvaluationBudget.economical() if args.economical else EvaluationBudget()
    )
    budget = EvaluationBudget(
        max_cases=(
            args.limit
            if args.limit is not None
            else default_budget.max_cases
        ),
        max_requests=(
            args.max_requests
            if args.max_requests is not None
            else default_budget.max_requests
        ),
        max_total_tokens=(
            args.max_total_tokens
            if args.max_total_tokens is not None
            else default_budget.max_total_tokens
        ),
        max_npc_retries=default_budget.max_npc_retries,
        max_player_retries=default_budget.max_player_retries,
        compact_prompt=(
            default_budget.compact_prompt
            if args.compact_prompt is None
            else args.compact_prompt
        ),
        dynamic_player_input=(
            default_budget.dynamic_player_input
            if args.dynamic_player_input is None
            else args.dynamic_player_input
        ),
    )
    suite_cases = quality_cases_for_suite(args.suite)
    limit = len(suite_cases) if budget.max_cases is None else budget.max_cases
    cases = _select_cases(suite_cases, max_cases=limit, stages=stages)
    summary = run_evaluation(
        profile_index=args.profile_index,
        output_dir=args.output_dir,
        cases=cases,
        endpoint=args.endpoint,
        model=args.model,
        timeout=args.timeout,
        provider=args.provider,
        suite=args.suite,
        input_price_per_million=args.input_price_per_million,
        output_price_per_million=args.output_price_per_million,
        budget=budget,
        truncated=args.max_requests is not None,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
