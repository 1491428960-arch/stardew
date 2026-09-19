from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

from stardew_ai_bridge.models import ProviderResult
from stardew_ai_bridge.profile_index import ProfileIndexStore
from stardew_ai_bridge.character_quality_eval import (
    CharacterQualityCase,
    CharacterQualityTurn,
    case_by_id,
)

try:
    from stardew_ai_bridge.topic_start_intimacy_cases import topic_start_intimacy_cases
except ModuleNotFoundError:
    topic_start_intimacy_cases = None  # type: ignore[assignment]

try:
    from stardew_ai_bridge.topic_start_adaptive_cases import topic_start_adaptive_cases
except ModuleNotFoundError:
    topic_start_adaptive_cases = None  # type: ignore[assignment]


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


def test_eval_canonicalizes_rasmodia_for_requests_context_and_artifacts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    captured_npc_ids: list[str] = []

    class CapturingProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del messages
            captured_npc_ids.append(request.npc_id)
            return ProviderResult(
                reply="塔里的读数稳定了。你想先看哪一组？",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", CapturingProvider)
    case = replace(
        case_by_id("wizard-married-evening"),
        npc_id="Rasmodia",
        display_name="Rasmodia",
        romance_eligible=None,
    )

    context = module._build_context(module.ContextBuilder(), case)
    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert context["npcIdentity"]["npcId"] == "Wizard"
    assert context["npcIdentity"]["displayName"] == "Rasmodia"
    assert context["qualityContext"]["romanceEligible"] is True
    assert captured_npc_ids
    assert all(npc_id == "Wizard" for npc_id in captured_npc_ids)
    assert record["npcId"] == "Wizard"
    assert record["displayName"] == "Rasmodia"
    assert record["romanceEligible"] is True


def test_deep_flirt_eval_enables_natural_mode_without_changing_default_cases() -> None:
    module = _load_eval_module()

    deep_flirt_case = next(
        case
        for case in module.quality_cases_for_suite("deep-flirt")
        if case.case_id == "deep-flirt-wizard-married"
    )
    deep_flirt_context = module._build_context(
        module.ContextBuilder(),
        deep_flirt_case,
    )
    default_context = module._build_context(
        module.ContextBuilder(),
        case_by_id("wizard-married-evening"),
    )

    assert deep_flirt_context["qualityContext"]["naturalMode"] is True
    assert "naturalMode" not in default_context["qualityContext"]


def test_relationship_gating_eval_uses_natural_role_calibration() -> None:
    """事件前后只比较关系权限，不能让旧评测腔污染角色对白。"""

    module = _load_eval_module()
    cases = module.quality_cases_for_suite("relationship-stage-gating")

    elliott = next(
        case for case in cases if case.case_id == "relationship-gate-elliott-after"
    )
    elliott_context = module._build_context(module.ContextBuilder(), elliott)
    assert elliott_context["qualityContext"]["naturalMode"] is True
    assert (
        elliott_context["qualityContext"]["styleCalibration"]
        == "elliott_original_rhythm"
    )

    non_elliott = next(case for case in cases if case.npc_id != "Elliott")
    non_elliott_context = module._build_context(
        module.ContextBuilder(), non_elliott
    )
    assert non_elliott_context["qualityContext"]["naturalMode"] is True



def test_eval_carries_turn_intent_and_stage_provenance_into_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    captured_histories: list[list[dict[str, object]]] = []

    class CapturingProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del messages
            captured_histories.append([dict(item) for item in request.history])
            return ProviderResult(
                reply="我记下了。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", CapturingProvider)
    monkeypatch.setattr(
        module,
        "retry_for_format_noise",
        lambda result, messages, generate: result,
    )
    case = CharacterQualityCase(
        case_id="history-provenance",
        profile_key="wizard",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="dating",
        channel="remote",
        message="",
        friendship_hearts=10,
        relationship_context="Wizard 正在和玩家继续一段确认中的恋爱关系。",
        turns=(
            CharacterQualityTurn("turn-1", "先聊聊塔里的读数。", intent="chat"),
            CharacterQualityTurn("turn-2", "切到研究话题。", intent="topic"),
            CharacterQualityTurn("turn-3", "给你一枚物品。", intent="item"),
        ),
    )

    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
    )

    assert captured_histories[1][-2:] == [
        {
            "role": "user",
            "content": "先聊聊塔里的读数。",
            "intent": "chat",
            "relationshipStage": "dating",
        },
        {
            "role": "assistant",
            "content": "我记下了。",
            "intent": "chat",
            "relationshipStage": "dating",
        },
    ]
    assert captured_histories[2][-2:] == [
        {
            "role": "user",
            "content": "切到研究话题。",
            "intent": "topic",
            "relationshipStage": "dating",
        },
        {
            "role": "assistant",
            "content": "我记下了。",
            "intent": "topic",
            "relationshipStage": "dating",
        },
    ]


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


def test_eval_cloud_provider_defaults_to_google_gemini_endpoint_and_model(
    monkeypatch,
) -> None:
    module = _load_eval_module()
    captured: dict[str, object] = {}

    class CapturingProvider:
        def __init__(self, settings) -> None:
            captured["settings"] = settings

    for name in (
        "BRIDGE_CLOUD_URL",
        "BRIDGE_CLOUD_BASE_URL",
        "BRIDGE_CLOUD_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(module, "OpenAICompatibleProvider", CapturingProvider)

    module._build_provider(
        "cloud",
        endpoint=None,
        model=None,
        timeout=None,
    )

    settings = captured["settings"]
    assert (
        settings.url
        == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    assert settings.model == "gemini-3.7-flash"


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


def test_economical_budget_has_small_smoke_defaults_and_cli_switch(
    monkeypatch,
) -> None:
    module = _load_eval_module()

    budget = module.EvaluationBudget.economical()

    assert budget.max_cases == 3
    assert budget.max_requests == 24
    assert budget.max_npc_retries == 1
    assert budget.max_player_retries == 0
    assert budget.compact_prompt is True
    assert budget.dynamic_player_input is True
    assert module._parse_args(["--economical"]).economical is True


def test_eval_stops_before_next_request_when_budget_is_reached(
    monkeypatch,
    tmp_path: Path,
) -> None:
    if topic_start_intimacy_cases is None:
        raise AssertionError("topic-start-intimacy 案例套件尚未实现")

    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    calls = 0

    class CapturingProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            nonlocal calls
            del request, messages
            calls += 1
            return ProviderResult(
                reply=f"第{calls}轮内容。",
                provider="local",
                fallback=False,
                latencyMs=12,
                usage={
                    "inputTokens": 10,
                    "outputTokens": 2,
                    "totalTokens": 12,
                },
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", CapturingProvider)
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(topic_start_intimacy_cases()[0],),
        budget=module.EvaluationBudget(
            max_requests=2,
            max_total_tokens=1000,
            max_npc_retries=0,
            max_player_retries=0,
            compact_prompt=True,
        ),
    )

    assert calls == 2
    assert summary["requestCount"] == 2
    assert summary["processedTurnCount"] == 2
    assert summary["budgetStopReason"] == "max_requests"
    assert summary["budget"]["maxRequests"] == 2


def test_eval_records_request_retry_and_usage_counts_without_prompt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    calls = 0

    class NoisyThenCleanProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            nonlocal calls
            del request, messages
            calls += 1
            return ProviderResult(
                reply=(
                    "**今天还行。**"
                    if calls == 1
                    else "今天还行，事情不多。"
                ),
                provider="local",
                fallback=False,
                latencyMs=12,
                usage={
                    "inputTokens": 10,
                    "outputTokens": 2,
                    "totalTokens": 12,
                },
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", NoisyThenCleanProvider)
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-daily"),),
        budget=module.EvaluationBudget(
            max_requests=2,
            max_npc_retries=1,
            max_player_retries=0,
            compact_prompt=True,
        ),
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert calls == 2
    assert record["turns"][0]["requestCount"] == 2
    assert record["turns"][0]["retryCount"] == 1
    assert record["turns"][0]["usage"]["totalTokens"] == 24
    assert summary["npcRetryCount"] == 1
    assert "prompt" not in json.dumps(record, ensure_ascii=False)


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
                reply = "第三组稳定了，第二组还得重测。你想先看第二组还是第三组的记录？"
            elif len(calls) == 3:
                reply = "第二组先重测输入。你想先核对记录还是参数？"
            else:
                reply = "记录看完了，结论我已经写下。你想先看哪一条？"
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
    assert record["reply"] == "第三组稳定了，第二组还得重测。你想先看第二组还是第三组的记录？"
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


def test_eval_topic_case_sends_empty_topic_without_polluting_player_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    if topic_start_intimacy_cases is None:
        raise AssertionError("topic-start-intimacy 案例套件尚未实现")

    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    captured_requests = []
    captured_messages = []

    class CapturingProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            captured_requests.append(request)
            captured_messages.append(messages)
            turn = len(captured_requests)
            return ProviderResult(
                reply=f"第{turn}轮主动内容",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", CapturingProvider)
    monkeypatch.setattr(
        module,
        "retry_for_format_noise",
        lambda result, messages, generate: result,
    )
    case = topic_start_intimacy_cases()[0]
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
        suite="topic-start-intimacy",
    )

    assert summary["suite"] == "topic-start-intimacy"
    assert len(captured_requests) == 3
    assert captured_requests[0].intent == "topic"
    assert captured_requests[0].message == ""
    assert captured_requests[0].history == []
    assert captured_requests[1].intent == "chat"
    assert captured_requests[1].message == case.dialogue_turns()[1].message
    assert captured_requests[2].intent == "chat"
    assert captured_requests[2].message == case.dialogue_turns()[2].message
    assert all(
        not (item.get("role") == "user" and item.get("content") == "")
        for item in captured_requests[1].history
    )
    assert captured_requests[1].history[-1] == {
        "role": "assistant",
        "content": "第1轮主动内容",
        "intent": "topic",
        "relationshipStage": "dating",
    }
    assert captured_requests[2].history[-2:] == [
        {
            "role": "user",
            "content": case.dialogue_turns()[1].message,
            "intent": "chat",
            "relationshipStage": "dating",
        },
        {
            "role": "assistant",
            "content": "第2轮主动内容",
            "intent": "chat",
            "relationshipStage": "dating",
        },
    ]
    assert captured_requests[2].history[-1] == {
        "role": "assistant",
        "content": "第2轮主动内容",
        "intent": "chat",
        "relationshipStage": "dating",
    }
    assert any(
        item.get("name") == "topic_response_contract"
        for item in captured_messages[0]
    )
    assert any(
        item.get("name") == "topic_trigger" and item.get("content") == ""
        for item in captured_messages[0]
    )
    assert not any(
        item.get("name") == "topic_response_contract"
        for item in captured_messages[1]
    )
    assert any(
        item.get("name") == "player_input"
        and item.get("content") == case.dialogue_turns()[1].message
        for item in captured_messages[1]
    )
    assert any('"topicSeed"' in item["content"] for item in captured_messages[0])
    assert any('"topicKeywords"' in item["content"] for item in captured_messages[0])
    assert any('"continuationMode"' in item["content"] for item in captured_messages[0])
    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert [turn["turnPlan"]["mode"] for turn in record["turns"]] == [
        "answer_plus_lead",
        "answer_plus_lead",
        "answer_plus_lead",
    ]
    assert all(
        "missing_proactive_affection" not in turn["score"]["tags"]
        for turn in record["turns"]
    )
    assert record["casePassed"] is False
    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert record["caseNumber"] == 1
    assert record["suite"] == "topic-start-intimacy"


def test_eval_adaptive_topic_case_generates_player_turns_after_each_npc_reply(
    monkeypatch,
    tmp_path: Path,
) -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    captured = []

    class AdaptiveProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            captured.append((request, messages))
            if any(item.get("name") == "player_simulator" for item in messages):
                return ProviderResult(
                    reply="你刚才说的那盏灯还亮着吗？",
                    provider="local",
                    fallback=False,
                    latencyMs=12,
                )
            return ProviderResult(
                reply="塔里的灯还亮着，今晚想和你多待一会儿。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", AdaptiveProvider)
    monkeypatch.setattr(
        module,
        "retry_for_format_noise",
        lambda result, messages, generate: result,
    )
    case = topic_start_adaptive_cases()[0]
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
        suite="topic-start-adaptive",
    )

    assert summary["suite"] == "topic-start-adaptive"
    assert summary["npcRequestCount"] == 3
    assert summary["playerInputRequestCount"] == 2
    assert summary["playerInputValidCount"] == 2
    assert summary["playerInputInvalidCount"] == 0
    assert summary["playerInputQualityTags"] == []
    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    turns = record["turns"]
    assert [turn["playerInputSource"] for turn in turns] == ["fixed", "generated", "generated"]
    assert turns[1]["playerInput"] == "你刚才说的那盏灯还亮着吗？"
    assert turns[2]["playerInput"] == "你刚才说的那盏灯还亮着吗？"
    assert turns[1]["playerInputQuality"]["valid"] is True
    assert turns[1]["intent"] == "chat"
    assert captured[1][1][0]["name"] == "player_simulator"
    assert captured[3][1][0]["name"] == "player_simulator"


def test_adaptive_topic_scoring_uses_turn_plan_for_affection_diagnostic(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """普通找话题回合不应被旧的 proactive 诊断重新标成亲密失败。"""

    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)

    class PlainAdaptiveProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request, messages
            return ProviderResult(
                reply="桌上的记录还在，我先把最后一页看完。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", PlainAdaptiveProvider)
    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-wizard-married-study"
    )
    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
        suite="topic-start-adaptive",
        budget=module.EvaluationBudget(
            max_cases=1,
            max_requests=6,
            max_npc_retries=1,
            max_player_retries=0,
            compact_prompt=True,
            dynamic_player_input=False,
        ),
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert [turn["turnPlan"]["mode"] for turn in record["turns"]] == [
        "answer_only",
        "answer_only",
        "answer_only",
    ]
    assert all(
        "missing_proactive_affection" not in turn["score"]["tags"]
        for turn in record["turns"]
    )
    assert all(
        "response_affection_retry: missing_proactive_affection"
        not in turn["warnings"]
        for turn in record["turns"]
    )


def test_player_simulator_prompt_is_reply_anchored_and_respects_control_boundary() -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    target = topic_start_adaptive_cases()[0]
    control = next(
        case for case in topic_start_adaptive_cases() if case.flirt_intensity == "none"
    )
    target_prompt = module._player_simulator_messages(
        target,
        previous_reply="今晚的月光很亮，我还在整理记录。",
        history=[{"role": "assistant", "content": "今晚的月光很亮，我还在整理记录。"}],
        turn_number=2,
    )[0]["content"]
    control_prompt = module._player_simulator_messages(
        control,
        previous_reply="鸡舍今天很安静，饲料也刚添好。",
        history=[{"role": "assistant", "content": "鸡舍今天很安静，饲料也刚添好。"}],
        turn_number=2,
    )[0]["content"]

    assert "不能只摘抄一个词" in target_prompt
    assert "不要复述 NPC 原句" in target_prompt
    assert "不要使用‘你刚才提到的……后来怎么样了’这种固定句式" in target_prompt
    assert "最多 60 个汉字" in target_prompt
    assert "高亲密关系" in target_prompt
    assert "不调情、不升级关系" in control_prompt


def test_adaptive_player_simulator_uses_one_plain_reaction_without_literary_analysis() -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    target = topic_start_adaptive_cases()[0]
    prompt = module._player_simulator_messages(
        target,
        previous_reply="今晚的月光很亮，我还在整理记录。",
        history=[{"role": "assistant", "content": "今晚的月光很亮，我还在整理记录。"}],
        turn_number=2,
    )[0]["content"]

    assert "像熟人随口接话" in prompt
    assert "不要分析文学手法" in prompt
    assert "不要连续问两个问题" in prompt
    assert "不要复述对方完整比喻" in prompt
    assert "无论 NPC 多文学，玩家都用普通口语" in prompt
    assert "不要接着写景或改写意象" in prompt


def test_adaptive_elliott_follow_ups_drop_inherited_affection_kinds() -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )

    assert [turn.initiative_kind for turn in case.dialogue_turns()[1:]] == [
        "none",
        "none",
    ]


def test_adaptive_player_prompt_prefers_plain_reaction_to_literary_analysis() -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )
    prompt = module._player_simulator_messages(
        case,
        previous_reply="月光落在纸边，我还在改最后一句。",
        history=[{"role": "assistant", "content": "月光落在纸边，我还在改最后一句。"}],
        turn_number=2,
    )[0]["content"]

    assert "文学分享时优先用日常口语接话" in prompt


def test_adaptive_player_prompt_does_not_turn_a_concrete_line_into_a_literary_verdict() -> None:
    """玩家模拟不能把 NPC 的一句具体话改写成评测式文学结论。"""

    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-reading"
    )
    prompt = module._player_simulator_messages(
        case,
        previous_reply="我只记得那一行，船在雾里偏了方向，后来才看见灯塔。",
        history=[
            {
                "role": "assistant",
                "content": "我只记得那一行，船在雾里偏了方向，后来才看见灯塔。",
            }
        ],
        turn_number=2,
    )[0]["content"]

    assert "先问具体内容或说第一反应" in prompt
    assert "不要把一句话总结成‘什么都说了’或‘更有分量’" in prompt
    assert "不要写成文学评论或普遍道理" in prompt


def test_adaptive_cases_use_a_player_card_that_leaves_initiative_to_npc() -> None:
    """自适应测试例应有稳定的玩家口吻，而不是把评测步骤写进对白。"""

    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    target = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )
    card = target.player_expression_card
    assert card is not None
    assert "渴望被爱" in card.relationship_stance
    assert "不配得感" in card.relationship_stance
    assert "说得太满" in card.self_correction
    assert "把选择留给" in card.distance_pattern or "话头" in card.distance_pattern


def test_adaptive_topic_opener_does_not_inherit_intimacy_opening_contract() -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    target = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )
    first_turn = target.dialogue_turns()[0]

    assert first_turn.initiative_expectation == "none"
    assert first_turn.initiative_kind == "none"
    assert first_turn.turn_plan_mode == "answer_only"
    assert "亲密邀约" not in first_turn.evaluation_focus


def test_adaptive_player_prompt_exposes_card_and_discourages_scripted_flirt() -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )
    prompt = module._player_simulator_messages(
        case,
        previous_reply="信还在窗台上晾着，墨水没干。",
        history=[{"role": "assistant", "content": "信还在窗台上晾着，墨水没干。"}],
        turn_number=2,
    )[0]["content"]

    assert "玩家表达卡" in prompt
    assert "渴望被爱" in prompt
    assert "把话头留给 NPC" in prompt
    assert "不要写成告白、情书或小诗" in prompt
    assert "半句" in prompt
    assert "帮忙" in prompt


def test_adaptive_player_prompt_uses_one_choice_free_reaction_instead_of_a_menu() -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )
    prompt = module._player_simulator_messages(
        case,
        previous_reply="信还在窗台上晾着，墨水没干。",
        history=[{"role": "assistant", "content": "信还在窗台上晾着，墨水没干。"}],
        turn_number=2,
    )[0]["content"]

    assert "抓住一个点说自己的第一反应" in prompt
    assert "可以回应、轻轻打趣或问一个小问题，也可以只回半句" not in prompt


def test_adaptive_player_prompt_prefers_unpolished_phone_chat_over_ai_like_lines() -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    case = next(
        item
        for item in topic_start_adaptive_cases()
        if item.case_id == "adaptive-topic-elliott-married-letter"
    )
    prompt = module._player_simulator_messages(
        case,
        previous_reply="写的时候我就知道它不太驯服，但删掉它，整封信就少了点真话。",
        history=[
            {
                "role": "assistant",
                "content": "写的时候我就知道它不太驯服，但删掉它，整封信就少了点真话。",
            }
        ],
        turn_number=3,
    )[0]["content"]

    assert "像手机上临时想到就发的一小句普通话" in prompt
    assert "不用追求机灵、暧昧或文采" in prompt
    assert "不要把感受总结完整" in prompt


def test_fake_player_input_uses_a_concrete_anchor_from_previous_reply() -> None:
    module = _load_eval_module()
    case = next(
        case for case in module.DEFAULT_CASES if case.case_id == "wizard-daily"
    )

    generated = module._fake_player_input(
        case,
        "今晚的月光很好，我整理记录时又想起你了。",
    )

    assert "月光" in generated or "记录" in generated
    assert generated not in {
        "听起来不错。你愿意再说一点吗？",
        "真的吗？你是说今晚的月光很好，我整理记录时吗？",
    }


def test_adaptive_eval_diagnoses_restatement_from_the_actual_generated_input(
    monkeypatch,
    tmp_path: Path,
) -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    npc_turn = 0

    class AdaptiveRestatementProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            nonlocal npc_turn
            if any(item.get("name") == "player_simulator" for item in messages):
                return ProviderResult(
                    reply="你刚才提到的月光与研究记录，我想听下去。",
                    provider="local",
                    fallback=False,
                    latencyMs=12,
                )
            npc_turn += 1
            replies = (
                "今晚的月光很好，我整理记录时又想起你了。",
                "你刚才提到的月光与研究记录，我也可以继续说。",
                "我给你留一杯茶，等你有空再一起喝。",
            )
            return ProviderResult(
                reply=replies[npc_turn - 1],
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", AdaptiveRestatementProvider)
    monkeypatch.setattr(
        module,
        "retry_for_format_noise",
        lambda result, messages, generate: result,
    )
    case = topic_start_adaptive_cases()[0]
    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
        suite="topic-start-adaptive",
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert record["turns"][1]["mechanicalRestatement"] is True
    assert "mechanical_restatement" in record["turns"][1]["initiativeTags"]
    assert "mechanical_restatement" in record["turns"][1]["score"]["tags"]


def test_eval_marks_repeated_personal_affection_shape_as_failed_quality(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)

    class RepeatedAffectionProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request, messages
            return ProviderResult(
                reply="这首歌我只想先给你听。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", RepeatedAffectionProvider)
    monkeypatch.setattr(
        module,
        "retry_for_format_noise",
        lambda result, messages, generate: result,
    )
    case = CharacterQualityCase(
        case_id="variation-sophia-dating",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="dating",
        channel="remote",
        message="",
        friendship_hearts=10,
        flirt_intensity="direct",
        adult_consensual=True,
        romance_eligible=True,
        relationship_context="已确认恋爱关系，Sophia 想把新曲先分享给玩家。",
        turns=(
            CharacterQualityTurn(
                "turn-1",
                "聊聊新歌。",
                expected_terms=("歌",),
                initiative_expectation="proactive",
                initiative_kind="creative_share",
            ),
            CharacterQualityTurn(
                "turn-2",
                "你刚才说的歌是什么？",
                expected_terms=("歌",),
                initiative_expectation="proactive",
                initiative_kind="creative_share",
            ),
            CharacterQualityTurn(
                "turn-3",
                "再给我听一点。",
                expected_terms=("歌",),
                initiative_expectation="proactive",
                initiative_kind="creative_share",
            ),
        ),
    )

    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    second_turn = record["turns"][1]
    assert second_turn["affectionVariation"]["mechanical"] is True
    assert "mechanical_affection_shape" in second_turn["affectionVariation"]["tags"]
    assert second_turn["score"]["passed"] is False
    assert "mechanical_affection_shape" in second_turn["score"]["tags"]
    assert "mechanical_affection_shape" in record["progression"]["tags"]
    assert record["casePassed"] is False


def test_eval_uses_detected_initiative_kind_for_affection_variation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)

    class RepeatedShareProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request, messages
            return ProviderResult(
                reply="这首歌我只想先给你听。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", RepeatedShareProvider)
    monkeypatch.setattr(
        module,
        "retry_for_format_noise",
        lambda result, messages, generate: result,
    )
    case = CharacterQualityCase(
        case_id="variation-detected-kind",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="dating",
        channel="remote",
        message="",
        friendship_hearts=10,
        flirt_intensity="direct",
        adult_consensual=True,
        romance_eligible=True,
        relationship_context="已确认恋爱关系，Sophia 想把新曲先分享给玩家。",
        turns=(
            CharacterQualityTurn(
                "turn-1",
                "聊聊新歌。",
                expected_terms=("歌",),
                initiative_expectation="proactive",
                initiative_kind="specific_plan",
            ),
            CharacterQualityTurn(
                "turn-2",
                "再放一点。",
                expected_terms=("歌",),
                initiative_expectation="proactive",
                initiative_kind="shared_evening",
            ),
        ),
    )

    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    second_turn = record["turns"][1]
    assert second_turn["initiativeKind"] == "shared_evening"
    assert second_turn["detectedInitiativeKind"] == "creative_share"
    assert second_turn["affectionVariation"]["mechanical"] is True


def test_eval_marks_repeated_conversation_lead_as_failed_quality(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)

    class RepeatedConversationLeadProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request
            player_input = next(
                (
                    item.get("content", "")
                    for item in reversed(messages)
                    if item.get("name") == "player_input"
                ),
                "",
            )
            reply = (
                "新歌还是不错。你想先听完整的还是副歌？"
                if "听起来怎么样" in player_input
                else "新歌听起来不错。你想先听完整的还是副歌？"
            )
            return ProviderResult(
                reply=reply,
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", RepeatedConversationLeadProvider)
    monkeypatch.setattr(
        module,
        "retry_for_format_noise",
        lambda result, messages, generate: result,
    )
    case = CharacterQualityCase(
        case_id="conversation-lead-sophia-dating",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="dating",
        channel="remote",
        message="",
        friendship_hearts=10,
        flirt_intensity="direct",
        adult_consensual=True,
        romance_eligible=True,
        relationship_context="已确认恋爱关系，Sophia 想和玩家聊聊新歌。",
        turns=(
            CharacterQualityTurn(
                "turn-1",
                "新歌还不错吗？",
                expected_terms=("歌",),
            ),
            CharacterQualityTurn(
                "turn-2",
                "新歌听起来怎么样？",
                expected_terms=("歌",),
            ),
        ),
    )

    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    second_turn = record["turns"][1]
    assert second_turn["conversationLeadVariation"]["mechanical"] is True
    assert (
        "mechanical_conversation_lead"
        in second_turn["conversationLeadVariation"]["tags"]
    )
    assert second_turn["score"]["passed"] is False
    assert "mechanical_conversation_lead" in second_turn["score"]["tags"]
    assert "mechanical_conversation_lead" in record["progression"]["tags"]
    assert record["casePassed"] is False


def test_eval_adaptive_player_input_failure_is_reported_without_fake_npc_reply(
    monkeypatch,
    tmp_path: Path,
) -> None:
    if topic_start_adaptive_cases is None:
        raise AssertionError("topic-start-adaptive 案例套件尚未实现")

    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)

    class FailingPlayerSimulator:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            if any(item.get("name") == "player_simulator" for item in messages):
                raise RuntimeError("simulated player input failure")
            return ProviderResult(
                reply="塔里的灯还亮着。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", FailingPlayerSimulator)
    monkeypatch.setattr(
        module,
        "retry_for_format_noise",
        lambda result, messages, generate: result,
    )
    case = topic_start_adaptive_cases()[0]
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
        suite="topic-start-adaptive",
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert summary["successfulTurns"] == 1
    assert summary["playerInputRequestCount"] == 1
    assert record["turns"][1]["playerInputSource"] == "generated"
    assert record["turns"][1]["playerInputError"] == "RuntimeError"
    assert "reply" not in record["turns"][1]


def test_eval_cli_parses_topic_suite_and_limit() -> None:
    module = _load_eval_module()

    args = module._parse_args(
        ["--suite", "topic-start-intimacy", "--limit", "3"]
    )

    assert args.suite == "topic-start-intimacy"
    assert args.limit == 3


def test_eval_cli_defaults_to_the_resolved_profile_index_with_sophia_voice_data() -> None:
    module = _load_eval_module()

    args = module._parse_args([])

    assert args.profile_index.name == (
        "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
    )
    voice_card = ProfileIndexStore(args.profile_index).voice_card(
        "Sophia",
        relationship_stage="married",
    )
    assert voice_card["voiceAnchors"]


def test_eval_cli_parses_conversation_lead_suite() -> None:
    module = _load_eval_module()

    args = module._parse_args(["--suite", "conversation-lead"])

    assert args.suite == "conversation-lead"


def test_eval_cli_parses_affection_pacing_suite() -> None:
    module = _load_eval_module()

    args = module._parse_args(["--suite", "affection-pacing"])

    assert args.suite == "affection-pacing"


def test_eval_cli_parses_relationship_world_suite() -> None:
    module = _load_eval_module()

    args = module._parse_args(["--suite", "relationship-world", "--limit", "5"])

    assert args.suite == "relationship-world"
    assert args.limit == 5


def test_eval_cli_parses_deep_flirt_suite() -> None:
    module = _load_eval_module()

    args = module._parse_args(["--suite", "deep-flirt", "--limit", "4"])

    assert args.suite == "deep-flirt"
    assert args.limit == 4


def test_eval_builds_relationship_world_into_each_request() -> None:
    module = _load_eval_module()
    case = next(
        item
        for item in module.quality_cases_for_suite("relationship-world")
        if item.npc_id == "Shane"
    )

    request = module._build_request(case)

    assert request.relationship_world is not None
    assert request.relationship_world.views
    assert request.relationship_world.objective_relationships == []
    assert request.display_name == "珊恩"


def test_eval_records_resolved_feminine_display_name(
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    case = next(
        item
        for item in module.quality_cases_for_suite("relationship-world")
        if item.npc_id == "Shane"
    )

    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
        provider="fake",
        suite="relationship-world",
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert record["displayName"] == "珊恩"


def test_eval_records_relationship_diagnostics_only_for_relationship_suite(
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    case = module.quality_cases_for_suite("relationship-world")[0]

    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case,),
        provider="fake",
        suite="relationship-world",
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert summary["suite"] == "relationship-world"
    assert record["suite"] == "relationship-world"
    assert all(
        {
            "relationshipVisibility",
            "relationshipAcceptance",
            "mediationStatus",
            "jealousyTrigger",
            "jealousyActive",
        }.issubset(turn)
        for turn in record["turns"]
    )
    assert "relationshipWorld" not in record

    default_case = case_by_id("wizard-daily")
    default_output = tmp_path / "default"
    module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=default_output,
        cases=(default_case,),
        provider="fake",
        suite="default",
    )
    default_record = json.loads(
        (default_output / "results.jsonl").read_text(encoding="utf-8")
    )
    assert "relationshipVisibility" not in default_record["turns"][0]


def test_eval_records_affection_pacing_fields_for_selected_suite(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    cases = module.quality_cases_for_suite("affection-pacing")

    class StableProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request, messages
            return ProviderResult(
                reply="炉火还暖着，今晚先把记录放一放，过来坐一会儿。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", StableProvider)
    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=cases[:1],
        suite="affection-pacing",
    )

    record = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert summary["suite"] == "affection-pacing"
    assert "affectionPacing" in summary
    assert isinstance(summary["affectionPacing"]["eligibleTurns"], int)
    assert record["suite"] == "affection-pacing"
    assert "affectionPacing" in record
    assert len(record["turns"]) == 3
    assert all("affectionPacing" in turn for turn in record["turns"])


def test_eval_cli_allows_fake_provider_for_offline_smoke() -> None:
    module = _load_eval_module()

    args = module._parse_args(["--provider", "fake", "--limit", "3"])

    assert args.provider == "fake"
    assert module._build_provider(
        "fake",
        endpoint=None,
        model=None,
        timeout=None,
    ).name == "fake"


def test_eval_deep_flirt_fake_provider_carries_three_turn_history_for_dating_and_married(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """deep-flirt 的两种关系阶段都必须按三轮连续传递 NPC 回复。"""

    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)
    captured_requests = []
    captured_messages = []

    class FakeProvider:
        name = "fake"

        def generate(self, request, *, messages):
            captured_requests.append(request)
            captured_messages.append(messages)
            turn_number = len(captured_requests)
            return ProviderResult(
                reply=f"fake-reply-{turn_number}",
                provider="fake",
                fallback=False,
                latencyMs=0,
            )

    monkeypatch.setattr(
        module,
        "_build_provider",
        lambda provider, *, endpoint, model, timeout: FakeProvider(),
    )
    cases = module.quality_cases_for_suite("deep-flirt")
    selected_cases = (cases[0], cases[2])

    summary = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=selected_cases,
        provider="fake",
        suite="deep-flirt",
    )

    assert summary["suite"] == "deep-flirt"
    assert summary["caseCount"] == 2
    assert summary["successfulTurns"] == 6
    assert len(captured_requests) == 6
    assert len(captured_messages) == 6

    for case_index, case in enumerate(selected_cases):
        request_group = captured_requests[case_index * 3 : case_index * 3 + 3]
        assert [request.message for request in request_group] == [
            turn.message for turn in case.dialogue_turns()
        ]
        assert all(request.channel == "face_to_face" for request in request_group)
        assert all(
            not (item.get("role") == "user" and item.get("content") == "")
            for request in request_group
            for item in request.history
        )
        assert request_group[1].history[-1]["content"] == "fake-reply-" + str(
            case_index * 3 + 1
        )
        assert request_group[2].history[-1]["content"] == "fake-reply-" + str(
            case_index * 3 + 2
        )

    record_lines = (tmp_path / "results.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in record_lines if line.strip()]
    assert len(records) == 2
    assert all(record["suite"] == "deep-flirt" for record in records)
    assert all(len(record["turns"]) == 3 for record in records)
    assert all(
        all(turn["playerInputSource"] == "fixed" for turn in record["turns"])
        for record in records
    )
    assert all(
        "initiativeExpectation" in turn and "initiativeKind" in turn
        for record in records
        for turn in record["turns"]
    )
