"""好感度事件链解锁关系亲密权限的离线前后对照案例。"""

from __future__ import annotations

from dataclasses import replace

from .character_quality_eval import CharacterQualityCase, CharacterQualityTurn
from .topic_start_adaptive_cases import topic_start_adaptive_cases


RELATIONSHIP_GATING_SUITE_ID = "relationship-stage-gating"


RELATIONSHIP_GATING_SPECS: tuple[dict[str, object], ...] = (
    {
        "pair_id": "relationship-gate-wizard",
        "base_case_id": "adaptive-topic-wizard-married-study",
        "event_ids": ("1000075", "1724096", "1724097"),
        "summary": "Wizard 的关键好感度事件链完成后，才解锁 close 级的私人开放度。",
    },
    {
        "pair_id": "relationship-gate-sophia",
        "base_case_id": "adaptive-topic-sophia-married-studio",
        "event_ids": ("8185291", "8185292", "8185293", "8185295"),
        "summary": "Sophia 的已解析好感度事件链完成后，才解锁婚后高级亲密表达。",
    },
    {
        "pair_id": "relationship-gate-shane",
        "base_case_id": "adaptive-topic-shane-married-home",
        "event_ids": ("611944", "3910674", "3910975", "3900074"),
        "summary": "Shane 的关键事件链完成后，才解锁婚后更高的私人披露和主动亲密。",
    },
    {
        "pair_id": "relationship-gate-sebastian",
        "base_case_id": "adaptive-topic-sebastian-married-basement",
        "event_ids": ("2794460", "384883", "27", "29"),
        "summary": "Sebastian 的完整事件链完成后，才解锁婚后专属熟稔和亲密主动性。",
    },
    {
        "pair_id": "relationship-gate-alex",
        "base_case_id": "adaptive-topic-alex-married-evening",
        "event_ids": ("20", "2481135", "2119820", "288847"),
        "summary": "Alex 的完整事件链完成后，才解锁婚后更高阶段的偏爱和共同安排。",
    },
    {
        "pair_id": "relationship-gate-elliott",
        "base_case_id": "adaptive-topic-elliott-married-studio",
        "event_ids": ("39", "40", "423502", "1848481"),
        "summary": "Elliott 的完整事件链完成后，才解锁婚后高级私人分享和熟稔。",
    },
    {
        "pair_id": "relationship-gate-harvey",
        "base_case_id": "adaptive-topic-harvey-married-clinic",
        "event_ids": ("56", "57", "58", "571102"),
        "summary": "Harvey 的完整事件链完成后，才解锁婚后更高阶段的照料与依恋表达。",
    },
)


_FIXED_TURNS = (
    CharacterQualityTurn(
        turn_id="turn-1",
        message="今天还好吗？",
        evaluation_focus="高心级和婚姻标签保持不变，但检查事件链是否限制了高级亲密权限。",
        initiative_expectation="none",
        initiative_kind="none",
        intent="chat",
        turn_plan_mode="answer_only",
    ),
    CharacterQualityTurn(
        turn_id="turn-2",
        message="嗯，我在听。",
        evaluation_focus="观察事件完成前后是否仍围绕当前输入，而不是误用事件后专属熟稔。",
        initiative_expectation="none",
        initiative_kind="none",
        intent="chat",
        turn_plan_mode="answer_only",
    ),
    CharacterQualityTurn(
        turn_id="turn-3",
        message="你慢慢说。",
        evaluation_focus="确认完成事件链后才允许进入更高亲密权限，未完成时保留日常边界。",
        initiative_expectation="none",
        initiative_kind="none",
        intent="chat",
        turn_plan_mode="answer_only",
    ),
)


def _neutralize_case(case: CharacterQualityCase) -> CharacterQualityCase:
    """保留角色、关系和来源，只清除原案例的话题与历史铺垫。"""

    return replace(
        case,
        case_id="",
        message="今天还好吗？",
        intent="chat",
        topic_seed="当前近况",
        topic_keywords=(),
        continuation_mode="",
        follow_up_mode="fixed",
        player_simulation_style="固定玩家输入：只接住 NPC 当前说的内容。",
        player_expression_card=None,
        relationship_context="高心级和真实婚姻关系已确认，但事件链完成状态是本轮唯一变量。",
        history=(),
        expected_terms=(),
        forbidden_terms=(),
        story_progress=(
            "这是线下闲聊；当前没有已确认的共同场景、手边物件、未完成事务或未来计划。"
            "玩家只是在问近况；除角色资料中已有的稳定事实外，不新增地点、物件、动作、安排或事件经历。"
        ),
        # 空列表是有意写入 gameState 的：它表示“已确认没有完成事件”，
        # 与完全没有提供 completedEventIds 的未知状态不同。
        game_state=(("completedEventIds", []),),
        completed_event_ids=(),
        turns=_FIXED_TURNS,
    )


def _build_case(
    spec: dict[str, object],
    base_case: CharacterQualityCase,
    condition: str,
) -> CharacterQualityCase:
    pair_id = str(spec["pair_id"])
    event_ids = tuple(str(item) for item in spec["event_ids"])
    event_chain = " → ".join(event_ids)
    neutral_case = _neutralize_case(base_case)
    return replace(
        neutral_case,
        case_id=f"{pair_id}-{condition}",
        completed_event_ids=event_ids if condition == "after" else (),
        event_pair_id=pair_id,
        event_id=f"chain:{event_chain}",
        event_condition=condition,
        game_state=(
            (
                "completedEventIds",
                list(event_ids) if condition == "after" else [],
            ),
        ),
        event_summary=str(spec["summary"]),
        event_source_status="resolved",
        event_evidence=(
            f"完整解锁链：{event_chain}",
            "事件前：数值好感度已达到婚后高心级，但事件权限未解锁。"
            if condition == "before"
            else "事件后：完整事件链已确认，允许使用对应阶段的亲密权限。",
        ),
    )


def relationship_gating_cases() -> tuple[CharacterQualityCase, ...]:
    by_case_id = {case.case_id: case for case in topic_start_adaptive_cases()}
    cases: list[CharacterQualityCase] = []
    for spec in RELATIONSHIP_GATING_SPECS:
        base_case_id = str(spec["base_case_id"])
        try:
            base_case = by_case_id[base_case_id]
        except KeyError as exc:
            raise RuntimeError(f"关系事件锁缺少基础案例：{base_case_id}") from exc
        cases.extend(
            (
                _build_case(spec, base_case, "before"),
                _build_case(spec, base_case, "after"),
            )
        )
    return tuple(cases)


RELATIONSHIP_GATING_CASES: tuple[CharacterQualityCase, ...] = relationship_gating_cases()
