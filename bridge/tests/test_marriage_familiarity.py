"""已婚阶段与熟稔度：(2026-09-21 用户拍板) 两个维度的拆分。

背景：事件锁此前用「剧情链走完没有」判定关系阶段，而**婚姻是唯一一个
"玩家没走完那条链也可能达成"的阶段**——于是用户存档里 7 个配了事件门的
角色有 6 个被压到 `acquaintance` / `friend`，配偶 Alex 因为 `288847` 不在
存档里而恒被压到 `friend`，prompt 里写着「不得使用爱称、主动暧昧、
固定爱称或事件后专属熟稔」。

用户口径：

1. **已婚必须是最强力的阶段**：结婚没法靠刷好感度达成，必须实际走完流程，
   所以已婚本身就是强证据，不能被事件锁压到"朋友"以下。
2. **但仍然要有差分**：剧情链没走完的已婚应当体现为「生疏」——
   像结婚不久、还没磨合的夫妻，而不是"冷淡"，更不是"退回朋友"。

拆法：

* **关系阶段** = 婚姻状态 + 心数；`INTIMATE_STAGE_FLOOR` 保证 dating /
  married / parent 不低于 `close`，事件锁不再下调它们。
* **熟稔度** = 事件完成度，`unfamiliar / warming / settled`（生疏 / 逐渐熟络 /
  已磨合）是**独立调节量**，只影响爱称、内部梗、事件后专属熟稔与主动亲密的
  程度，不影响阶段本身。

注意：熟稔度在最终 prompt 里的唯一载体是 `stage_execution_card` 的
`eventGate.instruction`——`PromptBuilder` 对 `npcIdentity` 无条件走
`_compact_identity`，其 `_compact_stage_policy` 是白名单，不会带出
`stagePolicy.familiarity` 这个顶层键。本文件的端到端断言按这个事实写。
"""

from __future__ import annotations

import json

import pytest

from stardew_ai_bridge import guard
from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder
from stardew_ai_bridge.relationship_gating import (
    FAMILIARITY_LABELS,
    INTIMATE_STAGE_FLOOR,
    INTIMATE_STAGES,
    familiarity_from_event_progress,
    relationship_event_gates,
    resolve_relationship_gate,
)
from stardew_ai_bridge.stage_policy import (
    apply_relationship_event_gate,
    build_stage_policy,
)

_GATED_ROLES = ("Wizard", "Sophia", "Shane", "Sebastian", "Alex", "Elliott", "Harvey")
# 一句已被 `behavior_quality.diagnose_personal_affection` 认作主动亲密的样本
_DIRECT_AFFECTION = "这件事我只想先告诉你。"


def _chain(npc_id: str, stage: str) -> tuple[str, ...]:
    for gate in relationship_event_gates(npc_id):
        if gate.stage == stage:
            return tuple(gate.required_event_ids)
    raise AssertionError(f"{npc_id} 没有登记 {stage} 档事件链")


def _gate_dict(npc_id: str, stage: str, completed) -> dict:
    return resolve_relationship_gate(
        npc_id,
        relationship_stage=stage,
        friendship_hearts=14,
        completed_event_ids=completed,
    ).as_prompt_dict()


@pytest.mark.parametrize("relationship_stage", ("dating", "married", "parent"))
@pytest.mark.parametrize("npc_id", _GATED_ROLES)
def test_intimate_stages_are_never_pushed_below_the_floor(
    npc_id: str,
    relationship_stage: str,
) -> None:
    """既成亲密关系在四种事件进度下都保持自己的阶段与 close 下限。"""

    for completed, expected_familiarity in (
        ((), "unfamiliar"),
        (_chain(npc_id, "acquaintance"), "unfamiliar"),
        (_chain(npc_id, "friend"), "warming"),
        (_chain(npc_id, "close"), "settled"),
    ):
        result = resolve_relationship_gate(
            npc_id,
            relationship_stage=relationship_stage,
            friendship_hearts=14,
            completed_event_ids=completed,
        )
        assert result.effective_stage == relationship_stage, (npc_id, completed)
        assert result.effective_intimacy_stage == INTIMATE_STAGE_FLOOR
        assert result.event_gate_applied is False
        assert result.relationship_status_preserved is True
        assert result.familiarity == expected_familiarity
        # 真相没有被丢掉：诊断字段仍然记录事件链实际解锁到哪一档。
        assert result.event_unlocked_stage in (
            "stranger",
            "acquaintance",
            "friend",
            "close",
        )


@pytest.mark.parametrize("npc_id", _GATED_ROLES)
def test_plain_heart_stages_still_follow_the_event_chain(npc_id: str) -> None:
    """普通心级阶段的事件锁**没有**被这次改动关掉（数值 ≠ 叙事证据）。"""

    result = resolve_relationship_gate(
        npc_id,
        relationship_stage="close",
        friendship_hearts=8,
        completed_event_ids=(),
    )

    assert result.effective_stage == "acquaintance"
    assert result.effective_intimacy_stage == "acquaintance"
    assert result.event_gate_applied is True
    assert result.relationship_status_preserved is False
    assert result.familiarity == "unfamiliar"


def test_familiarity_is_an_independent_signal() -> None:
    """熟稔度只由事件完成度决定，与阶段是两套东西。"""

    assert familiarity_from_event_progress(
        unlocked_stage="close", missing_event_ids=()
    ) == "settled"
    assert familiarity_from_event_progress(
        unlocked_stage="close", missing_event_ids=("288847",)
    ) == "warming"
    assert familiarity_from_event_progress(
        unlocked_stage="friend", missing_event_ids=("288847",)
    ) == "warming"
    assert familiarity_from_event_progress(
        unlocked_stage="acquaintance", missing_event_ids=("20",)
    ) == "unfamiliar"
    # 没有走过第一个事件、也没有任何事件状态时都不能算"已磨合"。
    assert familiarity_from_event_progress(unlocked_stage="stranger") == "unfamiliar"
    assert set(FAMILIARITY_LABELS) == {"unfamiliar", "warming", "settled"}
    assert FAMILIARITY_LABELS["unfamiliar"] == "生疏"
    assert FAMILIARITY_LABELS["warming"] == "逐渐熟络"
    assert FAMILIARITY_LABELS["settled"] == "已磨合"


def test_married_policy_keeps_full_affection_and_only_softens_familiarity() -> None:
    """已婚 + 事件链没走完：亲密契约满配，只有熟稔度是"生疏"。"""

    policy = apply_relationship_event_gate(
        build_stage_policy("Alex", "married"),
        _gate_dict("Alex", "married", ()),
    )

    affection = policy["affectionInitiative"]
    assert affection["initiativeMode"] == "proactive"
    assert "direct" in affection["allowedIntensities"]
    assert "explicit" in affection["allowedIntensities"]
    assert affection["warmthSignals"]
    assert affection["personalSignals"]
    assert "conversationLead" in policy

    assert policy["familiarity"]["stage"] == "unfamiliar"
    assert policy["familiarity"]["label"] == "生疏"
    instruction = policy["eventGate"]["instruction"]
    # 正向的熟稔度差分……
    assert "磨合" in instruction
    # ……而不是旧的一刀切禁令。
    assert "不得使用" not in instruction
    assert "主动暧昧" not in instruction
    # 明确禁止把既成关系说成"还不熟"。
    assert "还不熟" in instruction
    assert policy["stage"] == "married"


def test_settled_marriage_opens_the_shared_history_register() -> None:
    policy = apply_relationship_event_gate(
        build_stage_policy("Alex", "married"),
        _gate_dict("Alex", "married", _chain("Alex", "close")),
    )

    assert policy["familiarity"]["stage"] == "settled"
    assert policy["familiarity"]["label"] == "已磨合"
    assert "内部梗" in policy["eventGate"]["instruction"]
    assert policy["affectionInitiative"]["initiativeMode"] == "proactive"


def test_unknown_event_state_injects_no_familiarity_differential() -> None:
    """没有事件状态就不做熟稔度推断，也不注入任何门控卡。"""

    gate = resolve_relationship_gate(
        "Alex",
        relationship_stage="married",
        friendship_hearts=14,
    )
    policy = apply_relationship_event_gate(
        build_stage_policy("Alex", "married"),
        gate.as_prompt_dict(),
    )

    assert gate.familiarity == "unknown"
    assert "familiarity" not in policy
    assert "eventGate" not in policy
    assert policy["affectionInitiative"]["initiativeMode"] == "proactive"


def test_prompt_carries_the_newlywed_differential_for_a_spouse() -> None:
    """端到端：配偶 + 空事件链（线上真实场景）在 prompt 里是"生疏但仍是夫妻"。"""

    context = ContextBuilder().build(
        "Alex",
        friendshipHearts=14,
        relationshipStage="married",
        completedEventIds=[],
    )
    gate = context["npcIdentity"]["relationshipGate"]
    assert gate["relationshipStage"] == "married"
    assert gate["effectiveStage"] == "married"
    assert gate["effectiveIntimacyStage"] == INTIMATE_STAGE_FLOOR
    assert gate["familiarity"] == "unfamiliar"

    prompt = PromptBuilder().build(context, "今天过得怎么样？", compact=False)
    cards = {
        message["name"]: json.loads(message["content"])
        for message in prompt
        if message.get("name") in ("stage_execution_card", "affection_initiative")
    }
    stage_card = cards["stage_execution_card"]
    affection_card = cards["affection_initiative"]

    assert stage_card["stage"] == "married"
    assert "磨合" in stage_card["eventGate"]["instruction"]
    assert "不得使用" not in stage_card["eventGate"]["instruction"]
    # 2026-09-23（B 档压缩 · 跨卡去重）：主动性配置原先同时出现在
    # `stage_execution_card` 与独立的 `affection_initiative` 卡里，两处是同一份
    # JSON，等于连发两次（dating 阶段实测 653 字符纯重复）。现在只由独立卡承载，
    # 而独立卡那份更完整（多 cooldownActive / recentStrongCount /
    # recentStrongFamilies 三个运行时字段）。
    #
    # 断言的信息没有变，只是换了承载卡。这里**特意从独立卡取值**：若哪天
    # `_build_affection_initiative_card` 不再产出（或本轮条件不满足导致它被摘掉），
    # 这两行会以 KeyError 直接失败——防止去重把信息真的删没了。
    affection = affection_card["affectionInitiative"]
    assert affection["initiativeMode"] == "proactive"
    assert "explicit" in affection["allowedIntensities"]


def _guard_prompt(event_gate: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "name": "stage_execution_card",
            "content": json.dumps({"eventGate": event_gate}, ensure_ascii=False),
        },
        {"role": "user", "name": "player_input", "content": "今天怎么样？"},
    ]


def test_guard_does_not_block_a_spouses_direct_affection() -> None:
    """guard 读到的亲密上限是 close，不再是 acquaintance。"""

    policy = apply_relationship_event_gate(
        build_stage_policy("Alex", "married"),
        _gate_dict("Alex", "married", ()),
    )

    assert guard._violates_event_gate(
        _guard_prompt(policy["eventGate"]), _DIRECT_AFFECTION
    ) is False
    # 对照：同一个判定对普通心级阶段仍然生效——事件锁没有失效。
    assert guard._violates_event_gate(
        _guard_prompt(
            {"effectiveIntimacyStage": "acquaintance", "instruction": "占位"}
        ),
        _DIRECT_AFFECTION,
    ) is True


def test_intimate_stage_set_is_unchanged() -> None:
    """parent 仍然继承 married 的亲密契约，集合没有在这次改动里漂移。"""

    assert INTIMATE_STAGES == frozenset({"dating", "married", "parent"})
    assert INTIMATE_STAGE_FLOOR == "close"
