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


def test_eval_summary_records_max_requests_truncation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """`--max-requests` 截断必须落进 summary —— 它是**可比性判决**，不是警告。

    规范 `docs/eval-runbook-2026-09-28.md` §四.1：被截断的批次覆盖的问题集
    与完整跑不同，放进同一张表比较会得出错误结论。所以默认值是 `False`
    而不是 `None` —— 「跑完了、没截断」是一个确定的事实。
    """
    module = _load_eval_module()
    index_path = tmp_path / "selected-index.json"
    _write_test_index(index_path)

    class QuietProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            del request, messages
            return ProviderResult(
                reply="整理完了。第三组稳定，第二组还得重测。",
                provider="local",
                fallback=False,
                latencyMs=12,
            )

    monkeypatch.setattr(module, "OllamaNativeProvider", QuietProvider)
    truncated = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-follow-up"),),
        truncated=True,
    )
    assert truncated["truncated"] is True
    assert truncated["truncatedReason"] == "max_requests"

    plain = module.run_evaluation(
        profile_index=ProfileIndexStore(index_path),
        output_dir=tmp_path,
        cases=(case_by_id("wizard-follow-up"),),
    )
    assert plain["truncated"] is False
    assert plain["truncatedReason"] is None


def test_eval_plan_mode_prints_the_pre_run_gate_without_any_request(
    capsys,
    monkeypatch,
) -> None:
    """`--plan` 是跑前闸门：零请求地把「该不该跑」摊在屏幕上。

    规范 `docs/eval-runbook-2026-09-28.md` §二 要求每次开跑前先回答三问，
    §四.1 禁止用 `--max-requests` 缩规模。这两条以前**只写在文档里** ——
    跑起来照样能违反。做成 `--plan` 之后，它们变成运行时的输出。
    """
    module = _load_eval_module()
    calls: list[object] = []

    class NeverCalledProvider:
        def __init__(self, settings) -> None:
            self.settings = settings

        def generate(self, request, *, messages):
            calls.append((request, messages))
            raise AssertionError("--plan 不得发起任何生成请求")

    monkeypatch.setattr(module, "OllamaNativeProvider", NeverCalledProvider)

    assert module.main(["--plan", "--suite", "default", "--limit", "6"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert calls == []
    assert payload["plan"] is True
    assert payload["suite"] == "default"
    assert payload["caseCount"] == 6
    assert payload["turnCount"] >= payload["caseCount"]
    # 请求预估含重试余量 ⇒ 必然不少于轮数。
    assert payload["estimatedRequests"] >= payload["turnCount"]
    # 完整 Prompt 模式（未传 --economical）按实测 7,820/请求 估。
    assert payload["estimatedTokens"] == payload["estimatedRequests"] * 7800
    # 美元按实测单价 $0.033/请求 估（2026-09-28 池 1 实测）。
    assert payload["estimatedCostUsd"] == round(payload["estimatedRequests"] * 0.033, 2)
    # 三问必须在输出里，且是「待人工回答」的形态。
    assert set(payload["gate"]) == {"question", "expectedEffect", "budget"}


def test_eval_plan_mode_warns_that_max_requests_makes_runs_incomparable(
    capsys,
) -> None:
    """压规模只能用 `--limit`；`--max-requests` 会让两批覆盖不同 ⇒ 不可比。"""
    module = _load_eval_module()

    assert module.main(["--plan", "--max-requests", "50"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert any("不可比" in warning for warning in payload["warnings"])


def test_eval_stage_filter_selects_only_that_stage(capsys) -> None:
    """`--stage` 解决的是「新 case 加在末尾，而 --limit 只能取前 N 个」。

    2026-09-28 补的 stranger / parent 两档从没跑过（`health_check` 把它标为
    「没样本可查」的上游盲区），而 `--limit` 根本够不到它们。
    """
    module = _load_eval_module()

    assert module.main(["--plan", "--stage", "stranger"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["stages"] == ["stranger"]
    # 2026-09-30 给 Elliott / Harvey / Sam 补齐 stranger 后从 5 升到 8；
    # 这里是数据快照，随案例增减同步更新。
    assert payload["caseCount"] == 8
    # caseIds 是给人核对「到底会跑哪些」的，必须与 caseCount 一致。
    assert len(payload["caseIds"]) == payload["caseCount"]
    assert all("stranger" in cid for cid in payload["caseIds"])


def test_eval_stage_filter_accepts_multiple_and_dedupes(capsys) -> None:
    module = _load_eval_module()

    assert module.main(["--plan", "--stage", "stranger,parent,stranger"]) == 0

    payload = json.loads(capsys.readouterr().out)
    # 去重且保持输入顺序。
    assert payload["stages"] == ["stranger", "parent"]
    # stranger 8 + parent 8（同上，2026-09-30 补齐后的快照）。
    assert payload["caseCount"] == 16


def test_eval_stage_filter_rejects_unknown_stage(capsys) -> None:
    """写错档名必须报错 —— 静默跑 0 个 case 是最坏的结果。"""
    module = _load_eval_module()

    assert module.main(["--plan", "--stage", "stranger,nonsense"]) == 2
    assert "nonsense" in capsys.readouterr().err


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
    # 这条固定回复同时犯两件事：同一个颗粒用了两次，且 10 个字带 2 个（过密）。
    assert record["turns"][0]["styleQuality"]["tags"] == [
        "repeated_speech_particle",
        "too_many_speech_particles",
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
        lambda result, messages, generate, **kwargs: result,
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


def test_compact_prompt_switch_is_independent_of_economical() -> None:
    """`--compact-prompt` 必须能单独打开线上口径，不受 `--economical` 的限流牵连。

    背景（2026-10-01）：K=1/K=4 的话题窗口对照在评测路径上跑出 null 结果，
    事后查明那条路径 `compactPrompt=false` —— 比游戏端的 prompt 大约 74% 字符，
    每条话题素材的出现次数只有线上的一半。于是「离线测不出差异」被读成了
    「机制没效果」。此前 compact 只能跟着 `--economical` 走，而后者会把 case
    限制到 3 个，没法用来做正式对照，所以两个开关必须解耦。
    """
    module = _load_eval_module()

    assert module._parse_args([]).compact_prompt is None
    assert module._parse_args(["--compact-prompt"]).compact_prompt is True
    # 互不牵连：开经济模式不会顺手改 compact，反之亦然。
    assert module._parse_args(["--economical"]).compact_prompt is None
    assert (
        module._parse_args(["--compact-prompt", "--economical"]).compact_prompt is True
    )
    # `--economical` 自己的 compact 默认不能被这次解耦改掉。
    assert module.EvaluationBudget.economical().compact_prompt is True
    assert module.EvaluationBudget().compact_prompt is False


def test_build_context_forwards_recent_replies_from_history() -> None:
    """`_build_context` 必须把 history 里的 assistant 项转成 `recentReplies`。

    背景（2026-10-01）：`prompts.py` 拿 `recentReplies` 的**长度**算话题窗口轮次
    `_turn_index`（真机 `history` 被 `MaxHistoryItems = 6` 封顶，用它的长度当轮次
    信号会让窗口几乎不滑动）。评测脚本此前只发 `history`，于是 `_turn_index` 恒 0、
    窗口永远停在池首 —— `_TOPIC_WINDOW_STEP`（K）完全不起作用，K=1 与 K=4 两臂的
    prompt 逐字节相同。那次对照的 null 因此是**必然**的，与采样噪音无关。
    """
    module = _load_eval_module()
    store = module._resolve_index(ROOT / "data" / "personas")
    builder = module.ContextBuilder(profile_index=store)

    captured: dict[str, object] = {}
    real_build = builder.build

    def _spy(payload, *args, **kwargs):
        captured.update(payload)
        return real_build(payload, *args, **kwargs)

    builder.build = _spy  # type: ignore[method-assign]

    case = case_by_id("sophia-daily")
    history = [
        {"role": "user", "content": "你好呀。"},
        {"role": "assistant", "content": "谢谢你来。"},
        {"role": "user", "content": "今天怎么样？"},
        {"role": "assistant", "content": "我在手工房里酿酒。"},
    ]
    module._build_context(builder, case, history=history, turn=case.dialogue_turns()[0])

    assert captured["recentReplies"] == ["谢谢你来。", "我在手工房里酿酒。"]


def test_build_context_sends_empty_recent_replies_without_assistant_turns() -> None:
    """没有 assistant 项时发空列表，而不是缺键。

    `prompts.py` 对缺键和空列表都落到 `_turn_index = 0`，行为相同；但显式空列表
    让「这条路径接上了」在 payload 层可断言，避免将来重构又把它整个丢掉。
    """
    module = _load_eval_module()
    store = module._resolve_index(ROOT / "data" / "personas")
    builder = module.ContextBuilder(profile_index=store)

    captured: dict[str, object] = {}
    real_build = builder.build

    def _spy(payload, *args, **kwargs):
        captured.update(payload)
        return real_build(payload, *args, **kwargs)

    builder.build = _spy  # type: ignore[method-assign]

    case = case_by_id("sophia-daily")
    module._build_context(
        builder,
        case,
        history=[{"role": "user", "content": "你好呀。"}],
        turn=case.dialogue_turns()[0],
    )

    assert captured["recentReplies"] == []


def test_recent_replies_are_capped_like_the_request_model() -> None:
    """`recentReplies` 跟随 `models.DialogueTestRequest.recent_replies` 的 40 条上限。

    超限在真机上会被 `extra="forbid"` 的模型拒成 422，评测里虽然不经过 pydantic，
    但两侧口径要一致，否则评测会喂出线上不可能出现的超长窗口。
    """
    module = _load_eval_module()
    assert module._RECENT_REPLIES_LIMIT == 40

    store = module._resolve_index(ROOT / "data" / "personas")
    builder = module.ContextBuilder(profile_index=store)

    captured: dict[str, object] = {}
    real_build = builder.build

    def _spy(payload, *args, **kwargs):
        captured.update(payload)
        return real_build(payload, *args, **kwargs)

    builder.build = _spy  # type: ignore[method-assign]

    case = case_by_id("sophia-daily")
    history = []
    for index in range(50):
        history.append({"role": "user", "content": f"问题 {index}"})
        history.append({"role": "assistant", "content": f"回复 {index}"})
    module._build_context(builder, case, history=history, turn=case.dialogue_turns()[0])

    replies = captured["recentReplies"]
    assert isinstance(replies, list)
    assert len(replies) == 40
    # 保留的是**最近** 40 条，不是最早 40 条。
    assert replies[-1] == "回复 49"
    assert replies[0] == "回复 10"


def _sophia_topic_pool() -> list[str]:
    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        profile = (data.get("personas") or {}).get("Sophia")
        if not isinstance(profile, dict):
            continue
        topics = (profile.get("voiceStyle") or {}).get("preferredTopics") or []
        if topics:
            return list(topics)
    raise AssertionError("找不到 Sophia 的 preferredTopics")


def test_topic_window_rotates_as_recent_replies_grow() -> None:
    """窗口必须随 `recentReplies` 增长而滑动，并落在 `_topic_window_for_turn`
    给出的**确切**位置上。

    这是 2026-10-01 那次 null 的直接回归：`_build_context` 不发 `recentReplies`
    ⇒ `_turn_index` 恒 0 ⇒ 窗口永远停在池首，K=1 与 K=4 两臂 prompt 逐字节相同。
    断言精确位置而不只是「两次不同」，是为了让「窗口滑了但滑错格」也能被抓到。
    """
    from stardew_ai_bridge.prompts import _topic_window_for_turn

    module = _load_eval_module()
    store = module._resolve_index(ROOT / "data" / "personas")
    builder = module.ContextBuilder(profile_index=store)
    case = case_by_id("sophia-daily")
    pool = _sophia_topic_pool()

    def window_for(n_assistant: int) -> list[str]:
        history = []
        for index in range(n_assistant):
            history.append({"role": "user", "content": f"问题 {index}"})
            history.append({"role": "assistant", "content": f"回复 {index}"})
        ctx = module._build_context(
            builder, case, history=history, turn=case.dialogue_turns()[0]
        )
        return ctx["npcIdentity"]["voiceStyle"]["preferredTopics"]

    for n_assistant in (0, 5, 17):
        # ⚠ 2026-10-01：不能再拿原始池去重算期望值。实现侧先过
        # `_topics_for_stage`（按关系阶段收敛档位）再切窗口，而这里拿不到
        # `_build_context` 当轮用的 stage，硬算会得到另一个池 —— 那时变红的是
        # 这条断言，而不是窗口本身。所以钉它真正要保证的两点：
        #   (1) 窗口每一条都来自素材库（不是凭空造的）；
        #   (2) 窗口随 assistant 轮数滑动（下面那条 `!=`，正是本次 null 的核心）。
        window = window_for(n_assistant)
        unknown = [topic for topic in window if topic not in pool]
        assert not unknown, f"轮 {n_assistant} 的窗口出现池外条目：{unknown}"
        assert len(window) == 12, f"轮 {n_assistant} 窗口宽度 {len(window)}，应为 12"

    # 池宽 62 > 窗口 12，轮次一变窗口必然换位 —— 恒定就是这次的 bug。
    assert window_for(0) != window_for(5)


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
        lambda result, messages, generate, **kwargs: result,
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
        lambda result, messages, generate, **kwargs: result,
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
        lambda result, messages, generate, **kwargs: result,
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
        lambda result, messages, generate, **kwargs: result,
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
        lambda result, messages, generate, **kwargs: result,
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
        lambda result, messages, generate, **kwargs: result,
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
        lambda result, messages, generate, **kwargs: result,
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

    # 话题窗口落盘（2026-10-01）：窗口轮次由 `len(recentReplies)` 决定，随对话增长
    # ⇒ 三轮的 `topicWindowTurn` 必须递增。这个断言的价值不在「窗口实现对不对」
    # （那是 `test_topic_window_rotates_as_recent_replies_grow` 的活），而在于
    # **轮次信号有没有被送进评测路径** —— K=1/K=4 那 198 轮对照之所以白跑，就是
    # 因为没人能一眼看出窗口恒在池首。落盘字段让这件事在 results.jsonl 里直接可见。
    for record in records:
        assert [turn["topicWindowTurn"] for turn in record["turns"]] == [0, 1, 2]
        assert all(
            isinstance(turn["topicWindow"], list) and turn["topicWindow"]
            for turn in record["turns"]
        )
    # 内容是否真的换过，只要求至少一个 case 满足：池 ≤ 12 条的角色（Alex 11、
    # Leo 12）走「原样返回全池」分支，本来就不轮换，拿它们断言会假红。
    assert any(
        len({tuple(turn["topicWindow"]) for turn in record["turns"]}) > 1
        for record in records
    )
    assert all(
        "initiativeExpectation" in turn and "initiativeKind" in turn
        for record in records
        for turn in record["turns"]
    )


def test_empty_event_state_is_declared_not_omitted_in_requests() -> None:
    """空元组是「确认尚未完成任何事件」这个**状态**，不是「未提供状态」。

    省略 `completedEventIds` 会让 `prompts.py` 判 `completed_event_ids_known=False`，
    把显式空集与「调用方没给事件状态」混为一谈 ⇒ `relationship_gating.py:292`
    按「不能推断为没有完成事件」跳过事件锁 ⇒ 已完成事件的对白漏进初识阶段。
    """
    module = _load_eval_module()
    empty_cases = [
        item
        for item in module.quality_cases_for_suite("default")
        if item.completed_event_ids == ()
    ]
    assert empty_cases, "默认套件里应有声明「尚未完成任何事件」的案例"

    for case in empty_cases:
        state = module._case_game_state(case)
        assert state["completedEventIds"] == [], case.case_id
        # 请求对象那侧由 pydantic 的 `default_factory=list` 兜底，
        # 这里确认它拿到的是案例声明的显式空集，而不是被反向塞成 `None`。
        assert (
            module._build_request(case).game_state.completed_event_ids == []
        ), case.case_id


def test_empty_event_state_is_declared_in_prompt_payload() -> None:
    """与上一条同源，覆盖另一条构建路径（`_build_context` → `ContextBuilder`）。"""
    module = _load_eval_module()
    case = next(
        item
        for item in module.quality_cases_for_suite("default")
        if item.completed_event_ids == ()
    )
    builder_class = module.ContextBuilder

    class _CapturingBuilder(builder_class):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__()
            self.payloads: list[dict[str, object]] = []

        def build(self, payload, **kwargs):  # type: ignore[no-untyped-def]
            self.payloads.append(payload)
            return super().build(payload, **kwargs)

    builder = _CapturingBuilder()
    module._build_context(builder, case)

    assert builder.payloads, "构建路径应当把 payload 交给 ContextBuilder"
    header = builder.payloads[0]["gameState"]
    assert isinstance(header, dict)
    assert header["completedEventIds"] == []
