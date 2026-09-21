"""批次 3：通用「别编生活细节」约束，**私聊与群聊两侧都要生效**（2026-09-21）。

背景（用户实测）：群聊里 Alex 说自己养了只叫「小黑」的狗。
这条**不是凭空编造** —— Alex 正典确有狗（Dusty，官方中文译名「小灰」），
模型说对了"有狗"、说错了名字。真因是名字进不了 prompt：
`speechEvidence[:4]` 是**切片不是选择**，Alex 的 211 条素材里含「小灰」的 8 条
排在深处，结构性永远取不到；那 8 条还全是受 `completedEventIds` 门控的
`event_dialogue`；而常驻通道 `knowledgeFacts` / `knownCharacters` 都不装宠物信息。

修复分两半，本文件钉的是**兜底那一半**（另一半是把专有名词提升为常驻事实，
见 `test_proper_noun_facts.py`）：`safety_content` 里补一条通用禁令。
此前唯一的"凭空添加"禁令只针对魔法现象（写在下方的日常寒暄分支里），
**没有推广成通用规则**，两侧都没兜底。

本文件验四件事：

1. 私聊（线上 `compactPrompt=True`）的 `safety_rules` 卡里有这条；
2. **群聊侧也有** —— 群聊走 `app._group_participant_prompts`，
   每个参与者各拿一份完整卡组（不是 compact），这条路必须一起验，
   否则"两侧都生效"只是一句空话；
3. 措辞**收在"没有资料依据"**上，不是"禁止编造一切"：用户口径是
   「补角色自己的日常可以，补玩家做过/说过的不行」
   （见记忆 `stardew-npc-invented-memories`），所以这条不能写成通用禁令；
4. 原有的魔法禁令**没有被顶掉**（它是为 Wizard/Rasmodia 加的，仍在）。
"""

from __future__ import annotations

import json

import pytest

# 与 `prompts.py` 的 `safety_content` 逐字一致。
INVENTED_LIFE_DETAIL_RULE = (
    "没有资料依据的具体事物（宠物及其名字、家人、物件、行程、别人的近况）不要编；"
    "资料里没有名字时就不要给它起名字，宁可只说态度、感受或笼统的日常。"
)

# 原有的魔法专属禁令（写在 `_is_plain_dialogue_input` 分支里），不能被新规则替换掉。
MAGIC_BAN = "不要凭空添加星界、符文、"


def _game_state(npc_id: str) -> dict[str, object]:
    return {
        "npcId": npc_id,
        "displayName": npc_id,
        "location": "Town",
        "season": "spring",
        "date": "25",
        "weather": "clear",
        "time": 1200,
        "friendship": 1500,
        "friendshipHearts": 6,
        "relationship": "friend",
    }


def _safety_text(messages: list[dict[str, str]]) -> str:
    for message in messages:
        if message.get("name") == "safety_rules":
            return message["content"]
    raise AssertionError("prompt 里没有 safety_rules 卡")


def _private_messages(npc_id: str, message: str) -> list[dict[str, str]]:
    from stardew_ai_bridge.app import _build_context

    body = {
        "npcId": npc_id,
        "message": message,
        "intent": "chat",
        "provider": "fake",
        "compactPrompt": True,
        "channel": "face_to_face",
        "sourceMods": ["vanilla"],
        "history": [],
        "gameState": _game_state(npc_id),
    }
    _, messages = _build_context(body)
    return messages


def _group_messages(
    npc_ids: tuple[str, ...],
    message: str,
) -> dict[str, list[dict[str, str]]]:
    from stardew_ai_bridge.app import _group_participant_prompts
    from stardew_ai_bridge.models import GroupDialogueRequest

    request = GroupDialogueRequest.model_validate(
        {
            "message": message,
            "provider": "local",
            "strategy": "multi_turn",
            "channel": "remote",
            "participants": [
                {
                    "npcId": npc_id,
                    "displayName": npc_id,
                    "sourceMods": ["vanilla"],
                }
                for npc_id in npc_ids
            ],
            "activeSpeakerNpcId": npc_ids[0],
            "turnCount": len(npc_ids),
            "gameState": _game_state(npc_ids[0]),
        }
    )
    return _group_participant_prompts(list(request.participants), request)


# --- 1. 私聊侧 ----------------------------------------------------------------


@pytest.mark.parametrize("npc_id", ["Alex", "Sophia", "Haley"])
@pytest.mark.parametrize("message", ["你好呀", "你养宠物吗？", "今天过得怎么样？"])
def test_private_chat_carries_the_rule(npc_id: str, message: str) -> None:
    text = _safety_text(_private_messages(npc_id, message))

    assert INVENTED_LIFE_DETAIL_RULE in text


# --- 2. 群聊侧（同一句话必须也在） --------------------------------------------


def test_group_chat_carries_the_rule_for_every_participant() -> None:
    """群聊走完整卡组（`_group_participant_prompts`），每个参与者都要有这条。

    这正是「小黑」事件发生的场景 —— 只改私聊等于没修。
    """

    npc_ids = ("Alex", "Haley", "Emily")
    prompts = _group_messages(npc_ids, "你们最近都在忙什么？")

    assert set(prompts) == set(npc_ids)
    for npc_id, messages in prompts.items():
        assert INVENTED_LIFE_DETAIL_RULE in _safety_text(messages), npc_id


def test_group_and_private_use_the_same_rule_text() -> None:
    """两侧文本必须逐字一致：只改一侧是这条约束最容易复发的方式。"""

    private_text = _safety_text(_private_messages("Alex", "你养宠物吗？"))
    group_prompts = _group_messages(("Alex", "Emily"), "你们最近都在忙什么？")

    for npc_id, messages in group_prompts.items():
        assert INVENTED_LIFE_DETAIL_RULE in private_text, npc_id
        assert INVENTED_LIFE_DETAIL_RULE in _safety_text(messages), npc_id


# --- 3. 措辞边界：不是"禁止编造一切" ------------------------------------------


def test_rule_is_scoped_to_unsourced_details() -> None:
    """必须保留「没有资料依据的」这个限定词。

    用户口径是**有依据的日常补全仍然允许**（补角色自己的日常可以，
    补玩家做过/说过的不行）。若有人把它改成"禁止编造""不得虚构"这种
    无限定的通用禁令，会把角色正常的日常自述一起掐死 —— 那是过度收紧。
    """

    from stardew_ai_bridge.prompts import PromptBuilder  # noqa: F401

    text = _safety_text(_private_messages("Alex", "你养宠物吗？"))

    assert "没有资料依据的" in text
    assert "宁可只说态度、感受或笼统的日常" in text
    # 无限定的通用禁令不得出现
    for over_broad in ("禁止编造", "不得编造", "禁止虚构", "不得虚构"):
        assert over_broad not in text, over_broad


def test_magic_ban_is_not_replaced_by_the_new_rule() -> None:
    """新规则是**追加**，不能顶掉原有的魔法禁令。"""

    text = _safety_text(_private_messages("Wizard", "你好呀"))

    assert MAGIC_BAN in text
    assert INVENTED_LIFE_DETAIL_RULE in text


def test_rule_lands_in_the_shared_block_not_only_the_plain_dialogue_branch() -> None:
    """这条必须写在 `safety_content` 主干里。

    如果只写进 `_is_plain_dialogue_input` 分支，那么带具体主题的输入
    （例如"你养宠物吗"被判定为非日常）就会漏掉约束 —— 而那恰恰是最容易
    触发编造的输入。这里用一个**明确不是纯寒暄**的问题来区分两条路。
    """

    probing = _safety_text(
        _private_messages("Alex", "说说你那只有名字的宠物吧，是哪一年养的？")
    )

    assert INVENTED_LIFE_DETAIL_RULE in probing


def test_rule_reaches_the_serialised_prompt_json() -> None:
    """整包 prompt 序列化后仍能看到 —— 防止字段被后续裁剪掉。"""

    blob = json.dumps(_private_messages("Alex", "你好呀"), ensure_ascii=False)

    assert "没有资料依据的具体事物" in blob
    assert "资料里没有名字时就不要给它起名字" in blob
