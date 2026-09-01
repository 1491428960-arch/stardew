import json
from pathlib import Path

import pytest

from stardew_ai_bridge.runtime_samples import (
    append_runtime_sample,
    load_runtime_samples,
    normalise_runtime_sample,
)


def _sample(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "sourceSampleId": (
            "FlashShifter.StardewValleyExpandedCP:"
            "assets/CharacterFiles/Dialogue/Claire/MarriageDialogue.json:"
            "funReturn_Claire"
        ),
        "npcId": "Claire",
        "sourceMod": "FlashShifter.StardewValleyExpandedCP",
        "sourcePath": "assets/CharacterFiles/Dialogue/Claire/MarriageDialogue.json",
        "sourceKey": "funReturn_Claire",
        "text": "欢迎回家，亲爱的。",
        "candidateKey": "Claire.funReturn.Spring_14",
        "conditions": {"relationshipStage": "married", "season": "Spring"},
        "gameState": {"season": "Spring", "day": 14, "time": 1830},
        "capturedAt": "2026-08-26T12:00:00+08:00",
    }
    value.update(overrides)
    return value


def test_normalise_runtime_sample_builds_stable_id_and_keeps_provenance() -> None:
    first = normalise_runtime_sample(_sample())
    second = normalise_runtime_sample(_sample())

    assert first == second
    assert first["sampleId"].startswith("runtime:")
    assert first["sourceSampleId"].endswith(":funReturn_Claire")
    assert first["evidenceKind"] == "runtime_dialogue"
    assert first["candidateKey"] == "Claire.funReturn.Spring_14"
    assert first["gameState"] == {"season": "Spring", "day": 14, "time": 1830}


def test_normalise_runtime_sample_rejects_unresolved_i18n() -> None:
    with pytest.raises(ValueError, match="未解析"):
        normalise_runtime_sample(_sample(text="{{i18n:Claire.funReturn.{{Random:1,2}}}}"))


def test_append_runtime_sample_is_idempotent(tmp_path: Path) -> None:
    output = tmp_path / "runtime-dialogue-samples.jsonl"
    append_runtime_sample(output, _sample())
    append_runtime_sample(output, _sample())

    rows = load_runtime_samples(output)
    assert len(rows) == 1
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1


def test_load_runtime_samples_reports_invalid_line(tmp_path: Path) -> None:
    output = tmp_path / "runtime-dialogue-samples.jsonl"
    output.write_text(json.dumps(_sample(), ensure_ascii=False) + "\nnot-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="第 2 行"):
        load_runtime_samples(output)
