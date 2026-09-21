"""事件锁数据补全（2026-09-20）的回归保护。

背景：`character_quality_eval` 的 `passed` 判定新增 `event_gate_intimacy` 之后，
一批评测案例因为没有声明「角色经历过哪些剧情事件」（`CharacterQualityCase.
completed_event_ids` 默认空元组）而被事件锁收窄到 acquaintance，连已婚 10 心
的案例都被判「主动亲密越界」。

用户拍板的修法是把**数据**补对（「忘了写的补上」），不是在评测侧加「未声明就
按阶段推导」的兜底。本文件把三类案例钉住：

- A 类｜数据缺失：按 `relationship_gating._EVENT_GATES` 补上对应档位的链，
  补完后这些案例不再出现事件锁。
- B 类｜数据写错：`topic-start-event-impact` 的 after 侧原本只声明单个被测事件
  （其中 112／384882／8185290 甚至不在该角色的登记链里），改成「被测事件 +
  该角色 close 档完整链」；before 侧保持空元组。
- C 类｜确实该锁着：before 对照组的语义就是「这段剧情还没发生」，保持空元组。

2026-09-21（用户拍板）语义变更：**已婚/恋爱不再被事件锁下调阶段**。
C 类对照组因此不再表现为"已婚被压成朋友"，而是同一 married 阶段的
**熟稔度差分**（`familiarity=unfamiliar` ↔ `settled`）。
`event_gate_applied` 对既成亲密关系恒为 False；事件链未走完时仍然生效的地方
是普通心级阶段（见 `test_dialogue_boundary_semantics` 的 Shane 对照）。

每一个事件 ID 的来源都在案例文件里逐条注明，本文件只校验「案例声明的事件链
必须与登记表同名档位一致」，不参与生成。
"""

from __future__ import annotations

import inspect

from stardew_ai_bridge import (
    affection_pacing_cases,
    character_quality_eval,
    deep_flirt_cases,
    deep_flirt_intimate_cases,
    relationship_world_cases,
    topic_start_intimacy_cases,
)
from stardew_ai_bridge.character_quality_eval import (
    QUALITY_SUITE_IDS,
    case_by_id,
    quality_cases_for_suite,
    score_character_reply,
)
from stardew_ai_bridge.relationship_gating import (
    relationship_event_gates,
    resolve_relationship_gate,
)

# 案例声明的 relationship_stage → `_EVENT_GATES` 里对应的档位。
# dating / married / parent 都是 close 之后的状态，登记表最高只到 close。
_STAGE_TO_GATE = {
    "acquaintance": "acquaintance",
    "friend": "friend",
    "close": "close",
    "dating": "close",
    "married": "close",
    "parent": "close",
}

# C 类：语义就是「这段剧情还没发生」的对照组。2026-09-21 之后它们**不再**被
# 事件锁收窄阶段（已婚是既成事实），但仍必须是「刻意声明空事件链」的那批案例。
# 数量与内容都是有意写死的；任何新增的「空事件链案例」都会让第一条测试失败，
# 从而逼出一次显式判断，而不是静默通过。
_INTENTIONAL_EMPTY_CHAIN_CASE_IDS = frozenset(
    {
        # topic-start-event-impact 的 before 侧
        "event-impact-wizard-112-before",
        "event-impact-shane-3900074-before",
        "event-impact-sebastian-384882-before",
        "event-impact-alex-20-before",
        "event-impact-elliott-40-before",
        "event-impact-harvey-56-before",
        "event-impact-sophia-8185290-before",
        # relationship-stage-gating 的 before 侧
        "relationship-gate-wizard-before",
        "relationship-gate-sophia-before",
        "relationship-gate-shane-before",
        "relationship-gate-sebastian-before",
        "relationship-gate-alex-before",
        "relationship-gate-elliott-before",
        "relationship-gate-harvey-before",
    }
)

# 兼容旧名字（此前叫 _INTENTIONAL_LOCKED_CASE_IDS）。
_INTENTIONAL_LOCKED_CASE_IDS = _INTENTIONAL_EMPTY_CHAIN_CASE_IDS


def _all_cases() -> list[object]:
    seen: dict[str, object] = {}
    for suite in QUALITY_SUITE_IDS:
        for case in quality_cases_for_suite(suite):
            seen.setdefault(case.case_id, case)
    return list(seen.values())


def _gate(case: object) -> object:
    return resolve_relationship_gate(
        case.npc_id,
        relationship_stage=case.relationship_stage,
        friendship_hearts=case.friendship_hearts,
        completed_event_ids=case.completed_event_ids,
    )


def _case_from_suite(suite: str, case_id: str) -> object:
    return next(
        case for case in quality_cases_for_suite(suite) if case.case_id == case_id
    )


def _gate_chain(npc_id: str, stage: str) -> tuple[str, ...] | None:
    wanted = _STAGE_TO_GATE.get(stage)
    if wanted is None:
        return None
    for gate in relationship_event_gates(npc_id):
        if gate.stage == wanted:
            return tuple(gate.required_event_ids)
    return None


def test_no_quality_case_is_silently_event_gated() -> None:
    """没有任何案例可以因为「忘了声明事件链」被静默压级。

    2026-09-21 之后，既成亲密关系（dating/married/parent）不再被事件锁下调，
    所以这里的期望集合是**空集**；一旦将来出现普通心级阶段的案例忘了补链，
    这条会立刻失败，逼出一次显式判断（补数据 or 归入 C 类）。
    """

    locked = {
        case.case_id
        for case in _all_cases()
        if _gate(case).event_gate_applied
    }

    assert locked == set()

    # C 类对照组的空事件链仍然是有意保留的，并且必须与非对照组区分开。
    # 只统计**配置了事件门**的角色：没有门的角色本来就不需要声明事件链。
    empty_chain = {
        case.case_id
        for case in _all_cases()
        if case.completed_event_ids == ()
        and relationship_event_gates(case.npc_id)
    }
    assert empty_chain == set(_INTENTIONAL_EMPTY_CHAIN_CASE_IDS)


def test_a_class_cases_declare_the_gate_chain_of_their_stage() -> None:
    """A 类：案例声明的事件链必须与登记表的同名档位逐字一致。"""

    checked = 0
    for case in _all_cases():
        if case.case_id in _INTENTIONAL_LOCKED_CASE_IDS:
            continue
        chain = _gate_chain(case.npc_id, case.relationship_stage)
        if chain is None:
            continue
        if case.case_id.startswith("event-impact-"):
            # B 类：被测事件会额外追加在链尾，所以断言链是子集。
            assert set(chain) <= set(case.completed_event_ids), case.case_id
        else:
            assert case.completed_event_ids == chain, case.case_id
        assert _gate(case).event_gate_applied is False, case.case_id
        checked += 1

    # 数据补全覆盖面的下界：受影响面是 197 个案例（190 个唯一 case_id），
    # 修复后仍应有同等规模的案例带着真实事件链。
    assert checked >= 190


def test_b_class_event_impact_before_and_after_differ_only_by_familiarity() -> None:
    """B 类：after 与 before 在 married 阶段下只差熟稔度，不差阶段。"""

    cases = quality_cases_for_suite("topic-start-event-impact")
    pairs: dict[str, list[object]] = {}
    for case in cases:
        pairs.setdefault(case.event_pair_id, []).append(case)
    assert len(pairs) == 7

    for pair_id, pair in pairs.items():
        by_condition = {item.event_condition: item for item in pair}
        before = by_condition["before"]
        after = by_condition["after"]

        assert before.completed_event_ids == (), pair_id
        before_gate = _gate(before)
        assert before_gate.event_gate_applied is False, pair_id
        assert before_gate.effective_stage == "married", pair_id
        assert before_gate.effective_intimacy_stage == "close", pair_id
        assert before_gate.familiarity == "unfamiliar", pair_id

        after_gate = _gate(after)
        assert after_gate.event_gate_applied is False, pair_id
        assert after_gate.effective_stage == "married", pair_id
        assert after_gate.effective_intimacy_stage == "close", pair_id
        assert after_gate.familiarity == "settled", pair_id
        # after 声明的是「被测事件 + 该角色 close 档完整链」。
        chain = _gate_chain(after.npc_id, after.relationship_stage)
        assert chain is not None, pair_id
        assert set(chain) <= set(after.completed_event_ids), pair_id
        assert after.event_id in after.completed_event_ids, pair_id


def test_c_class_before_cases_keep_their_empty_chain_and_read_as_unfamiliar() -> None:
    """C 类：空事件链的语义不变（这段剧情没发生），只是不再压阶段。"""

    for case_id in sorted(_INTENTIONAL_EMPTY_CHAIN_CASE_IDS):
        if case_id.startswith("event-impact-"):
            case = _case_from_suite("topic-start-event-impact", case_id)
        else:
            case = _case_from_suite("relationship-stage-gating", case_id)
        assert case.completed_event_ids == (), case_id
        gate = _gate(case)
        assert gate.relationship_stage == "married", case_id
        assert gate.effective_stage == "married", case_id
        assert gate.effective_intimacy_stage == "close", case_id
        assert gate.event_gate_applied is False, case_id
        assert gate.familiarity == "unfamiliar", case_id
        assert gate.missing_event_ids, case_id


def test_case_factories_require_explicit_event_state() -> None:
    """「忘记声明」必须报错，而不是被静默当成「事件都没发生」。

    这是本次数据问题的根因：`CharacterQualityCase.completed_event_ids` 的默认
    空元组同时表示「没写」和「确认没有事件」。各案例工厂因此改成必填参数。
    """

    factories = (
        topic_start_intimacy_cases._topic_case,
        topic_start_intimacy_cases._target,
        topic_start_intimacy_cases._control,
        affection_pacing_cases._case,
        relationship_world_cases._case,
        deep_flirt_cases._case,
        deep_flirt_intimate_cases._case,
        character_quality_eval._feminine_male_case,
    )
    for factory in factories:
        parameter = inspect.signature(factory).parameters["completed_event_ids"]
        assert parameter.default is inspect.Parameter.empty, factory.__qualname__


def test_married_case_intimacy_line_is_no_longer_gated() -> None:
    """端到端自证：补数据后，婚后案例的正常亲密台词不再被判越界。"""

    case = case_by_id("wizard-married-evening")
    assert case.completed_event_ids == ("1000075", "1724096", "1724097")

    score = score_character_reply(
        case,
        "今晚别管那些记录了，我想把这会儿留给你。",
        turn=case.dialogue_turns()[0],
    )

    assert "event_gate_intimacy" not in score["tags"]
    assert score["passed"] is True


def test_the_same_line_is_no_longer_blocked_for_a_married_case() -> None:
    """对照反转（2026-09-21 用户拍板）：已婚不再因事件链未走完被判"主动亲密越界"。

    同一句话在**普通心级阶段**仍然越界——事件锁没有失效，只是不再作用于
    既成亲密关系；那条对照在 `test_dialogue_boundary_semantics` 的 Shane
    close 案例里。
    """

    case = _case_from_suite("relationship-stage-gating", "relationship-gate-wizard-before")
    assert case.completed_event_ids == ()

    score = score_character_reply(
        case,
        "这件事我只想先告诉你。",
        turn=case.dialogue_turns()[0],
    )

    assert "event_gate_intimacy" not in score["tags"]
