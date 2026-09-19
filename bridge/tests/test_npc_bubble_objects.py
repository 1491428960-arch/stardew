"""The complete pixel prop atlas follows the checked-in design specification."""
import json
import re
from pathlib import Path
from xml.etree import ElementTree

from stardew_ai_bridge.npc_bubble_objects import OBJECT_SVGS


def test_prop_atlas_covers_exact_specification():
    root = Path(__file__).resolve().parents[2]
    spec = json.loads((root / 'docs/npc-bubble-elements-all-2026-09-19.json').read_text(encoding='utf-8'))
    assert set(OBJECT_SVGS) == set(spec['objectLibrary'])
    assert len(OBJECT_SVGS) == 96
    assert len(set(OBJECT_SVGS.values())) == len(OBJECT_SVGS)


def test_props_are_safe_integer_pixel_svg_with_intrinsic_color():
    for name, svg in OBJECT_SVGS.items():
        root = ElementTree.fromstring('<svg>' + svg + '</svg>')
        colors = set()
        for node in root.iter():
            assert node.tag in {'svg', 'g', 'path', 'rect'}, name
            assert not node.text or not node.text.strip(), name
            assert set(node.attrib) <= {'fill', 'd', 'x', 'y', 'width', 'height'}, name
            if 'fill' in node.attrib:
                assert re.fullmatch(r'#[0-9a-fA-F]{6}', node.attrib['fill']), name
                colors.add(node.attrib['fill'])
            if node.tag == 'path':
                assert re.fullmatch(r'[MHVZ0-9 ,]+', node.attrib['d']), name
                assert all(0 <= int(v) <= 32 for v in re.findall(r'\d+', node.attrib['d'])), name
            if node.tag == 'rect':
                x, y, w, h = (int(node.attrib[k]) for k in ('x', 'y', 'width', 'height'))
                assert 0 <= x < x + w <= 32 and 0 <= y < y + h <= 32, name
        assert '#20202c' in colors, name
        assert len(colors - {'#20202c'}) >= 3, name
