"""方案 B：一个主题别聊三轮 —— 落点轮换（2026-09-21）。

诊断的三条硬证据里最直接的一条是 `conversationLead.variationRule` 的原文：

    「连续轮次避免重复同一 leadKind、开场结构和问句模板；**没有新对象时继续承接
    当前话题**。」

前半句要求变化，后半句明确鼓励延续——同一条规则自己抵消自己，于是同一个落点
物件（哈维的早餐、酒、灯光）连着好几轮不换。本次只做两处最小改动：

1. `_CONVERSATION_LEAD_CARD["variationRule"]`：**允许**承接但给落点加上限
   （同一落点最多连续两次，第三次换一个生活面）；
2. 哈维的 `roleGuidance`：从「用一个具体照料」改成给出可轮换的落点池
   （水／咖啡／外套／伞／诊所班次），不再让模型自己收敛到一个默认落点。

本文件同时钉住这两处**确实到达线上紧凑路径**（`stage_execution_card` 会截断
`variationRule` 与 `roleGuidance`，超 240 字就白改）。
"""

from __future__ import annotations

import json

import pytest

from stardew_ai_bridge.prompts import PromptBuilder, _compact_stage_policy
from stardew_ai_bridge.stage_policy import (
    CONVERSATION_LEAD_TRIAL_NPC_IDS,
    build_stage_policy,
)

STAGES = ("friend", "close", "dating", "married")

# 哈维的可轮换照料落点（方案 B 指定的池子）。
HARVEY_FALLPOINTS = ("水", "咖啡", "外套", "伞", "诊所")


def _lead(npc_id: str, stage: str) -> dict[str, object]:
    return build_stage_policy(npc_id, stage)["conversationLead"]


# --- 1. variationRule：允许承接但限制延续 ------------------------------------


def test_variation_rule_allows_continuation_but_caps_the_fallpoint() -> None:
    rule = _lead("Harvey", "married")["variationRule"]

    assert "允许继续承接当前话题" in rule
    assert "同一落点物件最多连续出现两次" in rule
    assert "第三次换一个生活面" in rule


def test_variation_rule_no_longer_encourages_open_ended_continuation() -> None:
    """旧文案是无条件鼓励延续，正是主因。"""

    for npc_id in CONVERSATION_LEAD_TRIAL_NPC_IDS:
        for stage in STAGES:
            rule = _lead(npc_id, stage)["variationRule"]
            assert "没有新对象时继续承接当前话题" not in rule, (npc_id, stage)


def test_affection_variation_rule_is_untouched() -> None:
    """高好感那张卡的 variationRule 讲的是亲近形状，不是落点，本次不动。"""

    policy = build_stage_policy("Sophia", "married")
    assert policy["affectionInitiative"]["variationRule"] == (
        "连续轮次避免重复同一 personal signal、initiativeKind 和开场形状；"
        "保留角色自己的表达方式。"
    )


# --- 2. 哈维：可轮换落点 ------------------------------------------------------


def test_harvey_guidance_offers_rotatable_fallpoints() -> None:
    guidance = _lead("Harvey", "dating")["roleGuidance"]

    for fallpoint in HARVEY_FALLPOINTS:
        assert fallpoint in guidance, fallpoint
    assert "不要每轮都落到同一件事" in guidance
    assert "同一个落点最多连续两次" in guidance


@pytest.mark.parametrize("stage", STAGES)
def test_harvey_guidance_keeps_its_original_care_boundary(stage: str) -> None:
    """落点池是加法：照料语气与「不立刻诊断」的边界不能被顶掉。"""

    guidance = _lead("Harvey", stage)["roleGuidance"]

    assert "先确认玩家说出的状态" in guidance
    assert "不立刻诊断" in guidance


def test_fallpoints_do_not_leak_into_other_roles() -> None:
    for npc_id in CONVERSATION_LEAD_TRIAL_NPC_IDS - {"Harvey"}:
        guidance = _lead(npc_id, "married")["roleGuidance"]
        assert "外套" not in guidance, npc_id
        assert "诊所班次" not in guidance, npc_id


# --- 3. 存活到线上紧凑路径 ----------------------------------------------------


@pytest.mark.parametrize("stage", STAGES)
def test_compact_stage_card_keeps_both_texts_verbatim(stage: str) -> None:
    """紧凑卡按 240 字截断；超了就白改，所以逐字比对。"""

    for npc_id in CONVERSATION_LEAD_TRIAL_NPC_IDS:
        policy = build_stage_policy(npc_id, stage)
        compact = _compact_stage_policy(policy, include_response_order=False)
        lead = compact["conversationLead"]

        assert lead["variationRule"] == policy["conversationLead"]["variationRule"]
        assert (
            lead["roleGuidance"] == policy["conversationLead"]["roleGuidance"]
        ), f"{npc_id}/{stage} 的 roleGuidance 被 compact 截断"


def test_game_prompt_carries_the_rotation_rule_and_fallpoints() -> None:
    """线上（compact）请求里两张卡都要能看到这两处改动。"""

    body = {
        "npcId": "Harvey",
        "message": "今天有点累。",
        "intent": "chat",
        "provider": "fake",
        "compactPrompt": True,
        "channel": "face_to_face",
        "sourceMods": [],
        "history": [],
        "gameState": {
            "npcId": "Harvey",
            "displayName": "Harvey",
            "location": "Hospital",
            "season": "spring",
            "date": "25",
            "weather": "clear",
            "time": 1830,
            "friendship": 2000,
            "friendshipHearts": 8,
            "relationship": "dating",
            "marriageStatus": "dating",
        },
    }

    from stardew_ai_bridge.app import _build_context

    context, _ = _build_context(body)
    messages = PromptBuilder().build(context, body["message"], compact=True)
    blob = json.dumps(messages, ensure_ascii=False)

    assert "同一落点物件最多连续出现两次" in blob
    assert "照料落点在水、咖啡、外套、伞、诊所班次" in blob
    # 落点池必须出现在两张会进 prompt 的卡里（阶段执行卡 + 最终角色指纹）
    names = {message["name"] for message in messages}
    assert "stage_execution_card" in names
    for message in messages:
        if message["name"] == "stage_execution_card":
            assert "照料落点在水、咖啡、外套、伞、诊所班次" in message["content"]
        if message["name"] == "final_role_voice_contract":
            assert "照料落点在水、咖啡、外套、伞、诊所班次" in message["content"]
