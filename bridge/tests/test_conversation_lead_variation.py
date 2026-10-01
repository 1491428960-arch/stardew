"""方案 B：一个主题别聊三轮 —— 落点轮换（2026-09-21）。

诊断的三条硬证据里最直接的一条是 `conversationLead.variationRule` 的原文：

    「连续轮次避免重复同一 leadKind、开场结构和问句模板；**没有新对象时继续承接
    当前话题**。」

前半句要求变化，后半句明确鼓励延续——同一条规则自己抵消自己，于是同一个落点
物件（哈维的早餐、酒、灯光）连着好几轮不换。

2026-09-21 五轮（用户实测：索菲亚第 4 轮「收在画框边上」、第 5 轮「压在画框边上」）
把上限与出口一起收紧，本文件随之从"允许两次"改钉三件事：

1. `_CONVERSATION_LEAD_CARD["variationRule"]`：单位提到「生活面」，
   显式堵死"换物件 = 换面"，上限收紧为**不允许连续两轮同面**；
2. **`{topicPool}` 同源化推广到全部 8 个 `conversationLead` 角色** ——
   此前只有索菲亚一个模板含占位符，其余 7 个把职业对象硬编码在文案里
   （哈维的「水／咖啡／外套／伞／诊所班次」就是其中之一），那是**第二份数据**，
   会与角色自己的 `preferredTopics` 各自演化；
3. 两张卡都要**到达线上紧凑路径**（`stage_execution_card` 会按 240 字截断
   `variationRule` 与 `roleGuidance`，超了就白改）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.prompts import (
    PromptBuilder,
    _ROLE_GUIDANCE_LIMIT,
    _compact_stage_policy,
)
from stardew_ai_bridge.stage_policy import (
    _CONVERSATION_LEAD_ROLE_GUIDANCE,
    CONVERSATION_LEAD_TRIAL_NPC_IDS,
    build_stage_policy,
)

STAGES = ("friend", "close", "dating", "married")

# 哈维旧版硬编码的照料落点（2026-09-21 五轮已删，改由 preferredTopics 同源生成）。
HARVEY_OLD_HARDCODED_FALLPOINTS = ("外套", "伞", "诊所班次")

ROOT = Path(__file__).resolve().parents[2]


def _lead(npc_id: str, stage: str) -> dict[str, object]:
    return build_stage_policy(npc_id, stage)["conversationLead"]


def _persona_preferred_topics(npc_id: str) -> list[str]:
    """角色数据源里的 preferredTopics —— 落点池的唯一数据源。

    与 `prompts._preferred_topics_for_prompt` 同源：从 persona 文件读原始列表。
    只读模板层的断言验不到"渲染成什么"，所以凡涉及落点池内容的测试都要先取数据源。
    """

    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        profile = (payload.get("personas") or {}).get(npc_id)
        if not isinstance(profile, dict):
            continue
        voice_style = profile.get("voiceStyle")
        topics = (
            voice_style.get("preferredTopics") if isinstance(voice_style, dict) else None
        )
        if topics:
            return [str(topic) for topic in topics]
    raise AssertionError(f"data/personas 里找不到 {npc_id} 的 preferredTopics")


def _window_topics(npc_id: str, turn_index: int = 0) -> list[str]:
    """**真正进 prompt 的那一批**落点。

    2026-09-30 起 `preferredTopics` 是素材库（可以几十条），进 prompt 的是
    `_topic_window_for_turn` 按轮次切出的 12 条窗口。窗口每轮前进
    `prompts._TOPIC_WINDOW_STEP` 条 —— 2026-10-01 由 1 改为 **4**，于是相邻轮次
    共享 8 条、单轮换进 4 条（旧口径是共享 11 条、换进 1 条）。
    所以"渲染成什么"这类断言必须按窗口算：直接喂整库渲染出的超长 guidance
    既不是线上会发生的输入，测出来的红也不是真问题。
    """

    from stardew_ai_bridge.prompts import _topic_window_for_turn

    return _topic_window_for_turn(_persona_preferred_topics(npc_id), turn_index)


def _rendered_guidance(npc_id: str, turn_index: int = 0) -> str:
    return build_stage_policy(
        npc_id,
        "dating",
        preferred_topics=_window_topics(npc_id, turn_index),
    )["conversationLead"]["roleGuidance"]


# --- 1. variationRule：单层、无出口、不允许连续两轮同面 -----------------------


def test_variation_rule_allows_continuation_but_bans_two_in_a_row() -> None:
    """规则本身不变，**说法**从"三个不算换"换成"一个可感知的判据"（2026-09-23）。

    旧句把"不算换"枚举三遍（换物件 / 换时段 / 换个说法），与紧跟其后的"才算换"
    是同一件事的一反一正两遍 —— 用户要的方向是"减约束、给示例"，所以反例清单换成
    读者视角的判据（"读起来还是同一件事"），两个正例（从酿造换到…、从写作换到…）
    原文保留。跨面这条硬要求仍在首句。
    """

    rule = _lead("Harvey", "married")["variationRule"]

    assert "允许继续承接当前话题" in rule
    assert "同一个生活面不允许连续两轮出现" in rule
    assert "像这样换" in rule  # 正例示范保留
    assert "只在同一面里挪动物件、时段或说法，读起来还是同一件事" in rule
    assert "都不算换" not in rule  # 反例清单已删


def test_variation_rule_has_no_looser_second_copy() -> None:
    """旧上限的两份表述都必须消失。

    「同一落点物件最多连续出现两次」的单位是**物件**不是生活面，而
    「第三次换一个生活面（换物件、换时段或换一件正在做的事）」的括号把
    "换物件"写成了换面的合法途径 —— 画框 → 画笔就算交差，上限形同虚设。
    旧文案允许连着两轮、新上限禁止连着两轮，两者并排就是"一松一紧取最松"。
    """

    for npc_id in CONVERSATION_LEAD_TRIAL_NPC_IDS:
        for stage in STAGES:
            rule = _lead(npc_id, stage)["variationRule"]
            assert "最多连续出现两次" not in rule, (npc_id, stage)
            assert "第三次换一个生活面" not in rule, (npc_id, stage)
            assert "换一件正在做的事" not in rule, (npc_id, stage)


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


# --- 2. 落点池同源化：8/8 角色 -------------------------------------------------


def test_every_conversation_lead_role_uses_the_topic_pool_placeholder() -> None:
    """8 个角色**全部**同源：模板里不许再硬编码职业对象。

    此前只有索菲亚一个模板含 `{topicPool}`；其余 7 个点名的是写死在文案里的
    第二份数据（Elliott「写作、海风、光线」、Wizard「法师塔、研究记录、符文读数」、
    Sam「音乐、乐器、滑板或街上」、Alex「比赛、训练、好球或农场」、
    Sebastian「音乐、耳机、电脑、摩托车或房间」、Harvey「水、咖啡、外套、伞、
    诊所班次」、Shane 干脆没有落点池）。
    """

    missing = [
        npc_id
        for npc_id in sorted(CONVERSATION_LEAD_TRIAL_NPC_IDS)
        if "{topicPool}" not in _CONVERSATION_LEAD_ROLE_GUIDANCE[npc_id]
    ]

    assert missing == [], f"这些角色的 roleGuidance 还没同源化：{missing}"


@pytest.mark.parametrize("npc_id", sorted(CONVERSATION_LEAD_TRIAL_NPC_IDS))
def test_rendered_guidance_contains_every_topic_of_its_own_source(npc_id: str) -> None:
    """渲染结果必须包含**该轮窗口里的全部落点**，一个都不许漏。

    这是同源化的实质承诺：进 prompt 的那一批落点，在 `roleGuidance` 里一定看得到。
    反过来（点名了看不见的落点）就是 b307388 那种「要求落 A，而 A 不在 prompt 里」。

    口径是**窗口**不是整库：素材库可以几十条，而每轮只渲染 12 条（见
    `_window_topics`）。整库级别的"一个都不许漏"在窗口轮换下不可能成立。
    """

    topics = _window_topics(npc_id)
    guidance = _rendered_guidance(npc_id)

    assert topics, npc_id
    for topic in topics:
        assert topic in guidance, f"{npc_id} 的落点池漏了「{topic}」"
    assert "{topicPool}" not in guidance  # 占位符不得残留到 prompt 里


@pytest.mark.parametrize("npc_id", sorted(CONVERSATION_LEAD_TRIAL_NPC_IDS))
def test_rendered_guidance_survives_the_compact_path(npc_id: str) -> None:
    """上线紧凑路径不许截掉 roleGuidance 的任何内容。

    逐**窗口**验，而不是整库：2026-09-30 起池子是素材库、进 prompt 的是
    `_topic_window_for_turn` 切出的 12 条窗口，而且窗口**逐轮滑动**——所以
    任何一个窗口超了，就有一轮会被静默截断。整库渲染已经不是线上条件。

    2026-10-01 三处加固（此前只测渲染结果、只测 `dating`、且判据写错）：

    1. **改测紧凑路径**（`_compact_stage_policy`）。截断发生在紧凑这一步，而
       渲染结果永远"列得全"——上一版只测渲染，于是"渲染时列全了、到模型眼前
       已经被砍"这一整类缺陷都漏过。它与
       `test_rendered_guidance_contains_every_topic_of_its_own_source` 是一对：
       那个保证**渲染**列全，这个保证**上线**没被砍，两者缺一不可。
    2. **四个 `conversationLead` 阶段全测**，不只 `dating`：各阶段模板不同、
       渲染长度也不同，只测一个阶段等于把另外三个放过。
    3. **判据换成"渲染结果 == 紧凑结果"**，不是 `len(紧凑) <= 上限`。后者是
       **同义反复**：`_compact_stage_policy` 自己就用该上限截断，输出恒 ≤ 上限，
       断言恒真。实测把这个上限从 320 改回 230 后测试**照样全绿**——240 字被
       截成 230 后依然满足 `230 <= 230`。同一个盲区还让"紧凑后恰好等于旧上限
       240"被误读成"被截断到 240"。逐字相等与上限取值无关，截断必然暴露。

    上限 `_ROLE_GUIDANCE_LIMIT` 只用于报错信息，判据本身不依赖它的值。
    """

    topics = _persona_preferred_topics(npc_id)
    for turn in range(len(topics)):
        window = _window_topics(npc_id, turn)
        for stage in STAGES:
            policy = build_stage_policy(npc_id, stage, preferred_topics=window)
            rendered = policy["conversationLead"]["roleGuidance"]
            compacted = _compact_stage_policy(policy)["conversationLead"]["roleGuidance"]
            assert compacted == rendered, (
                f"{npc_id}/{stage} 第 {turn} 轮窗口的 roleGuidance 被紧凑路径截断："
                f"渲染 {len(rendered)} 字 → 上线 {len(compacted)} 字"
                f"（上限 {_ROLE_GUIDANCE_LIMIT}）"
            )


# --- 3. 哈维：落点池改由他自己的素材生成 --------------------------------------


def test_harvey_guidance_pool_comes_from_his_own_topics() -> None:
    topics = _window_topics("Harvey")
    guidance = _rendered_guidance("Harvey")

    assert "照料落点在" in guidance
    for topic in topics:
        assert topic in guidance, topic
    assert "不要每轮都落到同一件事" in guidance


def test_harvey_guidance_drops_the_old_hardcoded_pool_and_loose_cap() -> None:
    """旧硬编码池与旧上限都必须消失。

    「同一个落点最多连续两次」是 `variationRule` 上限的**第二份表述**，且比新上限
    （不允许连续两轮）更松；两句并排会让模型挑最松的读法 —— 这正是
    `stage_policy.py` 里记过两次的同型教训。
    """

    guidance = _rendered_guidance("Harvey")

    for fallpoint in HARVEY_OLD_HARDCODED_FALLPOINTS:
        assert fallpoint not in guidance, fallpoint
    assert "同一个落点最多连续两次" not in guidance
    assert "最多连续两次" not in guidance


@pytest.mark.parametrize("stage", STAGES)
def test_harvey_guidance_keeps_its_original_care_boundary(stage: str) -> None:
    """落点池是加法：照料语气与「不立刻诊断」的边界不能被顶掉。"""

    guidance = _lead("Harvey", stage)["roleGuidance"]

    assert "先确认玩家说出的状态" in guidance
    assert "不立刻诊断" in guidance


def test_old_hardcoded_fallpoints_do_not_leak_into_other_roles() -> None:
    for npc_id in CONVERSATION_LEAD_TRIAL_NPC_IDS - {"Harvey"}:
        guidance = _rendered_guidance(npc_id)
        for fallpoint in HARVEY_OLD_HARDCODED_FALLPOINTS:
            assert fallpoint not in guidance, (npc_id, fallpoint)


def test_no_role_guidance_keeps_a_looser_cap_sentence() -> None:
    """全角色回归闸：任何 roleGuidance 里都不许再有"最多连续两次"这类更松的上限。"""

    offenders = {
        npc_id: _rendered_guidance(npc_id)
        for npc_id in sorted(CONVERSATION_LEAD_TRIAL_NPC_IDS)
        if "最多连续两次" in _rendered_guidance(npc_id)
        or "最多连续出现两次" in _rendered_guidance(npc_id)
    }

    assert offenders == {}


# --- 4. 存活到线上紧凑路径 ----------------------------------------------------


@pytest.mark.parametrize("stage", STAGES)
def test_compact_stage_card_keeps_both_texts_verbatim(stage: str) -> None:
    """紧凑卡按 240 字截断；超了就白改，所以逐字比对。"""

    for npc_id in CONVERSATION_LEAD_TRIAL_NPC_IDS:
        policy = build_stage_policy(
            npc_id,
            stage,
            preferred_topics=_window_topics(npc_id),
        )
        compact = _compact_stage_policy(policy, include_response_order=False)
        lead = compact["conversationLead"]

        assert lead["variationRule"] == policy["conversationLead"]["variationRule"]
        assert (
            lead["roleGuidance"] == policy["conversationLead"]["roleGuidance"]
        ), f"{npc_id}/{stage} 的 roleGuidance 被 compact 截断"


def test_game_prompt_carries_the_rotation_rule_and_the_sourced_pool() -> None:
    """线上（compact）请求里两张卡都要能看到这两处改动。"""

    body = {
        "npcId": "Harvey",
        "message": "今天有点累。",
        "intent": "chat",
        "provider": "fake",
        "compactPrompt": True,
        "channel": "face_to_face",
        "sourceMods": ["female-bachelors", "vanilla"],
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

    assert "同一个生活面不允许连续两轮出现" in blob
    assert "照料落点在诊所和飞行爱好者的日常" in blob
    # 落点池必须出现在两张会进 prompt 的卡里（阶段执行卡 + 最终角色指纹）
    names = {message["name"] for message in messages}
    assert "stage_execution_card" in names
    for message in messages:
        if message["name"] == "stage_execution_card":
            assert "照料落点在诊所和飞行爱好者的日常" in message["content"]
        if message["name"] == "final_role_voice_contract":
            assert "照料落点在诊所和飞行爱好者的日常" in message["content"]
