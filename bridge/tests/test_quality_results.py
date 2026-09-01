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
