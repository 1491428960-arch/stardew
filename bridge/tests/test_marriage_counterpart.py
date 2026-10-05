"""婚姻事实必须说清楚「和谁结的婚」，而不只是「某人已婚」。

2026-10-04 实机发现（用户原话：「维克托不知道他妈嫁给我了，这不对吧」）。

**根因不是数据缺失**：`data/npc-relations.json` 里 `Olivia → Victor 儿子` /
`Victor → Olivia 妈妈` 一直都在，`townRelations` 也确实投给了每一个角色
（实测 Victor 拿到的是 `Victor：Olivia妈妈、Sophia好朋友`）。

缺口在婚姻事实的**语义**上：`_public_marriage_views` 造出来的 view 是

    {"subjectNpcId": "Olivia", "relationType": "married", "visibility": "known"}

主语只有配偶一端。Victor 拿到它，配上自己的 `townRelations`，能推出的上限是
「我妈妈结婚了」——**推不出新郎就是正在跟他说话的玩家**。

修法（用户口径：「只知道事实，不预设亲属称呼」）：view 补一个
`counterpartNpcId`，承载婚姻的另一端（这里是 `player`）。不映射「继父 / 后爸」
这类亲属称呼，只把事实交出去，怎么看待由模型按角色自己发挥。
"""

from __future__ import annotations

from stardew_ai_bridge.relationship_world import project_relationship_context


def _world_with_public_wedding() -> dict[str, object]:
    return {
        "objectiveRelationships": [
            {
                "npcId": "Olivia",
                "relationType": "married",
                "publicEventId": "wedding:olivia",
                "publicOn": "Spring 12",
            },
        ],
        "views": [],
    }


def test_public_marriage_view_says_who_the_spouse_married() -> None:
    """婚姻 view 必须带上另一端，否则「已婚」是一句没有宾语的话。"""

    victor = project_relationship_context("Victor", _world_with_public_wedding())
    knowledge = {item["subjectNpcId"]: item for item in victor["knowledge"]}

    assert "Olivia" in knowledge, "公开婚礼应当让所有 NPC 都知道 Olivia 已婚"
    assert knowledge["Olivia"]["counterpartNpcId"] == "player"


def test_every_npc_sees_the_same_counterpart_not_their_own_id() -> None:
    """另一端是玩家，不是 viewer 自己——这正是原实现丢掉的那一半。"""

    for viewer in ("Victor", "Sophia", "Abigail"):
        context = project_relationship_context(viewer, _world_with_public_wedding())
        knowledge = {item["subjectNpcId"]: item for item in context["knowledge"]}
        assert knowledge["Olivia"]["counterpartNpcId"] == "player", viewer


def test_counterpart_survives_an_explicit_public_view() -> None:
    """C# 侧已经为每个 viewer 单独造过 view；补字段不能只在某一条分支生效。"""

    world = _world_with_public_wedding()
    world["views"] = [
        {
            "ownerNpcId": "Victor",
            "subjectNpcId": "Olivia",
            "relationType": "married",
            "visibility": "known",
            "source": "wedding",
            "evidence": "wedding:olivia",
            "counterpartNpcId": "player",
        },
    ]

    victor = project_relationship_context("Victor", world)
    knowledge = {item["subjectNpcId"]: item for item in victor["knowledge"]}
    assert knowledge["Olivia"]["counterpartNpcId"] == "player"


def test_private_dating_does_not_gain_a_counterpart() -> None:
    """只有公开婚礼才进 knowledge；私下恋爱不该被顺手补上 counterparts。"""

    world = {
        "objectiveRelationships": [
            {"npcId": "Sophia", "relationType": "dating"},
        ],
        "views": [],
    }

    victor = project_relationship_context("Victor", world)
    assert all(
        item.get("counterpartNpcId") is None for item in victor["knowledge"]
    ), "私下恋爱不应因为这次改动被提升为公开知识"