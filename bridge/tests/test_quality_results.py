from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.quality_results import load_latest_quality_run


def _write_run(root: Path, name: str, *, reply: str = "这是一条测试回复") -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "caseCount": 1,
                "successful": 1,
                "errors": 0,
                "passed": 1,
                "elapsedMs": 123,
                "profileIndex": "E:/private/profile-index.json",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "demo-case",
                "reply": reply,
                "provider": "local",
                "fallback": False,
                "latencyMs": 42,
                "elapsedMs": 48,
                "warnings": ["response_format_retry: markdown"],
                "score": {
                    "passed": False,
                    "tags": ["format_noise"],
                    "expectedHits": 1,
                    "forbiddenHits": 0,
                },
                "prompt": "不要把这段完整 prompt 暴露给浏览器",
                "apiKey": "secret-key",
                "token": "secret-token",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir


def test_load_latest_quality_run_returns_reply_and_safe_summary(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path, "20260830-guard-markdown")

    payload = load_latest_quality_run(tmp_path)

    assert payload["batchId"] == run_dir.name
    assert payload["summary"] == {
        "schemaVersion": 1,
        "caseCount": 1,
        "successful": 1,
        "errors": 0,
        "passed": 1,
        "elapsedMs": 123,
    }
    assert payload["results"] == [
        {
            "caseId": "demo-case",
            "reply": "这是一条测试回复",
            "provider": "local",
            "fallback": False,
            "latencyMs": 42,
            "elapsedMs": 48,
            "warnings": ["response_format_retry: markdown"],
            "score": {
                "passed": False,
                "tags": ["format_noise"],
                "expectedHits": 1,
                "forbiddenHits": 0,
            },
        }
    ]


def test_load_latest_quality_run_ignores_corrupt_lines_and_missing_runs(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260830-corrupt-line"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps({"schemaVersion": 1, "caseCount": 1}), encoding="utf-8"
    )
    (run_dir / "results.jsonl").write_text(
        "not-json\n"
        + json.dumps({"caseId": "ok", "reply": "保留这条"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["batchId"] == run_dir.name
    assert payload["results"] == [{"caseId": "ok", "reply": "保留这条"}]


def test_load_latest_quality_run_keeps_safe_multiturn_usage_and_legacy_fields(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260830-multiturn"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "caseCount": 1,
                "requestCount": 3,
                "successfulTurns": 3,
                "failedTurns": 0,
                "usage": {
                    "inputTokens": 90,
                    "outputTokens": 45,
                    "totalTokens": 135,
                    "usageReturnedTurns": 3,
                    "missingUsageTurns": 0,
                },
                "estimatedCost": {
                    "currency": "CNY",
                    "amount": 0.12,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "demo-case",
                "turns": [
                    {
                        "turnId": "turn-1",
                        "playerInput": "你好",
                        "reply": "你好。",
                        "provider": "cloud",
                        "latencyMs": 42,
                        "usage": {
                            "inputTokens": 30,
                            "outputTokens": 15,
                            "totalTokens": 45,
                        },
                        "score": {"passed": True, "tags": []},
                    }
                ],
                "prompt": "secret prompt",
                "apiKey": "secret key",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["summary"]["schemaVersion"] == 2
    assert payload["summary"]["usage"]["totalTokens"] == 135
    result = payload["results"][0]
    assert result["turns"][0]["playerInput"] == "你好"
    assert result["turns"][0]["usage"]["inputTokens"] == 30
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "secret prompt" not in rendered
    assert "secret key" not in rendered


def test_load_latest_quality_run_preserves_bounded_initiative_diagnostics(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260902-initiative"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 3,
                "caseCount": 1,
                "passedCases": 0,
                "initiativeDetected": 1,
                "initiativeTags": ["missing_proactive_affection"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "sophia-dating-wine",
                "initiativeExpectation": "proactive",
                "initiativeKind": "specific_plan",
                "initiativeDetected": True,
                "initiativeTags": ["specific_plan", "secret prompt"],
                "turns": [
                    {
                        "turnId": "turn-1",
                        "initiativeExpectation": "proactive",
                        "initiativeKind": "specific_plan",
                        "initiativeDetected": True,
                        "initiativeTags": ["specific_plan"],
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["summary"]["initiativeDetected"] == 1
    assert payload["results"][0]["initiativeExpectation"] == "proactive"
    assert payload["results"][0]["initiativeDetected"] is True
    assert payload["results"][0]["initiativeTags"] == ["specific_plan", "secret prompt"]
    assert payload["results"][0]["turns"][0]["initiativeKind"] == "specific_plan"


def test_load_latest_quality_run_preserves_mechanical_restatement_flag(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260902-mechanical-restatement"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps({"schemaVersion": 3, "caseCount": 1}),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "sophia-dating-wine",
                "mechanicalRestatement": True,
                "turns": [
                    {
                        "turnId": "turn-2",
                        "mechanicalRestatement": True,
                        "initiativeTags": ["mechanical_restatement"],
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["results"][0]["mechanicalRestatement"] is True
    assert payload["results"][0]["turns"][0]["mechanicalRestatement"] is True


def test_load_latest_quality_run_preserves_only_known_suite_identifier(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260902-topic-start-intimacy-cloud"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "suite": "topic-start-intimacy",
                "caseCount": 32,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "topic-wizard-1",
                "suite": "topic-start-intimacy",
                "reply": "今晚留一点时间给你。",
                "prompt": "secret prompt",
                "token": "secret token",
            },
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps(
            {
                "caseId": "unsafe-suite",
                "suite": "topic-start-intimacy<script>",
                "reply": "普通回复",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["summary"]["suite"] == "topic-start-intimacy"
    assert payload["results"][0]["suite"] == "topic-start-intimacy"
    assert "suite" not in payload["results"][1]
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "secret prompt" not in rendered
    assert "secret token" not in rendered


def test_load_latest_quality_run_preserves_topic_continuity_metadata_only(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260902-topic-start-continuity-cloud"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "suite": "topic-start-intimacy",
                "caseCount": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "topic-sebastian-dating-mixtape",
                "suite": "topic-start-intimacy",
                "topicSeed": "新歌单",
                "topicKeywords": ["歌单", "音乐"],
                "continuationMode": "anchored",
                "turns": [
                    {"turnId": "turn-1", "intent": "topic", "reply": "新歌单。"},
                    {"turnId": "turn-2", "intent": "chat", "reply": "我给你听。"},
                ],
                "prompt": "secret prompt",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)
    result = payload["results"][0]

    assert result["topicSeed"] == "新歌单"
    assert result["topicKeywords"] == ["歌单", "音乐"]
    assert result["continuationMode"] == "anchored"
    assert [turn["intent"] for turn in result["turns"]] == ["topic", "chat"]
    assert "secret prompt" not in json.dumps(payload, ensure_ascii=False)


def test_load_latest_quality_run_preserves_adaptive_player_input_diagnostics(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260902-topic-start-adaptive-cloud"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "suite": "topic-start-adaptive",
                "caseCount": 1,
                "requestCount": 5,
                "npcRequestCount": 3,
                "playerInputRequestCount": 2,
                "playerInputGenerationCount": 2,
                "playerInputValidCount": 1,
                "playerInputInvalidCount": 1,
                "playerInputQualityTags": ["player_input_unlinked"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "adaptive-topic-wizard-dating-moonlight",
                "suite": "topic-start-adaptive",
                "followUpMode": "adaptive",
                "playerSimulationStyle": "先接住具体内容",
                "turns": [
                    {
                        "turnId": "turn-2",
                        "playerInput": "你刚才提到的灯，后来怎么样了？",
                        "playerInputSource": "generated",
                        "playerInputProvider": "cloud",
                        "playerInputQuality": {
                            "valid": True,
                            "linkedToPreviousReply": True,
                            "replyLength": 18,
                            "tags": [],
                        },
                    }
                ],
                "prompt": "secret prompt",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)
    assert payload["summary"]["suite"] == "topic-start-adaptive"
    assert payload["summary"]["playerInputRequestCount"] == 2
    assert payload["summary"]["playerInputGenerationCount"] == 2
    assert payload["summary"]["playerInputValidCount"] == 1
    assert payload["summary"]["playerInputInvalidCount"] == 1
    assert payload["summary"]["playerInputQualityTags"] == ["player_input_unlinked"]
    result = payload["results"][0]
    assert result["followUpMode"] == "adaptive"
    assert result["turns"][0]["playerInputSource"] == "generated"
    assert result["turns"][0]["playerInputQuality"]["linkedToPreviousReply"] is True
    assert "secret prompt" not in json.dumps(payload, ensure_ascii=False)
