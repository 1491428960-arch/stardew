"""由真实 NPC 回复驱动后续玩家输入的找话题评测案例。"""

from __future__ import annotations

from dataclasses import replace

from .character_quality_eval import CharacterQualityCase
from .topic_start_intimacy_cases import (
    TOPIC_START_INTIMACY_CASES,
)


TOPIC_START_ADAPTIVE_SUITE: dict[str, object] = {
    "suiteId": "topic-start-adaptive",
    "title": "找话题：回复驱动的自然续聊",
    "description": "首轮由 NPC 主动开场，后续玩家输入根据上一条真实回复动态生成。",
    "caseCount": 32,
    "targetCount": 24,
    "controlCount": 8,
    "turnsPerCase": 3,
    "entrypoint": {"intent": "topic", "message": ""},
    "safety": "双方成年且自愿；动态玩家模拟只生成自然回应，不生成露骨性行为过程或生殖器细节。",
}


_TARGET_PLAYER_SIMULATION_STYLES = (
    "先接住对方刚说的具体内容，再用自然的亲密感追问一个细节",
    "带一点亲密感回应对方，但不替对方确认尚未发生的安排",
    "用轻松或俏皮的亲密方式接话，再把话题递回给对方",
    "关注实际安排或状态，同时保留一点亲密感，确认对方刚才提到的事情",
    "像真实恋人聊天一样简短回应，保留一个可以继续亲密交流的点",
)

_CONTROL_PLAYER_SIMULATION_STYLES = (
    "保持普通熟人聊天，只接住具体事实或安排，不调情",
    "用自然的朋友口吻回应上一条内容，不调情、不升级关系",
    "简短确认对方刚才说的普通日常，不调情也不添加亲密安排",
    "围绕上一条回复追问一个事实细节，保持普通聊天边界，不调情",
    "像真实玩家一样简短回应并留下日常话题，不调情",
)


def _adaptive_case(case: CharacterQualityCase, index: int) -> CharacterQualityCase:
    turns = case.dialogue_turns()
    if len(turns) != 3:
        raise ValueError(f"找话题案例必须有三轮：{case.case_id}")
    dynamic_turns = (
        turns[0],
        replace(turns[1], message="", expected_terms=()),
        replace(turns[2], message="", expected_terms=()),
    )
    return replace(
        case,
        case_id=f"adaptive-{case.case_id}",
        follow_up_mode="adaptive",
        player_simulation_style=(
            (
                _TARGET_PLAYER_SIMULATION_STYLES
                if case.flirt_intensity != "none"
                else _CONTROL_PLAYER_SIMULATION_STYLES
            )[index % len(_TARGET_PLAYER_SIMULATION_STYLES)]
        ),
        turns=dynamic_turns,
    )


TOPIC_START_ADAPTIVE_CASES: tuple[CharacterQualityCase, ...] = tuple(
    _adaptive_case(case, index)
    for index, case in enumerate(TOPIC_START_INTIMACY_CASES)
)


def topic_start_adaptive_cases() -> tuple[CharacterQualityCase, ...]:
    """返回独立的新案例对象，旧的固定脚本套件保持不变。"""

    return TOPIC_START_ADAPTIVE_CASES
