"""紧凑 prompt 的记忆恢复与渠道标注（§3 / §4）。

背景见 `docs/diagnosis-compact-scene-hard-facts-2026-09-21.md`：

* **§3**：`recentFacts` 与 `gameState` 挤在同一个 `if not runtime_compact:` 门控里，
  于是游戏端（`smapi/BridgeClient.CompactPrompt` 默认 true）**从来没有跨会话记忆**进 prompt
  ——而这套记忆刚经过 `select_memory_facts` 的长度/去重/排序筛选，等于白做。
  现在紧凑分支单独渲染一张 `recent_memory` 卡，且**只留记忆行**：
  `scene` 卡已给出当前状态，`时间从“1830”变为“1840”` 这类差异行成了纯冗余。
* **§4**：紧凑路径此前唯一的渠道信息是 `post_history_voice_guard.channel` 里
  一个没有解释的英文 token（`"face_to_face"`）。`scene` 卡补一个 `场合` 结论。

**群聊路径**：`smapi/GroupDialogueMenu.cs:349` 群聊请求硬编码 `Array.Empty<string>()`，
所以线上群聊的 `recentFacts` 恒为空；且群聊走 `group_conversation.build_group_messages`
自己的渲染路径（`group_scene` 卡），不经过 `PromptBuilder.build`，
因此本文件的 `recent_memory` / `scene` 两张卡**都不适用于群聊**。
群聊补记忆是独立议题（需先改 C# 侧填充），未在本次范围内。
"""

from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.prompts import (
    ContextBuilder,
    PromptBuilder,
    is_state_delta_fact,
    select_compact_memory_facts,
    select_memory_facts,
)


NPCS_DIR = Path(__file__).parents[2] / "data" / "personas"

MESSAGE = "早上好，今天怎么样？"

# 状态差异行的 11 个 label（`smapi/BridgeClient.cs:999-1009` + `AddEventChanges`）。
STATE_DELTA_LABELS = (
    "季节", "日期", "天气", "地点", "时间", "好感",
    "心级", "关系", "婚姻状态", "孩子数量", "剧情事件",
)

# 贴近线上实际产出：4 条状态差异 + 2 条记忆。
MIXED_FACTS = [
    "时间从“1830”变为“1840”",
    "地点从“SeedShop”变为“Town”",
    "好感从“128”变为“140”",
    "剧情事件从“无”变为“spring_14”",
    "记忆（14）：玩家说：“早上好，今天诊所忙吗？”；NPC回应：“还好，上午只有两位预约。”",
    "玩家说：“昨天在矿洞待久了，腰有点酸。”；NPC回应：“下次别一个人下去。”",
]

MEMORY_ONLY = MIXED_FACTS[4:]


def _payload(
    *,
    facts: list[str] | None = None,
    channel: str | None = "face_to_face",
    compact: bool = True,
) -> dict[str, object]:
    body: dict[str, object] = {
        "npcId": "Harvey",
        "message": MESSAGE,
        "intent": "chat",
        "provider": "fake",
        "compactPrompt": compact,
        "sourceMods": [],
        "recentFacts": list(MIXED_FACTS if facts is None else facts),
        "history": [],
        "gameState": {
            "npcId": "Harvey",
            "displayName": "Harvey",
            "location": "Hospital",
            "season": "spring",
            "date": "25",
            "weather": "clear",
            "time": 600,
            "friendship": 1500,
            "friendshipHearts": 6,
            "relationship": "friend",
        },
    }
    if channel is not None:
        body["channel"] = channel
    return body


def _build(**kwargs: object) -> list[dict[str, str]]:
    from stardew_ai_bridge.app import _build_context

    _, prompt = _build_context(_payload(**kwargs))  # type: ignore[arg-type]
    return prompt


def _card(prompt: list[dict[str, str]], name: str) -> object:
    found = next((m for m in prompt if m.get("name") == name), None)
    return json.loads(found["content"]) if found else None


# --- §3 单元：状态差异行识别 --------------------------------------------------


def test_state_delta_detection_covers_all_eleven_labels() -> None:
    for label in STATE_DELTA_LABELS:
        assert is_state_delta_fact(f"{label}从“旧”变为“新”"), f"{label} 未被识别"


def test_state_delta_detection_requires_whole_line_match() -> None:
    """必须锚定整行，否则玩家原话里的相同措辞会被误杀。"""

    assert not is_state_delta_fact("记忆（14）：时间从“1”变为“2”")
    assert not is_state_delta_fact("玩家说：“时间从“1”变为“2””；NPC回应：“嗯。”")
    assert not is_state_delta_fact("我记得时间从“1”变为“2”")
    assert not is_state_delta_fact("时间从“1”变为“2”，对吧")


def test_state_delta_detection_ignores_ordinary_memory_text() -> None:
    for fact in (
        "记忆（14）：玩家说：“早上好”；NPC回应：“你来得正好。”",
        "玩家答应明天帮哈维送药",
        "哈维提到肩膀最近发僵",
    ):
        assert not is_state_delta_fact(fact)


def test_select_compact_memory_facts_keeps_memory_and_order() -> None:
    assert select_compact_memory_facts(MIXED_FACTS) == MEMORY_ONLY
    # 全是记忆时原样返回，不重排、不去重（那是 select_memory_facts 的职责）
    assert select_compact_memory_facts(MEMORY_ONLY) == MEMORY_ONLY
    assert select_compact_memory_facts([]) == []


# --- §3 端到端：记忆确实进 prompt --------------------------------------------


def test_compact_prompt_restores_cross_session_memory() -> None:
    prompt = _build()

    memory = _card(prompt, "recent_memory")
    assert memory is not None, "紧凑路径必须带上跨会话记忆"
    assert memory["近期记忆"] == MEMORY_ONLY


def test_compact_prompt_drops_redundant_state_delta_facts() -> None:
    """状态差异行的当前值已在 `scene` 卡里，再带一遍是纯冗余。"""

    prompt = _build()
    blob = json.dumps(prompt, ensure_ascii=False)

    for fact in MIXED_FACTS[:4]:
        assert fact not in blob, f"状态差异行不该进 prompt：{fact}"
    assert "变为" not in json.dumps(_card(prompt, "recent_memory"), ensure_ascii=False)


def test_compact_memory_card_matches_select_memory_facts_pipeline() -> None:
    """卡内容必须等于 `select_memory_facts` 的产物再剔掉状态差异行。

    这条是防止有人绕过那套筛选（长度/去重/排序）直接塞原文——
    绕过去的话，`select_memory_facts` 就又白做了一次。
    """

    context = ContextBuilder(None).build(_payload())  # type: ignore[arg-type]
    expected = select_compact_memory_facts(context["recentFacts"])

    prompt = PromptBuilder().build(
        {**context, "_runtime_compact": True}, MESSAGE, compact=True
    )

    assert _card(prompt, "recent_memory")["近期记忆"] == expected


def test_compact_memory_card_keeps_select_memory_facts_deduplication() -> None:
    """重复行应由 `select_memory_facts` 去掉，紧凑路径不重新引入。"""

    duplicated = MEMORY_ONLY + [MEMORY_ONLY[0]]

    prompt = _build(facts=duplicated)

    assert _card(prompt, "recent_memory")["近期记忆"] == MEMORY_ONLY


def test_compact_prompt_omits_memory_card_when_there_is_no_memory() -> None:
    """纯状态差异（首次对话常见）或空记忆时不该产空卡。"""

    for facts in ([], MIXED_FACTS[:4]):
        prompt = _build(facts=facts)
        assert _card(prompt, "recent_memory") is None, f"facts={facts} 不该产卡"


def test_offline_compact_path_has_no_recent_memory_card() -> None:
    """评测路径（`compact` 真但无 `_runtime_compact`）仍走完整 `game_state` 卡。"""

    prompt = _build(compact=False)
    names = [m.get("name") for m in prompt]

    assert "recent_memory" not in names
    game_state = _card(prompt, "game_state")
    assert game_state["recentFacts"]  # 完整卡里记忆照旧


# --- §4 渠道标注 --------------------------------------------------------------


def test_compact_scene_card_labels_face_to_face_channel() -> None:
    assert _card(_build(channel="face_to_face"), "scene")["场合"] == "当面"


def test_compact_scene_card_labels_remote_channel() -> None:
    """渠道取值必须随请求变化，不能恒为「当面」。"""

    remote = _card(_build(channel="remote"), "scene")
    face_to_face = _card(_build(channel="face_to_face"), "scene")

    assert remote["场合"] == "远程"
    assert face_to_face["场合"] == "当面"
    assert remote["场合"] != face_to_face["场合"]


def test_compact_scene_card_omits_channel_when_request_has_none() -> None:
    """没传渠道就不硬塞，避免凭空断言「当面」。"""

    scene = _card(_build(channel=None), "scene")

    assert "场合" not in scene
    assert scene["地点"] == "Hospital"  # 其余场景字段不受影响


def test_channel_labels_stay_in_sync_with_channel_instructions() -> None:
    """`场合` 的短标签与 `channelInstruction` 的长文案必须覆盖同一组渠道。"""

    from stardew_ai_bridge.prompts import _CHANNEL_INSTRUCTIONS, _CHANNEL_LABELS

    assert set(_CHANNEL_LABELS) == set(_CHANNEL_INSTRUCTIONS)
