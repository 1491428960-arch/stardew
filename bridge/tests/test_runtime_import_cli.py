from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_import_smapi_runtime_samples_extracts_markers_and_deduplicates(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "SMAPI-latest.txt"
    output_path = tmp_path / "runtime.jsonl"
    payload = {
        "schemaVersion": 1,
        "sourceSampleId": "runtime:Wizard:Wizard.Rain",
        "npcId": "Wizard",
        "sourceMod": "runtime.unattributed",
        "sourcePath": "runtime/dialogue",
        "sourceKey": "Wizard.Rain",
        "candidateKey": "Wizard.Rain",
        "text": "雨水会改变星界的回声。",
        "gameState": {"season": "Spring", "day": 3, "time": 900},
    }
    marker = "[StardewAI.RuntimeDialogueSample] "
    log_path.write_text(
        "普通日志\n"
        + marker
        + json.dumps(payload, ensure_ascii=False)
        + "\n"
        + marker
        + json.dumps(payload, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    script = Path(__file__).parents[2] / "scripts" / "import_smapi_runtime_samples.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    result = subprocess.run(
        [sys.executable, str(script), "--log", str(log_path), "--output", str(output_path)],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["evidenceKind"] == "runtime_dialogue"
    assert rows[0]["text"] == "雨水会改变星界的回声。"


def test_import_smapi_runtime_samples_attributes_unique_corpus_match(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "SMAPI-latest.txt"
    output_path = tmp_path / "runtime.jsonl"
    corpus_path = tmp_path / "corpus.json"
    payload = {
        "schemaVersion": 1,
        "sourceSampleId": "runtime:Wizard:Wizard.Rain",
        "npcId": "Wizard",
        "sourceMod": "runtime.unattributed",
        "sourcePath": "runtime/dialogue",
        "sourceKey": "Wizard.Rain",
        "candidateKey": "Wizard.Rain",
        "text": "雨水会改变星界的回声。",
    }
    corpus_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "records": [
                    {
                        "npcId": "Wizard",
                        "sourceMod": "vanilla",
                        "sourcePath": "Characters/Dialogue/Wizard.json",
                        "sourceKey": "Wizard.Rain",
                        "resolvedText": "雨水会改变星界的回声。",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log_path.write_text(
        "[StardewAI.RuntimeDialogueSample] "
        + json.dumps(payload, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    script = Path(__file__).parents[2] / "scripts" / "import_smapi_runtime_samples.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--log",
            str(log_path),
            "--output",
            str(output_path),
            "--corpus",
            str(corpus_path),
        ],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    row = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["sourceMod"] == "vanilla"
    assert row["sourcePath"] == "Characters/Dialogue/Wizard.json"
    assert row["sourceKey"] == "Wizard.Rain"
    assert row["attribution"]["match"] == "npc+sourceKey+text"


def test_import_smapi_runtime_samples_keeps_ambiguous_match_unattributed(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "SMAPI-latest.txt"
    output_path = tmp_path / "runtime.jsonl"
    corpus_path = tmp_path / "corpus.json"
    payload = {
        "schemaVersion": 1,
        "sourceSampleId": "runtime:Wizard:Wizard.Rain",
        "npcId": "Wizard",
        "sourceMod": "runtime.unattributed",
        "sourcePath": "runtime/dialogue",
        "sourceKey": "Wizard.Rain",
        "text": "雨水会改变星界的回声。",
    }
    record = {
        "npcId": "Wizard",
        "sourceKey": "Wizard.Rain",
        "resolvedText": payload["text"],
    }
    corpus_path.write_text(
        json.dumps(
            {"records": [{**record, "sourceMod": "vanilla"}, {**record, "sourceMod": "Some.Mod"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log_path.write_text(
        "[StardewAI.RuntimeDialogueSample] "
        + json.dumps(payload, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    script = Path(__file__).parents[2] / "scripts" / "import_smapi_runtime_samples.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--log",
            str(log_path),
            "--output",
            str(output_path),
            "--corpus",
            str(corpus_path),
        ],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    row = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["sourceMod"] == "runtime.unattributed"
    assert row["sourcePath"] == "runtime/dialogue"
    assert "attribution" not in row
