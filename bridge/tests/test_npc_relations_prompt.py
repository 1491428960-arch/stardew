"""NPC↔NPC 关系必须真的进 prompt —— 尤其是游戏走的那条 compact 路径。

## 背景（2026-09-24 实机）

用户在游戏里和索菲亚聊天，她说：

    格斯做的菜总是很有味道……我可以去问问他，就是、就是有点怕打扰到他，
    如果你真的想让我学，那我就去！

而 SVE 的事件对白里，Gus 对她说的是
`"Of course, Sophia! Anything for a close family friend!"`，中文 i18n 是
「当然，索菲娅！我很乐意为一位**亲密的家庭朋友**做任何事！」；8 心事件更直白：
「**我知道你来这里是为了什么！** 格兰普顿香橙鸡马上就到！」—— 熟到不用点单。

**她的素材里关于格斯只有「格斯做菜时那股香味」这一条**（`sve.json` 第 37、
77–80 行），关系事实从来没进过 prompt，模型在缺口处自己编，编成了陌生人。

## 这个文件防什么

本项目栽过多次「数据有了、却没到模型眼前」：`topicPool` 因缩进缺陷整批丢失
（`test_stage_profile_topic_pool.py`）、`coreTraits` 被 limit=4 砍到只剩前四条。
关系数据同样要过两层白名单（`_IDENTITY_FIELDS` 与 `persona_core` 的
`persona_fields`）和一次压缩，所以这里既钉压缩器本身，也用**真实人设 +
真实派生索引**验证它在 `_runtime_compact` 那条游戏路径上确实出现。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from stardew_ai_bridge.personas import PersonaStore
from stardew_ai_bridge.profile_index import ProfileIndexStore
from stardew_ai_bridge.prompts import (
    ContextBuilder,
    PromptBuilder,
    _compact_npc_relations,
)

ROOT = Path(__file__).resolve().parents[2]
INDEX = (
    ROOT
    / "data"
    / "generated"
    / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)


# --- 压缩器本身 -------------------------------------------------------------


def test_compaction_keeps_the_target_term_and_note() -> None:
    compact = _compact_npc_relations(
        [{"npc": "Gus", "term": "家人的朋友", "note": "他知道我要格兰普顿香橙鸡。"}]
    )

    assert compact == [
        {"npc": "Gus", "term": "家人的朋友", "note": "他知道我要格兰普顿香橙鸡。"}
    ]


def test_compaction_keeps_an_entry_without_a_note() -> None:
    """亲属关系大多只有 `term`（`Data/Characters.json` 不给描述），不能不收。"""

    assert _compact_npc_relations([{"npc": "Shane", "term": "外甥"}]) == [
        {"npc": "Shane", "term": "外甥"}
    ]


def test_compaction_drops_entries_without_a_target() -> None:
    assert _compact_npc_relations([{"term": "朋友"}, "坏数据"]) == []


def test_compaction_is_capped() -> None:
    """上限 8 条。索菲亚按原句挖出来就有 7 条，6 会静静砍掉一条。"""

    entries = [{"npc": f"NPC{index}", "term": "朋友"} for index in range(12)]

    assert len(_compact_npc_relations(entries)) == 8


def test_compaction_of_nothing_is_empty() -> None:
    assert _compact_npc_relations(None) == []
    assert _compact_npc_relations({}) == []


# --- 真实数据端到端 ---------------------------------------------------------


def _source_mods(npc_id: str) -> list[str]:
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    profile = payload["profiles"].get(npc_id) or {}
    return list(profile.get("sourceMods") or [])


def _game_path_messages(npc_id: str, player_input: str) -> list[dict[str, Any]]:
    """按游戏实际那条路构造 messages：`compact=True` + `_runtime_compact`。"""

    mods = _source_mods(npc_id)
    payload = {
        "npcId": npc_id,
        "message": player_input,
        "provider": "fake",
        "displayName": npc_id,
        "sourceMods": mods,
        "history": [],
        "gameState": {
            "npcId": npc_id,
            "season": "spring",
            "date": "25",
            "weather": "clear",
            "time": 1200,
            "location": "Saloon",
            "friendshipHearts": 14,
            "relationshipStage": "dating",
            "relationship": "dating",
            "marriageStatus": "single",
            "childrenCount": 0,
            "sourceMods": mods,
        },
        "intent": "chat",
        "compactPrompt": True,
    }
    context = ContextBuilder(PersonaStore(), ProfileIndexStore(INDEX)).build(payload)
    context["_runtime_compact"] = True
    return PromptBuilder().build(context, player_input, compact=True)


@pytest.mark.skipif(not INDEX.exists(), reason="派生索引未生成")
def test_sophia_knows_gus_on_the_compact_game_path() -> None:
    """只看 `compact=True` 不够 —— 游戏还额外设了 `_runtime_compact`。"""

    rendered = json.dumps(
        _game_path_messages("Sophia", "格斯做的菜真不错"),
        ensure_ascii=False,
    )

    assert "家人的朋友" in rendered
    assert "格兰普顿香橙鸡" in rendered


@pytest.mark.skipif(not INDEX.exists(), reason="派生索引未生成")
def test_relations_also_reach_the_full_prompt_path() -> None:
    """非 compact 路径（测试、群聊等）同样要带上关系。"""

    context = ContextBuilder(PersonaStore(), ProfileIndexStore(INDEX)).build(
        {
            "npcId": "Sophia",
            "message": "格斯做的菜真不错",
            "provider": "fake",
            "displayName": "Sophia",
            "sourceMods": _source_mods("Sophia"),
            "history": [],
            "gameState": {
                "npcId": "Sophia",
                "season": "spring",
                "date": "25",
                "weather": "clear",
                "time": 1200,
                "location": "Saloon",
                "friendshipHearts": 14,
                "relationshipStage": "dating",
                "sourceMods": _source_mods("Sophia"),
            },
            "intent": "chat",
        }
    )

    rendered = json.dumps(
        PromptBuilder().build(context, "格斯做的菜真不错"),
        ensure_ascii=False,
    )

    assert "家人的朋友" in rendered


@pytest.mark.skipif(not INDEX.exists(), reason="派生索引未生成")
def test_a_character_without_relations_does_not_get_the_field() -> None:
    """没有关系的角色不能凭空多出一张卡 —— 那是在花 prompt 预算买空气。"""

    rendered = json.dumps(
        _game_path_messages("Linus", "最近怎么样？"),
        ensure_ascii=False,
    )

    assert "npcRelations" not in rendered


# --- 覆盖面：SVE 角色的关系不能只剩索菲亚 -------------------------------------

RELATIONS = ROOT / "data" / "npc-relations.json"


@pytest.mark.skipif(not RELATIONS.exists(), reason="关系表未生成")
def test_every_sve_persona_has_relations() -> None:
    """SVE 的 8 个 persona 角色都必须有关系数据。

    这条防的是一次真实的退化：SVE 把 `FriendsAndFamily` 全留空了，SVE 角色的
    关系**只能靠 `npc-relations-extras.json` 策展**。于是「只做了索菲亚」在
    数据层完全看不出来 —— 表照样生成、测试照样过、prompt 照样注入，另外七个
    角色却一个字都没有。目标写的是「覆盖所有主要角色」，就在这里钉住。
    """

    relations = json.loads(RELATIONS.read_text(encoding="utf-8"))["relations"]

    for npc in ("Wizard", "Sophia", "Victor", "Olivia", "Andy", "Lance", "Claire", "Morris"):
        assert relations.get(npc), f"{npc} 没有关系数据"


@pytest.mark.skipif(not INDEX.exists(), reason="派生索引未生成")
def test_olivia_and_victor_know_each_other_both_ways() -> None:
    """母子关系两个方向都要到 prompt —— 单向的数据会让一方把另一方当陌生人。

    证据本身是双向的：`Olivia.CharacterDialogue.001`「你见过我**儿子**维克多了
    吗？」与 `Victor.divorcedOlivia`「我**妈妈**对离婚的事情还无法完全接受」。
    """

    from_mother = json.dumps(
        _game_path_messages("Olivia", "维克多最近怎么样？"),
        ensure_ascii=False,
    )
    assert "儿子" in from_mother

    from_son = json.dumps(
        _game_path_messages("Victor", "你妈妈还好吗？"),
        ensure_ascii=False,
    )
    assert "妈妈" in from_son
