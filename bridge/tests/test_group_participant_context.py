"""群聊「每人一份」私有上下文：协议层与渲染层回归。

背景（2026-09-22 的判据，2026-10-05 的改法）：`group_scene` 卡里的
`recentFacts` / `relationshipWorld` 原本是**无归属的单槽位**，多人场里取谁的
都是把别人的私事摊给全场看（「把 Alex 的关系网塞给 Shane」），所以生产端一直
传 null。改法是把槽位下移到参与者身上，并由 Bridge 侧渲染成**带归属的卡**
（卡名带 npcId + 卡内声明「只属于他」），与参与者角色卡同构。
"""

from __future__ import annotations

import json

from stardew_ai_bridge.group_conversation import build_group_messages
from stardew_ai_bridge.models import GroupDialogueRequest


def _payload() -> dict[str, object]:
    return {
        "message": "你们谁更喜欢夜市？",
        "strategy": "multi_turn",
        "channel": "remote",
        "participants": [
            {"npcId": "Abigail"},
            {"npcId": "Emily"},
        ],
    }


def _messages(participants: list[dict[str, object]]) -> list[dict[str, str]]:
    return build_group_messages(
        participants=participants,
        active_npc_id="Abigail",
        participant_prompts={
            "abigail": [{"role": "system", "content": "A 卡", "name": "persona_core"}],
            "emily": [{"role": "system", "content": "E 卡", "name": "persona_core"}],
        },
        strategy="multi_turn",
        player_message="你们谁更喜欢夜市？",
    )


def _context_blocks(messages: list[dict[str, str]]) -> list[dict[str, object]]:
    return [
        json.loads(item["content"])
        for item in messages
        if item.get("name", "").startswith("participant_private_context")
    ]


# --------------------------------------------------------------------------
# 协议层：字段必须真的被模型接受（ApiModel 是 extra="forbid"，漏加就 422）
# --------------------------------------------------------------------------


def test_group_participant_carries_its_own_recent_facts() -> None:
    payload = _payload()
    payload["participants"][0]["recentFacts"] = ["玩家上周说要去矿洞"]
    payload["participants"][1]["recentFacts"] = ["玩家说过想换把好锄头"]

    request = GroupDialogueRequest.model_validate(payload)

    assert request.participants[0].recent_facts == ["玩家上周说要去矿洞"]
    assert request.participants[1].recent_facts == ["玩家说过想换把好锄头"]


def test_group_participant_carries_its_own_relationship_world() -> None:
    payload = _payload()
    payload["participants"][0]["relationshipWorld"] = {
        "acceptanceByNpc": {"Abigail": "accepted"},
    }

    request = GroupDialogueRequest.model_validate(payload)

    assert request.participants[0].relationship_world is not None
    assert request.participants[0].relationship_world.acceptance_by_npc == {
        "Abigail": "accepted"
    }
    # 未给的那位保持空，绝不串用别人的那一份。
    assert request.participants[1].relationship_world is None
    assert request.participants[1].recent_facts == []


# --------------------------------------------------------------------------
# 渲染层：带归属的卡
# --------------------------------------------------------------------------


def test_each_participant_gets_its_own_private_context_block() -> None:
    messages = _messages(
        [
            {
                "npcId": "Abigail",
                "displayName": "Abigail",
                "recentFacts": ["玩家上周说要去矿洞"],
            },
            {
                "npcId": "Emily",
                "displayName": "Emily",
                "recentFacts": ["玩家说过想换把好锄头"],
            },
        ]
    )

    blocks = _context_blocks(messages)
    by_npc = {item["npcId"]: item for item in blocks}

    assert by_npc["Abigail"]["recentFacts"] == ["玩家上周说要去矿洞"]
    assert by_npc["Emily"]["recentFacts"] == ["玩家说过想换把好锄头"]
    # 归属化：块名带上 npcId，且块内声明只属于本人。
    assert any(
        item.get("name") == "participant_private_context_Abigail"
        for item in messages
    )
    assert "只属于" in str(by_npc["Abigail"]["scope"])
    assert "不要让名单里的其他人" in str(by_npc["Abigail"]["scope"])


def test_participant_without_private_context_gets_no_block() -> None:
    messages = _messages([{"npcId": "Abigail"}, {"npcId": "Emily"}])

    assert _context_blocks(messages) == []


def test_private_context_block_precedes_its_owner_card() -> None:
    """归属链必须连续：边界卡 → 本人私有上下文 → 本人角色卡。"""

    messages = _messages(
        [
            {"npcId": "Abigail", "recentFacts": ["玩家上周说要去矿洞"]},
            {"npcId": "Emily"},
        ]
    )
    names = [item.get("name", "") for item in messages]

    boundary_at = names.index("participant_card_boundary")
    context_at = next(
        index
        for index, name in enumerate(names)
        if name.startswith("participant_private_context")
    )
    card_at = names.index("persona_core")

    assert boundary_at < context_at < card_at


# --------------------------------------------------------------------------
# 穿透：请求 JSON → 模型校验 → 群聊卡。
# 项目纪律（STATE §四 #10）：字段在传输途中被悄悄吞掉时，两个套件都可能全绿，
# 所以必须有一条打通全链的测试。
# --------------------------------------------------------------------------


def test_private_context_survives_the_full_request_path() -> None:
    request = GroupDialogueRequest.model_validate(
        {
            "message": "你们谁更喜欢夜市？",
            "strategy": "multi_turn",
            "channel": "remote",
            "participants": [
                {
                    "npcId": "Abigail",
                    "displayName": "Abigail",
                    "recentFacts": ["玩家上周说要去矿洞"],
                    "relationshipWorld": {"acceptanceByNpc": {"Abigail": "accepted"}},
                },
                {"npcId": "Emily", "displayName": "Emily"},
            ],
        }
    )

    messages = build_group_messages(
        participants=request.participants,
        active_npc_id="Abigail",
        participant_prompts={},
        strategy="multi_turn",
        player_message=request.message,
    )

    contexts = _context_blocks(messages)

    assert len(contexts) == 1, "只有带了私有上下文的那位才该有卡"
    assert contexts[0]["npcId"] == "Abigail"
    assert contexts[0]["recentFacts"] == ["玩家上周说要去矿洞"]
    assert contexts[0]["relationshipWorld"] == {
        "acceptanceByNpc": {"Abigail": "accepted"}
    }
