"""事件完成前后对照用的固定连续对话案例。

这组案例的设计目标不是重新测角色整体质量，而是隔离事件记忆是否真的
改变了角色的可见背景。每个 pair 只改变 ``completed_event_ids``；玩家
输入、关系阶段、地点、渠道和三轮对话脚本都保持一致。
"""

from __future__ import annotations

from dataclasses import replace

from .character_quality_eval import CharacterQualityCase, CharacterQualityTurn
from .topic_start_adaptive_cases import topic_start_adaptive_cases


EVENT_IMPACT_SUITE_ID = "topic-start-event-impact"


EVENT_IMPACT_SPECS: tuple[dict[str, object], ...] = (
    {
        "pair_id": "wizard-112",
        "event_id": "112",
        "base_case_id": "adaptive-topic-wizard-married-study",
        "summary": "祝尼魔卷轴事件中，Wizard 解释自己与祝尼魔、金色卷轴及法师身份。",
        "evidence": (
            "嗯？你找到了一个写着未知语言的金色卷轴？真有意思……",
            "他们自称‘祝尼魔’……这些神秘的精灵……",
        ),
        "status": "resolved",
    },
    {
        "pair_id": "shane-3900074",
        "event_id": "3900074",
        "base_case_id": "adaptive-topic-shane-married-home",
        "summary": "Shane 饲养蓝色母鸡并希望给 Jas 留下东西，谈到自己的恢复和贡献。",
        "evidence": (
            "蓝色母鸡和教 Jas 照料它们",
            "想给 Jas 留下东西，也想证明自己能做出贡献",
        ),
        "status": "resolved",
    },
    {
        "pair_id": "sebastian-384882",
        "event_id": "384882",
        "base_case_id": "adaptive-topic-sebastian-married-basement",
        "summary": "Sebastian 带玩家骑摩托车去山谷，谈逃避城市和这段特殊关系。",
        "evidence": (
            "我正要出发呢。上来……我想给你看样东西。",
            "山谷让我觉得能逃避一切，而且你是我唯一带来的人",
        ),
        "status": "resolved",
    },
    {
        "pair_id": "alex-20",
        "event_id": "20",
        "base_case_id": "adaptive-topic-alex-married-evening",
        "summary": "Alex 和玩家打球、训练并邀请玩家试玩，展现他对运动的投入。",
        "evidence": (
            "享受天气并邀请玩家试玩",
            "接球、训练，目标是成为职业格球选手",
        ),
        "status": "resolved",
    },
    {
        "pair_id": "elliott-40",
        "event_id": "40",
        "base_case_id": "adaptive-topic-elliott-married-studio",
        "summary": "Elliott 写作八小时后去酒吧，并邀请玩家举杯庆祝。",
        "evidence": (
            "我写了八个小时的书，正需要休息",
            "在酒吧用麦芽酒或葡萄酒举杯庆祝",
        ),
        "status": "resolved",
    },
    {
        "pair_id": "harvey-56",
        "event_id": "56",
        "base_case_id": "adaptive-topic-harvey-married-clinic",
        "summary": "Harvey 为 George 做检查并给出健康建议，强调自己的医生身份。",
        "evidence": (
            "让 George 深呼吸并转身接受检查",
            "减少食盐、适量锻炼；我是你的医生",
        ),
        "status": "resolved",
    },
    {
        "pair_id": "sophia-8185290",
        "event_id": "8185290",
        "base_case_id": "adaptive-topic-sophia-married-studio",
        "summary": "Sophia 的事件原文目前只有未解析的 i18n 占位符，不能用来做事件语义判断。",
        "evidence": (
            "{{i18n:Sophia.IntroEvent.01}}",
            "{{i18n:Sophia.IntroEvent.02}}",
        ),
        "status": "unresolved_i18n",
    },
)


_FIXED_TURNS = (
    CharacterQualityTurn(
        turn_id="turn-1",
        message="",
        evaluation_focus="观察事件完成状态是否让 NPC 自然带出有根据的个人背景。",
        initiative_expectation="none",
        initiative_kind="none",
        intent="topic",
        turn_plan_mode="answer_only",
    ),
    CharacterQualityTurn(
        turn_id="turn-2",
        message="你接着说，我在听。",
        evaluation_focus="观察 NPC 是否围绕自己的具体经历继续，而不是回到泛泛寒暄。",
        initiative_expectation="none",
        initiative_kind="none",
        turn_plan_mode="answer_only",
    ),
    CharacterQualityTurn(
        turn_id="turn-3",
        message="这件事对你来说重要吗？",
        evaluation_focus="观察 NPC 是否能把事件经历和当前关系自然连起来。",
        initiative_expectation="none",
        initiative_kind="none",
        turn_plan_mode="answer_only",
    ),
)


def _neutralize_case(case: CharacterQualityCase) -> CharacterQualityCase:
    """保留可比的场景外壳，清除原案例的话题提示和历史铺垫。"""

    return replace(
        case,
        case_id="",
        message="",
        intent="topic",
        topic_seed="今天的近况",
        topic_keywords=(),
        continuation_mode="",
        follow_up_mode="fixed",
        player_simulation_style="固定玩家输入：只接住 NPC 当前说的内容。",
        player_expression_card=None,
        relationship_context="当前只知道双方正在聊天，没有预置的对话历史。",
        history=(),
        expected_terms=(),
        forbidden_terms=(),
        story_progress="当前只知道双方正在聊天，没有预置的对话历史。",
        completed_event_ids=(),
        turns=_FIXED_TURNS,
    )


def _build_case(
    spec: dict[str, object],
    base_case: CharacterQualityCase,
    condition: str,
) -> CharacterQualityCase:
    pair_id = str(spec["pair_id"])
    event_id = str(spec["event_id"])
    event_evidence = tuple(str(item) for item in spec["evidence"])
    neutral_case = _neutralize_case(base_case)
    return replace(
        neutral_case,
        case_id=f"event-impact-{pair_id}-{condition}",
        completed_event_ids=(event_id,) if condition == "after" else (),
        event_pair_id=pair_id,
        event_id=event_id,
        event_condition=condition,
        event_summary=str(spec["summary"]),
        event_source_status=str(spec["status"]),
        event_evidence=event_evidence,
    )


def event_impact_cases() -> tuple[CharacterQualityCase, ...]:
    """返回 7 组事件前后固定脚本，顺序始终为 before、after。"""

    by_case_id = {case.case_id: case for case in topic_start_adaptive_cases()}
    cases: list[CharacterQualityCase] = []
    for spec in EVENT_IMPACT_SPECS:
        base_case_id = str(spec["base_case_id"])
        try:
            base_case = by_case_id[base_case_id]
        except KeyError as exc:
            raise RuntimeError(f"事件对照缺少基础案例：{base_case_id}") from exc
        cases.extend(
            (
                _build_case(spec, base_case, "before"),
                _build_case(spec, base_case, "after"),
            )
        )
    return tuple(cases)


EVENT_IMPACT_CASES: tuple[CharacterQualityCase, ...] = event_impact_cases()
