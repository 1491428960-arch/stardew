"""隐性知识的**跨语言契约**（2026-10-04）。

需求原话：「群聊记忆中别的 npc 说了什么能不能作为一个隐性的知识库这样的形式，
**我不主动提到就不唤醒**」。

`test_latent_knowledge_card.py` 已经证明卡片渲染成立，但那只覆盖了
`prompts.py` 这一半。**请求模型是另一道门**：`ApiModel` 是 `extra="forbid"`，
游戏端发了 `latentKnowledge` 而这里没有对应字段 ⇒ **422 ⇒ 整轮对话退化成兜底**
（静默降级，玩家看到的是「暂时联系不上她」）。

所以本文件钉的是**契约两侧对齐**：
- 游戏端真的会发这个键（`BridgeClient.BridgeDialogueRequest.LatentKnowledge`）
- Bridge 侧真的收得下这个键（`DialogueRequest.latent_knowledge`）
- 而且是**显式加进请求模型的**，不是靠 `extra="ignore"` 混过去
"""

from __future__ import annotations

import json

import pytest

from stardew_ai_bridge.models import DialogueTestRequest as DialogueRequest


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "npcId": "Sophia",
        "message": "你最近在忙什么？",
        "intent": "chat",
        "compactPrompt": True,
        "channel": "face_to_face",
    }
    base.update(overrides)
    return base


def test_latent_knowledge_is_accepted_from_the_game_client() -> None:
    """游戏端发的 `latentKnowledge` 必须被接受，而不是 422。"""
    request = DialogueRequest.model_validate(
        _payload(latentKnowledge=["听说 Abigail 说：我倒是想练练剑。"])
    )

    assert request.latent_knowledge == ["听说 Abigail 说：我倒是想练练剑。"]


def test_latent_knowledge_defaults_to_empty_when_absent() -> None:
    """没带这个键时是空列表，不是 None——下游会直接迭代它。"""
    request = DialogueRequest.model_validate(_payload())

    assert request.latent_knowledge == []


def test_latent_knowledge_is_not_silently_swallowed() -> None:
    """证明它是**显式字段**，而不是靠 `extra` 放宽混进来的。

    判据：一个真正不存在的键仍然必须被拒。若这条测试开始通过
    （即未知键被接受了），说明 `extra="forbid"` 被改松了——
    那会让所有拼错的字段名都静默失效，是更危险的失效形态。
    """
    with pytest.raises(Exception):
        DialogueRequest.model_validate(_payload(noSuchFieldAtAll="x"))


def test_latent_knowledge_never_leaks_into_recent_facts_card() -> None:
    """两个字段在 prompt 层必须走两条路。

    `recent_facts` 那张卡带的是「把记忆自然用起来」的指令（会主动提），
    隐性知识的要求是「不主动提就不唤醒」。混在一起就是两套打架的约束，
    而项目实测过**「取最宽」**——同类约束有多个实例时跟最松的那个。
    """
    request = DialogueRequest.model_validate(
        _payload(
            recentFacts=["玩家送过我一条项链。"],
            latentKnowledge=["听说 Abigail 说：我倒是想练练剑。"],
        )
    )

    assert request.recent_facts == ["玩家送过我一条项链。"]
    assert request.latent_knowledge == ["听说 Abigail 说：我倒是想练练剑。"]
    # 物理上就是两个独立字段，不存在「并进 recentFacts」的可能。
    assert "练练剑" not in json.dumps(request.recent_facts, ensure_ascii=False)


def test_latent_knowledge_has_a_cap() -> None:
    """要有上限：群聊攒久了隐性知识会线性增长并挤占 prompt。"""
    with pytest.raises(Exception):
        DialogueRequest.model_validate(
            _payload(latentKnowledge=[f"第 {index} 句话" for index in range(200)])
        )


def test_group_request_does_not_carry_latent_knowledge() -> None:
    """群聊请求不该有隐性知识这条路。

    隐性知识是**私聊**的召回机制（她私下想起听谁说过什么）。群聊当场就听得见，
    再塞一遍等于让模型以为自己早已知情，反而会说出「我听 Abigail 说过」
    这种在当场很怪的话。这条测试把「群聊侧不存在该字段」钉住，
    防止后来者顺手加过去。
    """
    from stardew_ai_bridge.models import GroupDialogueRequest

    assert "latent_knowledge" not in GroupDialogueRequest.model_fields