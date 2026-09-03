from __future__ import annotations

import argparse
from datetime import datetime
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
    diagnose_affection_initiative,
    quality_cases_for_suite,
    score_affection_variation,
    score_dialogue_progression,
    score_character_reply,
    score_generated_player_input,
    _turn_intent,
    validate_quality_cases,
)
from stardew_ai_bridge.artifact_paths import stable_artifact_path  # noqa: E402
from stardew_ai_bridge.config import ProviderSettings, load_local_env  # noqa: E402
from stardew_ai_bridge.models import (  # noqa: E402
    DialogueTestRequest,
    ProviderResult,
    ProviderUsage,
)
from stardew_ai_bridge.profile_index import ProfileIndexStore  # noqa: E402
from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: E402
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
    ROOT / "data" / "generated" / "vanilla-sve-rasmodia-profile-index-zh-CN.json"
)
DEFAULT_ENDPOINT = "http://127.0.0.1:11435/api/chat"
DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_CLOUD_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_CLOUD_MODEL = "gpt-5.6-terra"


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


def _resolve_index(value: ProfileIndexStore | Path | str) -> ProfileIndexStore:
    if isinstance(value, ProfileIndexStore):
        return value
    return ProfileIndexStore(Path(value))


def _build_request(
    case: CharacterQualityCase,
    *,
    message: str | None = None,
    history: list[dict[str, str]] | None = None,
    intent: str | None = None,
) -> DialogueTestRequest:
    game_state = dict(case.game_state)
    game_state.setdefault("friendshipHearts", _relationship_hearts(case.relationship_stage))
    game_state["sourceMods"] = list(case.source_mods)
    if case.completed_event_ids:
        game_state["completedEventIds"] = list(case.completed_event_ids)
    return DialogueTestRequest(
        npcId=case.npc_id,
        displayName=case.display_name,
        sourceMods=list(case.source_mods),
        recentFacts=[case.story_progress] if case.story_progress else [],
        history=[dict(item) for item in (case.history if history is None else history)],
        message=case.message if message is None else message,
        intent=case.intent if intent is None else intent,
        channel=case.channel,
        gameState=game_state,
    )


def _build_context(
    builder: ContextBuilder,
    case: CharacterQualityCase,
    *,
    message: str | None = None,
    history: list[dict[str, str]] | None = None,
    turn: object | None = None,
    intent: str | None = None,
) -> dict[str, Any]:
    game_state = dict(case.game_state)
    game_state.setdefault("friendshipHearts", _relationship_hearts(case.relationship_stage))
    game_state["relationshipStage"] = case.relationship_stage
    game_state["sourceMods"] = list(case.source_mods)
    if case.completed_event_ids:
        game_state["completedEventIds"] = list(case.completed_event_ids)
    game_state["relationshipStage"] = case.relationship_stage
    quality_context: dict[str, object] = {
        "flirtIntensity": case.flirt_intensity,
        "adultConsensual": case.adult_consensual,
        "romanceEligible": (
            case.romance_eligible
            if case.romance_eligible is not None
            else case.npc_id in {"Wizard", "Sophia", "Shane", "Sebastian", "Alex"}
        ),
        "relationshipContext": case.relationship_context or case.story_progress,
        "genderPresentation": case.gender_presentation,
    }
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
    return builder.build(
        {
            "npcId": case.npc_id,
            "displayName": case.display_name,
            "sourceMods": list(case.source_mods),
            "recentFacts": [case.story_progress] if case.story_progress else [],
            "message": case.message if message is None else message,
            "intent": case.intent if intent is None else intent,
            "channel": case.channel,
            "qualityContext": quality_context,
            "history": [dict(item) for item in (case.history if history is None else history)],
            "gameState": game_state,
        }
    )


def _safe_record(record: dict[str, object]) -> dict[str, object]:
    return dict(sanitize_quality_artifact(record))  # type: ignore[arg-type]


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
    transcript = "\n".join(
        f"{item.get('role', 'unknown')}: {str(item.get('content', ''))[:500]}"
        for item in history[-6:]
    )
    style = case.player_simulation_style or "自然回应上一条 NPC 回复"
    intimacy_boundary = (
        "这是高亲密关系案例，可以回应亲密信号，但不要凭空添加未发生的动作。"
        if case.flirt_intensity != "none"
        else "这是普通熟人或朋友对照案例，只保持日常聊天，不调情、不升级关系。"
    )
    return [
        {
            "role": "system",
            "name": "player_simulator",
            "content": (
                "你是对话质量测试中的真实玩家，不是 NPC，也不是评审。"
                "只输出一句玩家会发送的简体中文消息，不要解释，不要加引号。"
                "从上一条 NPC 回复中自然接住一个具体对象、动作、情绪或安排，"
                "用真实反应、认可、轻微追问或亲密回应继续聊；不要复述 NPC 原句，"
                "不要使用‘你刚才提到的……后来怎么样了’这类测试模板，也不能只摘抄一个词。"
                "不能用和上一条语义无关的泛泛寒暄填充。"
                "最多 60 个汉字，最多保留一个追问点。"
                "不要复述测试目标，不要提到测试、评分、关键词、模型或提示词，"
                "不要替 NPC 说话，也不要凭空添加上一条回复没有依据的事实。"
                f"{intimacy_boundary}本次是第 {turn_number} 轮续聊，玩家反应方式：{style}。"
            ),
        },
        {
            "role": "user",
            "name": "npc_reply",
            "content": (
                f"NPC（{case.display_name}）刚才的回复：\n{previous_reply[:1600]}\n\n"
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
) -> dict[str, object]:
    """使用实际 ContextBuilder/PromptBuilder 对固定角色场景做脱敏评测。"""

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
                turn_records.append(
                    {
                        "turnId": turn.turn_id,
                        "intent": current_intent,
                        "playerInput": actual_message,
                        "playerInputSource": player_input_source,
                        "playerInputQuality": player_input_quality,
                        "playerInputProvider": player_input_provider,
                        "playerInputLatencyMs": player_input_latency_ms,
                        "playerInputUsage": player_input_usage,
                        "error": type(exc).__name__,
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
                turn=turn,
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
                turn,
                result.reply,
                player_input=actual_message,
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
                    "playerInput": actual_message,
                    "playerInputSource": player_input_source,
                    "playerInputQuality": player_input_quality,
                    "playerInputProvider": player_input_provider,
                    "playerInputLatencyMs": player_input_latency_ms,
                    "playerInputUsage": player_input_usage,
                    "reply": result.reply,
                    "provider": result.provider,
                    "fallback": result.fallback,
                    "latencyMs": result.latency_ms,
                    "warnings": list(result.warnings),
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
                }
            )
            if actual_message:
                conversation_history.append(
                    {"role": "user", "content": actual_message}
                )
            conversation_history.append(
                {"role": "assistant", "content": result.reply}
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
        case_record: dict[str, object] = {
            "caseId": case.case_id,
            "caseNumber": case_numbers.get(case.case_id),
            "suite": normalized_suite,
            "profileKey": case.profile_key,
            "npcId": case.npc_id,
            "displayName": case.display_name,
            "channel": case.channel,
            "friendshipHearts": (
                dict(case.game_state).get("friendshipHearts", case.friendship_hearts)
            ),
            "flirtIntensity": case.flirt_intensity,
            "adultConsensual": case.adult_consensual,
            "romanceEligible": (
                case.romance_eligible
                if case.romance_eligible is not None
                else case.npc_id in {"Wizard", "Sophia", "Shane", "Sebastian", "Alex"}
            ),
            "relationshipContext": case.relationship_context or case.story_progress,
            "relationshipStage": case.relationship_stage,
            "gameState": dict(case.game_state),
            "storyProgress": case.story_progress,
            "completedEventIds": list(case.completed_event_ids),
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
        "budget": evaluation_budget.as_dict(),
        "budgetStopReason": budget_tracker.stop_reason,
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
    parser.add_argument("--input-price-per-million", type=float, default=None)
    parser.add_argument("--output-price-per-million", type=float, default=None)
    parser.add_argument("--suite", choices=QUALITY_SUITE_IDS, default="default")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--economical",
        action="store_true",
        help="只跑少量案例、使用 compact Prompt，并限制重试与预算",
    )
    parser.add_argument("--max-requests", type=int, default=None)
    parser.add_argument("--max-total-tokens", type=int, default=None)
    parser.add_argument(
        "--dynamic-player-input",
        action="store_true",
        default=None,
        help="在经济模式下显式启用模型生成的后续玩家输入",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    args = _parse_args(argv)
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
        compact_prompt=default_budget.compact_prompt,
        dynamic_player_input=(
            default_budget.dynamic_player_input
            if args.dynamic_player_input is None
            else args.dynamic_player_input
        ),
    )
    suite_cases = quality_cases_for_suite(args.suite)
    limit = len(suite_cases) if budget.max_cases is None else budget.max_cases
    cases = suite_cases[: max(0, min(limit, len(suite_cases)))]
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
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
