from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bridge" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stardew_ai_bridge.character_quality_eval import (  # noqa: E402
    DEFAULT_CASES,
    CharacterQualityCase,
    score_character_reply,
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
    OllamaNativeProvider,
    OpenAICompatibleProvider,
)
from stardew_ai_bridge.behavior_quality import sanitize_quality_artifact  # noqa: E402
from stardew_ai_bridge.dialogue_style_quality import (  # noqa: E402
    analyze_dialogue_style,
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
) -> DialogueTestRequest:
    game_state = dict(case.game_state)
    game_state.setdefault("friendshipHearts", _relationship_hearts(case.relationship_stage))
    game_state["sourceMods"] = list(case.source_mods)
    return DialogueTestRequest(
        npcId=case.npc_id,
        displayName=case.display_name,
        sourceMods=list(case.source_mods),
        recentFacts=[case.story_progress] if case.story_progress else [],
        history=[dict(item) for item in (case.history if history is None else history)],
        message=message or case.message,
        channel=case.channel,
        gameState=game_state,
    )


def _build_context(
    builder: ContextBuilder,
    case: CharacterQualityCase,
    *,
    message: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    game_state = dict(case.game_state)
    game_state.setdefault("friendshipHearts", _relationship_hearts(case.relationship_stage))
    game_state["relationshipStage"] = case.relationship_stage
    game_state["sourceMods"] = list(case.source_mods)
    return builder.build(
        {
            "npcId": case.npc_id,
            "displayName": case.display_name,
            "sourceMods": list(case.source_mods),
            "recentFacts": [case.story_progress] if case.story_progress else [],
            "message": message or case.message,
            "channel": case.channel,
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


def run_evaluation(
    *,
    profile_index: ProfileIndexStore | Path | str,
    output_dir: Path | str,
    cases: Iterable[CharacterQualityCase] = DEFAULT_CASES,
    endpoint: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
    provider: str = "local",
    input_price_per_million: float | None = None,
    output_price_per_million: float | None = None,
) -> dict[str, object]:
    """使用实际 ContextBuilder/PromptBuilder 对固定角色场景做脱敏评测。"""

    index_store = _resolve_index(profile_index)
    context_builder = ContextBuilder(profile_index=index_store)
    prompt_builder = PromptBuilder()
    upstream = _build_provider(
        provider,
        endpoint=endpoint,
        model=model,
        timeout=timeout,
    )
    selected_cases = list(cases)
    records: list[dict[str, object]] = []
    request_count = 0
    successful_turns = 0
    failed_turns = 0
    all_usages: list[ProviderUsage | None] = []
    usage_returned_turns = 0
    started_at = perf_counter()
    for case in selected_cases:
        case_started_at = perf_counter()
        conversation_history = [dict(item) for item in case.history]
        turn_records: list[dict[str, object]] = []
        for turn in case.dialogue_turns():
            turn_started_at = perf_counter()
            context = _build_context(
                context_builder,
                case,
                message=turn.message,
                history=conversation_history,
            )
            messages = prompt_builder.build(context, turn.message)
            request = _build_request(
                case,
                message=turn.message,
                history=conversation_history,
            )
            attempt_usages: list[ProviderUsage | None] = []

            def generate_attempt(
                prompt_messages: list[dict[str, str]],
            ) -> ProviderResult:
                nonlocal request_count
                request_count += 1
                result = upstream.generate(request, messages=prompt_messages)
                attempt_usages.append(result.usage)
                return result

            try:
                result = generate_attempt(messages)
            except Exception as exc:  # noqa: BLE001 - 单轮失败不阻断其他轮次
                failed_turns += 1
                turn_records.append(
                    {
                        "turnId": turn.turn_id,
                        "playerInput": turn.message,
                        "error": type(exc).__name__,
                        "elapsedMs": int((perf_counter() - turn_started_at) * 1000),
                    }
                )
                continue

            result = retry_for_format_noise(
                result,
                messages,
                generate_attempt,
            )
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
            turn_records.append(
                {
                    "turnId": turn.turn_id,
                    "playerInput": turn.message,
                    "reply": result.reply,
                    "provider": result.provider,
                    "fallback": result.fallback,
                    "latencyMs": result.latency_ms,
                    "warnings": list(result.warnings),
                    "elapsedMs": int((perf_counter() - turn_started_at) * 1000),
                    "usage": usage,
                    "score": score,
                    "styleQuality": style_quality,
                }
            )
            conversation_history.extend(
                [
                    {"role": "user", "content": turn.message},
                    {"role": "assistant", "content": result.reply},
                ]
            )

        first_result = next((item for item in turn_records if "reply" in item), None)
        case_record: dict[str, object] = {
            "caseId": case.case_id,
            "profileKey": case.profile_key,
            "npcId": case.npc_id,
            "displayName": case.display_name,
            "channel": case.channel,
            "relationshipStage": case.relationship_stage,
            "gameState": dict(case.game_state),
            "storyProgress": case.story_progress,
            "turnCount": len(case.dialogue_turns()),
            "turns": turn_records,
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
        "caseCount": len(selected_cases),
        "successful": successful,
        "errors": len(records) - successful,
        "turnCount": sum(len(case.dialogue_turns()) for case in selected_cases),
        "requestCount": request_count,
        "successfulTurns": successful_turns,
        "failedTurns": failed_turns,
        "passed": sum(
            len(record.get("turns", [])) == len(case.dialogue_turns())
            and all(
                isinstance(turn, dict)
                and bool(turn.get("score", {}).get("passed"))
                for turn in record.get("turns", [])
            )
            for record, case in zip(records, selected_cases)
        ),
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
    parser.add_argument("--provider", choices=("local", "cloud"), default="local")
    parser.add_argument("--input-price-per-million", type=float, default=None)
    parser.add_argument("--output-price-per-million", type=float, default=None)
    parser.add_argument("--limit", type=int, default=len(DEFAULT_CASES))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    args = _parse_args(argv)
    cases = DEFAULT_CASES[: max(0, min(args.limit, len(DEFAULT_CASES)))]
    summary = run_evaluation(
        profile_index=args.profile_index,
        output_dir=args.output_dir,
        cases=cases,
        endpoint=args.endpoint,
        model=args.model,
        timeout=args.timeout,
        provider=args.provider,
        input_price_per_million=args.input_price_per_million,
        output_price_per_million=args.output_price_per_million,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
