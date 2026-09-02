from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from stardew_ai_bridge.models import ProviderResult
from stardew_ai_bridge.profile_index import ProfileIndexStore
from stardew_ai_bridge.character_quality_eval import case_by_id

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
    }
    assert captured_requests[2].history[-2:] == [
        {"role": "user", "content": case.dialogue_turns()[1].message},
        {"role": "assistant", "content": "第2轮主动内容"},
    ]
    assert captured_requests[2].history[-1] == {
        "role": "assistant",
        "content": "第2轮主动内容",
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
    assert all(
        "missing_proactive_affection" in turn["score"]["tags"]
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
    assert "不要使用‘你刚才提到的……后来怎么样了’这类测试模板" in target_prompt
    assert "最多 60 个汉字" in target_prompt
    assert "高亲密关系" in target_prompt
    assert "不调情、不升级关系" in control_prompt


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
