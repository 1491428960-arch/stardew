"""`stageProfiles.<stage>.topicPool` 曾被一个缩进缺陷整批丢掉（2026-09-21）。

## 缺陷

`prompts._compact_stage_profile` 里写的是：

    for key in ("topicPool", "boundaries"):
        items = _compact_text_list(value.get(key), limit=3, item_limit=80)
    if items:                      # ← 缩进在 for 外面
        result[key] = items

`if` 落在循环外，于是 `items` 只保留最后一次循环（`boundaries`）的值、
`key` 也泄漏成 `"boundaries"`——`topicPool` **永远写不进 `result`**。

## 影响面

44 角色 × 7 阶段 × 3 条 = **924 条话题池**从未进入 prompt。这批数据是
「这个角色在不同关系阶段能聊什么」的权威清单，也正是「话题单一」的正面解药：
索菲亚 close 档的「恐惧与期待」、parent 档的「如何保留个人空间」都与画无关。

本文件钉住压缩器的行为（两个键都要保留），并用真实人设 + 真实派生索引验证
索菲亚 close / parent 两档的话题池确实出现在 `persona_core` 里。
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
    _compact_stage_profile,
)

ROOT = Path(__file__).resolve().parents[2]
INDEX = (
    ROOT
    / "data"
    / "generated"
    / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)


# --- 压缩器本身 -------------------------------------------------------------


def test_topic_pool_and_boundaries_both_survive_compaction() -> None:
    compact = _compact_stage_profile(
        {
            "stage": "close",
            "topicPool": ["未来计划", "恐惧与期待", "共同经历"],
            "boundaries": ["不替对方承诺或下结论"],
        }
    )

    assert compact["topicPool"] == ["未来计划", "恐惧与期待", "共同经历"]
    assert compact["boundaries"] == ["不替对方承诺或下结论"]
    # 旧症状：`key` 泄漏成 "boundaries"，话题池被边界那一条顶掉。
    assert compact["topicPool"] != compact["boundaries"]


def test_the_topic_pool_is_capped_at_three_items() -> None:
    compact = _compact_stage_profile(
        {"stage": "friend", "topicPool": ["a", "b", "c", "d", "e"]}
    )

    assert compact["topicPool"] == ["a", "b", "c"]


def test_an_absent_topic_pool_does_not_create_the_key() -> None:
    compact = _compact_stage_profile({"stage": "close", "boundaries": ["尊重同意"]})

    assert "topicPool" not in compact
    assert compact["boundaries"] == ["尊重同意"]


def test_a_non_mapping_stage_profile_yields_nothing() -> None:
    assert _compact_stage_profile(None) == {}
    assert _compact_stage_profile("close") == {}


# --- 真实数据端到端 ---------------------------------------------------------


def _source_mods(npc_id: str) -> list[str]:
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    profile = payload["profiles"].get(npc_id) or {}
    return list(profile.get("sourceMods") or [])


def _hello_payload(npc_id: str, stage: str) -> dict[str, Any]:
    mods = _source_mods(npc_id)
    return {
        "npcId": npc_id,
        "message": "今天过得怎么样？",
        "provider": "fake",
        "displayName": npc_id,
        "sourceMods": mods,
        "history": [],
        "gameState": {
            "npcId": npc_id,
            "season": "spring",
            "date": "12",
            "weather": "clear",
            "time": 1010,
            "location": "Farm",
            "friendshipHearts": 10,
            "relationshipStage": stage,
            "relationship": "married" if stage in {"married", "parent"} else "friend",
            "marriageStatus": "married" if stage in {"married", "parent"} else "single",
            "childrenCount": 1 if stage == "parent" else 0,
            # 刻意**不传** completedEventIds：传空列表会启用事件锁，把 close 档
            # 降到 acquaintance，这里要验的是真实阶段那一档的话题池。
            "sourceMods": mods,
        },
        "intent": "chat",
        "compactPrompt": True,
        "channel": "face_to_face",
    }


def _stage_profile_of(npc_id: str, stage: str) -> dict[str, Any]:
    builder = ContextBuilder(PersonaStore(), ProfileIndexStore(INDEX))
    payload = _hello_payload(npc_id, stage)
    context = builder.build(payload)
    context["_runtime_compact"] = True
    messages = PromptBuilder().build(context, payload["message"], compact=True)
    core = json.loads(
        next(
            message["content"]
            for message in messages
            if message.get("name") == "persona_core"
        )
    )
    return core["npcIdentity"]["stageProfile"]


@pytest.mark.skipif(not INDEX.exists(), reason="派生索引未生成")
def test_sophia_topic_pool_reaches_persona_core() -> None:
    """修复前这里是 `topicPool=null`——924 条话题池一条都没进过 prompt。"""

    close_profile = _stage_profile_of("Sophia", "close")
    parent_profile = _stage_profile_of("Sophia", "parent")

    assert close_profile["stage"] == "close"
    assert close_profile["topicPool"] == ["未来计划", "恐惧与期待", "共同经历"]
    assert parent_profile["stage"] == "parent"
    assert parent_profile["topicPool"] == [
        "孩子与家庭",
        "安全的日常",
        "如何保留个人空间",
    ]
    # 这两条正是「总是谈画」的对症解药：与绘画、酿造都无关。
    assert "恐惧与期待" in close_profile["topicPool"]
    assert "如何保留个人空间" in parent_profile["topicPool"]
    # 边界没有被话题池顶掉（两个键同时存在）。
    assert close_profile["boundaries"]


@pytest.mark.skipif(not INDEX.exists(), reason="派生索引未生成")
def test_other_roles_topic_pools_are_restored_too() -> None:
    """横向抽查三个角色，确认恢复的不是索菲亚一个人的特例。"""

    wizard = _stage_profile_of("Wizard", "close")
    leah = _stage_profile_of("Leah", "close")
    birdie = _stage_profile_of("Birdie", "parent")

    assert wizard["topicPool"] == ["长期目标", "过去的选择", "共同承担的风险"]
    assert leah["topicPool"] == ["共同看作品", "自然与材料", "彼此如何提供支持"]
    assert birdie["topicPool"] == ["安全钓鱼", "简单手作", "家庭记忆"]
