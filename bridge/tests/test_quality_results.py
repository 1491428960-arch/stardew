from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.quality_results import SAFE_SUITE_IDS, load_latest_quality_run


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
        "runStatus": "valid",
        "runStatusReasons": [],
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


def test_load_latest_quality_run_preserves_safe_turn_retry_count(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260913-turn-retry-count"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "suite": "relationship-world",
                "caseCount": 1,
                "successful": 1,
                "errors": 0,
                "turnCount": 1,
                "successfulTurns": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "retry-case",
                "suite": "relationship-world",
                "turns": [
                    {
                        "turnId": "turn-1",
                        "reply": "我听见了。",
                        "retryCount": 2,
                        "warnings": [
                            "response_affection_retry: missing_proactive_affection",
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["results"][0]["turns"][0]["retryCount"] == 2


def test_quality_results_whitelist_includes_deep_flirt_suite() -> None:
    assert "deep-flirt" in SAFE_SUITE_IDS


def test_load_latest_quality_run_can_select_deep_flirt_batch(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260914-deep-flirt-smoke-v1"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "suite": "deep-flirt",
                "caseCount": 1,
                "successful": 1,
                "errors": 0,
                "turnCount": 3,
                "successfulTurns": 3,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "deep-flirt-wizard-married",
                "suite": "deep-flirt",
                "turns": [
                    {"turnId": "turn-1", "reply": "第一轮"},
                    {"turnId": "turn-2", "reply": "第二轮"},
                    {"turnId": "turn-3", "reply": "第三轮"},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path, "deep-flirt")

    assert payload["batchId"] == run_dir.name
    assert payload["summary"]["suite"] == "deep-flirt"
    assert payload["results"][0]["caseId"] == "deep-flirt-wizard-married"
    assert payload["runStatus"] == "valid"


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


def test_load_latest_quality_run_marks_provider_failures_as_diagnostic_only(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260907-relay-failure"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "suite": "conversation-lead",
                "caseCount": 1,
                "successful": 1,
                "errors": 0,
                "turnCount": 3,
                "successfulTurns": 2,
                "failedTurns": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "demo-case",
                "reply": "半截回复",
                "provider": "cloud",
                "fallback": False,
                "turns": [
                    {
                        "turnId": "turn-1",
                        "reply": "半截回复",
                        "provider": "cloud",
                    },
                    {
                        "turnId": "turn-2",
                        "error": "ProviderError",
                    },
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["runStatus"] == "diagnostic_invalid"
    assert payload["runStatusReasons"] == ["provider_error", "missing_reply"]
    assert payload["summary"]["runStatus"] == "diagnostic_invalid"
    assert payload["summary"]["runStatusReasons"] == [
        "provider_error",
        "missing_reply",
    ]


def test_load_latest_quality_run_marks_fallback_and_truncation_without_exposing_secrets(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260907-truncated-fallback"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "caseCount": 1,
                "successful": 1,
                "errors": 0,
                "turnCount": 1,
                "successfulTurns": 1,
                "failedTurns": 0,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "demo-case",
                "reply": "截断内容",
                "provider": "fallback",
                "fallback": True,
                "warnings": ["response_truncated: finish_reason=length"],
                "prompt": "secret prompt",
                "apiKey": "secret key",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["runStatus"] == "diagnostic_invalid"
    assert payload["runStatusReasons"] == ["fallback", "truncated_output"]
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "secret prompt" not in rendered
    assert "secret key" not in rendered


def test_load_latest_quality_run_marks_complete_cloud_run_valid(
    tmp_path: Path,
) -> None:
    run_dir = _write_run(tmp_path, "20260907-valid-cloud")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    summary.update(
        {
            "suite": "default",
            "turnCount": 1,
            "successfulTurns": 1,
            "failedTurns": 0,
        }
    )
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["runStatus"] == "valid"
    assert payload["runStatusReasons"] == []
    assert payload["summary"]["runStatus"] == "valid"
    assert payload["summary"]["runStatusReasons"] == []


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
                        "detectedInitiativeKind": "creative_share",
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
    assert payload["results"][0]["turns"][0]["detectedInitiativeKind"] == "creative_share"


def test_load_latest_quality_run_preserves_safe_personal_affection_diagnostics(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260903-personal-affection"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps({"schemaVersion": 3, "caseCount": 1}),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "sophia-dating-wine",
                "personalAffectionDetected": True,
                "companionshipDetected": False,
                "specificPlanDetected": False,
                "affectionEvidence": ["exclusive_share"],
                "affectionShape": "exclusive_share",
                "turns": [
                    {
                        "turnId": "turn-2",
                        "personalAffectionDetected": True,
                        "companionshipDetected": False,
                        "specificPlanDetected": False,
                        "affectionEvidence": ["exclusive_share"],
                        "affectionShape": "exclusive_share",
                        "affectionVariation": {
                            "mechanical": False,
                            "affectionShape": "exclusive_share",
                            "initiativeKind": "creative_share",
                            "hasNewAnchor": True,
                            "tags": [],
                            "opening": "这首歌我只想先给你听",
                        },
                    }
                ],
                "prompt": "secret prompt",
                "token": "secret token",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    result = payload["results"][0]
    assert result["personalAffectionDetected"] is True
    assert result["affectionEvidence"] == ["exclusive_share"]
    turn = result["turns"][0]
    assert turn["affectionShape"] == "exclusive_share"
    assert turn["affectionVariation"] == {
        "mechanical": False,
        "affectionShape": "exclusive_share",
        "initiativeKind": "creative_share",
        "hasNewAnchor": True,
        "tags": [],
    }
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "secret prompt" not in rendered
    assert "secret token" not in rendered


def test_load_latest_quality_run_preserves_safe_conversation_lead_diagnostics(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260903-conversation-lead"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps({"schemaVersion": 3, "caseCount": 1}),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "sophia-dating-song",
                "conversationLeadDetected": True,
                "conversationLeadKind": "specific_follow_up",
                "conversationLeadEvidence": ["specific_question"],
                "conversationLeadTags": ["specific_follow_up"],
                "turns": [
                    {
                        "turnId": "turn-2",
                        "answeredCurrentTopic": True,
                        "conversationLeadDetected": True,
                        "conversationLeadKind": "specific_follow_up",
                        "conversationLeadEvidence": ["specific_question"],
                        "conversationLeadTags": ["specific_follow_up"],
                        "conversationLeadOpening": "那首歌还不错",
                        "conversationLeadAnchors": ["歌"],
                        "conversationLeadVariation": {
                            "mechanical": True,
                            "conversationLeadKind": "specific_follow_up",
                            "hasNewAnchor": False,
                            "tags": ["mechanical_conversation_lead"],
                            "opening": "那首歌还不错",
                        },
                    }
                ],
                "prompt": "secret prompt",
                "token": "secret token",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    result = payload["results"][0]
    assert result["conversationLeadDetected"] is True
    assert result["conversationLeadKind"] == "specific_follow_up"
    turn = result["turns"][0]
    assert turn["answeredCurrentTopic"] is True
    assert turn["conversationLeadEvidence"] == ["specific_question"]
    assert turn["conversationLeadVariation"] == {
        "mechanical": True,
        "conversationLeadKind": "specific_follow_up",
        "hasNewAnchor": False,
        "tags": ["mechanical_conversation_lead"],
    }
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "那首歌还不错" not in rendered
    assert "secret prompt" not in rendered
    assert "secret token" not in rendered


def test_load_latest_quality_run_preserves_safe_semantic_expected_evidence(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260904-semantic-expected-evidence"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps({"schemaVersion": 3, "caseCount": 1}),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "shane-dating-boundary",
                "score": {
                    "passed": True,
                    "expectedHits": 1,
                    "exactExpectedHits": 0,
                    "semanticExpectedHits": 1,
                    "evidenceMatches": {},
                    "semanticEvidenceMatches": {"想我": ["想你了"]},
                    "tags": [],
                },
                "prompt": "secret prompt",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["results"][0]["score"] == {
        "passed": True,
        "expectedHits": 1,
        "exactExpectedHits": 0,
        "semanticExpectedHits": 1,
        "tags": [],
        "evidenceMatches": {},
        "semanticEvidenceMatches": {"想我": ["想你了"]},
    }
    assert "secret prompt" not in json.dumps(payload, ensure_ascii=False)


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


def test_load_latest_quality_run_preserves_conversation_lead_suite_identifier(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260904-conversation-lead-cloud-v2"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 3,
                "suite": "conversation-lead",
                "caseCount": 5,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "wizard-married-evening",
                "suite": "conversation-lead",
                "reply": "塔里的记录今晚只想先给你看。",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["summary"]["suite"] == "conversation-lead"
    assert payload["results"][0]["suite"] == "conversation-lead"


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


def test_load_latest_quality_run_preserves_safe_relationship_diagnostics_only(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260905-relationship-world"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "suite": "relationship-world",
                "caseCount": 1,
                "relationshipDiagnostics": {
                    "focusedTurnCount": 3,
                    "focusCounts": {"unknown_view": 1},
                    "tagCounts": {"public_wedding_visibility": 1},
                    "tags": ["public_wedding_visibility"],
                    "prompt": "不要暴露这段内部关系提示",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "relationship-wizard-view-gap",
                "suite": "relationship-world",
                "relationshipWorld": {
                    "objectiveRelationships": [{"npcId": "secret-partner"}],
                    "views": [{"visibility": "known"}],
                },
                "turns": [
                    {
                        "turnId": "turn-1",
                        "relationshipVisibility": {
                            "Sophia": "known",
                            "Alex": "unknown",
                        },
                        "relationshipAcceptance": "conditional",
                        "mediationStatus": "active",
                        "jealousyTrigger": "companionship",
                        "jealousyActive": True,
                        "relationshipTags": ["public_wedding_visibility"],
                        "prompt": "不要暴露这段内部关系提示",
                        "apiKey": "secret-key",
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert payload["summary"]["suite"] == "relationship-world"
    assert payload["summary"]["relationshipDiagnostics"] == {
        "focusedTurnCount": 3,
        "focusCounts": {"unknown_view": 1},
        "tagCounts": {"public_wedding_visibility": 1},
        "tags": ["public_wedding_visibility"],
    }
    turn = payload["results"][0]["turns"][0]
    assert turn["relationshipVisibility"] == {
        "Sophia": "known",
        "Alex": "unknown",
    }
    assert turn["relationshipAcceptance"] == "conditional"
    assert turn["mediationStatus"] == "active"
    assert turn["jealousyTrigger"] == "companionship"
    assert turn["jealousyActive"] is True
    assert turn["relationshipTags"] == ["public_wedding_visibility"]
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "objectiveRelationships" not in rendered
    assert "secret-partner" not in rendered
    assert "不要暴露这段内部关系提示" not in rendered
    assert "secret-key" not in rendered


def test_load_latest_quality_run_does_not_add_relationship_fields_to_old_suite(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "20260905-conversation-lead"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "schemaVersion": 3,
                "suite": "conversation-lead",
                "relationshipDiagnostics": {"focusedTurnCount": 99},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "results.jsonl").write_text(
        json.dumps(
            {
                "caseId": "legacy-case",
                "suite": "conversation-lead",
                "relationshipVisibility": {"Sophia": "known"},
                "relationshipAcceptance": "accepted",
                "relationshipTags": ["should_not_appear"],
                "turns": [
                    {
                        "turnId": "turn-1",
                        "relationshipVisibility": {"Sophia": "known"},
                        "jealousyActive": True,
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = load_latest_quality_run(tmp_path)

    assert "relationshipDiagnostics" not in payload["summary"]
    result = payload["results"][0]
    assert "relationshipVisibility" not in result
    assert "relationshipAcceptance" not in result
    assert "relationshipTags" not in result
    assert "relationshipVisibility" not in result["turns"][0]
    assert "jealousyActive" not in result["turns"][0]
