from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from stardew_ai_bridge.models import ProviderResult
from stardew_ai_bridge.profile_index import ProfileIndexStore
from stardew_ai_bridge.character_quality_eval import case_by_id


ROOT = Path(__file__).resolve().parents[2]


def _load_eval_module():
    path = ROOT / "scripts" / "run_character_quality_eval.py"
    spec = importlib.util.spec_from_file_location("run_character_quality_eval", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_test_index(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "profiles": {
                    "Wizard": {
                        "npcId": "Wizard",
                        "displayName": "Rasmodia",
                        "voiceStyle": {"tone": "克制、直接"},
                    }
                },
                "styleSamples": [],
                "speechEvidence": [],
                "behaviorExamples": [
                    {
                        "exampleId": "wizard:follow-up",
                        "npcId": "Wizard",
                        "sourceMods": ["Romanceable Rasmodius"],
                        "channels": ["face_to_face"],
                        "relationshipStages": ["friend"],
                        "speechFunction": "give_specific_detail",
                        "topic": "research",
                        "emotion": "focused",
                        "playerInput": "那第三组现在稳定了吗？",
                        "npcReply": "第三组稳定了，第二组还得重测。",
                        "sourceType": "human_approved",
                    }
                ],
                "voiceCards": {},
                "knowledgeFacts": [],
                "storyEvents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_eval_cli_uses_selected_profile_index_and_temp_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    captured: list[list[dict[str, str]]] = []

    class CapturingProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request
            captured.append(messages)
            return ProviderResult(
                reply="整理完了。第三组稳定，第二组还得重测。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", CapturingProvider)
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-follow-up"),),
    )

    assert summary["successful"] == 1
    assert "conversation_history" in {item.get("name") for item in captured[0]}
    assert summary["profileIndex"] == "external/selected-index.json"
    assert all(path.parent == tmp_path for path in tmp_path.iterdir())


def test_eval_records_safe_style_quality_for_each_generated_turn(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)

    class RepetitiveProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request, messages
            return ProviderResult(
                reply="嗯，今天还行。嗯，没别的事。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", RepetitiveProvider)
    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-daily"),),
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert record["turns"][0]["styleQuality"]["tags"] == [
        "repeated_speech_particle"
    ]
    assert "prompt" not in json.dumps(record, ensure_ascii=False)


def test_eval_runs_three_turns_and_carries_real_replies_forward(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    captured: list[list[dict[str, str]]] = []

    class CapturingProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request
            captured.append(messages)
            turn = len(captured)
            return ProviderResult(
                reply=f"第{turn}轮真实内容",
                provider="local",
                fallback=False,
                latencyMs=12,
                usage={
                    "inputTokens": turn * 10,
                    "outputTokens": turn * 4,
                    "totalTokens": turn * 14,
                },
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", CapturingProvider)
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-daily"),),
    )

    assert len(captured) == 3
    assert any(item.get("content") == "第1轮真实内容" for item in captured[1])
    assert any(item.get("content") == "第2轮真实内容" for item in captured[2])
    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert [turn["reply"] for turn in record["turns"]] == [
        "第1轮真实内容",
        "第2轮真实内容",
        "第3轮真实内容",
    ]
    assert summary["caseCount"] == 1
    assert summary["requestCount"] == 3
    assert summary["successfulTurns"] == 3
    assert summary["usage"]["totalTokens"] == 84


def test_eval_can_select_cloud_provider_from_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    captured: dict[str, object] = {}

    class CapturingProvider:
        def __init__(self, settings) -> None:
            captured["settings"] = settings

        def generate(self, request, *, messages):
            del request, messages
            return ProviderResult(
                reply="云端评测回复。",
                provider="cloud",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setenv(
        "BRIDGE_CLOUD_URL",
        "https://api.openai.com/v1/chat/completions",
    )
    monkeypatch.setenv("BRIDGE_CLOUD_MODEL", "gpt-5.6-terra")
    monkeypatch.setenv("BRIDGE_CLOUD_API_KEY", "test-key")
    monkeypatch.setattr(module, "OpenAICompatibleProvider", CapturingProvider)

    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-follow-up"),),
        provider="cloud",
    )

    settings = captured["settings"]
    assert summary["successful"] == 1
    assert settings.name == "cloud"
    assert settings.url == "https://api.openai.com/v1/chat/completions"
    assert settings.model == "gpt-5.6-terra"
    assert settings.api_key == "test-key"


def test_eval_cli_output_does_not_store_prompt_or_provider_secrets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)

    class SecretProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request, messages
            return ProviderResult(
                reply="apiKey=secret-token prompt=secret-prompt",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", SecretProvider)
    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-follow-up"),),
    )

    rendered = "".join(
        path.read_text(encoding="utf-8")
        for path in tmp_path.iterdir()
        if path.is_file() and path.name != index_path.name
    )
    assert "secret-token" not in rendered
    assert "secret-prompt" not in rendered


def test_eval_retries_format_noise_like_bridge(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    calls: list[list[dict[str, str]]] = []

    class NoisyThenCleanProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request
            calls.append(messages)
            if len(calls) == 1:
                reply = "**第三组稳定了。**"
            elif len(calls) == 2:
                reply = "第三组稳定了，第二组还得重测。"
            elif len(calls) == 3:
                reply = "第3轮第二组已处理。"
            else:
                reply = "第4轮记录已处理。"
            return ProviderResult(
                reply=reply,
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", NoisyThenCleanProvider)
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-follow-up"),),
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert summary["successful"] == 1
    assert len(calls) == 4
    assert calls[1][-1]["name"] == "format_retry"
    assert record["reply"] == "第三组稳定了，第二组还得重测。"
    assert "response_format_retry: markdown" in record["warnings"]


def test_eval_marks_persistent_format_noise_as_failed_quality(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)

    class AlwaysNoisyProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request, messages
            return ProviderResult(
                reply="**第三组稳定了，第二组还得重测。**",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", AlwaysNoisyProvider)
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-follow-up"),),
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert summary["passed"] == 0
    assert record["score"]["passed"] is False
    assert "format_noise" in record["score"]["tags"]


def test_eval_does_not_mark_case_passed_when_one_turn_failed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    calls = 0

    class FailsOnSecondTurnProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            nonlocal calls
            del request, messages
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated turn failure")
            return ProviderResult(
                reply="还行，事情不多；塔里还在忙，有空可以聊。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", FailsOnSecondTurnProvider)
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-daily"),),
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert summary["successfulTurns"] == 2
    assert summary["failedTurns"] == 1
    assert sum(bool(turn.get("score", {}).get("passed")) for turn in record["turns"]) == 2
    assert summary["passed"] == 0
    assert any("error" in turn for turn in record["turns"])
