"""泛寒暄下的行为样例兜底（2026-09-21）。

## 背景

39/44 角色的行为样例 topic 全是主题型（`farm_work` / `clinic_and_coffee` /
`music_practice` …），没有一条落在 `_PLAIN_BEHAVIOR_TOPICS` 里。而「你好」
「今天过得怎么样」这类泛寒暄恰好是玩家最常用的开场——实测这批角色在
游戏 chat 路径的行为样例注入数是 **0**（不是 1）。

## 三道门，缺一条都拿不到样例

1. **检索层** `ProfileIndexStore.behavior_examples`：`score == 0` 的样例直接丢弃，
   而泛寒暄与主题型关键词零重叠，得分必然是 0；
2. **选择层** `prompts._select_behavior_examples`：没有 plain 样例时原先 `return []`；
3. **渲染层** `PromptBuilder.build`（compact 分支）：泛日常会把非 plain 主题的样例
   再过滤一次。

本次三处都改成「降级到该角色第一条样例」。**具体话题仍必须命中**——非泛寒暄输入
走不到任何兜底分支；兜底也不绕过来源 Mod、关系阶段与渠道这三道门。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.profile_index import ProfileIndexStore

ROOT = Path(__file__).resolve().parents[2]
INDEX = (
    ROOT
    / "data"
    / "generated"
    / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)


def _example(
    *,
    topic: str = "farm_work",
    keywords: tuple[str, ...] = ("鸡舍",),
    player_input: str = "牧场需要帮手吗？",
    npc_id: str = "Marnie",
    stages: tuple[str, ...] | None = ("friend", "close"),
) -> dict[str, object]:
    """构造一条主题型样例。

    `playerInput` 刻意与「今天过得怎么样？」零重叠：`_behavior_topic_score` 会给
    连续共同短语（≥2 字）加分（每字 4 分），用「鸡舍那边怎么样？」这种写法会让
    样例拿到 8 分而**绕过**兜底路径，测的就不是本文件要钉的东西了。
    """

    item: dict[str, object] = {
        "exampleId": f"{npc_id}-{topic}",
        "npcId": npc_id,
        "sourceMods": ["vanilla"],
        "topic": topic,
        "topicKeywords": list(keywords),
        "playerInput": player_input,
        "npcReply": "今天鸡舍那边挺忙的，不过还行。",
        "sourceType": "handcrafted_example",
    }
    if stages is not None:
        item["relationshipStages"] = list(stages)
    return item


def _store(tmp_path: Path, examples: list[dict[str, object]]) -> ProfileIndexStore:
    path = tmp_path / "index.json"
    path.write_text(
        json.dumps(
            {"schemaVersion": 2, "behaviorExamples": examples},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ProfileIndexStore(path)


def _search(
    store: ProfileIndexStore,
    player_input: str,
    *,
    stage: str = "close",
    source_mods: tuple[str, ...] = ("vanilla",),
    channel: str = "face_to_face",
) -> list[dict[str, object]]:
    return store.behavior_examples(
        "Marnie",
        source_mods,
        relationship_stage=stage,
        channel=channel,
        player_input=player_input,
        limit=4,
    )


# --- 检索层 -----------------------------------------------------------------


def test_generic_small_talk_falls_back_to_a_themed_example(tmp_path: Path) -> None:
    """泛寒暄 + 样例全是主题型（得分 0）→ 仍然给一条。"""

    store = _store(tmp_path, [_example()])

    got = _search(store, "今天过得怎么样？")

    assert len(got) == 1
    assert got[0]["topic"] == "farm_work"


def test_the_fallback_keeps_the_first_example_in_index_order(tmp_path: Path) -> None:
    store = _store(
        tmp_path,
        [
            _example(topic="ranch_and_animals", keywords=("牧场", "动物")),
            _example(topic="family_boundaries", keywords=("家人", "边界")),
        ],
    )

    got = _search(store, "你好")

    assert [item["topic"] for item in got] == [
        "ranch_and_animals",
        "family_boundaries",
    ]


def test_a_specific_topic_that_does_not_match_still_yields_nothing(
    tmp_path: Path,
) -> None:
    """兜底只对泛寒暄生效：点名了对象却对不上，仍然不给样例。"""

    store = _store(tmp_path, [_example()])

    assert _search(store, "你最近在看什么书？") == []


def test_a_matching_example_wins_over_the_fallback(tmp_path: Path) -> None:
    store = _store(
        tmp_path,
        [
            _example(topic="ranch_and_animals", keywords=("牧场", "动物")),
            _example(
                topic="daily_status",
                keywords=("你好", "最近", "怎么样", "今天"),
                player_input="今天状态怎么样？",
            ),
        ],
    )

    got = _search(store, "今天过得怎么样？")

    # 兜底候选排在得分样例之后，且得分样例存在时根本不会被取用。
    assert [item["topic"] for item in got][0] == "daily_status"
    assert "ranch_and_animals" not in [item["topic"] for item in got]


def test_the_fallback_does_not_bypass_the_stage_gate(tmp_path: Path) -> None:
    """关系阶段不匹配时，兜底也拿不到样例——它只放开得分门，不放开别的门。"""

    store = _store(tmp_path, [_example(stages=("dating", "married"))])

    assert _search(store, "今天过得怎么样？", stage="close") == []


def test_the_fallback_does_not_bypass_the_source_gate(tmp_path: Path) -> None:
    example = _example()
    example["sourceMods"] = ["FlashShifter.StardewValleyExpandedCP"]
    store = _store(tmp_path, [example])

    assert _search(store, "今天过得怎么样？", source_mods=("vanilla",)) == []


def test_the_fallback_does_not_bypass_the_channel_gate(tmp_path: Path) -> None:
    example = _example()
    example["channels"] = ["remote"]
    store = _store(tmp_path, [example])

    assert _search(store, "今天过得怎么样？", channel="face_to_face") == []


def test_an_empty_player_input_is_unaffected(tmp_path: Path) -> None:
    """NPC 主动找话题时 `player_input` 为空，得分门本来就不生效。"""

    store = _store(tmp_path, [_example()])

    assert len(_search(store, "")) == 1


# --- 真实索引 ---------------------------------------------------------------


@pytest.mark.skipif(not INDEX.exists(), reason="派生索引未生成")
def test_real_index_roles_without_plain_samples_get_one_example() -> None:
    """报告里注入数为 0 的那批角色，泛寒暄下现在都拿到 1 条。"""

    store = ProfileIndexStore(INDEX)
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    profiles = payload["profiles"]

    names = (
        "Abigail",
        "Marnie",
        "Caroline",
        "Lewis",
        "Linus",
        "Evelyn",
        "Dwarf",
        "Gunther",
        "Marlon",
        "Willy",
    )
    missing: list[str] = []
    for npc_id in names:
        mods = list((profiles.get(npc_id) or {}).get("sourceMods") or [])
        got = store.behavior_examples(
            npc_id,
            mods,
            relationship_stage="close",
            channel="face_to_face",
            player_input="今天过得怎么样？",
            limit=4,
        )
        if not got:
            missing.append(npc_id)

    assert missing == []


@pytest.mark.skipif(not INDEX.exists(), reason="派生索引未生成")
def test_real_index_keeps_rejecting_a_specific_topic_that_does_not_match() -> None:
    """真实索引上的对照：泛寒暄有兜底，点名对象却对不上时仍然没有样例。"""

    store = ProfileIndexStore(INDEX)
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    profiles = payload["profiles"]
    mods = list((profiles.get("Marnie") or {}).get("sourceMods") or [])

    assert (
        store.behavior_examples(
            "Marnie",
            mods,
            relationship_stage="close",
            channel="face_to_face",
            player_input="红石矿脉的走向怎么判断？",
            limit=4,
        )
        == []
    )
