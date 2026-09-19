"""`PersonaStore._load()` 的加载健壮性。

资料库是叠加式的：`vanilla.json` 是先加载的基线，其它文件按来源标记塞进
`modOverlay`，由 `merge_persona` 在取值时叠加。这里钉住四种数据形态：
坏文件跳过、裸映射、条目类型错误、以及“没有基线时基线用 npcId 兜底”。
"""

from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.personas import PersonaStore


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_load_skips_a_file_whose_personas_key_is_not_a_mapping(tmp_path: Path) -> None:
    # vanilla.json 写坏（personas 是列表）时整份跳过，不能拖垮其它文件。
    _write(tmp_path / "vanilla.json", {"mod": "vanilla", "personas": ["坏数据"]})
    _write(tmp_path / "sve.json", {"mod": "sve", "personas": {"Shane": {"displayName": "珊恩"}}})

    loaded = PersonaStore(tmp_path)._load()

    assert "Shane" in loaded
    # 没有 vanilla 基线时，基线取 npcId；来源内容留在 modOverlay 里。
    assert loaded["Shane"]["displayName"] == "Shane"
    assert loaded["Shane"]["modOverlay"]["sve"]["displayName"] == "珊恩"


def test_load_accepts_a_bare_persona_mapping(tmp_path: Path) -> None:
    # 没有 personas 包裹时，顶层映射本身就是条目表。
    _write(tmp_path / "vanilla.json", {"Shane": {"displayName": "谢恩"}})

    loaded = PersonaStore(tmp_path)._load()

    assert loaded["Shane"]["displayName"] == "谢恩"
    assert loaded["Shane"]["npcId"] == "Shane"


def test_load_skips_entries_that_are_not_mappings(tmp_path: Path) -> None:
    _write(
        tmp_path / "vanilla.json",
        {
            "mod": "vanilla",
            "personas": {"Shane": "坏数据", "Emily": {"displayName": "艾米丽"}},
        },
    )

    loaded = PersonaStore(tmp_path)._load()

    assert "Emily" in loaded
    assert "Shane" not in loaded
    assert loaded["Emily"]["displayName"] == "艾米丽"


def test_load_keeps_vanilla_as_the_base_and_layers_other_files(tmp_path: Path) -> None:
    _write(tmp_path / "vanilla.json", {"mod": "vanilla", "personas": {"Shane": {"displayName": "谢恩"}}})
    _write(
        tmp_path / "female-bachelors.json",
        {"mod": "female-bachelors", "personas": {"Shane": {"displayName": "珊恩"}}},
    )

    loaded = PersonaStore(tmp_path)._load()

    # 基线仍是 vanilla 的内容，叠加层单独保存（真实取值由 merge_persona 决定）。
    assert loaded["Shane"]["displayName"] == "谢恩"
    assert loaded["Shane"]["modOverlay"]["female-bachelors"]["displayName"] == "珊恩"
