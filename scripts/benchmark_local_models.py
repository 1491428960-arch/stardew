from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
PREFERRED_PROFILE_INDEX = (
    ROOT / "data" / "generated" / "vanilla-sve-rasmodia-profile-index-zh-CN.json"
)
LEGACY_PROFILE_INDEX = ROOT / "data" / "generated" / "profile-index.json"
SRC = ROOT / "bridge" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stardew_ai_bridge.config import ProviderSettings  # noqa: E402
from stardew_ai_bridge.artifact_paths import stable_artifact_path  # noqa: E402
from stardew_ai_bridge.local_benchmark import (  # noqa: E402
    DEFAULT_CASES,
    RasmodiaBenchmarkCase,
    build_case_messages,
    parse_ollama_stream_lines,
    score_reply,
    summarize_ollama_stream,
)
from stardew_ai_bridge.profile_index import ProfileIndexStore  # noqa: E402
from stardew_ai_bridge.providers import (  # noqa: E402
    OllamaNativeProvider,
    ProviderError,
)


def _resolve_profile_index_path(configured_path: str | None) -> Path:
    """解析基准测试索引，默认与 Bridge 启动脚本使用同一份资料。"""

    if configured_path and configured_path.strip():
        configured = Path(configured_path.strip()).expanduser()
        if not configured.is_absolute():
            configured = ROOT / configured
        return configured
    if PREFERRED_PROFILE_INDEX.is_file():
        return PREFERRED_PROFILE_INDEX
    return LEGACY_PROFILE_INDEX


def _run_case(
    provider: OllamaNativeProvider,
    case: RasmodiaBenchmarkCase,
    *,
    stream_metrics: bool = False,
    profile_index: ProfileIndexStore | None = None,
) -> dict[str, Any]:
    if stream_metrics:
        if profile_index is None:
            # 保持旧的可替换测试钩子签名，同时让正式运行传入索引。
            return _run_stream_case(provider.settings, case)
        return _run_stream_case(
            provider.settings,
            case,
            profile_index=profile_index,
        )

    started_at = perf_counter()
    try:
        result = provider.generate(
            case.request(),
            messages=build_case_messages(case, profile_index=profile_index),
        )
    except ProviderError as exc:
        return {
            "caseId": case.case_id,
            "label": case.label,
            "relationshipStage": case.relationship_stage,
            "error": str(exc),
            "elapsedMs": int((perf_counter() - started_at) * 1000),
        }

    return {
        "caseId": case.case_id,
        "label": case.label,
        "relationshipStage": case.relationship_stage,
        "reply": result.reply,
        "latencyMs": result.latency_ms,
        "score": score_reply(case, result.reply),
    }


def _run_stream_case(
    settings: ProviderSettings,
    case: RasmodiaBenchmarkCase,
    *,
    profile_index: ProfileIndexStore | None = None,
) -> dict[str, Any]:
    """通过 Ollama NDJSON 流式接口采集首段内容和生成指标。"""

    started_at = perf_counter()
    payload = {
        "model": settings.model,
        "messages": build_case_messages(case, profile_index=profile_index),
        "stream": True,
        "think": False,
    }
    first_content_latency_ms: int | None = None
    try:
        with httpx.Client(timeout=settings.timeout, trust_env=False) as client:
            with client.stream(
                "POST",
                settings.url,
                headers={"content-type": "application/json"},
                json=payload,
            ) as response:
                if response.is_error:
                    raise ProviderError(f"ollama returned HTTP {response.status_code}")
                raw_lines: list[str] = []
                for line in response.iter_lines():
                    raw_lines.append(line)
                    if first_content_latency_ms is None:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        message = event.get("message") if isinstance(event, dict) else None
                        content = message.get("content") if isinstance(message, dict) else None
                        if isinstance(content, str) and content:
                            first_content_latency_ms = int(
                                (perf_counter() - started_at) * 1000
                            )

        events = parse_ollama_stream_lines(raw_lines)
        summary = summarize_ollama_stream(
            events,
            total_latency_ms=int((perf_counter() - started_at) * 1000),
            first_content_latency_ms=first_content_latency_ms,
        )
        reply = summary["reply"]
        if not isinstance(reply, str) or not reply:
            raise ProviderError("ollama returned an empty stream")
    except (httpx.HTTPError, ProviderError, ValueError) as exc:
        return {
            "caseId": case.case_id,
            "label": case.label,
            "relationshipStage": case.relationship_stage,
            "error": str(exc),
            "elapsedMs": int((perf_counter() - started_at) * 1000),
        }

    metrics = {
        key: value
        for key, value in summary.items()
        if key != "reply"
    }
    return {
        "caseId": case.case_id,
        "label": case.label,
        "relationshipStage": case.relationship_stage,
        "reply": reply,
        "latencyMs": summary["totalLatencyMs"],
        "metrics": metrics,
        "score": score_reply(case, reply),
    }


def run_model(
    model: str,
    endpoint: str,
    cases: tuple[RasmodiaBenchmarkCase, ...],
    timeout: float,
    *,
    stream_metrics: bool = False,
    profile_index: ProfileIndexStore | None = None,
) -> dict[str, Any]:
    provider = OllamaNativeProvider(
        ProviderSettings(
            name="ollama",
            url=endpoint,
            model=model,
            timeout=timeout,
            api_mode="ollama",
        )
    )
    results = [
        _run_case(
            provider,
            case,
            stream_metrics=stream_metrics,
            profile_index=profile_index,
        )
        for case in cases
    ]
    successful = [item for item in results if "score" in item]
    passed = sum(1 for item in successful if item["score"]["passed"])
    latencies = [int(item["latencyMs"]) for item in successful]
    stream_results = [item for item in successful if "metrics" in item]
    first_content_latencies = [
        float(item["metrics"]["firstContentLatencyMs"])
        for item in stream_results
        if item["metrics"].get("firstContentLatencyMs") is not None
    ]
    token_rates = [
        float(item["metrics"]["tokensPerSecond"])
        for item in stream_results
        if item["metrics"].get("tokensPerSecond") is not None
    ]
    return {
        "model": model,
        "endpoint": endpoint,
        "profileIndex": (
            stable_artifact_path(profile_index.index_path, root=ROOT)
            if profile_index is not None
            else None
        ),
        "caseCount": len(cases),
        "passed": passed,
        "successful": len(successful),
        "errors": len(results) - len(successful),
        "averageLatencyMs": (
            round(sum(latencies) / len(latencies), 1) if latencies else None
        ),
        "streamMetrics": stream_metrics,
        "averageFirstContentLatencyMs": (
            round(sum(first_content_latencies) / len(first_content_latencies), 1)
            if first_content_latencies
            else None
        ),
        "averageTokensPerSecond": (
            round(sum(token_rates) / len(token_rates), 2) if token_rates else None
        ),
        "results": results,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用项目真实 Rasmodia 上下文比较本机 Ollama 模型"
    )
    parser.add_argument(
        "--model",
        nargs="+",
        default=["qwen3.5:4b", "qwen3.5:9b"],
        help="Ollama 模型名，可传多个",
    )
    parser.add_argument(
        "--endpoint",
        default=(
            os.environ.get("BRIDGE_LOCAL_URL")
            or "http://127.0.0.1:11435/api/chat"
        ),
        help="Ollama 原生 chat endpoint",
    )
    parser.add_argument(
        "--case",
        dest="case_ids",
        nargs="*",
        help="只运行指定 caseId，默认运行全部用例",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--stream-metrics",
        action="store_true",
        help="使用 Ollama 流式接口记录首段内容延迟和生成速度",
    )
    parser.add_argument(
        "--profile-index",
        type=Path,
        default=None,
        help=(
            "资料索引路径；默认读取 BRIDGE_PROFILE_INDEX，"
            "否则优先使用已解析的中文索引"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出 JSON 路径，默认写入 artifacts/",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    selected = tuple(
        case
        for case in DEFAULT_CASES
        if not args.case_ids or case.case_id in set(args.case_ids)
    )
    if not selected:
        raise SystemExit("没有匹配的 caseId")

    output = args.output or (
        ROOT
        / "artifacts"
        / f"model-benchmark-{datetime.now():%Y%m%d-%H%M%S}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    configured_index = (
        str(args.profile_index)
        if args.profile_index is not None
        else os.environ.get("BRIDGE_PROFILE_INDEX")
    )
    profile_index_path = _resolve_profile_index_path(configured_index)
    profile_index = ProfileIndexStore(profile_index_path)
    payload = {
        "generatedAt": datetime.now().astimezone().isoformat(),
        "cases": [case.case_id for case in selected],
        "profileIndex": stable_artifact_path(profile_index_path, root=ROOT),
        "models": [
            run_model(
                model,
                args.endpoint,
                selected,
                args.timeout,
                stream_metrics=args.stream_metrics,
                profile_index=profile_index,
            )
            for model in args.model
        ],
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.resolve())
    print(f"资料索引：{profile_index_path}")
    for summary in payload["models"]:
        print(
            f"{summary['model']}: {summary['passed']}/{summary['caseCount']} passed, "
            f"{summary['averageLatencyMs']} ms avg, {summary['errors']} errors"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
