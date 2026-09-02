from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
from typing import Any


RESULT_TEXT_LIMIT = 4000
WARNING_LIMIT = 20
WARNING_TEXT_LIMIT = 500
TAG_LIMIT = 20
TAG_TEXT_LIMIT = 80
SAFE_SUITE_IDS = {
    "default",
    "topic-start-intimacy",
    "topic-start-adaptive",
}
USAGE_KEYS = (
    "inputTokens",
    "outputTokens",
    "totalTokens",
)
SUMMARY_USAGE_KEYS = USAGE_KEYS + (
    "usageReturnedTurns",
    "missingUsageTurns",
)


def _text(value: Any, *, limit: int = RESULT_TEXT_LIMIT) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _safe_suite(value: Any) -> str | None:
    return value if isinstance(value, str) and value in SAFE_SUITE_IDS else None


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _non_negative_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if value >= 0 and math.isfinite(float(value)) else None


def _safe_usage(value: Any, *, summary: bool = False) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    keys = SUMMARY_USAGE_KEYS if summary else USAGE_KEYS
    safe: dict[str, object] = {}
    for key in keys:
        number = _non_negative_int(value.get(key))
        if number is not None:
            safe[key] = number
    return safe or None


def _safe_cost(value: Any) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    safe: dict[str, object] = {}
    currency = _text(value.get("currency"), limit=12)
    if currency is not None:
        safe["currency"] = currency
    for key in (
        "inputPricePerMillion",
        "outputPricePerMillion",
        "amount",
    ):
        number = _non_negative_number(value.get(key))
        if number is not None:
            safe[key] = number
    return safe or None


def _safe_summary(value: Any) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    safe: dict[str, object] = {}
    schema_version = value.get("schemaVersion")
    if schema_version in (1, 2, 3):
        safe["schemaVersion"] = schema_version
    suite = _safe_suite(value.get("suite"))
    if suite is not None:
        safe["suite"] = suite
    for key in (
        "caseCount",
        "successful",
        "errors",
        "passed",
        "passedCases",
        "passedTurns",
        "turnCount",
        "requestCount",
        "npcRequestCount",
        "playerInputRequestCount",
        "playerInputGenerationCount",
        "playerInputValidCount",
        "playerInputInvalidCount",
        "successfulTurns",
        "failedTurns",
        "playerInputUsageReturned",
        "mechanicalRestatementCount",
        "elapsedMs",
    ):
        number = _non_negative_int(value.get(key))
        if number is not None:
            safe[key] = number
    for key in ("turnPassRate", "casePassRate"):
        number = _non_negative_number(value.get(key))
        if number is not None:
            safe[key] = number
    initiative_detected = _non_negative_int(value.get("initiativeDetected"))
    if initiative_detected is not None:
        safe["initiativeDetected"] = initiative_detected
    initiative_tags = value.get("initiativeTags")
    if isinstance(initiative_tags, list):
        safe["initiativeTags"] = [
            tag[:TAG_TEXT_LIMIT]
            for tag in initiative_tags[:TAG_LIMIT]
            if isinstance(tag, str)
        ]
    player_input_quality_tags = value.get("playerInputQualityTags")
    if isinstance(player_input_quality_tags, list):
        safe["playerInputQualityTags"] = [
            tag[:TAG_TEXT_LIMIT]
            for tag in player_input_quality_tags[:TAG_LIMIT]
            if isinstance(tag, str)
        ]
    usage = _safe_usage(value.get("usage"), summary=True)
    if usage is not None:
        safe["usage"] = usage
    estimated_cost = _safe_cost(value.get("estimatedCost"))
    if estimated_cost is not None:
        safe["estimatedCost"] = estimated_cost
    return safe


def _safe_score(value: Any) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    safe: dict[str, object] = {}
    for key in ("passed", "continuity", "topicEvidence"):
        flag = value.get(key)
        if isinstance(flag, bool):
            safe[key] = flag
    for key in ("replyLength", "expectedHits", "exactExpectedHits", "forbiddenHits"):
        number = _non_negative_int(value.get(key))
        if number is not None:
            safe[key] = number
    tags = value.get("tags")
    if isinstance(tags, list):
        safe["tags"] = [
            tag[:TAG_TEXT_LIMIT]
            for tag in tags[:TAG_LIMIT]
            if isinstance(tag, str)
        ]
    evidence = value.get("evidenceMatches")
    if isinstance(evidence, Mapping):
        safe_evidence: dict[str, list[str]] = {}
        for term, matches in list(evidence.items())[:20]:
            if not isinstance(term, str) or not isinstance(matches, list):
                continue
            safe_evidence[term[:TAG_TEXT_LIMIT]] = [
                match[:TAG_TEXT_LIMIT]
                for match in matches[:10]
                if isinstance(match, str)
            ]
        safe["evidenceMatches"] = safe_evidence
    topic_matches = value.get("topicMatches")
    if isinstance(topic_matches, Mapping):
        safe_topic_matches: dict[str, list[str]] = {}
        for term, matches in list(topic_matches.items())[:20]:
            if not isinstance(term, str) or not isinstance(matches, list):
                continue
            safe_topic_matches[term[:TAG_TEXT_LIMIT]] = [
                match[:TAG_TEXT_LIMIT]
                for match in matches[:10]
                if isinstance(match, str)
            ]
        safe["topicMatches"] = safe_topic_matches
    return safe


def _safe_style_quality(value: Any) -> dict[str, object] | None:
    """保留表达质量提示，拒绝把上下文或敏感字段透传到浏览器。"""

    if not isinstance(value, Mapping):
        return None
    safe: dict[str, object] = {}
    tags = value.get("tags")
    if isinstance(tags, list):
        safe["tags"] = [
            tag[:TAG_TEXT_LIMIT]
            for tag in tags[:TAG_LIMIT]
            if isinstance(tag, str)
        ]
    counts = value.get("speechParticleCounts")
    if isinstance(counts, Mapping):
        safe_counts: dict[str, int] = {}
        for particle, count in list(counts.items())[:20]:
            if not isinstance(particle, str):
                continue
            if particle.casefold() in {"api_key", "apikey", "key", "prompt", "secret", "token"}:
                continue
            number = _non_negative_int(count)
            if number is not None:
                safe_counts[particle[:TAG_TEXT_LIMIT]] = number
        safe["speechParticleCounts"] = safe_counts
    opening = _text(value.get("opening"), limit=80)
    if opening is not None:
        safe["opening"] = opening
    return safe or None


def _safe_progression(value: Any) -> dict[str, object] | None:
    """保留多轮推进的短标签和数值，不透传生成上下文。"""

    if not isinstance(value, Mapping):
        return None
    safe: dict[str, object] = {}
    passed = value.get("passed")
    if isinstance(passed, bool):
        safe["passed"] = passed
    tags = value.get("tags")
    if isinstance(tags, list):
        safe["tags"] = [
            tag[:TAG_TEXT_LIMIT]
            for tag in tags[:TAG_LIMIT]
            if isinstance(tag, str)
        ]
    overlap = _non_negative_number(value.get("overlap"))
    if overlap is not None:
        safe["overlap"] = overlap
    novel_terms = value.get("novelExpectedTerms")
    if isinstance(novel_terms, list):
        safe["novelExpectedTerms"] = [
            term[:TAG_TEXT_LIMIT]
            for term in novel_terms[:TAG_LIMIT]
            if isinstance(term, str)
        ]
    return safe or None


def _safe_player_input_quality(value: Any) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    safe: dict[str, object] = {}
    valid = value.get("valid")
    if isinstance(valid, bool):
        safe["valid"] = valid
    linked = value.get("linkedToPreviousReply")
    if isinstance(linked, bool):
        safe["linkedToPreviousReply"] = linked
    length = _non_negative_int(value.get("replyLength"))
    if length is not None:
        safe["replyLength"] = length
    tags = value.get("tags")
    if isinstance(tags, list):
        safe["tags"] = [
            tag[:TAG_TEXT_LIMIT]
            for tag in tags[:TAG_LIMIT]
            if isinstance(tag, str)
        ]
    return safe or None


def _safe_turn(value: Any) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    safe: dict[str, object] = {}
    for key in (
        "turnId",
        "playerInput",
        "playerInputSource",
        "playerInputProvider",
        "playerInputError",
        "reply",
        "provider",
        "error",
    ):
        text = _text(value.get(key))
        if text is not None:
            safe[key] = text
    for key in ("initiativeExpectation", "initiativeKind", "intent"):
        text = _text(value.get(key), limit=40)
        if text is not None:
            safe[key] = text
    initiative_detected = value.get("initiativeDetected")
    if isinstance(initiative_detected, bool):
        safe["initiativeDetected"] = initiative_detected
    mechanical_restatement = value.get("mechanicalRestatement")
    if isinstance(mechanical_restatement, bool):
        safe["mechanicalRestatement"] = mechanical_restatement
    initiative_tags = value.get("initiativeTags")
    if isinstance(initiative_tags, list):
        safe["initiativeTags"] = [
            tag[:TAG_TEXT_LIMIT]
            for tag in initiative_tags[:TAG_LIMIT]
            if isinstance(tag, str)
        ]
    fallback = value.get("fallback")
    if isinstance(fallback, bool):
        safe["fallback"] = fallback
    for key in ("latencyMs", "elapsedMs", "playerInputLatencyMs"):
        number = _non_negative_int(value.get(key))
        if number is not None:
            safe[key] = number
    warnings = value.get("warnings")
    if isinstance(warnings, list):
        safe["warnings"] = [
            warning[:WARNING_TEXT_LIMIT]
            for warning in warnings[:WARNING_LIMIT]
            if isinstance(warning, str)
        ]
    usage = _safe_usage(value.get("usage"))
    if usage is not None:
        safe["usage"] = usage
    player_usage = _safe_usage(value.get("playerInputUsage"))
    if player_usage is not None:
        safe["playerInputUsage"] = player_usage
    player_quality = _safe_player_input_quality(value.get("playerInputQuality"))
    if player_quality is not None:
        safe["playerInputQuality"] = player_quality
    score = _safe_score(value.get("score"))
    if score is not None:
        safe["score"] = score
    progression = _safe_progression(value.get("progression"))
    if progression is not None:
        safe["progression"] = progression
    style_quality = _safe_style_quality(value.get("styleQuality"))
    if style_quality is not None:
        safe["styleQuality"] = style_quality
    return safe or None


def _safe_result(value: Any) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    case_id = _text(value.get("caseId"), limit=200)
    if not case_id:
        return None
    safe: dict[str, object] = {"caseId": case_id}
    suite = _safe_suite(value.get("suite"))
    if suite is not None:
        safe["suite"] = suite
    case_number = _non_negative_int(value.get("caseNumber"))
    if case_number is not None:
        safe["caseNumber"] = case_number
    for key in ("topicSeed", "continuationMode", "followUpMode", "playerSimulationStyle"):
        text = _text(value.get(key), limit=120)
        if text is not None:
            safe[key] = text
    topic_keywords = value.get("topicKeywords")
    if isinstance(topic_keywords, list):
        safe["topicKeywords"] = [
            item[:TAG_TEXT_LIMIT]
            for item in topic_keywords[:8]
            if isinstance(item, str)
        ]
    for key in ("reply", "provider", "error"):
        text = _text(value.get(key))
        if text is not None:
            safe[key] = text
    for key in ("initiativeExpectation", "initiativeKind", "intent"):
        text = _text(value.get(key), limit=40)
        if text is not None:
            safe[key] = text
    initiative_detected = value.get("initiativeDetected")
    if isinstance(initiative_detected, bool):
        safe["initiativeDetected"] = initiative_detected
    mechanical_restatement = value.get("mechanicalRestatement")
    if isinstance(mechanical_restatement, bool):
        safe["mechanicalRestatement"] = mechanical_restatement
    initiative_tags = value.get("initiativeTags")
    if isinstance(initiative_tags, list):
        safe["initiativeTags"] = [
            tag[:TAG_TEXT_LIMIT]
            for tag in initiative_tags[:TAG_LIMIT]
            if isinstance(tag, str)
        ]
    fallback = value.get("fallback")
    if isinstance(fallback, bool):
        safe["fallback"] = fallback
    for key in ("latencyMs", "elapsedMs"):
        number = _non_negative_int(value.get(key))
        if number is not None:
            safe[key] = number
    warnings = value.get("warnings")
    if isinstance(warnings, list):
        safe["warnings"] = [
            warning[:WARNING_TEXT_LIMIT]
            for warning in warnings[:WARNING_LIMIT]
            if isinstance(warning, str)
        ]
    score = _safe_score(value.get("score"))
    if score is not None:
        safe["score"] = score
    style_quality = _safe_style_quality(value.get("styleQuality"))
    if style_quality is not None:
        safe["styleQuality"] = style_quality
    for key in (
        "turnCount",
        "passedTurnCount",
        "failedTurnCount",
        "mechanicalRestatementCount",
    ):
        number = _non_negative_int(value.get(key))
        if number is not None:
            safe[key] = number
    case_passed = value.get("casePassed")
    if isinstance(case_passed, bool):
        safe["casePassed"] = case_passed
    progression = _safe_progression(value.get("progression"))
    if progression is not None:
        safe["progression"] = progression
    usage = _safe_usage(value.get("usage"))
    if usage is not None:
        safe["usage"] = usage
    turns = value.get("turns")
    if isinstance(turns, list):
        safe_turns = [turn for item in turns if (turn := _safe_turn(item)) is not None]
        safe["turns"] = safe_turns
    return safe


def _candidate_runs(root: Path) -> list[tuple[int, Path]]:
    try:
        children = [child for child in root.iterdir() if child.is_dir()]
    except OSError:
        return []
    candidates: list[tuple[int, Path]] = []
    for child in children:
        summary_path = child / "summary.json"
        results_path = child / "results.jsonl"
        if not summary_path.is_file() or not results_path.is_file():
            continue
        try:
            mtime = max(
                summary_path.stat().st_mtime_ns,
                results_path.stat().st_mtime_ns,
            )
        except OSError:
            continue
        candidates.append((mtime, child))
    return sorted(candidates, key=lambda item: item[0], reverse=True)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_latest_quality_run(root: str | Path) -> dict[str, object]:
    """读取最新一轮质量评测，并只返回适合浏览器展示的字段。"""

    for _, run_dir in _candidate_runs(Path(root)):
        try:
            summary = _safe_summary(_read_json(run_dir / "summary.json"))
            raw_results = (run_dir / "results.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        results: list[dict[str, object]] = []
        for line in raw_results:
            if not line.strip():
                continue
            try:
                safe = _safe_result(json.loads(line))
            except (TypeError, json.JSONDecodeError):
                continue
            if safe is not None:
                results.append(safe)
        return {
            "schemaVersion": summary.get("schemaVersion", 1),
            "batchId": run_dir.name,
            "summary": summary,
            "results": results,
        }
    return {
        "schemaVersion": 1,
        "batchId": None,
        "summary": None,
        "results": [],
    }
