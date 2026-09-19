from __future__ import annotations

import importlib
import importlib.util
import json
import re
from pathlib import Path
from xml.etree import ElementTree


SPEC = json.loads(
    (Path(__file__).resolve().parents[2] / "docs/npc-bubble-elements-2026-09-19.json")
    .read_text(encoding="utf-8")
)


def _elements():
    module_name = "stardew_ai_bridge.npc_bubble_elements"
    assert importlib.util.find_spec(module_name) is not None, "缺少角色视觉单一数据源"
    return importlib.import_module(module_name).NPC_BUBBLE_ELEMENTS


def test_visual_elements_cover_the_nine_npcs_without_persona_or_duplicate_glyphs():
    elements = _elements()

    assert [npc for npc in elements if npc in SPEC["npcOrder"]] == SPEC["npcOrder"]
    for value in elements.values():
        assert set(value) == {"icon", "tone", "palette", "motifs", "ornament"}
        assert isinstance(value["motifs"], tuple)
        assert len(value["motifs"]) == 3


def test_visual_elements_keep_approved_palettes_tones_and_fallback_icons():
    elements = _elements()
    fallback_icons = dict(zip(SPEC["npcOrder"], "✦★◇✒✚◢☕✿✧"))

    for npc_id, expected in SPEC["npcs"].items():
        assert elements[npc_id]["palette"] == expected["palette"]
        assert elements[npc_id]["tone"] == expected["toneLabel"]
        assert elements[npc_id]["icon"] == fallback_icons[npc_id]


def test_secondary_motifs_preserve_the_approved_library():
    elements = _elements()

    for npc_id, expected in SPEC["npcs"].items():
        assert elements[npc_id]["motifs"][1:] == tuple(expected["motifs"][1:])


def test_avatar_motifs_are_distinct_integer_pixel_art_with_three_color_layers():
    elements = _elements()
    motifs = [elements[npc]["motifs"][0] for npc in SPEC["npcOrder"]]
    assert len(set(motifs)) == 9

    for motif in motifs:
        root = ElementTree.fromstring(f"<svg>{motif}</svg>")
        assert "currentColor" in motif
        assert "var(--accent-soft)" in motif
        assert "#171a20" in motif
        for element in root.iter():
            assert element.tag in {"svg", "g", "path", "rect"}
            assert "transform" not in element.attrib
            if element.tag == "path":
                path = element.attrib["d"]
                assert set(re.findall(r"[A-Za-z]", path)) <= set("MHVZ")
                coordinates = re.findall(r"-?\d+(?:\.\d+)?", path)
                assert all(number.isdigit() and 0 <= int(number) <= 24 for number in coordinates)
            elif element.tag == "rect":
                x, y, width, height = (int(element.attrib[key]) for key in ("x", "y", "width", "height"))
                assert 0 <= x < x + width <= 24
                assert 0 <= y < y + height <= 24


def test_ornaments_assign_two_character_objects_and_a_matching_frame_to_every_npc():
    expected = {
        "Abigail": ("crystal", "紫水晶与小剑"),
        "Alex": ("laurel", "橄榄球与哑铃"),
        "Emily": ("ribbon", "宝石与彩色线轴"),
        "Elliott": ("paper", "羽毛笔墨水瓶与手稿"),
        "Harvey": ("vine", "咖啡杯与医疗包"),
        "Sebastian": ("cable", "游戏手柄与蝙蝠"),
        "Shane": ("wheat", "小鸡与咖啡杯"),
        "Sophia": ("grapevine", "葡萄串与葡萄叶粉花"),
        "Wizard": ("arcane", "水晶球与魔法书"),
    }
    for npc_id, (kind, label) in expected.items():
        ornament = _elements()[npc_id].get("ornament")
        assert ornament is not None, f"{npc_id} 缺少环绕特征物"
        assert set(ornament) == {"label", "kind", "colors", "objects"}
        assert (ornament["kind"], ornament["label"]) == (kind, label)
        assert set(ornament["colors"]) == {"line", "highlight", "leaf", "leafHi"}
        assert all(re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in ornament["colors"].values())
        assert len(set(ornament["colors"].values())) == 4
        assert isinstance(ornament["objects"], tuple)
        assert len(ornament["objects"]) == 2


def test_ornament_objects_are_distinct_safe_integer_pixel_art_on_a_32_pixel_canvas():
    objects = []
    for npc_id in SPEC["npcOrder"]:
        value = _elements()[npc_id]
        assert "ornament" in value, f"{npc_id} 缺少环绕特征物"
        objects.extend(value["ornament"]["objects"])
    assert len(set(objects)) == 18

    for svg in objects:
        root = ElementTree.fromstring(f"<svg>{svg}</svg>")
        colors, xs, ys = set(), [], []
        for element in root.iter():
            assert not (element.text or "").strip()
            assert not (element.tail or "").strip()
            assert element.tag in {"svg", "g", "path", "rect"}
            allowed = {"path": {"d", "fill"}, "rect": {"x", "y", "width", "height", "fill"}, "g": {"fill"}, "svg": set()}
            assert set(element.attrib) <= allowed[element.tag]
            if "fill" in element.attrib:
                assert re.fullmatch(r"#[0-9a-fA-F]{6}", element.attrib["fill"])
                colors.add(element.attrib["fill"])
            if element.tag == "path":
                path = element.attrib["d"]
                assert re.fullmatch(r"[MHVZ0-9 ,]+", path)
                assert path.startswith("M") and path.endswith("Z")
                coordinates = re.findall(r"\d+", path)
                assert all(1 <= int(number) <= 31 for number in coordinates)
                for command, numbers in re.findall(r"([MHVZ])([^MHVZ]*)", path):
                    values = [int(number) for number in re.findall(r"\d+", numbers)]
                    if command == "M":
                        assert len(values) == 2
                        xs.append(values[0])
                        ys.append(values[1])
                    elif command == "H":
                        xs.extend(values)
                    elif command == "V":
                        ys.extend(values)
            elif element.tag == "rect":
                assert all(element.attrib[key].isdigit() for key in ("x", "y", "width", "height"))
                x, y, width, height = (int(element.attrib[key]) for key in ("x", "y", "width", "height"))
                assert 1 <= x < x + width <= 31
                assert 1 <= y < y + height <= 31
                xs.extend((x, x + width))
                ys.extend((y, y + height))
        assert len(colors) >= 4, "特征物需要深轮廓、固有色、阴影和高光"
        assert "#20202c" in colors
        assert 24 <= max(max(xs) - min(xs), max(ys) - min(ys)) <= 30


ALL_SPEC = json.loads(
    (Path(__file__).resolve().parents[2] / "docs/npc-bubble-elements-all-2026-09-19.json")
    .read_text(encoding="utf-8")
)


def test_all_friendship_characters_and_aliases_resolve_to_one_definition():
    from stardew_ai_bridge.npc_bubble_elements import canonical_npc_id, NPC_BUBBLE_ALIASES
    elements = _elements()
    assert set(elements) == set(ALL_SPEC["npcs"])
    assert len(elements) == 46
    expected = {**ALL_SPEC["roster"]["aliases"], "SVE_Henchman": "Henchman"}
    assert NPC_BUBBLE_ALIASES == expected
    for npc in ALL_SPEC["roster"]["npcs"]:
        assert canonical_npc_id(npc) in elements
    for alias, canonical in expected.items():
        assert elements[canonical_npc_id(alias)] is elements[canonical]
    for unknown in ("Player", "__proto__", "constructor", "Unknown", "", None):
        assert canonical_npc_id(unknown) == unknown


def test_added_characters_follow_the_authoritative_catalog():
    from stardew_ai_bridge.npc_bubble_objects import OBJECT_SVGS
    for npc, expected in ALL_SPEC["npcs"].items():
        value = _elements()[npc]
        assert value["palette"] == expected["palette"]
        if npc in SPEC["npcs"]:
            continue
        assert value["tone"] == expected["tone"]
        assert value["ornament"]["kind"] == expected["kind"]
        assert value["ornament"]["objects"] == tuple(OBJECT_SVGS[key] for key in expected["objects"])
        glyph = ElementTree.fromstring(f'<svg>{value["motifs"][0]}</svg>')
        assert glyph[0].tag == "svg"
        assert glyph[0].attrib == {"width": "24", "height": "24", "viewBox": "0 0 32 32"}
        assert OBJECT_SVGS[expected["glyph"]] in value["motifs"][0]


def test_packaged_catalog_is_current_without_runtime_document_access():
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, str(root / "scripts/sync_npc_bubble_catalog.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    from stardew_ai_bridge.npc_bubble_catalog import NPC_CATALOG, OBJECT_CATALOG, KIND_CATALOG
    assert NPC_CATALOG == ALL_SPEC["npcs"]
    assert OBJECT_CATALOG == ALL_SPEC["objectLibrary"]
    assert KIND_CATALOG == ALL_SPEC["kindLibrary"]
