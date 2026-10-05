"""隐性知识**端到端穿透**（2026-10-04）。

前两个文件各自证明了一半：
- `test_latent_knowledge_contract.py` —— 请求模型收得下 `latentKnowledge`；
- `test_latent_knowledge_card.py` —— 给了数据就渲染得出卡片。

**两半都绿也推不出中间通着**。项目反复出现过的失效形态正是这个：
字段定义齐了、卡片渲染写好了，但请求进来的数据没被接到 prompt 构建上去，
于是线上永远是一张空卡、而且**没有任何报错**。

本文件从 `DialogueTestRequest` 出发，走真实的服务端路径（`NpcContext` →
`build`），断言卡片真的出现。它钉的是**接缝**，不是两端。
"""

from __future__ import annotations

from stardew_ai_bridge.models import DialogueTestRequest
from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder

_LATENT = "听说 Abigail 说：我倒是想练练剑。"


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "npcId": "Sophia",
        "message": "你最近在忙什么？",
        "intent": "chat",
        "provider": "fake",
    }
    payload.update(overrides)
    return payload


def _messages(**overrides: object) -> list[dict[str, object]]:
    """走项目真实的组装链：payload → ContextBuilder → PromptBuilder。

    ⚠ 必须经过 `ContextBuilder`：它才是把**请求字段**映射到 **prompt 上下文**
    的那一跳。直接拿 `NpcContext` 自己拼字典会绕过它，于是测出来的是
    「PromptBuilder 认不认这个键」，而不是「请求里的数据有没有走到 PromptBuilder」——
    后者才是线上会失效的地方。
    """
    payload = _payload(**overrides)
    # 先过一遍请求模型：契约层的失败要在这一步就炸，而不是悄悄少个字段。
    DialogueTestRequest.model_validate(payload)
    context = ContextBuilder().build(payload)
    return PromptBuilder().build(context, str(payload["message"]))


def _card_names(messages: list[dict[str, object]]) -> list[str]:
    return [
        str(message.get("name"))
        for message in messages
        if message.get("name")
    ]


def test_latent_knowledge_reaches_the_prompt_card() -> None:
    """请求里带了隐性知识 ⇒ prompt 里必须出现那张卡。

    这是本文件存在的唯一理由：证明中间那一跳没有断。
    """
    messages = _messages(latentKnowledge=[_LATENT])

    assert "latent_knowledge" in _card_names(messages), (
        "请求收下了 latentKnowledge，但 prompt 里没有 latent_knowledge 卡 —— "
        "数据断在 NpcContext → build 之间。"
    )

    card = next(
        message for message in messages if message.get("name") == "latent_knowledge"
    )
    assert "练练剑" in str(card.get("content"))


def test_no_request_field_means_no_card() -> None:
    """不带隐性知识时不出现空卡，也不报错。"""
    messages = _messages()

    assert "latent_knowledge" not in _card_names(messages)


def test_card_sits_before_the_closing_voice_cards() -> None:
    """位置是要紧的：必须在收束性的语气约束卡**之前**。

    隐性知识是「背景资料」性质（她知道什么），而 `final_role_voice_contract` /
    `player_echo_guard` 那一组是**决定这一轮怎么说话**的收束卡。插在它们后面
    等于把已经定好的语气重新打开——本项目在卡序上踩过这类账。

    ⚠ 用**恒存在**的卡做锚点：`relationship_world` 只在配了关系世界数据时才出现，
    `recent_memory` 只在 `select_compact_memory_facts` 筛得出东西时才出现。
    拿它们做相对定位会让用例在**实现没坏**时空红——本项目记过这种
    「测试自己写错」的账。位置相对 `recent_memory` 的关系另有用例覆盖
    （那边给足了 `recentFacts`）。
    """
    messages = _messages(latentKnowledge=[_LATENT])
    names = _card_names(messages)

    assert "latent_knowledge" in names, "隐性知识卡没生成，后面的位置断言无从谈起。"
    for closing_card in ("final_role_voice_contract", "player_echo_guard"):
        assert closing_card in names, (
            f"{closing_card} 不在卡序里——锚点失效，这条用例的前提没了。"
        )
        assert names.index("latent_knowledge") < names.index(closing_card), (
            f"隐性知识卡排到了 {closing_card} 之后——那是收束性的语气卡，"
            "背景资料不该插在它后面。"
        )


def test_latent_knowledge_does_not_join_recent_memory_card() -> None:
    """隐性知识**不得**出现在 `recent_memory` 卡里。

    那张卡的指令是「把记忆自然用起来」（会主动提），而需求是
    「不主动提就不唤醒」。混进去等于两套打架的约束同时在场，
    项目实测过**「取最宽」**——跟最松的那个，于是「不主动提」直接失效。

    没有 `recent_memory` 卡时这条自然成立（无条件通过也是正确结论：
    「不在那张卡里」）。
    """
    messages = _messages(latentKnowledge=[_LATENT])

    for message in messages:
        if message.get("name") == "recent_memory":
            assert "练练剑" not in str(message.get("content")), (
                "隐性知识混进了 recent_memory 卡 —— 「不主动提」会因「取最宽」失效。"
            )

    # 但隐性知识卡自己必须存在，否则这个用例会在「什么都没生成」时空转通过。
    assert "latent_knowledge" in _card_names(messages)


def test_latent_card_does_not_claim_first_person_experience() -> None:
    """卡片必须让模型知道「这是听来的」，否则她会当成自己的经历讲。

    这正是「人格连续」的反面：同一个 NPC 在私聊里把自己没做过的事
    说成自己做的，玩家一眼就看出不是同一个人。
    """
    messages = _messages(latentKnowledge=[_LATENT])
    card = next(
        message for message in messages if message.get("name") == "latent_knowledge"
    )
    content = str(card.get("content"))

    assert "不主动" in content, "卡片没有传达「不主动提」这条要求。"
    assert "Abigail" in content, "转述里没有指明是谁说的 —— 会被当成她自己的经历。"


def test_compact_path_also_carries_the_card() -> None:
    """紧凑路径同样要带上。

    线上默认走紧凑（C# 侧 `CompactPrompt` 默认 true，见 `models.py` 的
    「语义层审计 #46」注释）。若只有完整路径有这张卡，**线上永远看不到它** ——
    而离线评测会一路绿灯。这是最危险的一种「测过了但没生效」。
    """
    payload = _payload(
        compactPrompt=True,
        latentKnowledge=[_LATENT],
    )
    context = ContextBuilder().build(payload)
    messages = PromptBuilder().build(context, str(payload["message"]))

    assert "latent_knowledge" in _card_names(messages), (
        "紧凑路径没有隐性知识卡 —— 线上默认走紧凑，等于这个功能线上不存在。"
    )