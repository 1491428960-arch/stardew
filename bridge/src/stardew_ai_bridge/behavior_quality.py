from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any

from .personas import canonical_npc_id


REVIEW_DIMENSIONS = (
    "stardewVoice",
    "characterDistinctiveness",
    "relationshipFit",
    "channelFit",
    "topicResponse",
    "contextContinuity",
    "naturalChinese",
    "boundarySafety",
)

_ALLOWED_CHANNELS = {"remote", "face_to_face", "any"}
_ALLOWED_STAGES = {
    "stranger",
    "acquaintance",
    "friend",
    "close",
    "dating",
    "married",
    "parent",
    "any",
}
_REVISION_TAGS = {
    "too_formal",
    "generic_voice",
    "wrong_stage",
    "wrong_channel",
    "magic_overreach",
    "repeated_opener",
    "unnatural_chinese",
    "invented_lore",
}
_SENSITIVE_KEYS = {
    "apikey",
    "api_key",
    "token",
    "cookie",
    "authorization",
    "bearer",
    "prompt",
    "payload",
}
_CONTAINER_KEYS = {"request", "response", "config"}
_SECRET_LABEL = re.compile(
    r"(?i)\b(api[_-]?key|token|cookie|authorization|bearer|prompt)\s*[:=]\s*"
    r"(?:bearer\s+)?[^\s,;]+"
)
_KNOWN_FIELDS = (
    "exampleId",
    "npcId",
    "sourceMods",
    "channels",
    "relationshipStages",
    "speechFunction",
    "topic",
    "topicKeywords",
    "emotion",
    "playerInput",
    "npcReply",
    "sourceType",
    "sourceRefs",
    "review",
)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: object) -> list[str] | None:
    if isinstance(value, str):
        values: Iterable[object] = (value,)
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        values = value
    else:
        return None
    return list(dict.fromkeys(
        item.strip()
        for item in values
        if isinstance(item, str) and item.strip()
    ))


def validate_review(review: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    for dimension in REVIEW_DIMENSIONS:
        score = review.get(dimension)
        if (
            not isinstance(score, int)
            or isinstance(score, bool)
            or score not in {0, 1, 2}
        ):
            errors.append(f"invalid-score:{dimension}")
    hard_errors = review.get("hardErrors", [])
    if hard_errors is not None and not isinstance(hard_errors, list):
        errors.append("invalid:hardErrors")
    tags = review.get("tags", [])
    if tags is not None and not isinstance(tags, list):
        errors.append("invalid:tags")
    return errors


def validate_behavior_example(
    raw: Mapping[str, object],
    *,
    require_review: bool = False,
) -> tuple[dict[str, object] | None, list[str]]:
    if not isinstance(raw, Mapping):
        return None, ["invalid:example"]

    errors: list[str] = []
    normalized: dict[str, object] = {}
    for field in ("exampleId", "npcId", "playerInput", "npcReply"):
        value = _text(raw.get(field))
        if not value:
            errors.append(f"missing:{field}")
        else:
            normalized[field] = value

    if "npcId" in normalized:
        normalized["npcId"] = canonical_npc_id(normalized["npcId"])

    for field in ("sourceMods", "channels", "relationshipStages", "topicKeywords", "sourceRefs"):
        if field not in raw:
            continue
        values = _string_list(raw[field])
        if values is None or (field in {"channels", "relationshipStages"} and not values):
            errors.append(f"invalid:{field}")
            continue
        normalized[field] = values
        if field == "channels":
            errors.extend(
                f"invalid:channels:{value}"
                for value in values
                if value.casefold() not in _ALLOWED_CHANNELS
            )
        if field == "relationshipStages":
            errors.extend(
                f"invalid:relationshipStages:{value}"
                for value in values
                if value.casefold() not in _ALLOWED_STAGES
            )

    for field in ("speechFunction", "topic", "emotion"):
        if field not in raw:
            continue
        value = _text(raw[field])
        if value:
            normalized[field] = value

    source_type = _text(raw.get("sourceType")) or "handcrafted_example"
    normalized["sourceType"] = source_type

    if "review" in raw:
        review = raw["review"]
        if not isinstance(review, Mapping):
            errors.append("invalid:review")
        else:
            review_errors = validate_review(review)
            errors.extend(review_errors)
            normalized["review"] = sanitize_quality_artifact(dict(review))
    elif require_review:
        errors.append("missing:review")

    return (None, errors) if errors else (normalized, [])


def review_passes(review: Mapping[str, object]) -> bool:
    if not isinstance(review, Mapping) or review.get("hardErrors"):
        return False
    tags = review.get("tags", [])
    if isinstance(tags, list) and _REVISION_TAGS.intersection(
        str(tag).strip().casefold() for tag in tags
    ):
        return False
    return all(
        isinstance(review.get(dimension), int)
        and not isinstance(review.get(dimension), bool)
        and int(review[dimension]) >= 1
        for dimension in REVIEW_DIMENSIONS
    )


def _sanitize_text(value: str) -> str:
    return _SECRET_LABEL.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        value,
    )


def sanitize_quality_artifact(value: object) -> object:
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            folded = key_text.casefold().replace("-", "_")
            if folded in _SENSITIVE_KEYS:
                continue
            if folded in _CONTAINER_KEYS:
                sanitized[key_text] = {}
                continue
            sanitized[key_text] = sanitize_quality_artifact(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_quality_artifact(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_quality_artifact(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value
