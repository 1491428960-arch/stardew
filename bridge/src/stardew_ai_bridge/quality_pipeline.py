from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from typing import Protocol

from .behavior_quality import (
    REVIEW_DIMENSIONS,
    sanitize_quality_artifact,
    review_passes,
    validate_behavior_example,
    validate_review,
)


class MessageGenerator(Protocol):
    def generate(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class QualityRun:
    candidates: list[dict[str, object]]
    reviews: list[dict[str, object]]
    revised: list[dict[str, object]]
    approved: list[dict[str, object]]
    rejections: list[dict[str, object]]
    revision_count: int
    review_count: int


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_object(value: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return dict(parsed) if isinstance(parsed, Mapping) else None


def _scenario_defaults(scenario: Mapping[str, object]) -> dict[str, object]:
    defaults: dict[str, object] = {}
    for field in (
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
    ):
        if field in scenario:
            defaults[field] = scenario[field]
    if "channel" in scenario and "channels" not in defaults:
        defaults["channels"] = [scenario["channel"]]
    if "relationshipStage" in scenario and "relationshipStages" not in defaults:
        defaults["relationshipStages"] = [scenario["relationshipStage"]]
    if "sourceMod" in scenario and "sourceMods" not in defaults:
        defaults["sourceMods"] = [scenario["sourceMod"]]
    return defaults


def _messages(
    name: str,
    instruction: str,
    payload: Mapping[str, object],
) -> list[dict[str, str]]:
    return [
        {"role": "system", "name": name, "content": instruction},
        {"role": "user", "name": f"{name}_input", "content": _json(payload)},
    ]


class CharacterQualityPipeline:
    """离线角色样本流水线；不会自动把模型输出写入正式资料库。"""

    def __init__(self, generator: MessageGenerator) -> None:
        self.generator = generator

    def run(
        self,
        scenario: Mapping[str, object],
        *,
        candidate_count: int = 2,
        approved_ids: Iterable[str] = (),
    ) -> QualityRun:
        safe_scenario = sanitize_quality_artifact(dict(scenario))
        if not isinstance(safe_scenario, Mapping):
            safe_scenario = {}
        candidates, rejections = self._draft_candidates(
            safe_scenario,
            candidate_count,
        )
        reviews: list[dict[str, object]] = []
        revised: list[dict[str, object]] = []
        approved: list[dict[str, object]] = []
        approved_id_set = {
            str(value).strip()
            for value in approved_ids
            if str(value).strip()
        }

        for candidate in candidates:
            first_review, review_error = self._review(candidate, safe_scenario)
            if first_review is None:
                rejections.append(
                    {
                        "exampleId": candidate["exampleId"],
                        "reasons": [review_error or "invalid_review"],
                    }
                )
                continue
            reviews.append(first_review)
            selected = candidate
            if not review_passes(first_review):
                selected, revision_error = self._revise_once(
                    candidate,
                    first_review,
                    safe_scenario,
                )
                if selected is None:
                    rejections.append(
                        {
                            "exampleId": candidate["exampleId"],
                            "reasons": [revision_error or "revision_failed"],
                        }
                    )
                    continue
                revised.append(selected)
                second_review, second_error = self._review(selected, safe_scenario)
                if second_review is None:
                    rejections.append(
                        {
                            "exampleId": selected["exampleId"],
                            "reasons": [second_error or "invalid_review"],
                        }
                    )
                    continue
                reviews.append(second_review)
                if not review_passes(second_review):
                    rejections.append(
                        {
                            "exampleId": selected["exampleId"],
                            "reasons": ["review_failed"],
                        }
                    )
                    continue
            if str(selected.get("exampleId", "")) in approved_id_set:
                approved.append(selected)

        return QualityRun(
            candidates=candidates,
            reviews=reviews,
            revised=revised,
            approved=approved,
            rejections=rejections,
            revision_count=len(revised),
            review_count=len(reviews),
        )

    def _draft_candidates(
        self,
        scenario: Mapping[str, object],
        candidate_count: int,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        count = max(0, min(int(candidate_count), 3))
        candidates: list[dict[str, object]] = []
        rejections: list[dict[str, object]] = []
        defaults = _scenario_defaults(scenario)
        for position in range(1, count + 1):
            raw_text = self.generator.generate(
                _messages(
                    "draft",
                    (
                        "根据场景生成一个候选行为样本。只返回 JSON 对象，不要解释生成过程；"
                        "对象必须包含 exampleId、npcId、playerInput 和 npcReply，"
                        "npcReply 必须是 NPC 实际会说的完整中文对白。"
                    ),
                    {
                        **defaults,
                        "candidateNumber": position,
                        "sourceType": "model_draft",
                    },
                )
            )
            raw = _parse_object(raw_text)
            if raw is None:
                rejections.append(
                    {
                        "exampleId": f"{scenario.get('scenarioId', 'scenario')}:{position}",
                        "reasons": ["invalid_draft"],
                    }
                )
                continue
            candidate = dict(defaults)
            candidate.update(raw)
            candidate.setdefault(
                "exampleId",
                f"{scenario.get('scenarioId', 'scenario')}:{position}",
            )
            candidate["sourceType"] = "model_draft"
            normalized, errors = validate_behavior_example(candidate)
            if normalized is None:
                rejections.append(
                    {
                        "exampleId": candidate["exampleId"],
                        "reasons": errors or ["invalid_draft"],
                    }
                )
                continue
            candidates.append(normalized)
        return candidates, rejections

    def _review(
        self,
        candidate: Mapping[str, object],
        scenario: Mapping[str, object],
    ) -> tuple[dict[str, object] | None, str | None]:
        raw = _parse_object(
            self.generator.generate(
                _messages(
                    "review",
                    (
                        "按固定评分维度审查候选，只返回 JSON 对象，不要重写候选回复。"
                        "必须为以下每个字段填写 0～2 的整数："
                        f"{', '.join(REVIEW_DIMENSIONS)}；"
                        "还必须包含 hardErrors 数组和 tags 数组。"
                    ),
                    {"scenario": scenario, "candidate": candidate},
                )
            )
        )
        if raw is None:
            return None, "invalid_review"
        errors = validate_review(raw)
        if errors:
            return None, "invalid_review"
        return sanitize_quality_artifact(raw), None  # type: ignore[return-value]

    def _revise_once(
        self,
        candidate: Mapping[str, object],
        review: Mapping[str, object],
        scenario: Mapping[str, object],
    ) -> tuple[dict[str, object] | None, str | None]:
        raw = _parse_object(
            self.generator.generate(
                _messages(
                    "revise",
                    "只依据审查结果修订候选一次，只返回完整 JSON 对象，不要解释修改过程。",
                    {
                        "scenario": scenario,
                        "candidate": candidate,
                        "review": review,
                    },
                )
            )
        )
        if raw is None:
            return None, "invalid_revision"
        revised = dict(candidate)
        revised.update(raw)
        revised["exampleId"] = candidate["exampleId"]
        revised["sourceType"] = "model_revision"
        normalized, errors = validate_behavior_example(revised)
        if normalized is None:
            return None, errors[0] if errors else "invalid_revision"
        return normalized, None
