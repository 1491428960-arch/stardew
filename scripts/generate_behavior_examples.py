from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
from typing import Iterable, Mapping, Protocol


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "bridge" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stardew_ai_bridge.behavior_quality import (  # noqa: E402
    sanitize_quality_artifact,
)
from stardew_ai_bridge.config import ProviderSettings  # noqa: E402
from stardew_ai_bridge.models import DialogueTestRequest  # noqa: E402
from stardew_ai_bridge.personas import canonical_npc_id  # noqa: E402
from stardew_ai_bridge.quality_pipeline import (  # noqa: E402
    CharacterQualityPipeline,
    QualityRun,
)
from stardew_ai_bridge.providers import OllamaNativeProvider  # noqa: E402


DEFAULT_SCENARIOS = ROOT / "data" / "personas" / "behavior-quality-scenarios.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "character-quality"
DEFAULT_ENDPOINT = "http://127.0.0.1:11435/api/chat"
DEFAULT_MODEL = "qwen3.5:9b"
MAX_SCENARIOS = 10


class MessageGenerator(Protocol):
    def generate(self, messages: list[dict[str, str]]) -> str:
        """根据离线流水线消息返回模型文本。"""


@dataclass
class BatchQualityResult:
    candidates: list[dict[str, object]] = field(default_factory=list)
    reviews: list[dict[str, object]] = field(default_factory=list)
    revised: list[dict[str, object]] = field(default_factory=list)
    approved: list[dict[str, object]] = field(default_factory=list)
    rejections: list[dict[str, object]] = field(default_factory=list)
    scenario_count: int = 0


class OllamaMessageGenerator:
    """把现有 Ollama Provider 适配为质量流水线的消息生成器。"""

    def __init__(self, endpoint: str, model: str, timeout: float) -> None:
        self.provider = OllamaNativeProvider(
            ProviderSettings(
                name="local",
                url=endpoint,
                model=model,
                timeout=timeout,
                enabled=True,
                api_mode="ollama",
            )
        )

    def generate(self, messages: list[dict[str, str]]) -> str:
        payload = _last_message_payload(messages)
        scenario = payload.get("scenario", payload)
        candidate = payload.get("candidate", {})
        if not isinstance(scenario, Mapping):
            scenario = {}
        if not isinstance(candidate, Mapping):
            candidate = {}
        npc_id = _first_text(
            candidate.get("npcId"),
            scenario.get("npcId"),
            default="NPC",
        )
        message = _first_text(
            candidate.get("playerInput"),
            scenario.get("playerInput"),
            default="请根据给定场景生成回复。",
        )
        source_mods = _string_list(
            candidate.get("sourceMods") or scenario.get("sourceMods")
        )
        request = DialogueTestRequest(
            npcId=npc_id,
            message=message,
            displayName=_first_text(
                candidate.get("displayName"),
                scenario.get("displayName"),
                default=npc_id,
            ),
            sourceMods=source_mods,
        )
        return self.provider.generate(request, messages=messages).reply


def _last_message_payload(messages: list[dict[str, str]]) -> dict[str, object]:
    if not messages:
        return {}
    try:
        value = json.loads(messages[-1].get("content", "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _first_text(*values: object, default: str = "") -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, Iterable) or isinstance(value, (bytes, bytearray, Mapping)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _profile_key(npc_id: str) -> str:
    canonical = canonical_npc_id(npc_id)
    return {
        "Wizard": "wizard_rasmodia",
        "Sophia": "sophia",
        "Shane": "shane",
        "Sebastian": "sebastian",
        "Alex": "alex",
    }.get(canonical, canonical.casefold())


def load_scenarios(path: Path | str, *, limit: int = MAX_SCENARIOS) -> list[dict[str, object]]:
    """加载并规范化质量场景；单次运行最多处理十个场景。"""

    scenario_path = Path(path)
    data = json.loads(scenario_path.read_text(encoding="utf-8"))
    raw_scenarios = data.get("scenarios") if isinstance(data, Mapping) else None
    if not isinstance(raw_scenarios, list):
        raise ValueError("场景文件必须包含 scenarios 数组")
    bounded_limit = max(0, min(int(limit), MAX_SCENARIOS))
    scenarios: list[dict[str, object]] = []
    for raw in raw_scenarios[:bounded_limit]:
        if not isinstance(raw, Mapping):
            raise ValueError("场景必须是 JSON 对象")
        scenario = dict(raw)
        npc_id = _first_text(scenario.get("npcId"))
        if not npc_id:
            raise ValueError("场景缺少 npcId")
        scenario["npcId"] = canonical_npc_id(npc_id)
        scenario.setdefault("profileKey", _profile_key(npc_id))
        if "channels" not in scenario and "channel" in scenario:
            scenario["channels"] = [scenario["channel"]]
        if "relationshipStages" not in scenario and "relationshipStage" in scenario:
            scenario["relationshipStages"] = [scenario["relationshipStage"]]
        scenarios.append(scenario)
    return scenarios


def _safe(value: object) -> object:
    return sanitize_quality_artifact(value)


def _write_jsonl(path: Path, values: Iterable[Mapping[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(
                json.dumps(_safe(dict(value)), ensure_ascii=False, sort_keys=True)
            )
            handle.write("\n")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(_safe(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _approval_ids(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


def _run_summary(result: BatchQualityResult) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "scenarioCount": result.scenario_count,
        "candidateCount": len(result.candidates),
        "reviewCount": len(result.reviews),
        "revisionCount": len(result.revised),
        "approvedCount": len(result.approved),
        "rejectionCount": len(result.rejections),
    }


def run_cli(
    *,
    scenario_path: Path | str,
    output_dir: Path | str,
    generator: MessageGenerator | None = None,
    approve_ids: Iterable[str] = (),
    candidate_count: int = 1,
    limit: int = MAX_SCENARIOS,
    provider: str = "local",
    endpoint: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
) -> BatchQualityResult:
    """运行离线 Draft/Review/Revise，并把脱敏工件写入临时输出目录。"""

    if provider != "local":
        raise ValueError("当前质量 CLI 只支持本地 provider")
    scenarios = load_scenarios(scenario_path, limit=limit)
    if generator is None:
        generator = OllamaMessageGenerator(
            endpoint=endpoint or os.getenv("BRIDGE_LOCAL_URL") or DEFAULT_ENDPOINT,
            model=model or os.getenv("BRIDGE_LOCAL_MODEL") or DEFAULT_MODEL,
            timeout=timeout or _env_timeout(),
        )
    approvals = _approval_ids(approve_ids)
    result = BatchQualityResult(scenario_count=len(scenarios))
    pipeline = CharacterQualityPipeline(generator)
    for scenario in scenarios:
        run: QualityRun = pipeline.run(
            scenario,
            candidate_count=candidate_count,
            approved_ids=approvals,
        )
        result.candidates.extend(run.candidates)
        result.reviews.extend(run.reviews)
        result.revised.extend(run.revised)
        result.approved.extend(run.approved)
        result.rejections.extend(run.rejections)

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    _write_jsonl(destination / "candidates.jsonl", result.candidates)
    _write_jsonl(destination / "reviews.jsonl", result.reviews)
    _write_jsonl(destination / "revisions.jsonl", result.revised)
    _write_json(destination / "run-summary.json", _run_summary(result))
    if result.approved:
        _write_json(destination / "approved.json", result.approved)
    return result


def _env_timeout() -> float:
    value = os.getenv("BRIDGE_LOCAL_TIMEOUT", "45")
    try:
        timeout = float(value)
    except ValueError:
        return 45.0
    return timeout if timeout > 0 else 45.0


def _default_output_dir() -> Path:
    from datetime import datetime

    return DEFAULT_OUTPUT_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成可审核的 NPC 行为样本工件")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())
    parser.add_argument("--provider", choices=("local",), default="local")
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--candidate-count", type=int, default=1)
    parser.add_argument("--limit", type=int, default=MAX_SCENARIOS)
    parser.add_argument(
        "--approve",
        default="",
        help="逗号分隔的本次运行中已人工确认的 exampleId",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_cli(
        scenario_path=args.scenarios,
        output_dir=args.output_dir,
        approve_ids=args.approve.split(",") if args.approve else (),
        candidate_count=args.candidate_count,
        limit=args.limit,
        provider=args.provider,
        endpoint=args.endpoint,
        model=args.model,
        timeout=args.timeout,
    )
    print(json.dumps(_run_summary(result), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
