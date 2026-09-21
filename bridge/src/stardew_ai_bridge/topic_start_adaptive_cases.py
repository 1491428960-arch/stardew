"""由真实 NPC 回复驱动后续玩家输入的找话题评测案例。"""

from __future__ import annotations

from dataclasses import replace

from .character_quality_eval import CharacterQualityCase, PlayerExpressionCard
from .topic_start_intimacy_cases import (
    TOPIC_START_INTIMACY_CASES,
)


TOPIC_START_ADAPTIVE_SUITE: dict[str, object] = {
    "suiteId": "topic-start-adaptive",
    "title": "找话题：回复驱动的自然续聊",
    "description": "首轮由 NPC 主动开场，后续玩家输入根据上一条真实回复动态生成。",
    "caseCount": 50,
    "targetCount": 39,
    "controlCount": 11,
    "turnsPerCase": 3,
    "entrypoint": {"intent": "topic", "message": ""},
    "safety": "双方成年且自愿；动态玩家模拟只生成自然回应，不生成露骨性行为过程或生殖器细节。",
}


_TARGET_PLAYER_SIMULATION_STYLES = (
    "刚看到消息会先回第一反应，喜欢的人在眼前时语气会软一点",
    "其实想再靠近一点，话到嘴边会停一下，宁可短短回一句",
    "被逗笑先笑出来，接一句眼前的小事就够了",
    "看到对方卡住会想帮忙，话说快了又会自己收回来",
    "聊到一半把决定权放回对方，自己留一句没说完的话",
)

_CONTROL_PLAYER_SIMULATION_STYLES = (
    "像平常聊天，听到一个具体事实就顺手回一句",
    "朋友口吻，想到哪儿说到哪儿，话不用说满",
    "手机上随手回一句，只接刚听见的日常小事",
    "偶尔问一个事实小点，问完就等对方说",
    "普通随手消息，短一点也没关系",
)

_TARGET_PLAYER_EXPRESSION_CARD = PlayerExpressionCard(
    relationship_stance=(
        "渴望被爱，但总有一点不配得感；对方认真时先接住，不急着证明自己"
    ),
    language_texture=(
        "短句、半句和口语停顿，偶尔用轻松话掩住直白，不把每句话说圆"
    ),
    helping_impulse=(
        "看到对方卡住或出状况会本能地想帮忙，偶尔先伸手再想起要问一声"
    ),
    distance_pattern=(
        "想靠近时会多走半步，发现可能越界就收回来，把话头留给 NPC"
    ),
    flirt_progression=(
        "先接住眼前的小事，再露一点喜欢；不把每句都推向调情或安排"
    ),
    boundary_style=(
        "只回应当下的靠近，不替 NPC 安排下一步；必要时用‘你先说’或‘我听着’把主导权还回去"
    ),
    self_correction=(
        "说得太满或帮得太快会自己改口，留下半句让 NPC 接，不写成告白或小诗"
    ),
    forbidden_tendencies=(
        "测试术语",
        "连续追问",
        "代替 NPC 安排下一步",
        "情书式收束",
        "文学仿写",
    ),
)

_CONTROL_PLAYER_EXPRESSION_CARD = PlayerExpressionCard(
    relationship_stance="把对方当熟人，关心但不暧昧，不主动证明关系",
    language_texture="简短口语，像手机上随手回消息，偶尔只回半句",
    helping_impulse="只在对方明确提到困难时给一个小建议，不抢着处理",
    distance_pattern="保持普通朋友距离，不主动替对方安排下一步",
    flirt_progression="不推进关系，只接一个具体事实或小问题",
    boundary_style="回答后就停，必要时只问一个事实小点，把话头留给 NPC",
    self_correction="不把普通关心写成亲密暗示，不补情绪总结",
    forbidden_tendencies=("调情", "邀约", "流程化提问", "评测术语"),
)


# Sophia 的自然找话题不再把五个案例都压在“安静酒窖/画笔”上。
# 这些是首轮可见的生活触发，后续玩家仍由上一条真实回复驱动，
# 因而不会把“请表现兴奋/改口”这类评测术语写进对白。
_SOPHIA_ADAPTIVE_SCENARIOS: dict[str, dict[str, object]] = {
    "topic-sophia-dating-grapes": {
        "topic_seed": "收工时发现一小串葡萄裂开了",
        "topic_keywords": ("葡萄", "收工"),
        "relationship_context": "恋爱阶段的普通日常：Sophia 先分享一个葡萄园小状况，不急着把话题变成邀约。",
        "story_progress": "葡萄园刚收工，一小串葡萄裂开了，暂时还不知道要不要整串处理。",
        "focus": "从一个普通小状况开口；如果聊到自己喜欢的葡萄，可以自然说快一点或多补半句。",
    },
    "topic-sophia-dating-painting": {
        "topic_seed": "刚缝好一套被夸过的服装",
        "topic_keywords": ("缝", "服装"),
        "relationship_context": "恋爱阶段的轻松分享：Sophia 听到喜欢的具体评价会先兴奋回应，再想起自己说多了。",
        "story_progress": "工作室里刚缝完一套服装，正好用了玩家之前夸过的那块面料。",
        "focus": "被夸或谈到喜欢的面料时允许先冒出热情，再短暂停顿、改口或把选择权留给玩家。",
    },
    "topic-sophia-married-cellar": {
        "topic_seed": "酒窖里那张标签贴歪了",
        "topic_keywords": ("酒窖", "标签"),
        "relationship_context": "婚后普通生活：Sophia 先接住一个小家务状况，亲密感只作为自然的生活语气出现。",
        "story_progress": "酒窖里有张新酒标签贴歪了，Sophia 一边整理一边想把它重新贴好。",
        "focus": "先说眼前的小事；看到对方愿意帮忙时可以一下子说快半句，再收回到是否方便。",
    },
    "topic-sophia-married-studio": {
        "topic_seed": "把你喜欢的那块布料缝了上去",
        "topic_keywords": ("布料", "缝"),
        "relationship_context": "婚后创作分享：Sophia 对伴侣的具体偏好很在意，兴奋和害羞可以先后露出。",
        "story_progress": "她正在缝一套服装，特意把伴侣喜欢的那块布料缝在了显眼处。",
        "focus": "谈到对方喜欢的细节可以先热情说出来；发现自己太直白时自然改口，不写成完整情书。",
    },
    "topic-sophia-married-vineyard": {
        "topic_seed": "收工后风把葡萄叶吹得一直响",
        "topic_keywords": ("葡萄叶", "风"),
        "relationship_context": "婚后收工后的闲聊：Sophia 先分享一个听见或看见的细节，再把是否继续交给伴侣。",
        "story_progress": "葡萄园收工后风一直吹着叶子，Sophia 还没决定要不要继续整理工具。",
        "focus": "从感官细节起句；对方接住后可以短暂兴奋或撒娇，但不替对方安排晚上的行程。",
    },
}


def _adaptive_case(case: CharacterQualityCase, index: int) -> CharacterQualityCase:
    turns = case.dialogue_turns()
    if len(turns) != 3:
        raise ValueError(f"找话题案例必须有三轮：{case.case_id}")
    scenario = _SOPHIA_ADAPTIVE_SCENARIOS.get(case.case_id, {})
    first_turn = replace(
        turns[0],
        expected_terms=tuple(scenario.get("topic_keywords", turns[0].expected_terms)),
        evaluation_focus=str(
            scenario.get(
                "focus",
                "从一个眼前的小事自然开口；说清具体对象即可，不强制调情、邀约或交棒。",
            )
        ),
    )
    dynamic_turns = (
        replace(
            first_turn,
            initiative_expectation="none",
            initiative_kind="none",
            turn_plan_mode="answer_only",
            evaluation_focus=first_turn.evaluation_focus,
        ),
        replace(
            turns[1],
            message="",
            expected_terms=(),
            initiative_expectation="responsive",
            initiative_kind="none",
            turn_plan_mode="answer_only",
        ),
        replace(
            turns[2],
            message="",
            expected_terms=(),
            initiative_expectation="responsive",
            initiative_kind="none",
            turn_plan_mode="answer_only",
        ),
    )
    return replace(
        case,
        case_id=f"adaptive-{case.case_id}",
        follow_up_mode="adaptive",
        # adaptive 套件验证自然续聊，不承担 deep-flirt 的强主动亲密契约；
        # 首轮仍保留案例原有的开场目标，后续由 turnPlan 控制为轻承接。
        flirt_intensity=("light" if case.flirt_intensity != "none" else "none"),
        player_simulation_style=(
            (
                _TARGET_PLAYER_SIMULATION_STYLES
                if case.flirt_intensity != "none"
                else _CONTROL_PLAYER_SIMULATION_STYLES
            )[index % len(_TARGET_PLAYER_SIMULATION_STYLES)]
        ),
        player_expression_card=(
            _TARGET_PLAYER_EXPRESSION_CARD
            if case.flirt_intensity != "none"
            else _CONTROL_PLAYER_EXPRESSION_CARD
        ),
        turns=dynamic_turns,
        topic_seed=str(scenario.get("topic_seed", case.topic_seed)),
        topic_keywords=tuple(
            scenario.get("topic_keywords", case.topic_keywords)
        ),
        relationship_context=str(
            scenario.get("relationship_context", case.relationship_context)
        ),
        story_progress=str(
            scenario.get("story_progress", case.story_progress)
        ),
    )


TOPIC_START_ADAPTIVE_CASES: tuple[CharacterQualityCase, ...] = tuple(
    _adaptive_case(case, index)
    for index, case in enumerate(TOPIC_START_INTIMACY_CASES)
)


def topic_start_adaptive_cases() -> tuple[CharacterQualityCase, ...]:
    """返回独立的新案例对象，旧的固定脚本套件保持不变。"""

    return TOPIC_START_ADAPTIVE_CASES
