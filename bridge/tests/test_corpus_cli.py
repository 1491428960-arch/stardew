from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_export_dialogue_corpus_writes_provenance_safe_json(tmp_path: Path) -> None:
    vanilla_root = tmp_path / "vanilla-dialogue"
    vanilla_root.mkdir()
    (vanilla_root / "Wizard.json").write_text(
        json.dumps({"Rain": "雨天。", "Introduction": "你好。"}, ensure_ascii=False),
        encoding="utf-8",
    )

    mod_root = tmp_path / "Rasmodia"
    mod_root.mkdir()
    (mod_root / "manifest.json").write_text(
        json.dumps({"UniqueID": "Dacar.SeasRomRasmodia"}),
        encoding="utf-8",
    )
    (mod_root / "content.json").write_text(
        """
        {
          // Content Patcher allows comments.
          "Changes": [
            {
              "Action": "EditData",
              "Target": "Characters/Dialogue/MarriageDialogueRasmodia",
              "Entries": {"Rain": "雨天留在塔里。"}
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    output_path = tmp_path / "out" / "dialogue-corpus.json"
    project_root = Path(__file__).parents[2]
    script_path = project_root / "scripts" / "export_dialogue_corpus.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--vanilla-root",
            str(vanilla_root),
            "--mod-root",
            str(mod_root),
            "--output",
            str(output_path),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    exported = json.loads(output_path.read_text(encoding="utf-8"))
    assert exported["schemaVersion"] == 1
    assert {record["sourceMod"] for record in exported["records"]} == {
        "vanilla",
        "Dacar.SeasRomRasmodia",
    }
    assert any(
        record["evidenceKind"] == "marriage_dialogue"
        for record in exported["records"]
    )
    assert str(tmp_path) not in output_path.read_text(encoding="utf-8")


def test_build_profile_index_merges_corpus_and_vanilla_root(
    tmp_path: Path,
) -> None:
    vanilla_root = tmp_path / "vanilla-dialogue"
    vanilla_root.mkdir()
    (vanilla_root / "Wizard.json").write_text(
        json.dumps({"Rain": "魔法塔今天很安静。"}, ensure_ascii=False),
        encoding="utf-8",
    )
    corpus_path = tmp_path / "rasmodia-corpus.json"
    corpus_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "records": [
                    {
                        "sampleId": "Rasmodia:Dialogue.json:Rain",
                        "npcId": "Rasmodia",
                        "sourceMod": "Example.Rasmodia",
                        "sourcePath": "Dialogue.json",
                        "sourceKey": "Rain",
                        "text": "也许魔法需要边界。",
                        "evidenceKind": "dialogue",
                        "conditions": {},
                    }
                ],
                "sources": [],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    (persona_dir / "vanilla.json").write_text(
        json.dumps({"mod": "vanilla", "personas": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    output_path = tmp_path / "out" / "profile-index.json"
    project_root = Path(__file__).parents[2]
    script_path = project_root / "scripts" / "build_profile_index.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--persona-dir",
            str(persona_dir),
            "--corpus",
            str(corpus_path),
            "--vanilla-root",
            str(vanilla_root),
            "--output",
            str(output_path),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    index = json.loads(output_path.read_text(encoding="utf-8"))
    assert index["schemaVersion"] == 2
    assert {item["npcId"] for item in index["speechEvidence"]} == {"Wizard"}
    assert "Wizard" in index["voiceCards"]
    assert "Rasmodia" not in index["voiceCards"]


def test_build_profile_index_can_limit_vanilla_to_requested_locale(
    tmp_path: Path,
) -> None:
    vanilla_root = tmp_path / "vanilla-dialogue"
    vanilla_root.mkdir()
    (vanilla_root / "Wizard.de-DE.json").write_text(
        json.dumps({"Rain": "Deutscher Satz"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (vanilla_root / "Wizard.zh-CN.json").write_text(
        json.dumps({"Rain": "中文台词"}, ensure_ascii=False),
        encoding="utf-8",
    )
    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    (persona_dir / "vanilla.json").write_text(
        json.dumps({"mod": "vanilla", "personas": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    output_path = tmp_path / "out" / "profile-index.json"
    project_root = Path(__file__).parents[2]
    script_path = project_root / "scripts" / "build_profile_index.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--persona-dir",
            str(persona_dir),
            "--vanilla-root",
            str(vanilla_root),
            "--vanilla-locale",
            "zh-CN",
            "--output",
            str(output_path),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    index = json.loads(output_path.read_text(encoding="utf-8"))
    wizard_lines = [
        item for item in index["speechEvidence"] if item["npcId"] == "Wizard"
    ]
    assert [item["text"] for item in wizard_lines] == ["中文台词"]
