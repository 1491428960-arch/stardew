"""`models` 的文本规范化与 `ApiModel` 契约。

`models.py` 是 Bridge 的入参契约层（604 行 Pydantic 模型），但原有测试基本只经由 provider
间接用它；三个模块级校验函数此前**没有任何直接测试**，而它们的语义**各不相同**——
一个空值抛错、一个允许空、一个只动键不动值——这正是最容易在改动中悄悄走样的地方。
"""

from __future__ import annotations

import pytest
from pydantic import Field, ValidationError

from stardew_ai_bridge.models import (
    ApiModel,
    ItemConversationContext,
    NpcContext,
    RelationshipWorldContext,
    _strip_dialogue_message,
    _strip_mapping_keys,
    _strip_text,
)


# --- _strip_text ------------------------------------------------------------


def test_strip_text_trims_but_keeps_inner_spacing() -> None:
    assert _strip_text("  谢恩  ") == "谢恩"
    assert _strip_text("a  b") == "a  b"  # 内部空白不动


@pytest.mark.parametrize("value", ["", "   ", "\n\t "])
def test_strip_text_rejects_blank_strings(value: str) -> None:
    with pytest.raises(ValueError, match="文本不能为空"):
        _strip_text(value)


@pytest.mark.parametrize("value", [123, None, ["x"], {"k": "v"}])
def test_strip_text_passes_non_strings_through(value: object) -> None:
    # 非字符串交给 pydantic 的类型校验去处理，这里不替它做决定。
    assert _strip_text(value) is value


# --- _strip_dialogue_message -----------------------------------------------


def test_strip_dialogue_message_trims_but_allows_empty() -> None:
    # 与 `_strip_text` 的关键区别：空消息**不抛错**（topic 意图下允许空），
    # 是否拒绝交给模型级校验。
    assert _strip_dialogue_message("  你好  ") == "你好"
    assert _strip_dialogue_message("") == ""
    assert _strip_dialogue_message("   ") == ""


def test_strip_dialogue_message_passes_non_strings_through() -> None:
    assert _strip_dialogue_message(None) is None
    assert _strip_dialogue_message(7) == 7


# --- _strip_mapping_keys ---------------------------------------------------


def test_strip_mapping_keys_trims_string_keys_and_keeps_values() -> None:
    result = _strip_mapping_keys({"  a  ": 1, "b": {"nested": True}})

    assert result == {"a": 1, "b": {"nested": True}}


def test_strip_mapping_keys_keeps_non_string_keys() -> None:
    result = _strip_mapping_keys({1: "x", "  k  ": "y"})

    assert result == {1: "x", "k": "y"}


def test_strip_mapping_keys_passes_non_mappings_through() -> None:
    assert _strip_mapping_keys(["a"]) == ["a"]
    assert _strip_mapping_keys(None) is None


# --- ApiModel 契约 ---------------------------------------------------------


class _Probe(ApiModel):
    # 注意：`populate_by_name` 只在**字段确实定义了别名**时才让字段名也能用，
    # 并不会凭空接受任意 camelCase 写法（那会被 extra="forbid" 拒掉）。
    npc_id: str = Field(default="x", alias="npcId")


def test_api_model_forbids_extra_fields() -> None:
    # extra="forbid"：拼错字段名会当场报错，而不是被静默忽略。
    with pytest.raises(ValidationError):
        _Probe(npcId="x", unexpected=1)


def test_api_model_accepts_both_field_name_and_alias() -> None:
    assert _Probe(npcId="x").npc_id == "x"
    assert _Probe(npc_id="x").npc_id == "x"


# --- 具体模型的边界 --------------------------------------------------------


def test_npc_context_requires_a_non_empty_npc_id() -> None:
    assert NpcContext(npcId="Shane").npc_id == "Shane"

    with pytest.raises(ValidationError):
        NpcContext(npcId="")


def _item_context(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "itemId": "Minerals-1",
        "displayName": "紫水晶",
        "category": "Mineral",
        "quality": 0,
        "action": "display",
        "giftTaste": 0,
    }
    payload.update(overrides)
    return payload


def test_item_context_accepts_the_documented_values() -> None:
    context = ItemConversationContext(**_item_context())

    assert context.item_id == "Minerals-1"
    assert context.action == "display"
    assert context.consumes_item is False  # 展示默认不消耗


@pytest.mark.parametrize("quality", [-1, 5])
def test_item_context_rejects_quality_outside_zero_to_four(quality: int) -> None:
    with pytest.raises(ValidationError):
        ItemConversationContext(**_item_context(quality=quality))


@pytest.mark.parametrize("taste", [-11, 11])
def test_item_context_rejects_gift_taste_outside_the_documented_range(taste: int) -> None:
    with pytest.raises(ValidationError):
        ItemConversationContext(**_item_context(giftTaste=taste))


def test_item_context_rejects_an_unknown_action() -> None:
    # action 是 Literal：原版物品交互之外的写法一律拒绝。
    with pytest.raises(ValidationError):
        ItemConversationContext(**_item_context(action="eat"))


# --- relationshipWorld 的跨侧形状折叠 ---------------------------------------
#
# 2026-10-06 实机事故：游戏里每次对话都回「暂时联系不上她」
# （`ChatInputMenu.cs` 的 fallback 文案），根因是 Bridge 返回 **HTTP 422**——
# 游戏端发的关系世界快照里有 `RelationshipFact`／`RelationshipView` 不认识的
# 槽位，而 `ApiModel` 是 `extra="forbid"`。折叠点此前只 pop 了 fromNpcId／
# toNpcId，其余字段原样透传。
#
# 下面两个 helper 刻意照抄游戏端**真实发出的形状**（取自实机抓到的请求体），
# 而不是构造一个「刚好合法」的理想形状——上一版测试正是因此漏掉了它。


def _csharp_edge(**overrides: object) -> dict[str, object]:
    """游戏端 `objectiveRelationships` 实际发出的**有向边**。"""

    payload: dict[str, object] = {
        "fromNpcId": "player",
        "toNpcId": "Alex",
        "relationType": "married",
        "strength": 0,
        "tension": 0,
        "source": "player_spouse",
        "canonical": True,
        "updatedOn": "spring 28",
        "startedOn": "spring 28",
        "publicEventId": "wedding:Alex",
        "publicOn": "spring 28",
    }
    payload.update(overrides)
    return payload


def _csharp_view(**overrides: object) -> dict[str, object]:
    """游戏端 `views` 实际发出的**单条视图**（注意 counterpartNpcId）。"""

    payload: dict[str, object] = {
        "ownerNpcId": "Alex",
        "subjectNpcId": "Olivia",
        "counterpartNpcId": "player",
        "relationType": "married",
        "visibility": "known",
        "source": "wedding",
        "observedOn": "spring 28",
        "evidence": "wedding:Olivia",
    }
    payload.update(overrides)
    return payload


def test_relationship_world_accepts_the_full_csharp_edge_shape() -> None:
    world = RelationshipWorldContext(
        objectiveRelationships=[_csharp_edge()],
        views=[_csharp_view()],
    )

    assert world.objective_relationships[0].npc_id == "Alex"
    # 另一端必须保留：它是「和谁结的婚」的唯一来源（见 2026-10-04 的落实注释）。
    assert world.objective_relationships[0].counterpart_npc_id == "player"
    assert world.objective_relationships[0].public_event_id == "wedding:Alex"


def test_relationship_world_drops_edge_only_keys_instead_of_raising() -> None:
    """裁剪是**静默丢弃**，不是报错：游戏端多余的游戏内字段不该毁掉一次对话。"""

    world = RelationshipWorldContext(objectiveRelationships=[_csharp_edge(strength=7)])
    dumped = world.objective_relationships[0].model_dump(by_alias=True)

    assert dumped == {
        "npcId": "Alex",
        "relationType": "married",
        "counterpartNpcId": "player",
        "startedOn": "spring 28",
        "publicEventId": "wedding:Alex",
        "publicOn": "spring 28",
    }


def test_relationship_world_accepts_a_view_carrying_counterpart_npc_id() -> None:
    """只要关系世界里存在**一条** view，旧代码就必然 422。"""

    world = RelationshipWorldContext(views=[_csharp_view()])
    dumped = world.views[0].model_dump(by_alias=True)

    assert "counterpartNpcId" not in dumped
    assert dumped["ownerNpcId"] == "Alex"
    assert dumped["subjectNpcId"] == "Olivia"
    assert dumped["visibility"] == "known"


def test_relationship_world_still_rejects_unknown_top_level_keys() -> None:
    """白名单只作用于**嵌套条目**；`extra="forbid"` 对顶层依然生效，
    否则跨侧契约漂移会被整体掩盖。"""

    with pytest.raises(ValidationError):
        RelationshipWorldContext(unexpectedTopLevel={})
