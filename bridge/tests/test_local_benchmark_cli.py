from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from stardew_ai_bridge.models import ProviderResult
from stardew_ai_bridge.profile_index import ProfileIndexStore


def _load_cli_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "benchmark_local_models.py"
    spec = importlib.util.spec_from_file_location("benchmark_local_models", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_model_records_all_cases_without_network(monkeypatch) -> None:
    module = _load_cli_module()

    class StubProvider:
        def __init__(self, settings):
            self.settings = settings

        def generate(self, request, *, messages):
            del request, messages
            return ProviderResult(
                reply="这件事我不能确定。",
                provider="ollama",
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", StubProvider)

    summary = module.run_model(
        "qwen3.5:4b",
        "http://127.0.0.1:11434/api/chat",
        module.DEFAULT_CASES,
        timeout=1.0,
    )

    assert summary["caseCount"] == len(module.DEFAULT_CASES)
    assert summary["successful"] == len(module.DEFAULT_CASES)
    assert summary["errors"] == 0
    # 仅有 unknown_event_boundary 声明的拒答词能被这条 stub 回复命中；
    # 其他用例现在会按默认期望词阈值判为未通过。
    assert summary["passed"] == 1
    assert summary["averageLatencyMs"] == 12


def test_run_model_stream_mode_aggregates_generation_metrics(monkeypatch) -> None:
    module = _load_cli_module()
    case = module.DEFAULT_CASES[0]
    calls: list[str] = []

    def fake_stream_case(settings, selected_case):
        calls.append(selected_case.case_id)
        return {
            "caseId": selected_case.case_id,
            "label": selected_case.label,
            "relationshipStage": selected_case.relationship_stage,
            "reply": "早上好，旅行者。",
            "latencyMs": 600,
            "score": {"passed": True},
            "metrics": {
                "firstContentLatencyMs": 120,
                "tokensPerSecond": 8.0,
            },
        }

    monkeypatch.setattr(module, "_run_stream_case", fake_stream_case)

    summary = module.run_model(
        "qwen3.5:4b",
        "http://127.0.0.1:11435/api/chat",
        (case,),
        timeout=1.0,
        stream_metrics=True,
    )

    assert calls == [case.case_id]
    assert summary["streamMetrics"] is True
    assert summary["averageFirstContentLatencyMs"] == 120.0
    assert summary["averageTokensPerSecond"] == 8.0


def test_run_model_passes_selected_profile_index_into_prompt(monkeypatch, tmp_path: Path) -> None:
    module = _load_cli_module()
    index_path = tmp_path / "resolved-profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {},
                "styleSamples": [],
                "speechEvidence": [
                    {
                        "sampleId": "wizard-cli-1",
                        "npcId": "Wizard",
                        "sourceMod": "Romanceable Rasmodius",
                        "sourceKey": "wizard_cli_voice",
                        "text": "星界观测是我今晚的研究重点。",
                        "evidenceKind": "dialogue",
                        "conditions": {"relationshipStage": "friend"},
                    }
                ],
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    captured: list[list[dict[str, str]]] = []

    class StubProvider:
        def __init__(self, settings):
            self.settings = settings

        def generate(self, request, *, messages):
            del request
            captured.append(messages)
            return ProviderResult(
                reply="研究进展顺利。",
                provider="ollama",
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", StubProvider)
    store = ProfileIndexStore(index_path)
    case = next(item for item in module.DEFAULT_CASES if item.case_id == "friend_voice")

    summary = module.run_model(
        "qwen3.5:4b",
        "http://127.0.0.1:11434/api/chat",
        (case,),
        timeout=1.0,
        profile_index=store,
    )

    assert summary["profileIndex"] == "external/resolved-profile-index.json"
    rendered = "\n".join(item["content"] for item in captured[0])
    assert "星界观测" in rendered


def test_profile_index_resolution_uses_preferred_file_then_legacy(monkeypatch, tmp_path: Path) -> None:
    module = _load_cli_module()
    preferred = tmp_path / "preferred.json"
    legacy = tmp_path / "legacy.json"
    monkeypatch.setattr(module, "PREFERRED_PROFILE_INDEX", preferred)
    monkeypatch.setattr(module, "LEGACY_PROFILE_INDEX", legacy)

    assert module._resolve_profile_index_path(None) == legacy
    preferred.write_text("{}", encoding="utf-8")
    assert module._resolve_profile_index_path(None) == preferred
    assert module._resolve_profile_index_path("data/custom.json") == module.ROOT / "data/custom.json"


def test_cli_defaults_to_the_isolated_ollama_endpoint(monkeypatch) -> None:
    module = _load_cli_module()
    monkeypatch.setattr(sys, "argv", ["benchmark_local_models.py"])

    args = module._parse_args()

    assert args.endpoint == "http://127.0.0.1:11435/api/chat"
