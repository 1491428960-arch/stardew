from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from stardew_ai_bridge.profile_index import ProfileIndexBuilder


def _write_json(path: Path, value: str | dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_persona_layers_preserve_sources_and_overlay_boundaries(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {
            "mod": "vanilla",
            "personas": {
                "Wizard": {
                    "npcId": "Wizard",
                    "displayName": "Wizard",
                    "coreTraits": ["谨慎"],
                },
                "Sophia": {
                    "npcId": "Sophia",
                    "displayName": "Sophia",
                    "coreTraits": ["温和"],
                },
            },
        },
    )
    _write_json(
        persona_dir / "sve.json",
        {
            "mod": "SVE",
            "sourceMods": ["FlashShifter.SVECode"],
            "personas": {
                "Wizard": {"displayName": "Magnus"},
                "Sophia": {"displayName": "Sophia", "source": "SVE"},
            },
        },
    )

    index = ProfileIndexBuilder(persona_dir).build()

    assert index["schemaVersion"] == 1
    profiles = index["profiles"]
    assert isinstance(profiles, dict)
    assert profiles["Sophia"]["sourceMods"] == ["vanilla", "SVE"]
    assert profiles["Sophia"]["sourceFiles"] == ["vanilla.json", "sve.json"]
    assert profiles["Wizard"]["overlays"]["SVE"]["displayName"] == "Magnus"
    assert profiles["Wizard"]["displayName"] == "Wizard"


def test_content_patcher_dialogue_keeps_i18n_reference_and_source_key(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "sve"
    _write_json(
        mod_root / "manifest.json",
        {"Name": "Stardew Valley Expanded", "UniqueID": "FlashShifter.SVECode"},
    )
    _write_json(
        mod_root / "assets" / "Sophia" / "Dialogue.json",
        """
        {
          // Content Patcher allows comments and trailing commas.
          "Changes": [
            {
              "Action": "EditData",
              "Target": "Characters/Dialogue/Sophia",
              "Entries": {
                "Introduction": "{{i18n:Sophia.CharacterDialogue.001}}",
                "Rain": "今天适合待在家里。",
              },
            },
          ],
        }
        """,
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    samples = index["styleSamples"]
    assert isinstance(samples, list)
    assert {sample["sourceKey"] for sample in samples} == {"Introduction", "Rain"}
    introduction = next(sample for sample in samples if sample["sourceKey"] == "Introduction")
    assert introduction["npcId"] == "Sophia"
    assert introduction["sourceMod"] == "FlashShifter.SVECode"
    assert introduction["text"] == "{{i18n:Sophia.CharacterDialogue.001}}"
    assert introduction["sourcePath"] == "assets/Sophia/Dialogue.json"
    assert index["storyEvents"] == []


def test_invalid_json_becomes_warning_and_never_leaks_absolute_paths(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {"Alex": {"displayName": "Alex"}}},
    )
    mod_root = tmp_path / "mod"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    (mod_root / "broken-dialogue.json").write_text("{ not-json", encoding="utf-8")

    index = ProfileIndexBuilder(persona_dir).build([mod_root])
    rendered = json.dumps(index, ensure_ascii=False)

    assert any("invalid JSON" in warning for warning in index["warnings"])
    assert "broken-dialogue.json" in rendered
    assert str(tmp_path) not in rendered


def test_content_patcher_utf8_bom_is_accepted(tmp_path: Path) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "sve"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    dialogue = mod_root / "Dialogue.json"
    dialogue.write_text(
        '\ufeff{"Changes":[{"Action":"EditData","Target":"Characters/Dialogue/Alex",'
        '"Entries":{"Rain":"{{i18n:Alex.Rain}}"}}]}',
        encoding="utf-8",
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    assert len(index["styleSamples"]) == 1
    assert index["warnings"] == []


def test_content_patcher_multiline_dialogue_is_accepted(tmp_path: Path) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "sve"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    dialogue = mod_root / "MarriageDialogue.json"
    dialogue.write_text(
        '{"Changes":[{"Action":"EditData","Target":"Characters/Dialogue/MarriageDialogueAlex",'
        '"Entries":{"funLeave_Alex":"第一行\n{{i18n:Alex.funLeave}}\n第二行"}}]}',
        encoding="utf-8",
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    assert len(index["styleSamples"]) == 1
    assert index["styleSamples"][0]["npcId"] == "Alex"
    assert "\n" in index["styleSamples"][0]["text"]
    assert index["warnings"] == []


def test_non_dialogue_content_patcher_files_are_not_indexed_or_warned(
    tmp_path: Path,
) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {}},
    )
    mod_root = tmp_path / "sve"
    _write_json(mod_root / "manifest.json", {"UniqueID": "Example.Mod"})
    (mod_root / "code" / "NPCs").mkdir(parents=True)
    (mod_root / "code" / "NPCs" / "Krobus.json").write_text(
        '{"Changes":[{"Fields":{"Krobus":{0:99999}}}]}',
        encoding="utf-8",
    )

    index = ProfileIndexBuilder(persona_dir).build([mod_root])

    assert index["styleSamples"] == []
    assert index["warnings"] == []


def test_write_rejects_output_directory_that_is_a_file(tmp_path: Path) -> None:
    output = tmp_path / "output.json"
    output.write_text("not a directory", encoding="utf-8")

    with pytest.raises(OSError):
        ProfileIndexBuilder.write({"schemaVersion": 1}, output / "nested.json")


def test_cli_writes_index_to_explicit_output_path(tmp_path: Path) -> None:
    persona_dir = tmp_path / "personas"
    _write_json(
        persona_dir / "vanilla.json",
        {"mod": "vanilla", "personas": {"Alex": {"displayName": "Alex"}}},
    )
    output = tmp_path / "generated" / "profile-index.json"
    script = Path(__file__).parents[2] / "scripts" / "build_profile_index.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--persona-dir",
            str(persona_dir),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["schemaVersion"] == 1


def test_cli_rejects_missing_persona_directory_without_creating_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "generated" / "profile-index.json"
    script = Path(__file__).parents[2] / "scripts" / "build_profile_index.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--persona-dir",
            str(tmp_path / "does-not-exist"),
            "--output",
            str(output),
        ],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not output.exists()
