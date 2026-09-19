from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load_batch_module():
    path = ROOT / "scripts" / "run_group_dialogue_cloud_batch.py"
    spec = importlib.util.spec_from_file_location("run_group_dialogue_cloud_batch", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_batch_cases_are_remote_multi_turn_with_bounded_turn_count() -> None:
    module = _load_batch_module()
    cases = module.group_batch_cases()

    assert 4 <= len(cases) <= 6
    assert len({case["caseId"] for case in cases}) == len(cases)
    for case in cases:
        participants = case["participants"]
        assert 2 <= len(participants) <= 3
        assert 3 <= case["turnCount"] <= 4
        payload = module.build_request_payload(case)
        assert payload["provider"] == "cloud"
        assert payload["strategy"] == "multi_turn"
        assert payload["channel"] == "remote"
        assert payload["turnCount"] == case["turnCount"]
        assert payload["message"]
        assert payload["activeSpeakerNpcId"] in {
            item["npcId"] for item in participants
        }


def test_batch_case_catalog_returns_defensive_copies() -> None:
    module = _load_batch_module()
    first = module.group_batch_cases()
    first[0]["message"] = "tampered"
    first[0]["participants"][0]["npcId"] = "Tampered"

    assert module.group_batch_cases()[0]["message"] != "tampered"
    assert module.group_batch_cases()[0]["participants"][0]["npcId"] != "Tampered"


def test_batch_refuses_to_overwrite_an_existing_batch_directory(tmp_path: Path) -> None:
    module = _load_batch_module()
    target = tmp_path / "batch"
    target.mkdir()
    (target / "cases.json").write_text("[]", encoding="utf-8")
    sent: list[str] = []

    with pytest.raises(FileExistsError):
        module.run_batch(
            cases=module.group_batch_cases(),
            endpoint="http://127.0.0.1:5678",
            output_dir=target,
            confirm_cloud=True,
            request_fn=lambda endpoint, payload, case: sent.append(case["caseId"]) or {},
        )

    assert sent == []
    assert (target / "cases.json").read_text(encoding="utf-8") == "[]"


def test_batch_without_cloud_confirmation_sends_no_request(tmp_path: Path) -> None:
    module = _load_batch_module()
    sent: list[str] = []

    with pytest.raises(PermissionError):
        module.run_batch(
            cases=module.group_batch_cases(),
            endpoint="http://127.0.0.1:5678",
            output_dir=tmp_path / "batch",
            confirm_cloud=False,
            request_fn=lambda endpoint, payload, case: sent.append(case["caseId"]) or {},
        )

    assert sent == []


def _record(case_id: str, participants: list[str], turns: list[dict[str, object]]) -> dict:
    return {
        "caseId": case_id,
        "request": {
            "provider": "cloud",
            "strategy": "multi_turn",
            "channel": "remote",
            "participants": participants,
            "turnCount": 3,
        },
        "response": {
            "strategy": "multi_turn",
            "channel": "remote",
            "provider": "cloud",
            "fallback": False,
            "turns": turns,
            "providerCalls": 1,
            "providerErrors": [],
            "fallbackCount": 0,
            "latencyMs": 900,
            "warnings": [],
            "usage": {"inputTokens": 400, "outputTokens": 90, "totalTokens": 490},
        },
        "status": "ok",
    }


def test_batch_marks_provider_failure_as_error_case(tmp_path: Path) -> None:
    module = _load_batch_module()
    case = module.group_batch_cases()[0]

    def failing_request(endpoint: str, payload: dict, case: dict) -> dict:
        return {
            "strategy": "multi_turn",
            "channel": "remote",
            "provider": "local",
            "fallback": True,
            "turns": [],
            "providerCalls": 1,
            "providerErrors": ["cloud provider failed"],
            "fallbackCount": 1,
            "latencyMs": 12000,
            "warnings": ["cloud provider failed"],
            "usage": None,
        }

    target = tmp_path / "batch"
    result = module.run_batch(
        cases=[case],
        endpoint="http://127.0.0.1:5678",
        output_dir=target,
        confirm_cloud=True,
        request_fn=failing_request,
        log=lambda message: None,
    )

    assert result["summary"]["successfulCases"] == 0
    assert result["summary"]["failedCases"] == 1
    assert result["summary"]["allNoProviderErrors"] is False
    assert result["summary"]["allCloud"] is False
    record = json.loads((target / "cases.json").read_text(encoding="utf-8"))[0]
    assert record["status"] == "error"
    assert record["response"]["providerErrors"] == ["cloud provider failed"]


def test_summarize_counts_provider_error_records_as_failed() -> None:
    module = _load_batch_module()
    ok = _record(
        "case-ok",
        ["Emily", "Wizard"],
        [{"speakerNpcId": "Emily", "content": "…", "addressedTo": []}],
    )
    bad = _record("case-bad", ["Shane", "Harvey"], [])
    bad["response"]["providerErrors"] = ["cloud provider failed"]
    bad["response"]["fallback"] = True

    summary = module.summarize([ok, bad])

    assert summary["successfulCases"] == 1
    assert summary["failedCases"] == 1
    assert summary["allNoProviderErrors"] is False
    assert summary["allNoFallback"] is False


def test_batch_summary_records_natural_flow_signals() -> None:
    module = _load_batch_module()
    records = [
        _record(
            "case-a",
            ["Shane", "Harvey", "Sophia"],
            [
                {"speakerNpcId": "Shane", "content": "…", "addressedTo": []},
                {"speakerNpcId": "Shane", "content": "…", "addressedTo": ["Harvey"]},
                {"speakerNpcId": "Harvey", "content": "…", "addressedTo": []},
            ],
        ),
        _record(
            "case-b",
            ["Emily", "Wizard"],
            [
                {"speakerNpcId": "Emily", "content": "…", "addressedTo": []},
                {"speakerNpcId": "Wizard", "content": "…", "addressedTo": ["Emily"]},
            ],
        ),
    ]

    summary = module.summarize(records)

    assert summary["strategy"] == "multi_turn"
    assert summary["caseCount"] == 2
    assert summary["successfulCases"] == 2
    assert summary["providerCalls"] == 2
    assert summary["turnsTotal"] == 5
    assert summary["allRemote"] is True
    assert summary["allCloud"] is True
    assert summary["allNoFallback"] is True
    assert summary["allNoProviderErrors"] is True
    assert summary["allSpeakersInRoster"] is True
    assert summary["allParticipantsReplied"] is False
    assert summary["silentParticipantCases"] == 1
    assert summary["silentParticipants"] == ["Sophia"]
    assert summary["consecutiveSameSpeakerTurns"] == 1
    assert summary["addressedTurns"] == 2
    assert summary["usage"]["totalTokens"] == 980


def test_batch_run_writes_isolated_cases_and_summary(tmp_path: Path) -> None:
    module = _load_batch_module()
    replies = {
        "natural-group-shane-harvey-sleep": {
            "strategy": "multi_turn",
            "channel": "remote",
            "provider": "cloud",
            "fallback": False,
            "turns": [
                {"speakerNpcId": "Shane", "content": "…", "addressedTo": []},
                {"speakerNpcId": "Shane", "content": "…", "addressedTo": []},
                {"speakerNpcId": "Harvey", "content": "…", "addressedTo": ["Shane"]},
            ],
            "providerCalls": 1,
            "providerErrors": [],
            "fallbackCount": 0,
            "latencyMs": 700,
            "warnings": [],
            "usage": {"inputTokens": 300, "outputTokens": 60, "totalTokens": 360},
        }
    }

    def fake_request(endpoint: str, payload: dict, case: dict) -> dict:
        assert endpoint == "http://127.0.0.1:5678"
        assert payload["strategy"] == "multi_turn"
        assert payload["provider"] == "cloud"
        assert payload["message"] == case["message"]
        assert "_caseId" not in payload
        return replies[case["caseId"]]

    target = tmp_path / "20260918-group-dialogue-cloud-v4-natural-flow-cases"
    result = module.run_batch(
        cases=[module.group_batch_cases()[0]],
        endpoint="http://127.0.0.1:5678",
        output_dir=target,
        confirm_cloud=True,
        request_fn=fake_request,
        log=lambda message: None,
    )

    assert result["summary"]["caseCount"] == 1
    cases_payload = json.loads((target / "cases.json").read_text(encoding="utf-8"))
    summary_payload = json.loads((target / "summary.json").read_text(encoding="utf-8"))
    assert cases_payload[0]["caseId"] == "natural-group-shane-harvey-sleep"
    assert cases_payload[0]["checks"]["speakersInRoster"] is True
    assert cases_payload[0]["checks"]["allParticipantsReplied"] is True
    assert cases_payload[0]["response"]["turns"][1]["speakerNpcId"] == "Shane"
    assert summary_payload["strategy"] == "multi_turn"
    assert summary_payload["consecutiveSameSpeakerTurns"] == 1
    assert summary_payload["allRemote"] is True


def test_cli_turn_count_override_reaches_every_planned_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_batch_module()

    exit_code = module.main(
        [
            "--output-root",
            str(tmp_path / "artifacts"),
            "--batch",
            "turn-count-probe",
            "--turn-count",
            "2",
        ]
    )

    assert exit_code == 0
    plan = json.loads(capsys.readouterr().out.split("\n当前是 dry-run")[0])
    assert plan["requestCount"] == len(module.group_batch_cases())
    assert {case["turnCount"] for case in plan["cases"]} == {2}


def test_cli_turn_count_override_applies_after_case_selection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_batch_module()

    exit_code = module.main(
        [
            "--output-root",
            str(tmp_path / "artifacts"),
            "--batch",
            "turn-count-probe",
            "--turn-count",
            "1",
            "--case",
            "natural-group-shane-harvey-sleep",
        ]
    )

    assert exit_code == 0
    plan = json.loads(capsys.readouterr().out.split("\n当前是 dry-run")[0])
    assert [case["caseId"] for case in plan["cases"]] == [
        "natural-group-shane-harvey-sleep"
    ]
    assert [case["turnCount"] for case in plan["cases"]] == [1]


@pytest.mark.parametrize("value", ["0", "5", "-1"])
def test_cli_rejects_out_of_range_turn_count(
    tmp_path: Path, value: str
) -> None:
    module = _load_batch_module()

    exit_code = module.main(
        [
            "--output-root",
            str(tmp_path / "artifacts"),
            # 负值必须写成 --turn-count=-1，否则 argparse 会把它当成另一个选项。
            f"--turn-count={value}",
        ]
    )

    assert exit_code == 2


def test_cli_without_turn_count_override_keeps_catalog_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_batch_module()

    assert (
        module.main(["--output-root", str(tmp_path / "artifacts"), "--batch", "probe"])
        == 0
    )

    plan = json.loads(capsys.readouterr().out.split("\n当前是 dry-run")[0])
    assert [case["turnCount"] for case in plan["cases"]] == [
        case["turnCount"] for case in module.group_batch_cases()
    ]
