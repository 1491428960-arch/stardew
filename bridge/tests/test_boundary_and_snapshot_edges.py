"""两个判定函数的补测：关系边界是否被处理、C# 单对象快照的归一化。

用**缺失行数排序**（而非缺失比例）挑出来的——绝对行数多意味着影响面大。
这两个函数都不长，却各自缺失一半以上。

- `guard.should_retry_for_relationship_boundary`（缺 7/12）：语义是“**判断关系边界是否被
  回复处理，避免用浪漫重试覆盖明确收口**”。判错的代价是双向的：该重试的不重试
  （玩家说“我先睡了”却被敷衍过去），或把已经好好收口的回复再推一次浪漫表达。
- `models.RelationshipWorldContext._normalize_csharp_snapshot_shape`（缺 7/20）：
  游戏端按**当前 NPC** 发单对象快照（`mediation`／`jealousy`），Bridge 侧统一成
  **按 NPC 索引的 map**。转换条件写得很谨慎——值不是 Mapping、或没有有效 `npcId` 时
  原样放回，绝不弄丢数据。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.guard import should_retry_for_relationship_boundary
from stardew_ai_bridge.models import RelationshipWorldContext

_normalize = RelationshipWorldContext._normalize_csharp_snapshot_shape

# 一个确定的“玩家在收口”输入与一个确定的“回复也在收口”文本
_CLOSING_INPUT = "我先睡了，晚安"
_CLOSING_REPLY = "晚安，明天再聊。"


# --- 关系边界判定 -----------------------------------------------------------


@pytest.mark.parametrize(
    ("npc_id", "player_input"),
    [
        ("", _CLOSING_INPUT),  # 没有 NPC
        ("   ", _CLOSING_INPUT),
        ("Shane", 42),  # 玩家输入不是字符串
        ("Shane", None),
        ("Shane", "今天天气不错"),  # 玩家没有要收口
        ("Shane", ""),
    ],
)
def test_no_retry_when_the_input_is_not_a_closing(npc_id: object, player_input: object) -> None:
    assert should_retry_for_relationship_boundary(npc_id, player_input, "好的") is False


@pytest.mark.parametrize("reply", ["", "   ", None, 42])
def test_a_closing_input_with_an_empty_reply_should_be_retried(reply: object) -> None:
    # 玩家明确要收口，而回复是空的——这时候必须重试。
    assert should_retry_for_relationship_boundary("Shane", _CLOSING_INPUT, reply) is True


def test_a_closing_reply_is_not_retried_over() -> None:
    # 回复本身已经好好收口了，不该再推一次浪漫表达。
    assert should_retry_for_relationship_boundary("Shane", _CLOSING_INPUT, _CLOSING_REPLY) is False


@pytest.mark.parametrize("marker", ["明天再聊", "下次见", "先睡吧"])
def test_every_closing_reply_marker_disables_the_retry(marker: str) -> None:
    assert (
        should_retry_for_relationship_boundary("Shane", _CLOSING_INPUT, f"好，{marker}。")
        is False
    )


@pytest.mark.parametrize("marker", ["想一个人待", "需要空间", "不想见人"])
def test_a_guarded_boundary_reply_also_disables_the_retry(marker: str) -> None:
    # 回复承认了对方需要空间，同样属于“已处理边界”。
    assert (
        should_retry_for_relationship_boundary("Shane", _CLOSING_INPUT, f"我懂，{marker}。")
        is False
    )


def test_an_ordinary_reply_after_a_closing_input_is_retried() -> None:
    # 玩家说要睡了，回复却只是敷衍——边界没被处理，应当重试。
    assert (
        should_retry_for_relationship_boundary("Shane", _CLOSING_INPUT, "好的，那你早点休息。")
        is True
    )


@pytest.mark.parametrize("closing", ["不打扰你了", "我先走了", "改天再聊", "心情很差"])
def test_several_closing_phrasings_are_recognised(closing: str) -> None:
    assert should_retry_for_relationship_boundary("Shane", closing, "哦。") is True


# --- C# 单对象快照的归一化 --------------------------------------------------


@pytest.mark.parametrize("value", ["x", None, 42, ["a"]])
def test_non_mappings_are_returned_untouched(value: object) -> None:
    assert _normalize(value) == value


def test_mappings_without_the_singular_keys_are_untouched() -> None:
    payload = {"views": [], "acceptanceByNpc": {}}

    assert _normalize(payload) == payload


def test_a_none_singular_key_is_dropped() -> None:
    # 明文写了 None 等于“这一项没有”，键不该留在结果里。
    assert _normalize({"mediation": None, "views": []}) == {"views": []}


@pytest.mark.parametrize("bad", ["raw", 42, ["a"]])
def test_a_non_mapping_snapshot_is_put_back_as_is(bad: object) -> None:
    # 结构意外时保持原样，交给后面的字段校验去报错，而不是在这里吞掉。
    assert _normalize({"mediation": bad}) == {"mediation": bad}


@pytest.mark.parametrize("npc_id", [None, "", "   ", 42])
def test_a_snapshot_without_a_usable_npc_id_is_put_back_as_is(npc_id: object) -> None:
    snapshot = {"npcId": npc_id, "status": "active"}

    assert _normalize({"mediation": snapshot}) == {"mediation": snapshot}


def test_a_valid_snapshot_becomes_a_by_npc_map() -> None:
    normalized = _normalize({"mediation": {"npcId": " Shane ", "status": "active"}})

    # npcId 被 strip 后作为外层键，内层不再保留 npcId
    assert normalized == {"mediationByNpc": {"Shane": {"status": "active"}}}


def test_both_singular_keys_are_normalised() -> None:
    normalized = _normalize(
        {
            "mediation": {"npcId": "Shane", "status": "active"},
            "jealousy": {"npcId": "Emily", "level": 2},
        }
    )

    assert normalized == {
        "mediationByNpc": {"Shane": {"status": "active"}},
        "jealousyByNpc": {"Emily": {"level": 2}},
    }


def test_an_existing_plural_key_is_not_overwritten() -> None:
    # 已经有 map 时以它为准——游戏端偶尔两种形态同时出现。
    normalized = _normalize(
        {"mediation": {"npcId": "Shane", "status": "active"}, "mediationByNpc": {"keep": 1}}
    )

    assert normalized == {"mediationByNpc": {"keep": 1}}


def test_the_input_mapping_is_not_mutated() -> None:
    payload = {"mediation": {"npcId": "Shane", "status": "active"}}
    snapshot = dict(payload)

    _normalize(payload)

    assert payload == snapshot
