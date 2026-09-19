import json
import subprocess
from pathlib import Path

from stardew_ai_bridge.group_dialogue_review_page import _CHARACTER_FRAME_SCRIPT


def test_all_materials_have_distinct_silhouettes_with_identical_colors():
    spec = json.loads((Path(__file__).resolve().parents[2] / 'docs/npc-bubble-elements-all-2026-09-19.json').read_text(encoding='utf-8'))
    kinds = list(spec['kindLibrary'])
    script = _CHARACTER_FRAME_SCRIPT + '\nconst kinds=' + json.dumps(kinds) + ''';
    // Cancel the kind-dependent layout seed, so only material geometry differs.
    const frames=kinds.map(kind=>characterFrameSvg(360,120,{kind,colors:{line:'#556655',highlight:'#ccddee',leaf:'#889977',leafHi:'#ddeeff'},objects:['','']},(3-[...kind].reduce((n,ch)=>n+ch.charCodeAt(0),0)%3)%3));
    process.stdout.write(JSON.stringify(frames));'''
    result = subprocess.run(['node'], input=script, capture_output=True, text=True, encoding='utf-8', check=True)
    frames = json.loads(result.stdout)
    assert len(kinds) == 19
    assert len(set(frames)) == 19, '每种材质需要不同轮廓，不能只改颜色'


def test_aliases_resolve_styles_glyphs_and_ornaments_in_browser_javascript():
    import re
    from stardew_ai_bridge.group_dialogue_review_page import group_dialogue_review_page
    html = group_dialogue_review_page(Path('missing-artifacts'))
    names = ['NPC_ALIASES', 'NPC_STYLES', 'SPEAKER_GLYPHS', 'CHARACTER_ORNAMENTS', 'canonicalNpcId', 'ornamentFor', 'glyphFor', 'styleFor']
    declarations = []
    for name in names:
        match = re.search(rf'const {name} = .*?;', html)
        assert match, name
        declarations.append(match[0])
    script = '\n'.join(declarations) + '''
    for (const [alias,id] of Object.entries(NPC_ALIASES)) {
      if (styleFor(alias)!==styleFor(id)||glyphFor(alias)!==glyphFor(id)||ornamentFor(alias)!==ornamentFor(id)) throw Error(alias);
    }
    for (const id of ['Player','Unknown','__proto__','constructor']) {
      if(ornamentFor(id)!==null||glyphFor(id)!=='') throw Error('unsafe fallback '+id);
    }
    '''
    subprocess.run(['node'], input=script, capture_output=True, text=True, encoding='utf-8', check=True)
