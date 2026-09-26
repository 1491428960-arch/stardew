"""NPC ID 别名归一。

`canonical_npc_id()` 是索引构建、prompt、阶段策略、关系门控、行为评测的**公共入口**
（`profile_index.py` 里 30 多处调用），所以别名必须在这一层归 —— 在下游任何一处补，
都会漏掉其余调用点。

**这条修复的由来（2026-09-26）**：SVE 把三个角色的角色键写成全名，而 `data/personas/`
用短名，于是索引 `profiles` 里 `Morris` 与 `MorrisTod`、`Marlon` 与 `MarlonFay`、
`Gunther` 与 `GuntherSilvian` 各自并存 —— **同一个人的「特质」和「语料」挂在两个键上，
谁也见不到谁**：`MorrisTod` 名下 165 条日常对白从未出现在 `Morris` 的任何一张卡里。
"""

from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.personas import NPC_ID_ALIASES, canonical_npc_id

ROOT = Path(__file__).resolve().parents[2]
PERSONAS_DIR = ROOT / "data" / "personas"


def test_sve_full_names_collapse_to_their_persona_key() -> None:
    assert canonical_npc_id("MorrisTod") == "Morris"
    assert canonical_npc_id("MarlonFay") == "Marlon"
    assert canonical_npc_id("GuntherSilvian") == "Gunther"


def test_both_spellings_reach_the_same_key() -> None:
    """归一的**目的**是两种写法落到同一个桶里 —— 这一条才是修复本身。"""

    for alias, target in NPC_ID_ALIASES.items():
        assert canonical_npc_id(alias) == canonical_npc_id(target) == target


def test_alias_lookup_ignores_case_and_padding() -> None:
    assert canonical_npc_id("  morristod  ") == "Morris"
    assert canonical_npc_id("MARLONFAY") == "Marlon"


def test_aliases_do_not_swallow_lookalike_names() -> None:
    """过宽的归一（前缀匹配之类）会把不相干的角色并成一个。"""

    assert canonical_npc_id("Morris") == "Morris"
    assert canonical_npc_id("MorrisTodJr") == "MorrisTodJr"
    assert canonical_npc_id("GuntherSilvian") != "GuntherSilvianOther"


def test_existing_normalisations_still_hold() -> None:
    """别名表是**追加**的，不能碰原有的两条归一路径。"""

    assert canonical_npc_id("MarriageDialogueElliott") == "Elliott"
    assert canonical_npc_id("RoommateDialogueKrobus") == "Krobus"
    assert canonical_npc_id("Rasmodia") == "Wizard"
    assert canonical_npc_id("wizard") == "Wizard"
    assert canonical_npc_id("Abigail") == "Abigail"


def test_blank_input_is_returned_unchanged() -> None:
    assert canonical_npc_id("") == ""
    assert canonical_npc_id(None) == "None"


def test_every_alias_target_is_a_real_persona_key() -> None:
    """别名不能指向一个不存在的人设 —— 那会让语料归进一个永远取不到特质的键。"""

    keys: set[str] = set()
    for path in sorted(PERSONAS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("personas"), dict):
            keys.update(payload["personas"])
    for alias, target in NPC_ID_ALIASES.items():
        assert target in keys, f"{alias} 归到的 {target} 没有人设条目"
