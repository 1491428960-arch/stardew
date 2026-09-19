import json
from pathlib import Path

import pytest

from stardew_ai_bridge.runtime_samples import (
    append_runtime_sample,
    attribute_runtime_sample,
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


def _unattributed_sample() -> dict[str, object]:
    """没有来源的运行时样本：归属函数要能给它补上 sourceMod/sourcePath。"""

    raw = _sample()
    raw.pop("sourceMod")
    raw.pop("sourcePath")
    return raw


def _corpus_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "npcId": "Claire",
        # 真实运行时样本里 candidateKey 与 corpus 的 sourceKey 属同一命名空间
        # （形如 Wizard.Rain），这里必须与 _sample() 的 candidateKey 一致。
        "sourceKey": "Claire.funReturn.Spring_14",
        "resolvedText": "欢迎回家，亲爱的。",
        "sourceMod": "FlashShifter.StardewValleyExpandedCP",
        "sourcePath": "assets/CharacterFiles/Dialogue/Claire/MarriageDialogue.json",
    }
    record.update(overrides)
    return record


def test_attribute_runtime_sample_fills_source_for_a_unique_match() -> None:
    attributed = attribute_runtime_sample(
        _unattributed_sample(),
        [_corpus_record()],
    )

    assert attributed["sourceMod"] == "FlashShifter.StardewValleyExpandedCP"
    assert attributed["sourcePath"].endswith("MarriageDialogue.json")
    # 归属只补来源，不改动运行时采样到的内容。
    assert attributed["text"] == "欢迎回家，亲爱的。"
    assert attributed["npcId"] == "Claire"


def test_attribute_runtime_sample_keeps_ambiguous_matches_unattributed() -> None:
    raw = _unattributed_sample()

    attributed = attribute_runtime_sample(
        raw,
        [
            _corpus_record(),
            _corpus_record(sourceMod="Someone.Else"),
        ],
    )

    # 命中两条（不同 Mod）时宁可不归属，避免把动态分支挂到错误的 Mod。
    assert "sourceMod" not in attributed
    assert attributed["npcId"] == "Claire"


@pytest.mark.parametrize("missing", ["npcId", "text"])
def test_attribute_runtime_sample_requires_each_key_field(missing: str) -> None:
    raw = _unattributed_sample()
    raw.pop(missing)

    assert "sourceMod" not in attribute_runtime_sample(raw, [_corpus_record()])


def test_attribute_runtime_sample_requires_a_source_key_of_some_kind() -> None:
    raw = _unattributed_sample()
    raw.pop("candidateKey")
    raw.pop("sourceKey")

    assert "sourceMod" not in attribute_runtime_sample(raw, [_corpus_record()])


def test_attribute_runtime_sample_ignores_records_without_text_or_mod() -> None:
    raw = _unattributed_sample()

    assert "sourceMod" not in attribute_runtime_sample(
        raw, [_corpus_record(resolvedText="完全不同的台词")]
    )
    assert "sourceMod" not in attribute_runtime_sample(
        raw, [_corpus_record(sourceMod="   ")]
    )
    assert "sourceMod" not in attribute_runtime_sample(raw, [])
