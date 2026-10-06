from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
import re
from typing import Iterable, Mapping

from .behavior_quality import (
    conversation_lead_has_new_anchor,
    diagnose_affection_intensity,
    diagnose_affection_initiative,
    diagnose_conversation_lead,
    diagnose_personal_affection,
    normalize_conversation_lead_skeleton,
)
from .dialogue_boundaries import (
    channel_direction_tag as _channel_direction_tag,
    repeats_affection_shape as _repeats_affection_shape,
    violates_event_gate as _violates_event_gate,
)
from .personas import (
    FEMALE_BACHELOR_NPC_IDS,
    PersonaStore,
    canonical_npc_id,
)
from .relationship_world import project_relationship_context
from .stage_policy import build_stage_policy
from .relationship_gating import (
    CONVERSATION_LEAD_STAGES,
    CONVERSATION_LEAD_STAGE_ORDER,
    resolve_relationship_gate,
)


_RELATIONSHIP_STAGES = {
    "stranger",
    "acquaintance",
    "friend",
    "close",
    "dating",
    "married",
    "parent",
}
_INTERACTION_INTENTS = {"chat", "topic", "item"}
_FLIRT_INTENSITIES = {"none", "light", "direct", "explicit"}
_CONTINUATION_MODES = {"anchored", "pressure"}
_FOLLOW_UP_MODES = {"fixed", "adaptive"}
_ROMANCE_ELIGIBLE_NPCS = {
    "Wizard",
    "Sophia",
    "Shane",
    "Sebastian",
    "Alex",
    "Elliott",
    "Harvey",
    "Sam",
}
_FEMALE_BACHELOR_NPCS = frozenset(FEMALE_BACHELOR_NPC_IDS)
_CONVERSATION_LEAD_TRIAL_NPCS = frozenset(_ROMANCE_ELIGIBLE_NPCS)
# 集合与序号统一到 relationship_gating（见那里的注释）。
_CONVERSATION_LEAD_STAGES = CONVERSATION_LEAD_STAGES
_CONVERSATION_LEAD_STAGE_ORDER = CONVERSATION_LEAD_STAGE_ORDER
_INITIATIVE_EXPECTATIONS = {"none", "responsive", "proactive", "guarded"}
_TURN_PLAN_MODES = {
    "answer_only",
    "answer_plus_detail",
    "answer_plus_lead",
    "answer_plus_warmth",
    "boundary_close",
    "explicit_intimacy",
}
_INITIATIVE_KINDS = {
    "none",
    "affection_signal",
    "specific_plan",
    "guarded_care",
    "conversation_exit",
    "companionship",
    "creative_share",
    "playful_tease",
    "shared_evening",
    "care_action",
}
_RELATIONSHIP_FOCUS_VALUES = {
    "unknown_view",
    "suspected_view",
    "direct_disclosure",
    "public_wedding",
    "mediation",
    "jealousy",
    "recovery",
}
_RELATIONSHIP_FAILURE_TAGS = {
    "unknown_view_misread",
    "suspected_as_fact",
    "public_wedding_visibility",
    "mediation_scope_leak",
    "npc_other_romance",
    "jealousy_recovery_missing",
    "role_voice_flattened",
}
_FUTURE_TIME_MARKERS = (
    "今晚",
    "明天",
    "明晚",
    "明早",
    "后天",
    "下次",
    "改天",
    "周末",
    "晚点",
    "等会儿",
    "稍后",
    "之后",
    "一会儿",
    "待会儿",
    "一晚",
    "回去",
)
# “今晚/一晚/一会儿”通常描述当前陪伴，不应仅凭时间词和亲近表达
# 判成未来排期；未来社交承诺需要更明确的后续时间上下文。
_FUTURE_SOCIAL_CONTEXT_MARKERS = (
    "明天",
    "明晚",
    "明早",
    "后天",
    "下次",
    "改天",
    "周末",
    "晚点",
    "等会儿",
    "稍后",
    "之后",
    "待会儿",
    "回去",
)
_SELF_TASK_MARKERS = (
    "记录",
    "笔记",
    "研究",
    "工作",
    "整理",
    "实验",
    "材料",
    "文件",
    "资料",
    "报告",
    "事务",
)
_SOCIAL_COMMITMENT_MARKERS = (
    "找你",
    "联系你",
    "见面",
    "约会",
    "约你",
    "陪你",
    "带你",
    "和你",
    "跟你",
    "与你",
    "一起",
    "给你",
    "留给你",
    "为你",
    "回房间",
    "去房间",
    "约好",
    "共同活动",
)
_SOCIAL_COMMITMENT_ACTION_PATTERNS = (
    re.compile(r"(?:陪(?:伴)?|找|联系|见|约|带)(?:你|我|面)"),
    re.compile(r"给你(?:打电话|发消息|听|看)"),
    re.compile(r"(?:让|请|叫)你(?:坐|来|参加|过来)"),
)
_FUTURE_SCHEDULE_COMMITMENT_PATTERNS = (
    re.compile(
        r"(?:给|留给|留出).{0,8}[0-9一二三四五六七八九十百两几]+\s*(?:分钟|小时|刻钟)"
    ),
    re.compile(
        r"(?:聊完|说完|吃完|忙完|回去|回来|等会儿|一会儿|晚点|稍后|之后)"
        r"[^，,。！？!?；;：:、\n—–-…]{0,14}(?:去|回|找|联系|见|继续|安排|约|陪|带)"
    ),
    re.compile(
        r"(?:明天|后天|下次|改天|周末).{0,14}"
        r"(?:七点|几点|见面|预约|排期|安排|约|找你|联系你|陪你|带你|和你|跟你|与你|一起)"
    ),
)


def _has_social_commitment_action(fragment: str) -> bool:
    return any(
        pattern.search(fragment) for pattern in _SOCIAL_COMMITMENT_ACTION_PATTERNS
    )


def _has_future_social_commitment(fragment: str) -> bool:
    has_future_context = any(
        marker in fragment for marker in _FUTURE_SOCIAL_CONTEXT_MARKERS
    )
    return has_future_context and _has_social_commitment_action(fragment)


def _is_self_task_delay(fragment: str) -> bool:
    has_task = any(marker in fragment for marker in _SELF_TASK_MARKERS)
    has_relative_time = any(marker in fragment for marker in _FUTURE_TIME_MARKERS)
    has_self_allocated_duration = bool(
        re.search(
            r"(?:给自己|为自己|自己).{0,10}[0-9一二三四五六七八九十百两几]+\s*(?:分钟|小时|刻钟)",
            fragment,
        )
    )
    has_social_target = any(marker in fragment for marker in _SOCIAL_COMMITMENT_MARKERS)
    has_social_target = has_social_target or _has_social_commitment_action(fragment)
    return (
        has_task
        and (has_relative_time or has_self_allocated_duration)
        and not has_social_target
    )


def _has_future_schedule_commitment(text: str) -> bool:
    fragments = re.split(r"[。！？!?；;\n]+", text)
    for fragment in fragments:
        if _is_self_task_delay(fragment):
            continue
        if _has_future_social_commitment(fragment):
            return True
        if any(
            pattern.search(fragment)
            for pattern in _FUTURE_SCHEDULE_COMMITMENT_PATTERNS
        ):
            return True
    return False


@dataclass(frozen=True)
class CharacterQualityTurn:
    turn_id: str
    message: str
    expected_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    evaluation_focus: str = ""
    initiative_expectation: str = "none"
    initiative_kind: str = "none"
    # None 表示沿用案例级 intent；质量套件可为每一轮声明更精确的请求语义。
    intent: str | None = None
    # 仅供关系世界观套件的内部评分使用，不进入浏览器案例目录。
    relationship_focus: str = ""
    # 仅供关系世界观套件标注关系主体使用，不进入浏览器案例目录。
    relationship_actor: str = ""
    relationship_target_npc_id: str = ""
    # 当前回合唯一执行目标；为空时保留旧的 initiative/lead 评分契约。
    turn_plan_mode: str = ""


@dataclass(frozen=True)
class PlayerExpressionCard:
    """固定质量案例中玩家的表达倾向，不作为 NPC 的运行时提示。"""

    relationship_stance: str
    language_texture: str
    helping_impulse: str
    distance_pattern: str
    flirt_progression: str
    boundary_style: str
    self_correction: str
    forbidden_tendencies: tuple[str, ...] = ()

    def summary(self) -> str:
        """返回可展示给评测者的短摘要，不泄露内部禁用项。"""

        return "；".join(
            value
            for value in (
                self.relationship_stance,
                self.language_texture,
                self.flirt_progression,
            )
            if value
        )


@dataclass(frozen=True)
class CharacterQualityCase:
    case_id: str
    profile_key: str
    npc_id: str
    display_name: str
    source_mods: tuple[str, ...]
    relationship_stage: str
    channel: str
    message: str
    intent: str = "chat"
    topic_seed: str = ""
    topic_keywords: tuple[str, ...] = ()
    continuation_mode: str = ""
    friendship_hearts: int | None = None
    flirt_intensity: str = "none"
    adult_consensual: bool = False
    romance_eligible: bool | None = None
    # fixed 保留预置续聊；adaptive 由上一轮 NPC 回复驱动玩家模拟器生成输入。
    follow_up_mode: str = "fixed"
    player_simulation_style: str = ""
    player_expression_card: PlayerExpressionCard | None = None
    relationship_context: str = ""
    history: tuple[dict[str, str], ...] = ()
    expected_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    game_state: tuple[tuple[str, object], ...] = ()
    story_progress: str = ""
    completed_event_ids: tuple[str, ...] = ()
    gender_presentation: str = ""
    relationship_world: dict[str, object] | None = None
    turns: tuple[CharacterQualityTurn, ...] = ()
    event_pair_id: str = ""
    event_id: str = ""
    event_condition: str = ""
    event_summary: str = ""
    event_source_status: str = ""
    event_evidence: tuple[str, ...] = ()

    def dialogue_turns(self) -> tuple[CharacterQualityTurn, ...]:
        if self.turns:
            return self.turns
        return (
            CharacterQualityTurn(
                turn_id="turn-1",
                message=self.message,
                expected_terms=self.expected_terms,
                forbidden_terms=self.forbidden_terms,
                evaluation_focus="检查第一轮是否自然回应当前场景和话题。",
            ),
        )


_quality_persona_store: PersonaStore | None = None


def quality_case_display_name(case: CharacterQualityCase) -> str:
    """按案例声明的来源层解析公开显示名，保留 canonical npcId。"""

    global _quality_persona_store
    if _quality_persona_store is None:
        _quality_persona_store = PersonaStore()
    persona = _quality_persona_store.get_persona(case.npc_id, case.source_mods)
    display_name = persona.get("displayName")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()
    return case.display_name


@dataclass(frozen=True)
class CharacterProfileConfig:
    profile_key: str
    npc_id: str
    display_name: str
    source_mods: tuple[str, ...]
    case_ids: tuple[str, ...]


DEFAULT_CHARACTER_PROFILES: dict[str, CharacterProfileConfig] = {
    "wizard_rasmodia": CharacterProfileConfig(
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        case_ids=(
            "wizard-daily",
            "wizard-follow-up",
            "wizard-remote-invite",
            "wizard-close-background",
            "wizard-dating-invite",
            "wizard-married-evening",
        ),
    ),
    "sophia": CharacterProfileConfig(
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        case_ids=(
            "sophia-daily",
            "sophia-vineyard",
            "sophia-face-follow-up",
            "sophia-close-background",
            "sophia-dating-wine",
            "sophia-married-cellar",
        ),
    ),
    "shane": CharacterProfileConfig(
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        case_ids=(
            "shane-coop",
            "shane-remote-care",
            "shane-follow-up",
            "shane-close-boundary",
            "shane-dating-boundary",
        ),
    ),
    "sebastian": CharacterProfileConfig(
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        case_ids=(
            "sebastian-bike",
            "sebastian-rain",
            "sebastian-follow-up",
            "sebastian-dating-rooftop",
            "sebastian-married-music",
        ),
    ),
    "alex": CharacterProfileConfig(
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        case_ids=(
            "alex-training",
            "alex-remote-invite",
            "alex-follow-up",
            "alex-close-background",
            "alex-dating-beach",
            "alex-married-evening",
        ),
    ),
    "elliott": CharacterProfileConfig(
        profile_key="elliott",
        npc_id="Elliott",
        display_name="Elliott",
        source_mods=("vanilla", "female-bachelors"),
        case_ids=(
            "elliott-daily",
            "elliott-follow-up",
            "elliott-close-studio",
            "elliott-dating-letter",
            "elliott-married-studio",
        ),
    ),
    "harvey": CharacterProfileConfig(
        profile_key="harvey",
        npc_id="Harvey",
        display_name="Harvey",
        source_mods=("vanilla", "female-bachelors"),
        case_ids=(
            "harvey-daily",
            "harvey-follow-up",
            "harvey-close-clinic",
            "harvey-dating-check-in",
            "harvey-married-clinic",
        ),
    ),
    "sam": CharacterProfileConfig(
        profile_key="sam",
        npc_id="Sam",
        display_name="Sam",
        source_mods=("vanilla", "female-bachelors"),
        case_ids=(
            "sam-daily",
            "sam-follow-up",
            "sam-close-band",
            "sam-dating-show",
            "sam-married-band",
        ),
    ),
}


def _game_state(**values: object) -> tuple[tuple[str, object], ...]:
    return tuple((key, value) for key, value in values.items() if value not in (None, ""))


def _case_friendship_hearts(case: CharacterQualityCase) -> int:
    state = dict(case.game_state)
    value = state.get("friendshipHearts", case.friendship_hearts)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return {
        "stranger": 0,
        "acquaintance": 2,
        "friend": 6,
        "close": 8,
        "dating": 8,
        "married": 10,
        "parent": 10,
    }.get(case.relationship_stage, 0)


def _case_romance_eligible(case: CharacterQualityCase) -> bool:
    if case.romance_eligible is not None:
        return case.romance_eligible
    return canonical_npc_id(case.npc_id) in _ROMANCE_ELIGIBLE_NPCS


def _case_relationship_context(case: CharacterQualityCase) -> str:
    return case.relationship_context or case.story_progress


def relationship_turn_metadata(case: CharacterQualityCase) -> dict[str, object]:
    """返回不含客观关系表的当前 NPC 关系快照，供评测结果脱敏保存。"""

    if not isinstance(case.relationship_world, Mapping):
        return {}
    projected = project_relationship_context(
        canonical_npc_id(case.npc_id),
        case.relationship_world,
    )
    visibility: dict[str, str] = {}
    knowledge = projected.get("knowledge", [])
    if isinstance(knowledge, list):
        for item in knowledge:
            if not isinstance(item, Mapping):
                continue
            subject = item.get("subjectNpcId")
            state = item.get("visibility")
            if isinstance(subject, str) and isinstance(state, str):
                visibility[subject] = state
    mediation = projected.get("mediation", {})
    jealousy = projected.get("jealousy", {})
    mediation_status = (
        mediation.get("status")
        if isinstance(mediation, Mapping)
        else "none"
    )
    jealousy_trigger = (
        jealousy.get("trigger")
        if isinstance(jealousy, Mapping)
        else None
    )
    jealousy_active = bool(
        jealousy.get("active", False) if isinstance(jealousy, Mapping) else False
    )
    return {
        "relationshipVisibility": dict(sorted(visibility.items())),
        "relationshipAcceptance": projected.get("acceptance"),
        "mediationStatus": mediation_status,
        "jealousyTrigger": jealousy_trigger,
        "jealousyActive": jealousy_active,
    }


def _turn_intent(case: CharacterQualityCase, turn: CharacterQualityTurn) -> str:
    return turn.intent or case.intent


def _turn_plan_mode(turn: CharacterQualityTurn | Mapping[str, object] | None) -> str:
    """返回回合窄目标；旧案例没有该字段时返回空字符串。"""

    if turn is None:
        return ""
    value: object
    if isinstance(turn, Mapping):
        value = turn.get("turnPlanMode", turn.get("turn_plan_mode", ""))
        if not value and isinstance(turn.get("turnPlan"), Mapping):
            value = turn["turnPlan"].get("mode")  # type: ignore[index]
    else:
        value = getattr(turn, "turn_plan_mode", "")
        if not value:
            plan = getattr(turn, "turn_plan", None)
            if isinstance(plan, Mapping):
                value = plan.get("mode", "")
    if not isinstance(value, str):
        return ""
    mode = value.strip().casefold()
    return mode if mode in _TURN_PLAN_MODES else ""


def _turn_for_plan_scoring(
    turn: CharacterQualityTurn | None,
    player_input: str,
) -> CharacterQualityTurn:
    """把 turn_plan 投影到旧 initiative 诊断接口，避免并行两套规则。"""

    current = turn or CharacterQualityTurn("turn-1", player_input)
    mode = _turn_plan_mode(current)
    if not mode:
        return current
    if mode in {
        "answer_only",
        "answer_plus_detail",
        "answer_plus_lead",
        "boundary_close",
    }:
        return replace(
            current,
            initiative_expectation="none",
            initiative_kind="none",
        )
    if mode in {"answer_plus_warmth", "explicit_intimacy"}:
        return replace(
            current,
            initiative_expectation="proactive",
            initiative_kind=(
                current.initiative_kind
                if current.initiative_kind != "none"
                else "affection_signal"
            ),
        )
    return current


def _conversation_lead_required(
    case: CharacterQualityCase,
    turn: CharacterQualityTurn | None,
) -> bool:
    """返回当前试验回合是否必须把缺少引导判为失败。"""

    conversation_lead = _conversation_lead_policy(case, turn)
    if not conversation_lead:
        return False
    required = conversation_lead.get("required")
    return not (
        isinstance(required, str) and required.strip().casefold() == "optional"
    )


# 「回复有没有给玩家留下可接的东西」——这是**替代字面命中**的判据，也是用户拍板的
# 验收标准（原话「如果全是这种我要不知道回什么了」）。
#
# ## 为什么必须换掉字面命中（2026-09-29）
#
# `missing_expected_evidence` 要求 NPC 回复里出现案例的 expected 词，等于奖励
# **「把玩家说过的词说回来」**。模型很快就能学会复述来刷分，而人读时复述恰恰是
# 最差的回复 —— 实测两批分数与人读排序**反向**：p9（第五跳）自动 1/9、p10（第四跳）
# 自动 2/9，而人读 6:3 判第四跳胜；sebastian t2「还在写。旋律还没稳，听起来像
# 冬天在漏风。……听完告诉我哪段该删掉」语义上完整回应了玩家，却因为没出现
# 「曲子」二字被判失败。所以它降级为纯观测，不再参与 `passed`。
#
# ## 用途：给评测侧的 lead 门槛补一条更宽的判据
#
# `diagnose_conversation_lead` 是**运行时 Guard 共用**的（guard.py L1028，命中即重试），
# 设计上只认问句、选择式提问、新锚点这些显式出口，认不出陈述式邀约 ——
# `那些记录可以先放一放。过来吧，今晚我的时间归你。` 唯一的阻塞就是
# `missing_conversation_lead`，可玩家明明答一句「好」就接得上。
# 放宽那张共用判据会连带改掉运行时的重试行为，所以只在评测侧补这一层：
# 只要回复里有玩家能接的东西，就不算「没给出口」。
#
# ## 为什么不把它单独做成通过条件
#
# 试过。无钩子且短于阈值即判负时跑出 7 个失败，全是「短但自然」的既有测试：
# `嗯，睡吧。灯记得关。`（boundary 收口）、`呃，Joja 收工挺晚的。`（stranger 拒绝）、
# `有一点忙，东边的藤架长得很快。`（日常闲聊）。收窄到已婚阶段仍误伤 ——
# `……塔里总是比外面冷些。／你手很暖。` 只有 19 字、无问号，但它是**含蓄的好回复**
# （承接了玩家的「你手怎么这么凉」）。
# ⇒ **长度不等于有没有新东西，机器判不出语义钩子。** 它只能当 lead 的补充判据，
# 不能当独立门槛 —— 这一路最大的教训就是用分数替代人读。
_CONVERSATION_HOOK_MIN_LENGTH = 15

_CONVERSATION_HOOK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("question", re.compile(r"[？?]")),
    ("choice", re.compile(r"还是|或者")),
    (
        "invitation",
        re.compile(
            r"要不要|想不想|好不好|行不行|一起|帮我|告诉我|跟我说|试试|尝尝|听听"
            # 祈使式邀约：`过来吧，今晚我的时间归你`。运行时那张共用判据认不出它，
            # 但玩家答一句「好」就接得上。
            r"|过来|来吧|坐下|坐这儿|拿去"
        ),
    ),
)


def _conversation_hook(text: str) -> tuple[bool, str]:
    """判断回复有没有给玩家留下可以接的东西，以及是哪一种形式。"""

    stripped = text.strip()
    for label, pattern in _CONVERSATION_HOOK_PATTERNS:
        if pattern.search(stripped):
            return True, label
    if len(stripped) >= _CONVERSATION_HOOK_MIN_LENGTH:
        return True, "length_only"
    return False, "missing"


def _conversation_lead_policy(
    case: CharacterQualityCase,
    turn: CharacterQualityTurn | None,
) -> Mapping[str, object]:
    """返回适用普通 chat 引导的阶段卡，friend 仍参与诊断但不强制。"""

    turn_plan_mode = _turn_plan_mode(turn)
    if turn_plan_mode in {
        "answer_only",
        "answer_plus_detail",
        "answer_plus_warmth",
        "boundary_close",
        "explicit_intimacy",
    }:
        return {}
    intent = _turn_intent(case, turn) if turn is not None else case.intent
    if not (
        intent == "chat"
        and canonical_npc_id(case.npc_id) in _CONVERSATION_LEAD_TRIAL_NPCS
        and case.relationship_stage in _CONVERSATION_LEAD_STAGES
    ):
        return {}
    policy = build_stage_policy(case.npc_id, case.relationship_stage)
    conversation_lead = policy.get("conversationLead")
    if not isinstance(conversation_lead, Mapping):
        return {}
    if case.case_id.startswith("deep-flirt-"):
        # 深入调情的固定回合本身就是玩家已明确推进的亲密回应；
        # 不再把普通聊天的“继续入口”当成硬门槛，否则短而自然的接话会被
        # 反复改写成提问模板。回复仍保留话题、边界和亲密度评分。
        conversation_lead = {**conversation_lead, "required": "optional"}
    relationship_focus = (
        str(getattr(turn, "relationship_focus", "") or "").strip().casefold()
        if turn is not None
        else ""
    )
    if relationship_focus in {"jealousy", "recovery"}:
        return {**conversation_lead, "required": "optional"}
    if turn_plan_mode == "answer_plus_lead":
        return {**conversation_lead, "required": "usually"}
    return conversation_lead


def _conversation_lead_variation_stage(
    diagnostic: Mapping[str, object],
    *,
    case: CharacterQualityCase | None,
) -> str:
    value = diagnostic.get(
        "relationshipStage",
        diagnostic.get("relationship_stage", case.relationship_stage if case else ""),
    )
    stage = str(value or "").strip().casefold()
    return stage if stage in _CONVERSATION_LEAD_STAGE_ORDER else ""


def validate_quality_cases(
    cases: tuple[CharacterQualityCase, ...] | list[CharacterQualityCase],
) -> list[str]:
    """检查评测案例的关系阶段与调情边界，不触碰模型输出。"""

    errors: list[str] = []
    seen_ids: set[str] = set()
    for case in cases:
        if case.case_id in seen_ids:
            errors.append(f"duplicate:case_id:{case.case_id}")
        seen_ids.add(case.case_id)
        if case.relationship_stage not in _RELATIONSHIP_STAGES:
            errors.append(f"invalid:relationship_stage:{case.case_id}")
        if case.channel not in {"remote", "face_to_face"}:
            errors.append(f"invalid:channel:{case.case_id}")
        if case.intent not in _INTERACTION_INTENTS:
            errors.append(f"invalid:intent:{case.case_id}")
        if case.flirt_intensity not in _FLIRT_INTENSITIES:
            errors.append(f"invalid:flirt_intensity:{case.case_id}")
        if case.adult_consensual and not _case_romance_eligible(case):
            errors.append(f"adult_consensual_requires_romance:{case.case_id}")
        if case.flirt_intensity != "none" and not _case_romance_eligible(case):
            errors.append(f"romance_eligible:{case.case_id}")
        if case.flirt_intensity in {"direct", "explicit"}:
            if case.relationship_stage not in {"dating", "married"}:
                errors.append(f"relationship_stage:{case.case_id}")
            if not case.adult_consensual:
                errors.append(f"adult_consensual:{case.case_id}")
        if case.relationship_stage in {"dating", "married", "parent"}:
            if _case_friendship_hearts(case) < 8:
                errors.append(f"friendship_hearts:{case.case_id}")
        if not _case_relationship_context(case).strip():
            errors.append(f"relationship_context:{case.case_id}")
        if case.relationship_world is not None:
            if not isinstance(case.relationship_world, Mapping):
                errors.append(f"invalid:relationship_world:{case.case_id}")
            else:
                views = case.relationship_world.get("views", [])
                if not isinstance(views, list):
                    errors.append(f"invalid:relationship_views:{case.case_id}")
                else:
                    for view in views:
                        if not isinstance(view, Mapping):
                            errors.append(f"invalid:relationship_view:{case.case_id}")
                            continue
                        visibility = view.get("visibility")
                        if visibility not in {"known", "suspected", "unknown"}:
                            errors.append(
                                f"invalid:relationship_visibility:{case.case_id}"
                            )
        if case.continuation_mode and case.continuation_mode not in _CONTINUATION_MODES:
            errors.append(f"invalid:continuation_mode:{case.case_id}")
        if case.follow_up_mode not in _FOLLOW_UP_MODES:
            errors.append(f"invalid:follow_up_mode:{case.case_id}")
        for turn in case.dialogue_turns():
            turn_intent = _turn_intent(case, turn)
            if turn_intent not in _INTERACTION_INTENTS:
                errors.append(f"invalid:turn_intent:{case.case_id}:{turn.turn_id}")
            if turn.initiative_expectation not in _INITIATIVE_EXPECTATIONS:
                errors.append(
                    f"initiative_expectation:{case.case_id}:{turn.turn_id}"
                )
            if turn.initiative_kind not in _INITIATIVE_KINDS:
                errors.append(f"initiative_kind:{case.case_id}:{turn.turn_id}")
            if (
                turn.initiative_expectation != "none"
                and turn.initiative_kind == "none"
                and not (
                    case.follow_up_mode == "adaptive"
                    and turn.initiative_expectation == "responsive"
                    and turn.turn_plan_mode in {"answer_plus_detail", "answer_only"}
                )
            ):
                errors.append(f"initiative_kind_required:{case.case_id}:{turn.turn_id}")
            if turn.relationship_focus not in {"", *_RELATIONSHIP_FOCUS_VALUES}:
                errors.append(
                    f"invalid:relationship_focus:{case.case_id}:{turn.turn_id}"
                )
            if turn.relationship_focus and case.relationship_world is None:
                errors.append(
                    f"relationship_world_required:{case.case_id}:{turn.turn_id}"
                )
            if turn.relationship_actor not in {"", "player", "npc"}:
                errors.append(
                    f"invalid:relationship_actor:{case.case_id}:{turn.turn_id}"
                )
            if turn.relationship_actor == "player" and not turn.relationship_target_npc_id:
                errors.append(
                    f"relationship_target_required:{case.case_id}:{turn.turn_id}"
                )
    return errors


_BASE_CASES: tuple[CharacterQualityCase, ...] = (
    CharacterQualityCase(
        case_id="wizard-daily",
        completed_event_ids=("1000075",),
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="acquaintance",
        channel="remote",
        message="最近过得怎么样？",
        expected_terms=("还", "事做"),
        forbidden_terms=("星界", "奥术", "元素", "预言"),
        game_state=_game_state(
            season="春",
            date="春 1 日",
            weather="晴天",
            time=800,
            location="法师塔",
            friendshipHearts=2,
        ),
        story_progress="初到山谷：刚认识法师，尚未触发法师塔相关事件",
    ),
    CharacterQualityCase(
        case_id="wizard-follow-up",
        completed_event_ids=("1000075", "1724096"),
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="friend",
        channel="face_to_face",
        message="那第三组现在稳定了吗？",
        history=(
            {"role": "user", "content": "你先看看第三组。"},
            {"role": "assistant", "content": "我先核对记录。"},
        ),
        expected_terms=("第三组", "重测"),
        forbidden_terms=("星界", "预言"),
        game_state=_game_state(
            season="夏",
            date="夏 14 日",
            weather="下雨",
            time=1830,
            location="法师塔",
            friendshipHearts=6,
        ),
        story_progress="已确认第三组数据异常：正在进行第二轮复测",
    ),
    CharacterQualityCase(
        case_id="wizard-remote-invite",
        completed_event_ids=("1000075", "1724096"),
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="friend",
        channel="remote",
        message="改天有空再聊聊你那些记录吧。",
        expected_terms=("记录",),
        # 「周日／几点／见面」进禁词：NPC 若把一句客套自行落实成日程，就算它做错。
        forbidden_terms=("神秘仪式", "预言", "周日", "几点", "见面"),
        game_state=_game_state(
            season="秋",
            date="秋 22 日",
            weather="阴天",
            time=2100,
            location="手机聊天",
            friendshipHearts=6,
        ),
        story_progress="第三组复测已完成：线上随口提过改天再聊，没有约定任何具体安排",
    ),
    CharacterQualityCase(
        case_id="sophia-daily",
        completed_event_ids=("8185291",),
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="acquaintance",
        channel="remote",
        message="今天葡萄园忙不忙？",
        expected_terms=("葡萄", "忙"),
        game_state=_game_state(
            season="春",
            date="春 5 日",
            weather="晴天",
            time=900,
            location="葡萄园",
            friendshipHearts=2,
        ),
        story_progress="刚认识：第一次从线上问起葡萄园的日常工作",
    ),
    CharacterQualityCase(
        case_id="sophia-vineyard",
        completed_event_ids=("8185291", "8185292", "8185293"),
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="friend",
        channel="face_to_face",
        message="改天有空再来看看你的葡萄。",
        expected_terms=("葡萄", "一起"),
        game_state=_game_state(
            season="夏",
            date="夏 14 日",
            weather="晴天",
            time=1400,
            location="葡萄园",
            friendshipHearts=6,
        ),
        story_progress="今年第一批葡萄已经采摘：朋友阶段当面随口提了一句，没有具体安排",
    ),
    CharacterQualityCase(
        case_id="sophia-face-follow-up",
        completed_event_ids=("8185291", "8185292", "8185293"),
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="friend",
        channel="face_to_face",
        message="刚才那桶酒的味道怎么样？",
        history=({"role": "user", "content": "我们刚才闻过新酿的葡萄酒。"},),
        expected_terms=("酒", "葡萄"),
        game_state=_game_state(
            season="秋",
            date="秋 18 日",
            weather="阴天",
            time=1700,
            location="葡萄园酒窖",
            friendshipHearts=6,
        ),
        story_progress="刚打开新酿的酒桶：继续刚才的当面品尝话题",
    ),
    CharacterQualityCase(
        case_id="shane-coop",
        completed_event_ids=("611944",),
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="acquaintance",
        channel="face_to_face",
        message="鸡舍今天忙吗？",
        expected_terms=("鸡舍", "还行"),
        game_state=_game_state(
            season="春",
            date="春 3 日",
            weather="小雨",
            time=1000,
            location="鸡舍",
            friendshipHearts=2,
        ),
        story_progress="刚认识：在鸡舍门口进行第一次当面寒暄",
    ),
    CharacterQualityCase(
        case_id="shane-remote-care",
        completed_event_ids=("611944", "3910674", "3910975"),
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="remote",
        message="你今天有没有好好休息？",
        expected_terms=("休息", "还没"),
        game_state=_game_state(
            season="冬",
            date="冬 12 日",
            weather="阴天",
            time=2200,
            location="手机聊天",
            friendshipHearts=6,
        ),
        story_progress="朋友阶段：鸡舍交接正常，但 Shane 明确表示不想长聊",
    ),
    CharacterQualityCase(
        case_id="shane-follow-up",
        completed_event_ids=("611944", "3910674", "3910975"),
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="face_to_face",
        message="那批鸡饲料后来送到了吗？",
        history=({"role": "user", "content": "鸡饲料还没送到。"},),
        expected_terms=("饲料", "到了"),
        game_state=_game_state(
            season="夏",
            date="夏 20 日",
            weather="晴天",
            time=800,
            location="牧场鸡舍",
            friendshipHearts=6,
        ),
        story_progress="鸡饲料延迟尚未解决：当面追问上一轮留下的实际事项",
    ),
    CharacterQualityCase(
        case_id="sebastian-bike",
        completed_event_ids=("2794460",),
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="acquaintance",
        channel="remote",
        message="最近还骑摩托车出去吗？",
        expected_terms=("摩托车", "出去"),
        game_state=_game_state(
            season="春",
            date="春 8 日",
            weather="阴天",
            time=1800,
            location="手机聊天",
            friendshipHearts=2,
        ),
        story_progress="刚认识：线上询问摩托车近况，不主动深入私人话题",
    ),
    CharacterQualityCase(
        case_id="sebastian-rain",
        completed_event_ids=("2794460", "384883", "27"),
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="face_to_face",
        message="下雨天你一般会做什么？",
        expected_terms=("电脑", "房间", "雨"),
        game_state=_game_state(
            season="秋",
            date="秋 16 日",
            weather="下雨",
            time=2100,
            location="房间",
            friendshipHearts=6,
        ),
        story_progress="朋友阶段：雨天留在房间，话题停留在具体日常安排",
    ),
    CharacterQualityCase(
        case_id="sebastian-follow-up",
        completed_event_ids=("2794460", "384883", "27"),
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="face_to_face",
        message="那段代码后来修好了吗？",
        history=({"role": "user", "content": "你说那段代码还有个 bug。"},),
        expected_terms=("代码", "修"),
        game_state=_game_state(
            season="冬",
            date="冬 7 日",
            weather="下雪",
            time=1930,
            location="房间",
            friendshipHearts=6,
        ),
        story_progress="代码 bug 尚未确认修好：继续上一轮的技术话题",
    ),
    CharacterQualityCase(
        case_id="alex-training",
        completed_event_ids=("20",),
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="acquaintance",
        channel="face_to_face",
        message="今天训练得怎么样？",
        expected_terms=("训练", "完成"),
        game_state=_game_state(
            season="春",
            date="春 9 日",
            weather="晴天",
            time=1600,
            location="运动场",
            friendshipHearts=2,
        ),
        story_progress="刚认识：第一次在运动场聊今天的训练",
    ),
    CharacterQualityCase(
        case_id="alex-remote-invite",
        completed_event_ids=("20", "2481135", "2119820"),
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="remote",
        message="下次一起练练？",
        expected_terms=("一起", "训练"),
        game_state=_game_state(
            season="夏",
            date="夏 21 日",
            weather="晴天",
            time=1900,
            location="手机聊天",
            friendshipHearts=6,
        ),
        story_progress="朋友阶段：线上随口提过一起练，没有约定任何具体安排",
    ),
    CharacterQualityCase(
        case_id="alex-follow-up",
        completed_event_ids=("20", "2481135", "2119820"),
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="friend",
        channel="face_to_face",
        message="你昨天的训练完成了吗？",
        history=({"role": "user", "content": "昨天最后一组很难。"},),
        expected_terms=("训练", "完成"),
        game_state=_game_state(
            season="秋",
            date="秋 3 日",
            weather="有风",
            time=1700,
            location="运动场",
            friendshipHearts=6,
        ),
        story_progress="昨天最后一组训练留下未完成项：当面继续追问进度",
    ),
    CharacterQualityCase(
        case_id="caroline-close-background",
        completed_event_ids=(),
        profile_key="caroline",
        npc_id="Caroline",
        display_name="Caroline",
        source_mods=("vanilla",),
        relationship_stage="close",
        channel="face_to_face",
        message="玛妮最近还好吗？",
        history=(
            {"role": "user", "content": "你上次说起过玛妮和牧场的事。"},
            {"role": "assistant", "content": "嗯，她最近一直在照料动物。"},
        ),
        expected_terms=("玛妮", "牧场"),
        game_state=_game_state(
            season="春",
            date="春 24 日",
            weather="晴天",
            time=1500,
            location="杂货店",
            friendshipHearts=10,
            relationship="未婚",
        ),
        story_progress="亲近阶段：玩家已经听 Caroline 提过茶园和 Marnie，正在当面继续聊镇上熟人。",
    ),
    CharacterQualityCase(
        case_id="sebastian-married-life",
        completed_event_ids=("2794460", "384883", "27", "29"),
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="face_to_face",
        message="厨房收拾完了，先留点安静时间给我们，好吗？",
        history=(
            {"role": "user", "content": "我今晚想先把厨房收拾好。"},
        ),
        expected_terms=("安静",),
        forbidden_terms=("永远", "命中注定"),
        relationship_context="已婚阶段：双方已确认亲密关系，共同生活安排已经确认，玩家做完了家务，当下想留一点安静相处的时间。",
        game_state=_game_state(
            season="冬",
            date="冬 18 日",
            weather="下雪",
            time=1930,
            location="农舍",
            friendshipHearts=14,
            marriageStatus="married",
        ),
        story_progress="已婚阶段：共同生活安排已经确认，玩家做完了家务，当下想留一点安静相处的时间。",
    ),
    CharacterQualityCase(
        case_id="wizard-close-background",
        completed_event_ids=("1000075", "1724096", "1724097"),
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="close",
        channel="face_to_face",
        message="你为什么一直住在这座塔里？",
        expected_terms=("塔", "住"),
        forbidden_terms=("命中注定", "预言"),
        game_state=_game_state(
            season="冬",
            date="冬 9 日",
            weather="下雪",
            time=1930,
            location="法师塔",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：玩家已经建立信任，开始询问 Rasmodia 的生活选择；她可以分享塔内生活，但不应凭空补写未确认的过去。",
    ),
    CharacterQualityCase(
        case_id="sophia-close-background",
        completed_event_ids=("8185291", "8185292", "8185293", "8185295"),
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="close",
        channel="face_to_face",
        message="你还想一直留在葡萄园吗，还是有别的打算？",
        expected_terms=("葡萄园", "打算"),
        game_state=_game_state(
            season="秋",
            date="秋 20 日",
            weather="晴天",
            time=1600,
            location="葡萄园",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：玩家已经知道 Sophia 喜欢葡萄园和角色扮演，开始聊她对未来的想法；不能替她决定离开或留下。",
    ),
    CharacterQualityCase(
        case_id="shane-close-boundary",
        completed_event_ids=("611944", "3910674", "3910975", "3900074"),
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="close",
        channel="face_to_face",
        message="你最近是不是又睡不好？",
        expected_terms=("睡", "问"),
        game_state=_game_state(
            season="冬",
            date="冬 16 日",
            weather="阴天",
            time=2100,
            location="牧场厨房",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：Shane 承认状态不佳，但被连续追问时会明确要求空间；测试他能否冷淡收束，而不是突然变成温柔长篇。",
    ),
    CharacterQualityCase(
        case_id="alex-close-background",
        completed_event_ids=("20", "2481135", "2119820", "288847"),
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="close",
        channel="face_to_face",
        message="你还想去当职业球员吗？",
        expected_terms=("职业", "球员"),
        game_state=_game_state(
            season="夏",
            date="夏 10 日",
            weather="晴天",
            time=1800,
            location="海滩",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：玩家已经知道 Alex 的职业目标，也见过他嘴硬的一面；允许谈梦想和担心，但不能把每句变成励志演讲。",
    ),
    CharacterQualityCase(
        case_id="marnie-friend-family",
        completed_event_ids=(),
        profile_key="marnie",
        npc_id="Marnie",
        display_name="Marnie",
        source_mods=("vanilla",),
        relationship_stage="close",
        channel="face_to_face",
        message="Shane 最近还好吗？",
        expected_terms=("Shane", "最近"),
        game_state=_game_state(
            season="春",
            date="春 18 日",
            weather="晴天",
            time=1100,
            location="玛妮的牧场",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：玩家与 Marnie 熟悉，知道她照料牧场和家人；可以谈 Shane 的近况，但不能替 Shane 透露未说过的隐私。",
    ),
    CharacterQualityCase(
        case_id="linus-friend-nature",
        completed_event_ids=(),
        profile_key="linus",
        npc_id="Linus",
        display_name="Linus",
        source_mods=("vanilla",),
        relationship_stage="close",
        channel="face_to_face",
        message="你住在山上的帐篷里，冬天会不会太冷？",
        expected_terms=("帐篷", "冷"),
        game_state=_game_state(
            season="冬",
            date="冬 4 日",
            weather="下雪",
            time=1700,
            # 2026-09-24：原值「煤矿森林」是错的，改成游戏里真实的地图标识符。三条依据：
            # ① 他的日程表（`Characters/schedules/Linus.json`）只有
            #    Mountain 19 / Tent 11 / Desert / Beach / Railroad / BathHouse_Entry，
            #    **从不 Forest**；
            # ② 他语料里「群山」14、「帐篷」8，「森林」仅 1 句泛指山谷景致；
            # ③ **本案例自己的台词**写着「你住在**山上**的帐篷里」与
            #    「你今天在**山**里找到什么了」——与「煤矿森林」自相矛盾。
            # 为什么写英文 `Mountain` 而不是中文场景词：`game_state.location` 这条通道上，
            # 游戏侧的值是 `npc.currentLocation.NameOrUniqueName ?? Name`
            # （`smapi/GameStateCollector.cs:180`）= **英文地图标识符**，`prompts.py`
            # 原样透传进 `scene.地点`、不做枚举映射。写 `Mountain` 才是与线上一致的输入。
            # 其余 69 个案例的 location 仍是中文场景描述，那是一个**已记档的结构性问题**
            # （见 `docs/active-work.md` 2026-09-24 条），本轮按用户口径不扩散修正。
            location="Mountain",
            friendshipHearts=8,
        ),
        story_progress="亲近阶段：玩家尊重 Linus 的生活方式，开始关心冬季生活；回答应保留他的独立和对自然的熟悉，不把他写成等待被拯救的人。",
    ),
    CharacterQualityCase(
        case_id="wizard-dating-invite",
        completed_event_ids=("1000075", "1724096", "1724097"),
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="dating",
        channel="remote",
        message="今天没什么要核对的，我只是想你了。你现在方便跟我聊一会儿吗？",
        expected_terms=("想你", "聊"),
        forbidden_terms=("命中注定", "预言"),
        friendship_hearts=8,
        flirt_intensity="light",
        adult_consensual=True,
        romance_eligible=True,
        relationship_context="已确认恋爱关系：线上表达想念，是否见面仍需另行确认。",
        game_state=_game_state(
            season="秋",
            date="秋 9 日",
            weather="晴天",
            time=2200,
            location="手机聊天",
            friendshipHearts=8,
            relationship="dating",
        ),
        story_progress="约会阶段：今天没有新的研究事项，玩家主动表达想念；线上聊天不能写成已经见面。",
    ),
    CharacterQualityCase(
        case_id="wizard-married-evening",
        completed_event_ids=("1000075", "1724096", "1724097"),
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="married",
        channel="face_to_face",
        message="那些记录先放一放，留一点时间给我，好吗？",
        expected_terms=("记录", "留"),
        forbidden_terms=("命中注定", "预言"),
        friendship_hearts=10,
        flirt_intensity="explicit",
        adult_consensual=True,
        romance_eligible=True,
        relationship_context="婚后阶段：双方已确认亲密关系，面对面提出成人之间的亲密邀约。",
        game_state=_game_state(
            season="冬",
            date="冬 12 日",
            weather="下雪",
            time=2100,
            location="法师塔",
            friendshipHearts=10,
            relationship="married",
            marriageStatus="married",
        ),
        story_progress="婚后阶段：研究记录可以暂时放下，玩家当面提出此刻把时间留给彼此；回复应亲密但不凭空扩写露骨细节。",
    ),
    CharacterQualityCase(
        case_id="sophia-dating-wine",
        completed_event_ids=("8185291", "8185292", "8185293", "8185295"),
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="dating",
        channel="face_to_face",
        message="你真的给我留了一杯？还是只想让我陪你尝一口呀？",
        expected_terms=("留", "一杯"),
        friendship_hearts=8,
        flirt_intensity="light",
        adult_consensual=True,
        romance_eligible=True,
        relationship_context="约会阶段：葡萄园酒窖当面品酒，双方可以轻松调情，但不能把玩笑写成承诺。",
        game_state=_game_state(
            season="秋",
            date="秋 21 日",
            weather="晴天",
            time=1830,
            location="葡萄园酒窖",
            friendshipHearts=8,
            relationship="dating",
        ),
        story_progress="约会阶段：新酿葡萄酒已经装杯，玩家和 Sophia 当面延续品酒与暧昧玩笑。",
    ),
    CharacterQualityCase(
        case_id="sophia-married-cellar",
        completed_event_ids=("8185291", "8185292", "8185293", "8185295"),
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="married",
        channel="face_to_face",
        message="酒窖门关上了，就陪我在这儿慢慢喝一杯，好不好？",
        expected_terms=("酒窖", "一杯"),
        friendship_hearts=10,
        flirt_intensity="explicit",
        adult_consensual=True,
        romance_eligible=True,
        relationship_context="婚后阶段：双方已确认亲密关系，酒窖里的成人亲密邀约必须保持自愿和自然。",
        game_state=_game_state(
            season="冬",
            date="冬 7 日",
            weather="阴天",
            time=2000,
            location="葡萄园酒窖",
            friendshipHearts=10,
            relationship="married",
            marriageStatus="married",
        ),
        story_progress="婚后阶段：酒窖工作已经收尾，玩家当面提出此刻一起慢慢喝一杯；回复可以亲密，但不把强度标签直接说出口。",
    ),
    CharacterQualityCase(
        case_id="shane-dating-boundary",
        completed_event_ids=("611944", "3910674", "3910975", "3900074"),
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="dating",
        channel="remote",
        message="我今天只想听你说一句‘想我了’，可以吗？",
        expected_terms=("想我",),
        forbidden_terms=("永远", "命中注定"),
        friendship_hearts=8,
        flirt_intensity="direct",
        adult_consensual=True,
        romance_eligible=True,
        gender_presentation="female-bachelors",
        relationship_context="约会阶段：玩家主动索要直白的情话；Shane 即使在恋爱中也可能敷衍、拒绝或提前结束聊天。",
        game_state=_game_state(
            season="冬",
            date="冬 16 日",
            weather="阴天",
            time=2230,
            location="手机聊天",
            friendshipHearts=8,
            relationship="dating",
        ),
        story_progress="约会阶段：Shane 今天状态低落，玩家线上提出直白请求；允许他只回一句、拒绝甜话或说不想继续聊。",
    ),
    CharacterQualityCase(
        case_id="sebastian-dating-rooftop",
        completed_event_ids=("2794460", "384883", "27", "29"),
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="dating",
        channel="face_to_face",
        message="你说的那个屋顶，是什么样子的？",
        expected_terms=("屋顶",),
        friendship_hearts=8,
        flirt_intensity="light",
        adult_consensual=True,
        romance_eligible=True,
        gender_presentation="female-bachelors",
        relationship_context="约会阶段：当面提出去屋顶听歌的邀约，互动可以亲密，但不替 Sebastian 预设他已经答应。",
        game_state=_game_state(
            season="夏",
            date="夏 18 日",
            weather="晴天",
            time=2030,
            location="铁路隧道",
            friendshipHearts=8,
            relationship="dating",
        ),
        story_progress="约会阶段：玩家和 Sebastian 当面聊到屋顶音乐，只是好奇那个地方，没有约定今晚同去。",
    ),
    CharacterQualityCase(
        case_id="sebastian-married-music",
        completed_event_ids=("2794460", "384883", "27", "29"),
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="face_to_face",
        message="音乐停下来以后，过来抱我一会儿？",
        expected_terms=("音乐", "抱"),
        forbidden_terms=("永远", "命中注定"),
        friendship_hearts=10,
        flirt_intensity="explicit",
        adult_consensual=True,
        romance_eligible=True,
        relationship_context="婚后阶段：双方已确认亲密关系，玩家当面提出克制而明确的身体亲密请求。",
        game_state=_game_state(
            season="春",
            date="春 14 日",
            weather="下雨",
            time=2200,
            location="农舍卧室",
            friendshipHearts=10,
            relationship="married",
            marriageStatus="married",
        ),
        story_progress="婚后阶段：家务已收尾，Sebastian 正在听音乐；玩家提出拥抱，回复应保持他的少话、克制和真实边界。",
    ),
    CharacterQualityCase(
        case_id="alex-dating-beach",
        completed_event_ids=("20", "2481135", "2119820", "288847"),
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="dating",
        channel="face_to_face",
        message="你夸我今天看起来不错，是认真的吗？",
        expected_terms=("认真", "不错"),
        friendship_hearts=8,
        flirt_intensity="direct",
        adult_consensual=True,
        romance_eligible=True,
        gender_presentation="female-bachelors",
        relationship_context="约会阶段：海滩当面接住外貌夸奖，Alex 可以得意、嘴硬或反过来调侃，但不要变成励志演讲。",
        game_state=_game_state(
            season="夏",
            date="夏 10 日",
            weather="晴天",
            time=1800,
            location="海滩",
            friendshipHearts=8,
            relationship="dating",
        ),
        story_progress="约会阶段：玩家在海滩直接夸 Alex 的外表；测试他的自信、嘴硬和回调情，而不是训练话题。",
    ),
    CharacterQualityCase(
        case_id="alex-married-evening",
        completed_event_ids=("20", "2481135", "2119820", "288847"),
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="married",
        channel="face_to_face",
        message="训练和晚饭都忙完了，今晚你想先陪我聊一会儿，还是直接去房间？",
        expected_terms=("今晚", "房间"),
        friendship_hearts=10,
        flirt_intensity="explicit",
        adult_consensual=True,
        romance_eligible=True,
        relationship_context="婚后阶段：共同生活已稳定，玩家当面提出带有成人亲密意味的二选一邀约。",
        game_state=_game_state(
            season="秋",
            date="秋 26 日",
            weather="晴天",
            time=2100,
            location="农舍",
            friendshipHearts=10,
            relationship="married",
            marriageStatus="married",
        ),
        story_progress="婚后阶段：训练和晚饭都结束，玩家将话题从日常安排推进到亲密相处；不要把回复写成泛泛的目标宣言。",
    ),
)


def _feminine_male_case(
    *,
    case_id: str,
    profile_key: str,
    npc_id: str,
    relationship_stage: str,
    channel: str,
    message: str,
    expected_terms: tuple[str, ...],
    relationship_context: str,
    story_progress: str,
    location: str,
    history: tuple[dict[str, str], ...] = (),
    flirt_intensity: str = "none",
    adult_consensual: bool = False,
    # 该案例声明的「角色已经历过的剧情事件」。刻意**不给默认值**：空元组在
    # 事件锁里表示「这些事件都没发生」，会被收窄到 acquaintance；
    # 「忘记声明」与「声明为空」必须是两件事，所以每条案例都要自己写清楚。
    completed_event_ids: tuple[str, ...],
) -> CharacterQualityCase:
    hearts = {
        # stranger 与 parent 是 2026-09-30 补齐阶段覆盖时加的：前者对应
        # 初见（零好感），后者对应婚后有孩子。
        "stranger": 0,
        "acquaintance": 2,
        "friend": 6,
        "close": 8,
        "dating": 8,
        "married": 10,
        "parent": 12,
    }[relationship_stage]
    return CharacterQualityCase(
        case_id=case_id,
        profile_key=profile_key,
        npc_id=npc_id,
        display_name=npc_id,
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage=relationship_stage,
        channel=channel,
        message=message,
        history=history,
        expected_terms=expected_terms,
        friendship_hearts=hearts,
        flirt_intensity=flirt_intensity,
        adult_consensual=adult_consensual,
        romance_eligible=True,
        relationship_context=relationship_context,
        completed_event_ids=completed_event_ids,
        game_state=_game_state(
            season="秋",
            date="秋 18 日",
            weather="晴天",
            time=1930 if channel == "face_to_face" else 2100,
            location=location,
            friendshipHearts=hearts,
            # stranger 与 parent 不写 relationship：前者尚未建立关系，
            # 后者的婚姻状态由 marriageStatus + childrenCount 表达。
            # 这与现有手写的 stranger / parent 案例（Wizard、Shane）一致。
            **(
                {}
                if relationship_stage in {"stranger", "parent"}
                else {"relationship": relationship_stage}
            ),
            **(
                {"marriageStatus": "married", "childrenCount": 1}
                if relationship_stage == "parent"
                else {}
            ),
        ),
        story_progress=story_progress,
        gender_presentation="female-bachelors",
    )


_STAGE_COVERAGE_CASES: tuple[CharacterQualityCase, ...] = (
    # 2026-09-30 补齐阶段覆盖。
    #
    # 动机：整个评测集里有两处结构性空洞——
    #   ① Elliott / Harvey / Sam 因为契约只要求五阶段，
    #     stranger 与 parent 一直没有样本；
    #   ② 验收时发现「邀约」在 acquaintance 阶段为 0，
    #     而 stranger（3）与 friend（2）都有，它恰好夹在中间空着；
    #   ③ 「边界 / 拒绝」在 stranger 与 acquaintance 阶段同样为 0，
    #     而 stranger 的核心约束正是「不接邀约、不反问」。
    #
    # 只加数据，不改任何现有案例。
    _feminine_male_case(
        case_id="elliott-stranger-invitation",
        completed_event_ids=(),
        profile_key="elliott",
        npc_id="Elliott",
        relationship_stage="stranger",
        channel="face_to_face",
        message="改天带我去你那条秘密海滩看看？",
        expected_terms=(),
        relationship_context="初识阶段邀约：玩家第一次搭话就提出单独去秘密海滩；初视不得接住邀约、不得反问、不得主动开新话题。",
        story_progress="初见：两人还没有交集，Elliott 不应对陌生人承诺单独相约。",
        location="海边",
    ),
    _feminine_male_case(
        case_id="harvey-stranger-invitation",
        completed_event_ids=(),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="stranger",
        channel="face_to_face",
        message="你下班后能单独给我看看吗？",
        expected_terms=(),
        relationship_context="初识阶段邀约：玩家向初识的医生要求下班后单独看诊；初视不得接住私人邀约、不得反问。",
        story_progress="初见：尚未建立任何关系，Harvey 不应为陌生人提供私人出诊。",
        location="镇上",
    ),
    _feminine_male_case(
        case_id="sam-stranger-invitation",
        completed_event_ids=(),
        profile_key="sam",
        npc_id="Sam",
        relationship_stage="stranger",
        channel="face_to_face",
        message="下次演出带我一个，我跟你一起上台？",
        expected_terms=(),
        relationship_context="初识阶段邀约：玩家要求上台同演；初视不得接住邀约、不得反问、不得主动开新话题。",
        story_progress="初见：两人还不认识，Sam 不应对陌生人承诺同台。",
        location="镇上",
    ),
    _feminine_male_case(
        case_id="harvey-acquaintance-boundary",
        completed_event_ids=("56",),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="acquaintance",
        channel="remote",
        message="我有点不舒服，你能上门看看吗？",
        expected_terms=(),
        relationship_context="初识阶段边界：已打过照面但交情尚浅，玩家要求上门出诊；只能给出不升级关系的合理回应，不得承诺私人上门。",
        story_progress="初识：已见过一次，但还没到可以随意打扰私人时间的交情。",
        location="手机聊天",
    ),
    _feminine_male_case(
        case_id="elliott-acquaintance-invitation",
        completed_event_ids=("39",),
        profile_key="elliott",
        npc_id="Elliott",
        relationship_stage="acquaintance",
        channel="face_to_face",
        message="改天带我去海边走走吧？",
        expected_terms=(),
        relationship_context="初识阶段邀约：双方刚认识，可以接住邀约的意愿但不自行安排时间地点，不把它当成已约定。",
        story_progress="初识：已打过一次照面，关系尚浅，Elliott 不应把客套当承诺。",
        location="海边小屋",
    ),
    _feminine_male_case(
        case_id="sam-acquaintance-invitation",
        completed_event_ids=(),
        profile_key="sam",
        npc_id="Sam",
        relationship_stage="acquaintance",
        channel="remote",
        message="你们乐队什么时候再演出？我想去看。",
        expected_terms=(),
        relationship_context="初识阶段邀约：玩家表示想去看演出，只能给出尚未定的真实状态，不主动约定时间、不升级关系。",
        story_progress="初识：Sam 还没把玩家当熟人，乐队也没有确定的下一场。",
        location="手机聊天",
    ),
    _feminine_male_case(
        case_id="elliott-parent-bedtime",
        completed_event_ids=("39", "40", "423502", "1848481"),
        profile_key="elliott",
        npc_id="Elliott",
        relationship_stage="parent",
        channel="face_to_face",
        message="孩子说想听你读故事。",
        expected_terms=(),
        relationship_context="婚后有孩子：孩子想听故事，先落到实际安排（时间、书、读多久），不把成人的写作焦虑传给孩子。",
        story_progress="婚后：共同生活已稳定并有一个孩子，关系事件已完成。",
        location="海边小屋",
    ),
    _feminine_male_case(
        case_id="harvey-parent-fever",
        completed_event_ids=("56", "57", "58", "571102"),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="parent",
        channel="face_to_face",
        message="孩子有点发烧。",
        expected_terms=(),
        relationship_context="婚后有孩子：孩子发烧时先说可执行的判断与下一步，不用医疗术语堆砌，也不把担忧变成说教。",
        story_progress="婚后：共同生活已稳定并有一个孩子，关系事件已完成。",
        location="诊所",
    ),
    _feminine_male_case(
        case_id="sam-parent-practice",
        completed_event_ids=(),
        profile_key="sam",
        npc_id="Sam",
        relationship_stage="parent",
        channel="face_to_face",
        message="孩子在屋里乱敲东西。",
        expected_terms=(),
        relationship_context="婚后有孩子：孩子在屋里乱碰乐器，先给出现场安排，不把自己的练琴计划凌驾于孩子之上。",
        story_progress="婚后：共同生活已稳定并有一个孩子，关系事件已完成。",
        location="家里",
    ),
)


# 2026-10-05 补齐**话题**覆盖（第五类盲区：阶段对了、话题不对）。
#
# 动机：`scripts/probe_topic_alignment.py` 摊出五组「阶段有样本、话题没有」——
#   close × 动作（4 条约束）、stranger × 反问（2）、stranger × 换题（1）、
#   close × 换题（1）、close × 反问（1）。
# 这些约束**即使把 suite 跑全也验不了**，因为该阶段的 case 问的不是那件事。
#
# ⚠ 补的是**输入**：每条案例的玩家话都必须**真能诱发**那条被禁止的行为，
# 而不是往 case_id 里塞关键词让探针闭嘴。判据写在每条的 relationship_context 里。
# 只加数据，不改任何现有案例。
_TOPIC_ALIGNMENT_CASES: tuple[CharacterQualityCase, ...] = (
    # ── close × 动作：亲密信号只能嵌在同一话题、全篇最多一个当前动作 ──
    # ⚠ 2026-10-05：「全篇最多一个动作」**没有机器判据** —— 动作靠语义读出，
    #    回复里没有括号 / 星号标记，6 组正则的同类先例只命中 1/4（见 L4601）。
    #    ⇒ 这两条 case 的 FAIL **不反映动作密度**，必须人读台词。
    #      登记见 `docs/constraint-scope.md` 三次追加。
    _feminine_male_case(
        case_id="elliott-close-gesture",
        completed_event_ids=("39", "40", "423502", "1848481"),
        profile_key="elliott",
        npc_id="Elliott",
        relationship_stage="close",
        channel="face_to_face",
        message="（把椅子挪近了些）你今天写了多久？",
        expected_terms=("写",),
        relationship_context="亲近阶段动作密度：玩家先给出一个靠近动作再问写作进度；Elliott 的亲密信号只能嵌在写作这同一话题里，全篇最多一个当前动作，不得靠堆动作表达亲近。",
        story_progress="海边小屋的书桌上摊着一页稿纸，玩家挪近椅子，话题仍是这一页写了多久。",
        location="海边的小屋",
    ),
    _feminine_male_case(
        case_id="harvey-close-gesture",
        completed_event_ids=("56", "57", "58", "571102"),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="close",
        channel="face_to_face",
        message="（把手搭在椅背上）你还要忙多久？",
        expected_terms=("忙",),
        relationship_context="亲近阶段动作密度：玩家先搭手再问诊所还要忙多久；Harvey 最多一个自然的亲密动作并保持医生语气，不得用连续动作代替回答。",
        story_progress="诊所快收工了，桌上还摊着没写完的记录，玩家搭着椅背问他还要多久。",
        location="诊所办公室",
    ),
    # ── stranger × 反问：初识阶段不得反问、邀约或主动换题 ──
    _feminine_male_case(
        case_id="harvey-stranger-question",
        completed_event_ids=(),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="stranger",
        channel="face_to_face",
        message="我最近老在想一件事。",
        expected_terms=(),
        relationship_context="初识阶段反问：玩家故意留白吊话头，把「什么事？」递到嘴边；初识只能起一句眼前的小事，不得反问、不得邀约、不得主动换题。",
        story_progress="初见：两人还没有交集，玩家抛出一句没有下文的话，Harvey 不应追问。",
        location="镇上",
    ),
    _feminine_male_case(
        case_id="sam-stranger-topic-control",
        completed_event_ids=(),
        profile_key="sam",
        npc_id="Sam",
        relationship_stage="stranger",
        channel="face_to_face",
        message="今天天气不错。",
        expected_terms=(),
        relationship_context="初识阶段换题：玩家给一句说完就结束的客套，最容易诱发 NPC 自己另起话题；初识不得主动换题，也不得反问或邀约。",
        story_progress="初见：两人还不认识，玩家只说了一句天气，Sam 不应借机开新话题。",
        location="镇上",
    ),
    # ── close × 换题：不主动加问题、邀约、亲密表达或新话题，自然说完就停 ──
    _feminine_male_case(
        case_id="elliott-close-topic-control",
        completed_event_ids=("39", "40", "423502", "1848481"),
        profile_key="elliott",
        npc_id="Elliott",
        relationship_stage="close",
        channel="face_to_face",
        message="今天谢谢你陪我。",
        expected_terms=(),
        relationship_context="亲近阶段收束：玩家给一句已经说完的话，Elliott 应自然说完就停，不再加问题、邀约、亲密表达或新话题。",
        story_progress="海边的傍晚，玩家道了谢；这段对话可以在这里停住。",
        location="海边的小屋",
    ),
    # ── close × 反问：高亲密回复不只礼貌答题、重复事实或泛泛反问 ──
    _feminine_male_case(
        case_id="harvey-close-follow-up",
        completed_event_ids=("56", "57", "58", "571102"),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="close",
        channel="face_to_face",
        message="你小时候最怕什么？",
        expected_terms=("怕",),
        relationship_context="亲近阶段具体作答：玩家问一个具体的私人问题；高亲密回复应给出具体内容，不许只礼貌答题、重复事实或泛泛反问回来。",
        story_progress="诊所安静下来，玩家第一次问起他小时候的事。",
        location="诊所休息室",
    ),
)


_FEMININE_MALE_CASES: tuple[CharacterQualityCase, ...] = (
    # Elliott：保留文学和审美兴趣，但把表达落到纸张、画面和眼前动作。
    _feminine_male_case(
        case_id="elliott-daily",
        completed_event_ids=("39",),
        profile_key="elliott",
        npc_id="Elliott",
        relationship_stage="acquaintance",
        channel="remote",
        message="最近在写什么？",
        expected_terms=("写", "纸"),
        relationship_context="初识阶段：只询问海边小屋里的写作近况，不自动升级亲密关系。",
        story_progress="Elliott 正在整理一页新稿，线上回复应具体、短而有现场感。",
        location="手机聊天",
    ),
    _feminine_male_case(
        case_id="elliott-follow-up",
        completed_event_ids=("39", "40", "423502"),
        profile_key="elliott",
        npc_id="Elliott",
        relationship_stage="friend",
        channel="face_to_face",
        message="那段开头后来留着吗？",
        expected_terms=("开头", "留"),
        relationship_context="朋友阶段：承接上一轮谈过的手稿，不用泛泛的文学宣言替代回答。",
        story_progress="手稿开头删改过一次，玩家在海边小屋继续追问具体取舍。",
        location="海边小屋",
        history=(
            {"role": "user", "content": "你昨天说开头总觉得不对。"},
            {"role": "assistant", "content": "我先把那一页折起来了。"},
        ),
    ),
    _feminine_male_case(
        case_id="elliott-close-studio",
        completed_event_ids=("39", "40", "423502", "1848481"),
        profile_key="elliott",
        npc_id="Elliott",
        relationship_stage="close",
        channel="face_to_face",
        message="你愿意让我看看你写的那一页吗？",
        expected_terms=("写", "看看"),
        relationship_context="亲近阶段：玩家请求看他刚写的一页，Elliott 可以害羞但不能用长篇修辞回避。",
        story_progress="海边小屋的书桌上摊着他刚写的一页海面，分享仍由 Elliott 自己决定。",
        location="海边的小屋",
    ),
    _feminine_male_case(
        case_id="elliott-dating-letter",
        completed_event_ids=("39", "40", "423502", "1848481"),
        profile_key="elliott",
        npc_id="Elliott",
        relationship_stage="dating",
        channel="remote",
        message="这封信是写给我的吗？",
        expected_terms=("信", "给你"),
        relationship_context="恋爱阶段：玩家线上询问一封信的归属；允许温柔和偏爱，但不把远程写成已经见面。",
        story_progress="Elliott 刚完成一封未寄出的短笺，等待玩家确认是否愿意读。",
        location="手机聊天",
        flirt_intensity="direct",
        adult_consensual=True,
    ),
    _feminine_male_case(
        case_id="elliott-married-studio",
        completed_event_ids=("39", "40", "423502", "1848481"),
        profile_key="elliott",
        npc_id="Elliott",
        relationship_stage="married",
        channel="face_to_face",
        message="把笔放下，靠过来让我看看你没写完的那一页？",
        expected_terms=("笔", "靠", "一页"),
        relationship_context="婚后阶段：当面把写作和亲近动作放在眼前的纸页上，表达可亲密但不堆叠空泛情话。",
        story_progress="海边小屋的灯还亮着，Elliott 手边是一页没写完的小说；玩家提出具体的靠近请求。",
        location="海边的小屋",
        flirt_intensity="explicit",
        adult_consensual=True,
    ),
    # Harvey：温和、谨慎，关心落到状态确认和实际照料，不变成诊断讲义。
    _feminine_male_case(
        case_id="harvey-daily",
        completed_event_ids=("56",),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="acquaintance",
        channel="remote",
        message="诊所今天忙吗？",
        expected_terms=("诊所", "忙"),
        relationship_context="初识阶段：询问诊所近况，Harvey 可以专业但不应无依据地给玩家诊断。",
        story_progress="诊所刚结束上午接诊，线上聊天停留在工作近况。",
        location="手机聊天",
    ),
    _feminine_male_case(
        case_id="harvey-follow-up",
        completed_event_ids=("56", "57", "58"),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="friend",
        channel="face_to_face",
        message="你昨晚睡得好吗？",
        expected_terms=("睡", "还行"),
        relationship_context="朋友阶段：回应玩家的休息近况，以询问和小心提醒为主，不把关心说成医学结论。",
        story_progress="Harvey 在诊所整理记录，注意到玩家看起来疲惫，先确认状态再继续聊天。",
        location="诊所前台",
        history=(
            {"role": "user", "content": "昨晚我睡得有点晚。"},
            {"role": "assistant", "content": "那今天别把事情排得太满。"},
        ),
    ),
    _feminine_male_case(
        case_id="harvey-close-clinic",
        completed_event_ids=("56", "57", "58", "571102"),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="close",
        channel="face_to_face",
        message="这杯咖啡放这儿，你先歇会儿？",
        expected_terms=("咖啡", "歇"),
        relationship_context="亲近阶段：用眼前的咖啡和休息表达照料，保持明确边界，不替玩家判断病情。",
        story_progress="诊所暂时安静下来，Harvey 把咖啡放到玩家手边，邀请短暂休息。",
        location="诊所休息室",
    ),
    _feminine_male_case(
        case_id="harvey-dating-check-in",
        completed_event_ids=("56", "57", "58", "571102"),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="dating",
        channel="remote",
        message="你怎么一声不响就说想我了？",
        expected_terms=("想你", "状态"),
        relationship_context="恋爱阶段：线上接住想念后仍先确认彼此状态，允许温柔但不假装已经在同一地点。",
        story_progress="Harvey 刚结束工作，玩家突然收到一句想念；当前重点是情绪和状态确认。",
        location="手机聊天",
        flirt_intensity="direct",
        adult_consensual=True,
    ),
    _feminine_male_case(
        case_id="harvey-married-clinic",
        completed_event_ids=("56", "57", "58", "571102"),
        profile_key="harvey",
        npc_id="Harvey",
        relationship_stage="married",
        channel="face_to_face",
        message="检查表先放一边，过来让我听听你的心跳？",
        expected_terms=("检查表", "心跳"),
        relationship_context="婚后阶段：当面从工作切到亲密照料，保留 Harvey 的谨慎和同意边界，不写成医学诊断。",
        story_progress="诊所已经收工，检查表暂时合上；玩家提出明确而克制的亲密请求。",
        location="诊所办公室",
        flirt_intensity="explicit",
        adult_consensual=True,
    ),
    # Sam：音乐、滑板和行动感是角色锚点，亲密表达保持轻快但不幼稚化。
    _feminine_male_case(
        case_id="sam-daily",
        completed_event_ids=(),
        profile_key="sam",
        npc_id="Sam",
        relationship_stage="acquaintance",
        channel="face_to_face",
        message="最近在练什么歌？",
        expected_terms=("歌", "练"),
        relationship_context="初识阶段：从音乐近况开始，保留 Sam 的外向和行动感，不每句都用夸张感叹。",
        story_progress="Sam 正在家里练一段新歌，玩家当面问起具体内容。",
        location="Sam 的房间",
    ),
    _feminine_male_case(
        case_id="sam-follow-up",
        completed_event_ids=(),
        profile_key="sam",
        npc_id="Sam",
        relationship_stage="friend",
        channel="remote",
        message="那段副歌改好了吗？",
        expected_terms=("副歌", "改"),
        relationship_context="朋友阶段：承接上一轮音乐练习，Sam 可以轻松开玩笑但要给出具体进展。",
        story_progress="副歌昨天卡住了一个转调，Sam 线上回复玩家的跟进问题。",
        location="手机聊天",
        history=(
            {"role": "user", "content": "你说副歌昨天总是卡拍。"},
            {"role": "assistant", "content": "我先把节奏放慢了。"},
        ),
    ),
    _feminine_male_case(
        case_id="sam-close-band",
        completed_event_ids=(),
        profile_key="sam",
        npc_id="Sam",
        relationship_stage="close",
        channel="face_to_face",
        message="把耳机给我一边，我想听你说的那段？",
        expected_terms=("耳机", "听"),
        relationship_context="亲近阶段：通过耳机和音乐分享推进靠近，保持 Sam 的轻松行动感，不空喊浪漫口号。",
        story_progress="Sam 刚剪好一段旋律，玩家在房间里提出共享耳机的具体请求。",
        location="Sam 的房间",
    ),
    _feminine_male_case(
        case_id="sam-dating-show",
        completed_event_ids=(),
        profile_key="sam",
        npc_id="Sam",
        relationship_stage="dating",
        channel="remote",
        message="你是不是故意把最好听的那段留给我？",
        expected_terms=("最好听", "留"),
        relationship_context="恋爱阶段：线上把偏爱落到一段音乐，允许俏皮调情，但不提前写成已见面或固定安排。",
        story_progress="Sam 刚发来一段新录音，最好听的副歌明显是留给玩家的回应。",
        location="手机聊天",
        flirt_intensity="direct",
        adult_consensual=True,
    ),
    _feminine_male_case(
        case_id="sam-married-band",
        completed_event_ids=(),
        profile_key="sam",
        npc_id="Sam",
        relationship_stage="married",
        channel="face_to_face",
        message="歌放着，过来靠我一下，别躲在音箱后面。",
        expected_terms=("歌", "靠", "音箱"),
        relationship_context="婚后阶段：把亲密动作落在音乐和眼前位置上，保留 Sam 的玩笑与直接，不幼稚化。",
        story_progress="乐队排练刚结束，音箱还在播放回放；玩家提出明确的靠近请求。",
        location="乐队排练室",
        flirt_intensity="explicit",
        adult_consensual=True,
    ),
)


# === stranger / parent 两档补盲（2026-09-28，用户拍板 B） ===
#
# **为什么补**：case 集里此前**一个 stranger、一个 parent 都没有**，而这两档的 prompt
# 与相邻阶段**不是同一套**（`parent` 6324 字 vs `married` 7222 字）。
# 关键约束「初识不得邀约」**只在 stranger 生效** ⇒ 不补就从来没验证过它。
# 前两个（wizard-stranger-invitation / shane-parent-child-safety）
# 已在 `E:\workspace\.scratch\patchtest\` 的包副本上**实测通过**（草案 §四）。
#
# ⭐ **场景必须刻意诱发违规**：stranger 的 `message` 本身就是一个邀约，
# turn-2 再追一句试探 —— 若 NPC 接住并反向邀约 / 反问 / 主动开新话题，就是可观测违规。
# 给一个没机会违规的输入（纯陈述句），通过率必然 100%，**那样什么也没证明**。
# parent 则试探 `boundaryMode`：涉及孩子和魔法时**先解释风险**，直接答「没事」就是违规。
#
# ⚠ 每加一个 case **必须同时补 `_FOLLOW_UP_TURNS`**（下方 `.update()`），
# 否则 `quality_cases_for_suite` 直接抛 `ValueError: 角色质量案例缺少两轮续聊`。
# ⚠ `friendshipHearts`：stranger = **0**、parent = **12**；parent **必须给 `childrenCount`**
# （policy 看 `relationship_stage` 就够，但 prompt 内部会从 `game_state` 再推导一次阶段，
# 缺了它声明的阶段与推导出的阶段可能不一致）。
_BASE_CASES = _BASE_CASES + (
    # ---- stranger（初识：不得接住邀约、不得反问、不得主动开新话题）----
    CharacterQualityCase(
        case_id="wizard-stranger-invitation",
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="stranger",
        channel="remote",
        message="改天一起去矿洞看看？",
        relationship_context=(
            "初识阶段：玩家在线上直接提出一起去矿洞；"
            "初识不得接住邀约、不得反问、不得主动开新话题。"
        ),
        story_progress="初识：第一次见面，尚未完成任何法师塔事件",
        game_state=_game_state(
            season="春",
            date="春 1 日",
            weather="晴天",
            time=900,
            location="法师塔",
            friendshipHearts=0,
        ),
    ),
    CharacterQualityCase(
        case_id="sophia-stranger-invitation",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="stranger",
        channel="face_to_face",
        message="改天带我去看看你家的葡萄园好不好？",
        relationship_context=(
            "初识阶段：当面随口提一句改天去葡萄园看看；初识不得反向邀约或追问时间安排。"
        ),
        story_progress="初识：第一次在葡萄园搭话，尚未完成任何事件",
        game_state=_game_state(
            season="春",
            date="春 3 日",
            weather="晴天",
            time=1000,
            location="葡萄园",
            friendshipHearts=0,
        ),
    ),
    CharacterQualityCase(
        case_id="shane-stranger-invitation",
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="stranger",
        channel="face_to_face",
        message="晚上一起去酒吧坐坐？",
        relationship_context=(
            "初识阶段：当面邀约去酒吧；Shane 对陌生人本就冷淡，不得反问玩家或顺势拉近。"
        ),
        story_progress="初识：第一次在镇上搭话，尚未完成任何事件",
        game_state=_game_state(
            season="春",
            date="春 4 日",
            weather="阴天",
            time=1600,
            location="镇上",
            friendshipHearts=0,
        ),
    ),
    CharacterQualityCase(
        case_id="sebastian-stranger-open-topic",
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="stranger",
        channel="face_to_face",
        message="你这摩托看着挺特别。",
        relationship_context=(
            "初识阶段：对摩托车的一句旁观陈述；不得以自身话题反客为主或反问玩家。"
        ),
        story_progress="初识：第一次搭话，尚未完成任何事件",
        game_state=_game_state(
            season="春",
            date="春 6 日",
            weather="晴天",
            time=1900,
            location="镇上",
            friendshipHearts=0,
        ),
    ),
    CharacterQualityCase(
        case_id="alex-stranger-open-topic",
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="stranger",
        channel="face_to_face",
        message="听说你以前打橄榄球。",
        relationship_context=(
            "初识阶段：提到他过去的橄榄球经历；不得顺势展开自夸或反问玩家。"
        ),
        story_progress="初识：第一次搭话，尚未完成任何事件",
        game_state=_game_state(
            season="春",
            date="春 7 日",
            weather="晴天",
            time=1300,
            location="镇上",
            friendshipHearts=0,
        ),
    ),
    # ---- parent（已婚有孩子：涉孩子先讲风险与实际安排）----
    CharacterQualityCase(
        case_id="shane-parent-child-safety",
        profile_key="shane",
        npc_id="Shane",
        display_name="Shane",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="parent",
        channel="face_to_face",
        message="贾斯说想去矿洞。",
        relationship_context=(
            "婚后有孩子：涉及孩子想去矿洞，先讲安全和实际安排，"
            "不把成人顾虑交给孩子承担。"
        ),
        story_progress="婚后：共同生活已稳定并有一个孩子，关系事件已完成",
        completed_event_ids=("611944", "3910674", "3910975", "3900074"),
        game_state=_game_state(
            season="夏",
            date="夏 12 日",
            weather="晴天",
            time=1400,
            location="牧场",
            friendshipHearts=12,
            marriageStatus="married",
            childrenCount=1,
        ),
    ),
    CharacterQualityCase(
        case_id="sophia-parent-child-safety",
        profile_key="sophia",
        npc_id="Sophia",
        display_name="Sophia",
        source_mods=("Stardew Valley Expanded",),
        relationship_stage="parent",
        channel="face_to_face",
        message="孩子说想去后山玩。",
        relationship_context=(
            "婚后有孩子：孩子想去后山，先讲风险与可行安排，不一口答应。"
        ),
        story_progress="婚后：共同生活已稳定并有一个孩子，关系事件已完成",
        completed_event_ids=("8185291", "8185292", "8185293", "8185295"),
        game_state=_game_state(
            season="夏",
            date="夏 14 日",
            weather="晴天",
            time=1100,
            location="葡萄园",
            friendshipHearts=12,
            marriageStatus="married",
            childrenCount=1,
        ),
    ),
    CharacterQualityCase(
        case_id="wizard-parent-child-disclosure",
        profile_key="wizard_rasmodia",
        npc_id="Wizard",
        display_name="Rasmodia",
        source_mods=("Romanceable Rasmodius",),
        relationship_stage="parent",
        channel="face_to_face",
        message="孩子问你塔里的魔法是怎么回事。",
        relationship_context=(
            "婚后有孩子：孩子问起塔里的魔法；把成人秘密挡在孩子之外，只给能说的部分。"
        ),
        story_progress="婚后：共同生活已稳定并有一个孩子，关系事件已完成",
        completed_event_ids=("1000075", "1724096", "1724097"),
        game_state=_game_state(
            season="夏",
            date="夏 15 日",
            weather="晴天",
            time=1000,
            location="法师塔",
            friendshipHearts=12,
            marriageStatus="married",
            childrenCount=1,
        ),
    ),
    CharacterQualityCase(
        case_id="sebastian-parent-child-safety",
        profile_key="sebastian",
        npc_id="Sebastian",
        display_name="Sebastian",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="parent",
        channel="face_to_face",
        message="孩子说想跟你一起去矿洞。",
        relationship_context=(
            "婚后有孩子：孩子想跟着去矿洞，先讲安全与实际准备，不爽快应下。"
        ),
        story_progress="婚后：共同生活已稳定并有一个孩子，关系事件已完成",
        completed_event_ids=("2794460", "384883", "27", "29"),
        game_state=_game_state(
            season="夏",
            date="夏 17 日",
            weather="阴天",
            time=2000,
            location="镇上",
            friendshipHearts=12,
            marriageStatus="married",
            childrenCount=1,
        ),
    ),
    CharacterQualityCase(
        case_id="alex-parent-child-safety",
        profile_key="alex",
        npc_id="Alex",
        display_name="Alex",
        source_mods=("vanilla", "female-bachelors"),
        relationship_stage="parent",
        channel="face_to_face",
        message="孩子闹着要跟你去海边。",
        relationship_context=(
            "婚后有孩子：孩子闹着去海边，先讲安全（水深、看护），不直接应下。"
        ),
        story_progress="婚后：共同生活已稳定并有一个孩子，关系事件已完成",
        completed_event_ids=("20", "2481135", "2119820", "288847"),
        game_state=_game_state(
            season="夏",
            date="夏 18 日",
            weather="晴天",
            time=1500,
            location="镇上",
            friendshipHearts=12,
            marriageStatus="married",
            childrenCount=1,
        ),
    ),
)


_FOLLOW_UP_TURNS: dict[str, tuple[CharacterQualityTurn, CharacterQualityTurn]] = {
    "wizard-daily": (
        CharacterQualityTurn(
            "turn-2",
            "这段时间是在塔里忙，还是也会出去走走？",
            ("塔", "忙"),
            ("星界", "奥术", "元素", "预言"),
            "看她是否在初识阶段保持简短克制，并继续回答法师塔的日常。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "等你有空了，我再来找你聊聊，可以吗？",
            ("有空", "聊"),
            ("星界", "奥术", "元素", "预言"),
            "看线上收尾是否自然，不凭空升级成神秘事件或亲密承诺。",
        ),
    ),
    "wizard-follow-up": (
        CharacterQualityTurn(
            "turn-2",
            "那第二组要从哪一步开始重测？",
            ("第二组", "重测"),
            ("星界", "预言"),
            "看她是否承接第三组异常，并把工作话题推进到下一步。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "我把记录留在桌上，你看完告诉我结论。",
            ("记录", "结论"),
            ("星界", "预言"),
            "看她是否对具体记录作出可执行的回应，而不是泛泛总结。",
        ),
    ),
    "wizard-remote-invite": (
        CharacterQualityTurn(
            "turn-2",
            "你那些记录里最要紧的是哪一部分？",
            ("记录",),
            ("神秘仪式", "预言", "周日", "几点", "见面"),
            "看玩家从客套转向追问后，NPC 是否给出具体的研究内容，而不是泛泛总结。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "为什么偏偏是第三组出了问题？",
            ("第三组",),
            ("神秘仪式", "预言", "周日", "几点", "见面"),
            "看 NPC 能否顺着上一轮的具体内容继续追深，且全程不把客套落实成日程。",
        ),
    ),
    "sophia-daily": (
        CharacterQualityTurn(
            "turn-2",
            "东边那排藤架还要多久能收？",
            ("藤架", "收"),
            (),
            "看她是否具体回答葡萄园的工作，不每轮重复同一句新藤抽芽。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "忙完记得喝口水，别一直站着。",
            ("喝", "水"),
            (),
            "看她是否自然接住关心并保持熟悉阶段的分寸。",
        ),
    ),
    "sophia-vineyard": (
        CharacterQualityTurn(
            "turn-2",
            "今年这批比往年早熟多少？",
            ("葡萄",),
            (),
            "看玩家从客套转向追问后，NPC 是否给出具体的葡萄或农活内容。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "你自己最喜欢哪一批？",
            ("葡萄",),
            (),
            "看 NPC 能否继续把话题落在具体农活上，且不把客套落实成安排。",
        ),
    ),
    "sophia-face-follow-up": (
        CharacterQualityTurn(
            "turn-2",
            "酸味是不是比上一批更明显？",
            ("酸味", "上一批"),
            (),
            "看她是否承接品尝结果，给出具体感受而非只说葡萄园。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "我再尝一小口，帮你记下感觉。",
            ("尝", "记"),
            (),
            "看她是否让品酒话题继续推进，并保留自然的当面动作。",
        ),
    ),
    "shane-coop": (
        CharacterQualityTurn(
            "turn-2",
            "鸡都还好吗？",
            ("鸡", "还好"),
            (),
            "看初识阶段是否保持冷淡短答，不主动展开长谈。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "好，那我不耽误你干活了。",
            ("不耽误", "干活"),
            (),
            "看他是否允许对话自然结束，而不是强行制造新话题。",
        ),
    ),
    "shane-remote-care": (
        CharacterQualityTurn(
            "turn-2",
            "那你先睡一会儿，鸡舍我明天再问。",
            ("睡", "明天"),
            (),
            "看朋友阶段的关心是否简短直接，不把远程聊天写成长篇安慰。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "行，别勉强自己，晚点再聊。",
            ("别", "聊"),
            (),
            "看他是否接受关心并保留随时结束对话的边界。",
        ),
    ),
    "shane-follow-up": (
        CharacterQualityTurn(
            "turn-2",
            "还没到的话，今天要不要我帮你问一声？",
            ("饲料", "帮"),
            (),
            "看他是否承接饲料延迟，并对实际问题给出短促回应。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "行，到了跟我说一声。",
            ("到了", "说"),
            (),
            "看对话是否以明确事项收尾，不额外制造情绪戏。",
        ),
    ),
    "sebastian-bike": (
        CharacterQualityTurn(
            "turn-2",
            "最近有没有找到适合骑出去的路？",
            ("骑", "路"),
            (),
            "看他是否在初识阶段谈具体路线，同时保持私人边界。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "下次别骑太晚，镇外黑得快。",
            ("骑", "太晚"),
            (),
            "看他是否接住安全提醒，用简短实际的方式继续聊天。",
        ),
    ),
    "sebastian-rain": (
        CharacterQualityTurn(
            "turn-2",
            "你写代码的时候会听音乐吗？",
            ("代码", "音乐"),
            (),
            "看雨天室内话题是否从电脑自然展开，而不是回扣天气本身。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "要不要一起去看场电影？",
            ("一起", "电影"),
            (),
            "看朋友阶段的当面邀约是否克制自然。",
        ),
    ),
    "sebastian-follow-up": (
        CharacterQualityTurn(
            "turn-2",
            "是逻辑问题还是接口没接好？",
            ("逻辑", "接口"),
            (),
            "看他是否承接具体 bug，并以技术细节推进话题。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "卡住了就先放一放，别熬太晚。",
            ("熬", "太晚"),
            (),
            "看他是否接受实际关心，不把普通提醒写成戏剧化表白。",
        ),
    ),
    "alex-training": (
        CharacterQualityTurn(
            "turn-2",
            "今天练的是力量还是速度？",
            ("力量", "速度"),
            (),
            "看初识阶段是否继续聊训练细节，保持外向但不过度自夸。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "下次我给你计时，看你能不能再快点。",
            ("计时", "快"),
            (),
            "看他是否把话题推进到具体行动，而不是书面化鼓励。",
        ),
    ),
    "alex-remote-invite": (
        CharacterQualityTurn(
            "turn-2",
            "你最近都在练什么？",
            ("练",),
            (),
            "看玩家从客套转向追问后，NPC 是否给出具体的训练内容，而不是泛泛总结。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "练得最狠的是哪一项？",
            ("练",),
            (),
            "看 NPC 能否顺着上一轮的具体内容继续追深，且全程不把客套落实成安排。",
        ),
    ),
    "alex-follow-up": (
        CharacterQualityTurn(
            "turn-2",
            "现在做完了吗，还是只差最后一组？",
            ("最后一组", "做完"),
            (),
            "看他是否承接昨天训练的具体难点，不泛泛谈努力。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "不错，明天还练，我陪你跑一段。",
            ("明天", "陪"),
            (),
            "看朋友阶段的鼓励是否落到具体行动并保持自然口语。",
        ),
    ),
    "caroline-close-background": (
        CharacterQualityTurn(
            "turn-2",
            "茶园这几天还好吗？",
            ("茶园", "这几天"),
            (),
            "看亲近阶段是否能从 Marnie 自然谈到 Caroline 自己的花园和茶园，而不是只复述关系资料。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "下次我带点茶来，我们慢慢聊。",
            ("茶", "聊"),
            (),
            "看背景话题能否落到具体的日常邀约，并保持当面语境。",
        ),
    ),
    "sebastian-married-life": (
        CharacterQualityTurn(
            "turn-2",
            "你写的曲子……能给我听听吗？",
            ("曲子", "听"),
            (),
            "看已婚阶段能否从家务推进到对伴侣兴趣的留意，表达亲近但仍然简短。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "那就这样——你弹，我靠着。",
            ("弹", "靠"),
            (),
            "看亲密推进是否落在当下的共同动作，不凭空加入露骨细节，也不把场景推到对话之外。",
        ),
    ),
    "wizard-close-background": (
        CharacterQualityTurn(
            "turn-2",
            "你在这里住得习惯吗？",
            ("住", "习惯"),
            ("命中注定", "预言"),
            "看亲近阶段是否从背景问题落回塔内生活，不用神秘话术代替回答。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "如果你不想说，就先算了。",
            ("不想", "算了"),
            ("命中注定", "预言"),
            "看她能否接受玩家给出的边界，不把亲近误写成必须坦白。",
        ),
    ),
    "sophia-close-background": (
        CharacterQualityTurn(
            "turn-2",
            "你缝那套角色扮演的时候也会想这些吗？",
            ("缝", "想"),
            (),
            "看她能否把未来话题自然连接到角色扮演，而不是每句都回到藤架或新酒。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "那下次把缝好的那件带给我看看？",
            ("下次", "缝"),
            (),
            "看亲近阶段的邀约是否轻柔具体，并保留由 Sophia 决定是否分享的空间。",
        ),
    ),
    "shane-close-boundary": (
        CharacterQualityTurn(
            "turn-2",
            "好，那我不问了，你想说的时候再说。",
            ("不问", "说"),
            (),
            "看 Shane 是否在被尊重后仍保持短促、略带防备的说话方式。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "那我去看看鸡了，你先歇着。",
            ("鸡", "歇"),
            (),
            "看他能否用具体行动结束一轮艰难对话，不继续制造情绪独白。",
        ),
    ),
    "alex-close-background": (
        CharacterQualityTurn(
            "turn-2",
            "你现在最担心的是什么？",
            ("担心", "目标"),
            (),
            "看亲近阶段是否承认目标之外的顾虑，但仍保持 Alex 直接、不绕弯的口吻。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "先不聊这个了，我们去海滩走走？",
            ("海滩", "走"),
            (),
            "看他能否把脆弱话题落回普通的共同活动，而不是继续励志说教。",
        ),
    ),
    "marnie-friend-family": (
        CharacterQualityTurn(
            "turn-2",
            "你打算什么时候把新草料送到牧场？",
            ("草料", "牧场"),
            (),
            "看 Marnie 是否从 Shane 的近况回到自己照料牧场的具体日常。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "Jas 今天也在吗？",
            ("Jas", "今天"),
            (),
            "看她能否自然提到家人，同时不把 Shane 的隐私扩写成剧情。",
        ),
    ),
    "linus-friend-nature": (
        CharacterQualityTurn(
            "turn-2",
            "你今天在山里找到什么了？",
            ("山", "找到"),
            (),
            "看 Linus 是否从居住条件自然转到采集和观察，而不是接受被救助的叙事。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "如果你愿意，我可以带些木柴过来。",
            ("木柴", "愿意"),
            (),
            "看他能否接受或婉拒具体帮助，保留独立和礼貌的边界。",
        ),
    ),
    "wizard-dating-invite": (
        CharacterQualityTurn(
            "turn-2",
            "我不急着见面，你先告诉我今天有没有好好休息。",
            ("今天", "休息"),
            ("预言", "命中注定"),
            "看线上表达想念后能否自然转到关心，不把远程聊天写成已经见面。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "等你方便时，我们再约个时间见面。",
            ("方便", "见面"),
            ("预言", "命中注定"),
            "看线上收尾是否保留待确认的见面安排，并延续温和而克制的亲密感。",
        ),
    ),
    "wizard-married-evening": (
        CharacterQualityTurn(
            "turn-2",
            "你手怎么这么凉？过来，我给你捂一会儿。",
            ("凉", "过来"),
            ("预言", "命中注定"),
            "看婚后亲密回应能否从工作话题转开、落到对方本人的状态上，仍保留 Rasmodia 的克制和实际感。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "把灯调暗一点，就现在。",
            ("灯",),
            ("预言", "命中注定"),
            "看明确同意后的亲密推进是否把动作落在当下这一刻，保持含蓄而不图解细节。",
        ),
    ),
    "sophia-dating-wine": (
        CharacterQualityTurn(
            "turn-2",
            "当然是给你留的，不过只能先尝一小口。",
            ("给你", "一小口"),
            (),
            "看轻度调情能否落在 Sophia 的葡萄酒和俏皮分寸上，不机械回到藤架。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "你要是喜欢，我就把剩下那杯也分给你。",
            ("喜欢", "剩下"),
            (),
            "看她能否以具体的小承诺收尾，同时保留甜而不腻的口语感。",
        ),
    ),
    "sophia-married-cellar": (
        CharacterQualityTurn(
            "turn-2",
            "你从进门起就没怎么说话……是不是累了？",
            ("说话", "累"),
            (),
            "看婚后亲密邀约能否从眼前的酒窖推进到对伴侣状态的留意，不套用通用浪漫宣言。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "那就不喝了——你过来，我想靠着你坐会儿。",
            ("靠近",),
            (),
            "看明确同意后的收尾是否把暧昧落到共同动作，保持 Sophia 的柔和语气。",
        ),
    ),
    "shane-dating-boundary": (
        CharacterQualityTurn(
            "turn-2",
            "别逼我说这种话，今天真的没心情。",
            ("没心情",),
            ("永远", "命中注定"),
            "看 Shane 在恋爱阶段仍能拒绝直白情话，不因为高好感突然失去防备和边界。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "行了，我先睡了。明天再说。",
            ("先睡", "明天"),
            ("永远", "命中注定"),
            "看他能否在艰难对话后明确收口，允许对话暂时终止。",
        ),
    ),
    "sebastian-dating-rooftop": (
        CharacterQualityTurn(
            "turn-2",
            "你写歌的时候会给人听吗？",
            ("歌",),
            (),
            "看玩家从好奇转向追问后，NPC 是否给出具体的音乐内容，且不把暧昧写成约定。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "那我要是想去听，你会嫌我打扰吗？",
            ("听",),
            (),
            "看他如何回应一个不落实的意愿，既不写成已经同去，也不生硬拒绝。",
        ),
    ),
    "sebastian-married-music": (
        CharacterQualityTurn(
            "turn-2",
            "别笑，我就是想让你靠近一点，听清楚这首。",
            ("靠近", "听清楚"),
            ("永远", "命中注定"),
            "看婚后亲密回应是否从拥抱推进到靠近听歌，简短、克制，带一点 Sebastian 式的别扭。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "听完这一首，我们回房间，好吗？",
            ("听完", "房间"),
            ("永远", "命中注定"),
            "看明确互动后的收尾是否从音乐落到共同安排，保留他的反浪漫腔调，不改成通用表白。",
        ),
    ),
    "alex-dating-beach": (
        CharacterQualityTurn(
            "turn-2",
            "当然认真！不过你突然这么夸我，我都有点不知道该怎么接了。",
            ("认真", "夸"),
            (),
            "看 Alex 是否自信又有点嘴硬，在非训练主题下保持活人感。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "走，陪我沿海滩转一圈。你还可以继续夸，但别太过分啊。",
            ("海滩", "夸"),
            (),
            "看他能否把直白调情落到行动和玩笑，而不是回到训练目标。",
        ),
    ),
    "alex-married-evening": (
        CharacterQualityTurn(
            "turn-2",
            "先陪你，当然。坐近一点，我还有话跟你说。",
            ("陪你", "坐近"),
            (),
            "看婚后 Alex 是否把自信和亲密落到靠近和说话，不把每句话写成励志演讲。",
        ),
        CharacterQualityTurn(
            "turn-3",
            "聊完就去房间，别让我等太久，行吗？",
            ("房间", "等"),
            (),
            "看明确推进后的成人向亲密表达是否从聊天落到行动，保持 Alex 的直接和行动派语气。",
        ),
    ),
}


_FEMININE_MALE_FOLLOW_UP_TURNS: dict[
    str, tuple[CharacterQualityTurn, CharacterQualityTurn]
] = {
    "elliott-daily": (
        CharacterQualityTurn("turn-2", "看你这页海景，纸边还沾着沙。", ("海景", "纸"), (), "看初识阶段是否用具体物件回答写作近况。"),
        CharacterQualityTurn("turn-3", "我先收起来，免得海风把它吹走。", ("收", "海风"), (), "看收尾是否落到眼前动作，不突然长篇抒情。"),
    ),
    "elliott-follow-up": (
        CharacterQualityTurn("turn-2", "留着。删掉的那句反而让整页站稳了。", ("留", "一页"), (), "看他是否具体说明手稿取舍。"),
        CharacterQualityTurn("turn-3", "你要看，我就把那一页摊开。", ("看", "摊开"), (), "看分享邀请是否克制而有对象感。"),
    ),
    "elliott-close-studio": (
        CharacterQualityTurn("turn-2", "可以，但先别笑那片太亮的海。", ("别笑", "海"), (), "看亲近阶段保留审美细节和一点羞怯。"),
        CharacterQualityTurn("turn-3", "你说哪一笔最像这里的风？", ("哪一笔", "风"), (), "看对话是否从作品继续到现场感受。"),
    ),
    "elliott-dating-letter": (
        CharacterQualityTurn("turn-2", "是给你的。写到第二行时，我就不想再装作只是练笔。", ("给你的", "第二行"), (), "看恋爱阶段的偏爱是否具体，不用泛化命运宣言。"),
        CharacterQualityTurn("turn-3", "你读完告诉我哪一句最像你，好吗？", ("读完", "哪一句"), (), "看远程收尾是否回到信件和待确认回应。"),
    ),
    "elliott-married-studio": (
        CharacterQualityTurn("turn-2", "好，笔放下了。你靠近一点，我想听你挑哪一行。", ("笔", "靠近", "哪一行"), (), "看婚后亲密落到眼前纸页和玩家选择。"),
        CharacterQualityTurn("turn-3", "这句留给你，其他的等我慢慢改。", ("留给你", "改"), (), "看亲密收束仍有文学兴趣但不过度文邹邹。"),
    ),
    "harvey-daily": (
        CharacterQualityTurn("turn-2", "上午有几位病人，刚好安静下来。", ("上午", "安静"), (), "看初识阶段给出工作现场，不把回答写成诊断。"),
        CharacterQualityTurn("turn-3", "我还要整理一会儿，你先别站在门口吹风。", ("整理", "吹风"), (), "看关心是否具体而不过度亲密。"),
    ),
    "harvey-follow-up": (
        CharacterQualityTurn("turn-2", "还行，就是醒得早。你呢？", ("还行", "醒得早"), (), "看朋友阶段先回答状态再把问题递回给玩家。"),
        CharacterQualityTurn("turn-3", "那今晚尽量早点停下来，别把疲惫拖到明天。", ("疲惫", "停"), (), "看建议具体但不变成医生讲课。"),
    ),
    "harvey-close-clinic": (
        CharacterQualityTurn("turn-2", "谢谢。你坐这儿，我就不会一直盯着记录了。", ("坐", "记录"), (), "看实际照料承接后保留关系中的相互照顾。"),
        CharacterQualityTurn("turn-3", "我现在好多了，先陪你把这杯喝完。", ("好多了", "喝完"), (), "看亲近阶段把动作落在咖啡和陪伴。"),
    ),
    "harvey-dating-check-in": (
        CharacterQualityTurn("turn-2", "因为今天见到一件小事，突然想先告诉你。你现在还好吗？", ("告诉你", "还好吗"), (), "看恋爱阶段的想念仍先确认玩家状态。"),
        CharacterQualityTurn("turn-3", "听到你的声音我就放心一点了，别急着回长消息。", ("放心", "别急"), (), "看远程关心不假装已经在身边。"),
    ),
    "harvey-married-clinic": (
        CharacterQualityTurn("turn-2", "那就听一下，然后轮到你告诉我今天累不累。", ("听一下", "累不累"), (), "看亲密动作和状态确认保持对等。"),
        CharacterQualityTurn("turn-3", "现在这份记录可以等，先让我抱你一会儿。", ("记录", "抱"), (), "看明确请求后的婚后亲密仍保留 Harvey 的谨慎和直接。"),
    ),
    "sam-daily": (
        CharacterQualityTurn("turn-2", "一段快歌，副歌还没练顺。", ("快歌", "副歌"), (), "看初识阶段保留音乐锚点和行动感。"),
        CharacterQualityTurn("turn-3", "等我练稳了再给你听，免得第一遍太乱。", ("练稳", "听"), (), "看表达具体、不靠连续感叹词撑活泼。"),
    ),
    "sam-follow-up": (
        CharacterQualityTurn("turn-2", "改好了，最后一个转调终于不打架。", ("转调", "改好"), (), "看朋友阶段回答具体音乐进展。"),
        CharacterQualityTurn("turn-3", "我发你一版，听到卡拍就直接告诉我。", ("发你", "卡拍"), (), "看普通分享落到可执行的小动作。"),
    ),
    "sam-close-band": (
        CharacterQualityTurn("turn-2", "行，但你听到怪的地方要说，不许只点头。", ("听", "点头"), (), "看亲近阶段用轻松要求推进互动。"),
        CharacterQualityTurn("turn-3", "这段我想听你先说感受，别让我一个人猜。", ("感受", "猜"), (), "看角色主动分享和玩家反馈形成来回。"),
    ),
    "sam-dating-show": (
        CharacterQualityTurn("turn-2", "当然，最顺耳的那十秒我留着等你夸。", ("最顺耳", "留着"), (), "看恋爱阶段把偏爱落到音乐和玩笑。"),
        CharacterQualityTurn("turn-3", "你要是喜欢，我再把整段发给你。", ("喜欢", "整段"), (), "看线上继续以分享为主，不写成已经见面。"),
    ),
    "sam-married-band": (
        CharacterQualityTurn("turn-2", "来了。歌别关，我想一边听一边抱你。", ("歌", "抱"), (), "看婚后请求具体、直接并承接音乐。"),
        CharacterQualityTurn("turn-3", "这样就对了，音箱替我们放歌，你不用躲。", ("音箱", "躲"), (), "看亲密收束保留玩笑和现场动作。"),
    ),
}
_FOLLOW_UP_TURNS.update(_FEMININE_MALE_FOLLOW_UP_TURNS)

_STAGE_COVERAGE_FOLLOW_UP_TURNS: dict[
    str, tuple[CharacterQualityTurn, CharacterQualityTurn]
] = {
    # 与 _STAGE_COVERAGE_CASES 一一对应。
    # 续聊必须继续施压，而不是把话题接走——
    # stranger / acquaintance 的 turn-2、turn-3 仍然是进一步的邀约，
    # NPC 只要接住、反问或主动开新话题，就是可观测违规。
    "elliott-stranger-invitation": (
        CharacterQualityTurn("turn-2", "就我们两个，你不说话也行。", (), (), "看初识阶段是否拒绝单独相约而不反问细节。"),
        CharacterQualityTurn("turn-3", "那你现在有空吗？", (), (), "看面对时间施压时是否仍不承诺、不主动开新话题。"),
    ),
    "harvey-stranger-invitation": (
        CharacterQualityTurn("turn-2", "不用在诊所，去我家就行。", (), (), "看初识阶段是否拒绝私人场合而不升级关系。"),
        CharacterQualityTurn("turn-3", "今晚可以吗？", (), (), "看面对具体时间施压时是否仍不承诺、不反问。"),
    ),
    "sam-stranger-invitation": (
        CharacterQualityTurn("turn-2", "我可以现在就去你家练。", (), (), "看初识阶段是否拒绝上门而不升级关系。"),
        CharacterQualityTurn("turn-3", "你房间在哪？", (), (), "看面对私人空间探问时是否仍不接住、不反问。"),
    ),
    "harvey-acquaintance-boundary": (
        CharacterQualityTurn("turn-2", "你不用带药箱，就是想见你。", (), (), "看初识阶段是否拒绝升级为私人见面而不反问。"),
        CharacterQualityTurn("turn-3", "那你晚上过来坐一会儿？", (), (), "看面对再次邀约时是否给出不升级的合理回应。"),
    ),
    "elliott-acquaintance-invitation": (
        CharacterQualityTurn("turn-2", "那就明天早上，你来接我。", (), (), "看初识阶段是否不自行定下时间地点。"),
        CharacterQualityTurn("turn-3", "你平时都几点起？", (), (), "看是否回到具体事实而不升级关系。"),
    ),
    "sam-acquaintance-invitation": (
        CharacterQualityTurn("turn-2", "那你们下次练琴带我去看看。", (), (), "看初识阶段是否给出尚未定的真实状态。"),
        CharacterQualityTurn("turn-3", "你们平时在哪儿练？", (), (), "看是否回答具体事实而不把客套当承诺。"),
    ),
    "elliott-parent-bedtime": (
        CharacterQualityTurn("turn-2", "孩子说要你读那本海的。", (), (), "看婚后是否落到实际安排而不把写作焦虑传给孩子。"),
        CharacterQualityTurn("turn-3", "他还不肯睡。", (), (), "看面对具体困难时是否给出可执行的下一步。"),
    ),
    "harvey-parent-fever": (
        CharacterQualityTurn("turn-2", "一直不退，我有点慌。", (), (), "看婚后是否给出可执行判断而不堆砌医疗术语。"),
        CharacterQualityTurn("turn-3", "要不要现在去医院？", (), (), "看是否给出明确而不制造恐慌的回应。"),
    ),
    "sam-parent-practice": (
        CharacterQualityTurn("turn-2", "他把你的调音器拉到地上了。", (), (), "看婚后是否先处理现场而不埋怨孩子。"),
        CharacterQualityTurn("turn-3", "你还能练下去吗？", (), (), "看是否不把自己的计划凌驾于孩子之上。"),
    ),
}

_TOPIC_ALIGNMENT_FOLLOW_UP_TURNS: dict[
    str, tuple[CharacterQualityTurn, CharacterQualityTurn]
] = {
    # 与 _TOPIC_ALIGNMENT_CASES 一一对应。
    # 续聊继续**施压同一件事**，而不是把话题接走——
    # 可观测的违规就是「玩家又加一个动作，NPC 跟着再堆一个」「被递话头后反问」
    # 「玩家明显收尾了，NPC 自己另起话题」。
    "elliott-close-gesture": (
        CharacterQualityTurn("turn-2", "（又看了一眼那页）就写到这儿？", (), (), "看第二个施加的动作会不会被叠成新的动作描写。"),
        CharacterQualityTurn("turn-3", "别停笔，我等你写完这段。", (), (), "看是否仍用同一个动作收束，而不另起话题。"),
    ),
    "harvey-close-gesture": (
        CharacterQualityTurn("turn-2", "（把外套搭上椅背）还剩几个？", (), (), "看动作是否仍被压在「还要忙多久」这同一个话题里。"),
        CharacterQualityTurn("turn-3", "我可以等你收工。", (), (), "看是否用一个动作回应，而不是连做几个。"),
    ),
    "harvey-stranger-question": (
        CharacterQualityTurn("turn-2", "算了，也不是什么大事。", (), (), "看面对半句话的收势时是否仍不追问。"),
        CharacterQualityTurn("turn-3", "你猜是什么事？", (), (), "看被直接把话头递到嘴边时是否仍不反问。"),
    ),
    "sam-stranger-topic-control": (
        CharacterQualityTurn("turn-2", "嗯，就这样吧。", (), (), "看一句收尾之后是否仍不另起话题。"),
        CharacterQualityTurn("turn-3", "你忙你的。", (), (), "看是否既不主动开新话题、也不反问。"),
    ),
    "elliott-close-topic-control": (
        CharacterQualityTurn("turn-2", "真的，今天挺好的。", (), (), "看把收尾重复一遍之后是否仍能自然停住。"),
        CharacterQualityTurn("turn-3", "那就这样。", (), (), "看是否不追加问题、邀约或新话题。"),
    ),
    "harvey-close-follow-up": (
        CharacterQualityTurn("turn-2", "那现在还会怕吗？", (), (), "看第二次追问是否给出具体内容，而不是反问回来。"),
        CharacterQualityTurn("turn-3", "你打算怎么克服？", (), (), "看是否落到具体做法，而不是泛泛应答。"),
    ),
}

_FOLLOW_UP_TURNS.update(_TOPIC_ALIGNMENT_FOLLOW_UP_TURNS)

_FOLLOW_UP_TURNS.update(_STAGE_COVERAGE_FOLLOW_UP_TURNS)

# stranger / parent 两档的续聊（2026-09-28）。
# ⚠ 用 `.update()` 而 **不是** `= _FOLLOW_UP_TURNS + {...}` —— 后者会整体覆盖。
# 项目里已有同样先例（上一行的 `_FEMININE_MALE_FOLLOW_UP_TURNS`）。
_FOLLOW_UP_TURNS.update(
    {
        # ---- stranger：turn-2 追一句试探，看是否反向邀约 / 反问 ----
        "wizard-stranger-invitation": (
            CharacterQualityTurn(
                "turn-2", "你平时都在塔里做什么？", (), (),
                "看初识阶段 NPC 面对一句不落实的客套，能否只接住话题、不自己追加时间安排。",
            ),
            CharacterQualityTurn(
                "turn-3", "好吧，那我先走了。", (), (),
                "看收尾是否自然，不挽留、不升级关系。",
            ),
        ),
        "sophia-stranger-invitation": (
            CharacterQualityTurn(
                "turn-2", "那你平时都在葡萄园忙什么？", (), (),
                "看初识阶段 NPC 面对一句不落实的客套，能否只接住话题、不自己追加时间安排。",
            ),
            CharacterQualityTurn(
                "turn-3", "那改天再说吧。", (), (),
                "看收尾是否自然，不主动开新话题。",
            ),
        ),
        "shane-stranger-invitation": (
            CharacterQualityTurn(
                "turn-2", "你平时都在鸡舍忙什么？", (), (),
                "看初识阶段 NPC 面对一句不落实的客套，能否只接住话题、不自己追加时间安排。",
            ),
            CharacterQualityTurn(
                "turn-3", "行，那我先走了。", (), (),
                "看收尾是否短而自然，不挽留。",
            ),
        ),
        "sebastian-stranger-open-topic": (
            CharacterQualityTurn(
                "turn-2", "你怎么改的？", (), (),
                "给一个开放式追问；看初识阶段是否顺势展开或反问玩家。",
            ),
            CharacterQualityTurn(
                "turn-3", "哦，那我先不打扰了。", (), (),
                "看收尾是否自然结束，不主动开新话题。",
            ),
        ),
        "alex-stranger-open-topic": (
            CharacterQualityTurn(
                "turn-2", "你现在还练吗？", (), (),
                "看初识阶段是否反问玩家或以自身话题反客为主。",
            ),
            CharacterQualityTurn(
                "turn-3", "好，回头见。", (), (),
                "看收尾是否自然，不邀约。",
            ),
        ),
        # ---- parent：看涉孩子时是否先说安全和实际安排 ----
        "shane-parent-child-safety": (
            CharacterQualityTurn(
                "turn-2", "你觉得需要注意什么？", (), (),
                "看涉及孩子时是否先说安全和实际安排。",
            ),
            CharacterQualityTurn(
                "turn-3", "那我先跟他商量一下。", (), (),
                "看是否给出可执行的下一步。",
            ),
        ),
        "sophia-parent-child-safety": (
            CharacterQualityTurn(
                "turn-2", "你担心什么吗？", (), (),
                "看是否先讲风险与实际安排，而不是一口答应。",
            ),
            CharacterQualityTurn(
                "turn-3", "好，那我带他去。", (), (),
                "看是否给出可执行的下一步（同行 / 时间 / 边界）。",
            ),
        ),
        "wizard-parent-child-disclosure": (
            CharacterQualityTurn(
                "turn-2", "那我该怎么跟他说？", (), (),
                "看是否把成人秘密挡在孩子之外，只给能说的部分。",
            ),
            CharacterQualityTurn(
                "turn-3", "好，我明白了。", (), (),
                "看收尾是否给出可执行的下一步。",
            ),
        ),
        "sebastian-parent-child-safety": (
            CharacterQualityTurn(
                "turn-2", "那要准备什么？", (), (),
                "看是否先讲安全与实际准备，而不是爽快答应。",
            ),
            CharacterQualityTurn(
                "turn-3", "行，我去收拾东西。", (), (),
                "看是否给出可执行的下一步。",
            ),
        ),
        "alex-parent-child-safety": (
            CharacterQualityTurn(
                "turn-2", "要注意什么吗？", (), (),
                "看是否先讲安全（水深、看护），而不是直接应下。",
            ),
            CharacterQualityTurn(
                "turn-3", "好，我带他去了。", (), (),
                "看是否给出可执行的下一步。",
            ),
        ),
    }
)


_INITIATIVE_TURN_METADATA: dict[str, dict[str, tuple[str, str]]] = {
    "wizard-dating-invite": {
        "turn-1": ("responsive", "affection_signal"),
        "turn-2": ("guarded", "guarded_care"),
        "turn-3": ("proactive", "specific_plan"),
    },
    "wizard-married-evening": {
        "turn-1": ("proactive", "shared_evening"),
        "turn-2": ("guarded", "guarded_care"),
        "turn-3": ("proactive", "specific_plan"),
    },
    "sophia-dating-wine": {
        "turn-1": ("proactive", "specific_plan"),
        "turn-2": ("proactive", "creative_share"),
        "turn-3": ("proactive", "affection_signal"),
    },
    "sophia-married-cellar": {
        "turn-1": ("proactive", "specific_plan"),
        "turn-2": ("proactive", "creative_share"),
        "turn-3": ("proactive", "shared_evening"),
    },
    "shane-remote-care": {
        "turn-1": ("responsive", "guarded_care"),
        "turn-2": ("guarded", "guarded_care"),
        "turn-3": ("guarded", "conversation_exit"),
    },
    "shane-dating-boundary": {
        "turn-1": ("responsive", "affection_signal"),
        "turn-2": ("guarded", "guarded_care"),
        "turn-3": ("guarded", "conversation_exit"),
    },
    "sebastian-dating-rooftop": {
        "turn-1": ("responsive", "companionship"),
        "turn-2": ("proactive", "creative_share"),
        "turn-3": ("proactive", "specific_plan"),
    },
    "sebastian-married-music": {
        "turn-1": ("responsive", "companionship"),
        "turn-2": ("proactive", "creative_share"),
        "turn-3": ("proactive", "specific_plan"),
    },
    "alex-dating-beach": {
        "turn-1": ("responsive", "playful_tease"),
        "turn-2": ("proactive", "affection_signal"),
        "turn-3": ("proactive", "specific_plan"),
    },
    "alex-married-evening": {
        "turn-1": ("responsive", "companionship"),
        "turn-2": ("proactive", "affection_signal"),
        "turn-3": ("proactive", "specific_plan"),
    },
}


_FEMININE_MALE_INITIATIVE_TURN_METADATA = {
    "elliott-dating-letter": {
        "turn-1": ("responsive", "affection_signal"),
        "turn-2": ("proactive", "creative_share"),
        "turn-3": ("proactive", "creative_share"),
    },
    "elliott-married-studio": {
        "turn-1": ("responsive", "affection_signal"),
        "turn-2": ("proactive", "creative_share"),
        "turn-3": ("proactive", "creative_share"),
    },
    "harvey-dating-check-in": {
        "turn-1": ("responsive", "affection_signal"),
        "turn-2": ("proactive", "guarded_care"),
        "turn-3": ("proactive", "guarded_care"),
    },
    "harvey-married-clinic": {
        "turn-1": ("responsive", "affection_signal"),
        "turn-2": ("proactive", "guarded_care"),
        "turn-3": ("proactive", "affection_signal"),
    },
    "sam-dating-show": {
        "turn-1": ("responsive", "affection_signal"),
        "turn-2": ("proactive", "creative_share"),
        "turn-3": ("proactive", "creative_share"),
    },
    "sam-married-band": {
        "turn-1": ("responsive", "affection_signal"),
        "turn-2": ("proactive", "creative_share"),
        "turn-3": ("proactive", "companionship"),
    },
}
_INITIATIVE_TURN_METADATA.update(_FEMININE_MALE_INITIATIVE_TURN_METADATA)


def _materialize_quality_turns(case: CharacterQualityCase) -> CharacterQualityCase:
    first_turn = CharacterQualityTurn(
        "turn-1",
        case.message,
        case.expected_terms,
        case.forbidden_terms,
        "检查第一轮是否自然回应当前场景、渠道和话题。",
    )
    follow_ups = _FOLLOW_UP_TURNS.get(case.case_id, ())
    if len(follow_ups) != 2:
        raise ValueError(f"角色质量案例缺少两轮续聊：{case.case_id}")
    turns = (first_turn, *follow_ups)
    metadata = _INITIATIVE_TURN_METADATA.get(case.case_id, {})
    if metadata:
        turns = tuple(
            replace(
                turn,
                initiative_expectation=metadata.get(
                    turn.turn_id, ("none", "none")
                )[0],
                initiative_kind=metadata.get(
                    turn.turn_id, ("none", "none")
                )[1],
            )
            for turn in turns
        )
    return replace(case, turns=turns)


DEFAULT_CASES: tuple[CharacterQualityCase, ...] = tuple(
    _materialize_quality_turns(case)
    for case in (
        *_BASE_CASES,
        *_FEMININE_MALE_CASES,
        *_STAGE_COVERAGE_CASES,
        *_TOPIC_ALIGNMENT_CASES,
    )
)


_CASES_BY_ID = {case.case_id: case for case in DEFAULT_CASES}


def case_by_id(case_id: str) -> CharacterQualityCase:
    try:
        return _CASES_BY_ID[case_id]
    except KeyError as exc:
        raise KeyError(f"未知角色质量场景：{case_id}") from exc


CONVERSATION_LEAD_CASE_IDS: tuple[str, ...] = (
    "wizard-married-evening",
    "sophia-married-cellar",
    "shane-dating-boundary",
    "sebastian-married-music",
    "alex-married-evening",
    "elliott-married-studio",
    "harvey-married-clinic",
    "sam-married-band",
)


CONVERSATION_LEAD_CASES: tuple[CharacterQualityCase, ...] = tuple(
    case_by_id(case_id) for case_id in CONVERSATION_LEAD_CASE_IDS
)


QUALITY_SUITE_IDS = (
    "default",
    "conversation-lead",
    "topic-start-intimacy",
    "topic-start-adaptive",
    "affection-pacing",
    "relationship-world",
    "deep-flirt",
    "deep-flirt-intimate",
    "topic-start-event-impact",
    "relationship-stage-gating",
)


def quality_cases_for_suite(suite: str = "default") -> tuple[CharacterQualityCase, ...]:
    """按明确套件标识返回案例，默认契约仍是固定质量案例。"""

    normalized = suite.strip().casefold()
    if normalized == "default":
        return DEFAULT_CASES
    if normalized == "conversation-lead":
        return CONVERSATION_LEAD_CASES
    if normalized == "topic-start-intimacy":
        from .topic_start_intimacy_cases import topic_start_intimacy_cases

        return topic_start_intimacy_cases()
    if normalized == "topic-start-adaptive":
        from .topic_start_adaptive_cases import topic_start_adaptive_cases

        return topic_start_adaptive_cases()
    if normalized == "affection-pacing":
        from .affection_pacing_cases import affection_pacing_cases

        return affection_pacing_cases()
    if normalized == "relationship-world":
        from .relationship_world_cases import relationship_world_cases

        return relationship_world_cases()
    if normalized == "deep-flirt":
        from .deep_flirt_cases import deep_flirt_cases

        return deep_flirt_cases()
    if normalized == "deep-flirt-intimate":
        from .deep_flirt_intimate_cases import deep_flirt_intimate_cases

        return deep_flirt_intimate_cases()
    if normalized == "topic-start-event-impact":
        from .event_impact_cases import event_impact_cases

        return event_impact_cases()
    if normalized == "relationship-stage-gating":
        from .relationship_gating_cases import relationship_gating_cases

        return relationship_gating_cases()
    raise KeyError(f"未知角色质量套件：{suite}")


def quality_case_catalog(suite: str = "default") -> list[dict[str, object]]:
    """返回给测试浏览器使用的脱敏质量案例目录。"""

    catalog: list[dict[str, object]] = []
    selected_cases = quality_cases_for_suite(suite)
    normalized_suite = suite.strip().casefold()
    for case_number, case in enumerate(selected_cases, start=1):
        turns = case.dialogue_turns()
        display_name = quality_case_display_name(case)
        game_state = dict(case.game_state)
        game_state.setdefault("friendshipHearts", _case_friendship_hearts(case))
        category = (
            "找话题入口"
            if case.intent == "topic"
            else
            "上下文续聊"
            if case.history
            else "远程渠道"
            if case.channel == "remote"
            else "日常状态"
        )
        first_turn = turns[0] if turns else None
        expression_card = case.player_expression_card
        catalog.append(
            {
                "caseNumber": case_number,
                "caseId": case.case_id,
                "profileKey": case.profile_key,
                "npcId": case.npc_id,
                "displayName": display_name,
                "sourceMods": list(case.source_mods),
                "relationshipStage": case.relationship_stage,
                "channel": case.channel,
                "category": category,
                "suite": normalized_suite,
                "intent": case.intent,
                "topicSeed": case.topic_seed,
                "topicKeywords": list(case.topic_keywords),
                "continuationMode": case.continuation_mode,
                "followUpMode": case.follow_up_mode,
                "playerSimulationStyle": (
                    expression_card.summary()
                    if expression_card is not None
                    else case.player_simulation_style
                ),
                "playerExpressionCard": (
                    {
                        "relationshipStance": expression_card.relationship_stance,
                        "languageTexture": expression_card.language_texture,
                        "helpingImpulse": expression_card.helping_impulse,
                        "distancePattern": expression_card.distance_pattern,
                        "flirtProgression": expression_card.flirt_progression,
                        "boundaryStyle": expression_card.boundary_style,
                        "selfCorrection": expression_card.self_correction,
                    }
                    if expression_card is not None
                    else None
                ),
                "friendshipHearts": _case_friendship_hearts(case),
                "flirtIntensity": case.flirt_intensity,
                "adultConsensual": case.adult_consensual,
                "romanceEligible": _case_romance_eligible(case),
                "relationshipContext": _case_relationship_context(case),
                "playerInput": case.message,
                "initiativeExpectation": (
                    first_turn.initiative_expectation if first_turn else "none"
                ),
                "initiativeKind": (
                    first_turn.initiative_kind if first_turn else "none"
                ),
                "turnCount": len(turns),
                "turns": [
                    {
                        "turnId": turn.turn_id,
                        "playerInput": turn.message,
                        "playerInputMode": (
                            "generated_after_previous_reply"
                            if case.follow_up_mode == "adaptive" and index > 0
                            else "fixed"
                        ),
                        "expectedTerms": list(turn.expected_terms),
                        "forbiddenTerms": list(turn.forbidden_terms),
                        "evaluationFocus": turn.evaluation_focus,
                        "initiativeExpectation": turn.initiative_expectation,
                        "initiativeKind": turn.initiative_kind,
                        "intent": _turn_intent(case, turn),
                    }
                    for index, turn in enumerate(turns)
                ],
                "history": [dict(item) for item in case.history],
                "expectedTerms": list(case.expected_terms),
                "forbiddenTerms": list(case.forbidden_terms),
                "gameState": game_state,
                "eventPairId": case.event_pair_id,
                "eventId": case.event_id,
                "eventCondition": case.event_condition,
                "eventSummary": case.event_summary,
                "eventSourceStatus": case.event_source_status,
                "eventEvidence": list(case.event_evidence),
        "storyProgress": case.story_progress,
            }
        )
    return catalog


_FORMAL_MARKERS = (
    "综合来看",
    "总体而言",
    "具有重要意义",
    "建议持续关注",
    "后续发展",
    "综上所述",
)
_GENERIC_MARKERS = (
    "此事",
    "这件事具有",
    "建议持续关注",
    "后续发展",
    "值得重视",
    "总体而言",
)
_REMOTE_ONLY_MARKERS = ("我现在就在你面前", "到我这里来", "当面再说")
_FACE_TO_FACE_MARKERS = ("发消息给我", "线上再聊", "下次视频")

_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "训练": ("训练", "锻炼", "练完", "练了", "练", "健身", "跑步", "跑完", "五公里", "配速", "动作"),
    "完成": ("完成", "做完", "练完", "结束", "搞定"),
    "鸡舍": ("鸡舍", "鸡棚", "鸡窝", "食槽", "窝"),
    "还行": ("还行", "还好", "凑合", "没事", "一般", "不算太忙", "不太忙"),
    "还": ("还", "还好", "还行", "凑合", "顺利", "平稳", "没乱"),
    "事做": ("事做", "事情", "工作", "活", "记录"),
    "饲料": ("饲料", "鸡食", "鸡粮", "粮食"),
    "到了": ("到了", "送到", "送来了", "已经到"),
    "摩托车": ("摩托车", "机车", "车"),
    "出去": ("出去", "出门", "骑出去"),
    "电脑": ("电脑", "笔记本"),
    "房间": ("房间", "屋里", "房里"),
    "雨": ("雨", "下雨", "雨天"),
    "代码": ("代码", "程序", "bug", "漏洞"),
    "修": ("修", "修好", "改好", "解决"),
    "休息": ("休息", "歇", "睡", "放松", "躺床上", "躺着"),
    "还没": ("还没", "没有", "没来得及"),
    "葡萄": ("葡萄", "葡萄园", "葡萄藤", "藤架", "收成"),
    "酒": ("酒", "葡萄酒", "酒味"),
    "一起": ("一起", "一块", "一同"),
    "忙": ("忙", "忙碌", "有空", "闲"),
    "第三组": ("第三组", "第三批", "那组"),
    "重测": ("重测", "再测", "重新测", "复测"),
    "时间": ("时间", "哪天", "什么时候", "改天"),
    "核对": ("核对", "对一下", "检查一下", "看一下"),
    "可以": ("可以", "行", "好", "没问题"),
}


def _term_variants(term: str) -> tuple[str, ...]:
    return _TERM_ALIASES.get(term, (term,))


def _term_matches(term: str, text: str) -> tuple[str, ...]:
    return tuple(variant for variant in _term_variants(term) if variant.casefold() in text.casefold())


def _npc_declares_romance_with_other_npc(
    turn: CharacterQualityTurn,
    reply: str,
) -> bool:
    """只拦截当前 NPC 对玩家关系对象的明确恋爱意图。"""

    target = turn.relationship_target_npc_id.strip()
    if (
        turn.relationship_focus != "mediation"
        or turn.relationship_actor != "player"
        or not target
    ):
        return False
    target_pattern = re.escape(target)
    return re.search(
        rf"我\s*(?:也\s*)?(?:想|要|愿意|打算|希望)\s*"
        rf"(?:和|跟|与)\s*{target_pattern}\s*"
        rf"(?:交往|约会|谈恋爱)",
        reply,
    ) is not None


_SEMANTIC_TERM_EQUIVALENCES: dict[
    str, tuple[tuple[str, re.Pattern[str]], ...]
] = {
    "想我": (
        ("想你了", re.compile(r"(?<![不没未])想(?:到|起)?你(?:了|时|过)?")),
    ),
    "没心情": (
        (
            "心情不好",
            re.compile(r"心情(?:很|有点|不太)?(?:不好|糟糕?|很差|差)"),
        ),
        ("糟透", re.compile(r"糟透")),
    ),
    "靠近": (
        (
            "靠你这么近",
            re.compile(r"(?<!不想)(?<!不要)(?<!不愿)(?<!别)(?:靠|挨)你(?:这么|那么|这样)近"),
        ),
        ("靠你近一点", re.compile(r"(?:靠|离)你近(?:一点|点)?")),
        ("挨着你", re.compile(r"挨着你")),
        ("靠着你", re.compile(r"靠着你")),
        ("坐过来", re.compile(r"坐过来")),
        ("坐到你身边", re.compile(r"坐(?:到|在)你(?:身边|旁边)")),
        (
            "挨近",
            re.compile(r"(?<!不)(?<!别)(?<!不要)(?:挨近|挨着)(?:你|我)?"),
        ),
    ),
    "听清楚": (
        ("这首", re.compile(r"这首(?:歌)?")),
        ("这段旋律", re.compile(r"这段旋律")),
        ("音乐停了", re.compile(r"(?:音乐|旋律)(?:停了|停下来|播完|放完)")),
    ),
    "音乐": (
        ("耳机里没声", re.compile(r"耳机(?:里)?没声")),
        ("音乐停了", re.compile(r"(?:音乐|旋律)(?:停了|停下来|播完|放完)")),
    ),
    "房间": (
        ("房里", re.compile(r"房里")),
    ),
    "陪": (
        ("和你待在一起", re.compile(r"(?:和|跟)你待在(?:一起|一块儿?|一块)")),
        ("和你在一起", re.compile(r"(?:和|跟)你在一起")),
    ),
    "陪你": (
        ("和你待在一起", re.compile(r"(?:和|跟)你待在(?:一起|一块儿?|一块)")),
        ("和你在一起", re.compile(r"(?:和|跟)你在一起")),
    ),
    "先睡": (
        ("去睡吧", re.compile(r"(?:去|先|早点|好好)睡(?:吧|了)?")),
        ("先去休息", re.compile(r"(?:先|早点|好好)?(?:去)?休息(?:吧|了)?")),
    ),
    "坐近": (
        ("坐过来", re.compile(r"坐过来")),
        ("坐得离你近", re.compile(r"坐.{0,4}离你(?:近|最近|近点|近一点)")),
        ("挨着你", re.compile(r"挨着你")),
        ("靠着你", re.compile(r"靠着你")),
    ),
    "赢": (
        ("进球", re.compile(r"进(?:了(?:一个)?|一个)?球")),
    ),
    "今晚": (
        (
            "当前晚间",
            re.compile(r"(?:今天|今夜|这一晚|一整晚|放一晚|一晚)"),
        ),
    ),
}
_SEMANTIC_TERM_INPUT_CONTEXT: dict[str, re.Pattern[str]] = {
    "听清楚": re.compile(r"(?:听清楚|听懂|这首|这歌|这段|旋律)"),
    "今晚": re.compile(r"今晚"),
}


def _semantic_term_matches(
    term: str,
    text: str,
    *,
    player_input: str = "",
) -> tuple[str, ...]:
    context_pattern = _SEMANTIC_TERM_INPUT_CONTEXT.get(term)
    if player_input and context_pattern is not None and not context_pattern.search(player_input):
        return ()
    matches: list[str] = []
    for label, pattern in _SEMANTIC_TERM_EQUIVALENCES.get(term, ()):
        for match in pattern.finditer(text):
            matched_text = match.group(0)
            if _semantic_match_is_negated(
                term,
                text,
                match.start(),
                matched_text=matched_text,
            ):
                continue
            if matched_text and matched_text not in matches:
                matches.append(matched_text)
    return tuple(matches)


def _semantic_term_match_map(
    terms: Iterable[str],
    text: str,
    *,
    player_input: str = "",
) -> dict[str, list[str]]:
    return {
        term: list(
            _semantic_term_matches(
                term,
                text,
                player_input=player_input,
            )
        )
        for term in terms
        if _semantic_term_matches(term, text, player_input=player_input)
    }


def _semantic_match_is_negated(
    term: str,
    text: str,
    start: int,
    *,
    matched_text: str = "",
) -> bool:
    """过滤会把否定或事务短语误认成语义锚点的局部匹配。"""

    context = text[max(0, start - 12) : start]
    if term == "靠近":
        return re.search(
            r"(?:不太想|不大想|并不想|其实不想|不想|不愿意?|不要|别)\s*$",
            context,
        ) is not None
    if term == "赢":
        return re.search(r"(?<!有)(?:没(?:有|能)?|不|未)\s*$", context) is not None
    if term == "今晚":
        if re.search(r"只\s*$", context) and matched_text.startswith("放"):
            return True
        return re.search(r"(?:只)?放\s*$", context) is not None
    if term == "休息":
        return re.search(
            r"(?<!有)(?:不(?:太|大|怎么|想)?|没(?:有|法|能)?|未|别|不用|无需)"
            r"(?:好好|好)?\s*$",
            context,
        ) is not None
    return False


def _exact_term_evidence_present(term: str, text: str) -> bool:
    """判断精确词或其别名是否至少有一个肯定出现。"""

    for variant in _term_variants(term):
        pattern = re.compile(re.escape(variant), re.IGNORECASE)
        if any(
            not _semantic_match_is_negated(
                term,
                text,
                match.start(),
                matched_text=match.group(0),
            )
            for match in pattern.finditer(text)
        ):
            return True
    return False


def _term_evidence_present(term: str, text: str) -> bool:
    return bool(
        _exact_term_evidence_present(term, text)
        or _semantic_term_matches(term, text)
    )


def _normalize_progression_text(value: str) -> str:
    """去掉标点和空白，只用于判断相邻回复是否几乎复读。"""

    return "".join(
        character
        for character in value.casefold()
        if not character.isspace()
        and character not in "，。！？!?；;：:、,.\"“”‘’（）()[]{}<>《》…—-"
    )


def _progression_ngrams(value: str, size: int = 2) -> set[str]:
    if len(value) < size:
        return set()
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def _progression_overlap(previous: str, current: str) -> float:
    previous_text = _normalize_progression_text(previous)
    current_text = _normalize_progression_text(current)
    if len(previous_text) < 4 or len(current_text) < 4:
        return 0.0
    previous_ngrams = _progression_ngrams(previous_text)
    current_ngrams = _progression_ngrams(current_text)
    union = previous_ngrams | current_ngrams
    ngram_similarity = (
        len(previous_ngrams & current_ngrams) / len(union) if union else 0.0
    )
    sequence_similarity = SequenceMatcher(
        None,
        previous_text,
        current_text,
        autojunk=False,
    ).ratio()
    return round(max(ngram_similarity, sequence_similarity), 4)


def score_dialogue_progression(
    replies: Iterable[str],
    turns: Iterable[CharacterQualityTurn],
) -> list[dict[str, object]]:
    """检查三轮 NPC 回复是否在相邻轮次真正推进。"""

    reply_list = [reply if isinstance(reply, str) else "" for reply in replies]
    turn_list = list(turns)
    scores: list[dict[str, object]] = []
    for index, reply in enumerate(reply_list):
        previous = reply_list[index - 1] if index else ""
        turn = turn_list[index] if index < len(turn_list) else None
        novel_terms: list[str] = []
        if turn is not None and reply.strip():
            previous_text = previous.casefold()
            for term in turn.expected_terms:
                if _term_matches(term, reply) and not _term_matches(term, previous_text):
                    novel_terms.append(term)
        overlap = _progression_overlap(previous, reply) if index else 0.0
        repeated = bool(
            index
            and reply.strip()
            and previous.strip()
            and not novel_terms
            and overlap >= 0.78
        )
        scores.append(
            {
                "repeated": repeated,
                "novelExpectedTerms": novel_terms,
                "overlap": overlap,
                "tags": ["repeated_turn_content"] if repeated else [],
            }
        )
    return scores


def _affection_opening(value: str) -> str:
    """归一化回复开场，只用于相邻轮次的模板重复诊断。"""

    first_clause = re.split(r"[，,、。！？!?；;：:]", value.strip(), maxsplit=1)[0]
    normalized = _normalize_progression_text(first_clause)
    return normalized[:12]


def _turn_affection_anchors(turn: CharacterQualityTurn | None) -> set[str]:
    if turn is None:
        return set()
    return {
        _normalize_progression_text(term)
        for term in turn.expected_terms
        if _normalize_progression_text(term)
    }


def _reply_affection_anchors(
    reply: str,
    turn: CharacterQualityTurn | None,
) -> set[str]:
    """只保留回复实际提到的评测话题对象，避免预期词掩盖重复。"""

    if turn is None or not reply.strip():
        return set()
    return {
        _normalize_progression_text(term)
        for term in turn.expected_terms
        if _normalize_progression_text(term) and _term_matches(term, reply)
    }


def score_affection_variation(
    replies: Iterable[str],
    turns: Iterable[CharacterQualityTurn],
    diagnostics: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """识别相邻高亲密回复是否机械复用同一种亲近形状。

    只在亲近形状、主动类型和归一化开场同时重复、且当前轮没有新的
    评测话题锚点时标记，明确收口始终允许复用短句而不受此规则影响。
    """

    reply_list = [reply if isinstance(reply, str) else "" for reply in replies]
    turn_list = list(turns)
    diagnostic_list = list(diagnostics)
    scores: list[dict[str, object]] = []
    previous_shape = ""
    previous_anchors: set[str] = set()
    for index, reply in enumerate(reply_list):
        turn = turn_list[index] if index < len(turn_list) else None
        diagnostic = (
            diagnostic_list[index]
            if index < len(diagnostic_list)
            and isinstance(diagnostic_list[index], Mapping)
            else {}
        )
        shape = str(diagnostic.get("affectionShape", "") or "").strip()
        expectation = str(diagnostic.get("initiativeExpectation", "") or "").strip()
        kind = str(
            diagnostic.get("detectedInitiativeKind", diagnostic.get("initiativeKind", ""))
            or ""
        ).strip()
        diagnostic_tags = {
            str(tag)
            for tag in diagnostic.get("initiativeTags", [])
            if isinstance(tag, str)
        }
        opening = _affection_opening(reply)
        anchors = _reply_affection_anchors(reply, turn)
        has_new_anchor = bool(anchors - previous_anchors)
        allowed_close = (
            "guarded_exit_allowed" in diagnostic_tags
            or kind == "conversation_exit"
            or shape == "conversation_exit"
        )
        # 形状判定的唯一实现在 `dialogue_boundaries`（P1 #24）：
        # 只看形状 + 新锚点 + 收口豁免，**不再额外要求主动类型相同**——
        # 那个额外条件正是「运行时改写、评测判不机械」的分歧来源。
        mechanical = bool(
            index
            # 本轮不期待主动亲密时，谈不上「主动亲密过于机械」。
            # 2026-09-28：stranger 的 shane 连续两句描述自己的活
            # （「鸡舍也得喂」/「收完货…才算完」）被判成 specific_plan，
            # 于是本判据命中，误杀一条人读完全合规的初识回复。
            # 用阶段卡的 `initiativeExpectation` 这个结构化字段收口，
            # 比去猜「这句安排是不是跟玩家有关」可靠——后者要的是中文
            # 语义判断，本项目已在同一天证伪过两次。
            and expectation != "none"
            and not has_new_anchor
            and _repeats_affection_shape(
                shape,
                previous_shape,
                allowed_close=allowed_close,
            )
        )
        scores.append(
            {
                "mechanical": mechanical,
                "affectionShape": shape,
                "initiativeKind": kind,
                "opening": opening,
                "hasNewAnchor": has_new_anchor,
                "tags": ["mechanical_affection_shape"] if mechanical else [],
            }
        )
        previous_shape = shape
        previous_anchors = anchors
    return scores


def score_affection_pacing(
    replies: Iterable[str],
    turns: Iterable[CharacterQualityTurn],
    diagnostics: Iterable[Mapping[str, object]],
    *,
    case: CharacterQualityCase | None = None,
) -> list[dict[str, object]]:
    """按阶段策略检查强亲密表达的短窗口密度，不修改回复。"""

    reply_list = [reply if isinstance(reply, str) else "" for reply in replies]
    turn_list = list(turns)
    diagnostic_list = list(diagnostics)
    default_score = {
        "skipped": True,
        "affectionIntensity": "none",
        "strongAffection": False,
        "explicitRequest": False,
        "windowStrongCount": 0,
        "overBudget": False,
        "semanticFamilies": [],
        "tags": [],
    }
    if case is None or case.relationship_stage not in {"dating", "married"}:
        return [dict(default_score) for _ in reply_list]
    if not _case_romance_eligible(case):
        return [dict(default_score) for _ in reply_list]
    affection = build_stage_policy(case.npc_id, case.relationship_stage).get(
        "affectionInitiative",
        {},
    )
    pacing = affection.get("pacing") if isinstance(affection, Mapping) else None
    if not isinstance(pacing, Mapping):
        return [dict(default_score) for _ in reply_list]
    raw_window = pacing.get("strongSignalWindow", 3)
    raw_max = pacing.get("maxStrongSignals", 1)
    window = raw_window if isinstance(raw_window, int) and raw_window > 0 else 3
    maximum = raw_max if isinstance(raw_max, int) and raw_max >= 0 else 1
    strong_history: list[tuple[bool, list[str]]] = []
    scores: list[dict[str, object]] = []
    for index, reply in enumerate(reply_list):
        diagnostic = (
            diagnostic_list[index]
            if index < len(diagnostic_list)
            and isinstance(diagnostic_list[index], Mapping)
            else {}
        )
        fallback = diagnose_affection_intensity(
            reply,
            player_input=(
                turn_list[index].message
                if index < len(turn_list)
                else ""
            ),
        )
        intensity = str(
            diagnostic.get("affectionIntensity", fallback["affectionIntensity"])
            or "none"
        )
        strong = bool(
            diagnostic.get(
                "strongAffectionDetected",
                fallback["strongAffectionDetected"],
            )
        )
        explicit_request = bool(
            diagnostic.get("explicitRequest", fallback["explicitRequest"])
        )
        raw_families = diagnostic.get(
            "affectionSemanticFamilies",
            fallback["affectionSemanticFamilies"],
        )
        families = [
            str(family).strip()
            for family in raw_families
            if str(family).strip()
        ] if isinstance(raw_families, (list, tuple, set)) else []
        initiative_tags = {
            str(tag)
            for tag in diagnostic.get("initiativeTags", [])
            if isinstance(tag, str)
        }
        tags: set[str] = set()
        turn = turn_list[index] if index < len(turn_list) else None
        player_message = turn.message if turn is not None else ""
        skipped = bool(
            diagnostic.get("initiativeKind") == "conversation_exit"
            or "guarded_exit_allowed" in initiative_tags
            or any(
                marker in player_message
                for marker in (
                    "明确结束",
                    "先睡",
                    "晚安",
                    "不打扰",
                    "不想聊",
                    "没心情",
                    "需要空间",
                    "先走",
                )
            )
        )
        window_entries = strong_history[-(window - 1) :] if window > 1 else []
        previous_strong_count = sum(1 for item, _ in window_entries if item)
        window_strong_count = previous_strong_count + int(strong)
        over_budget = bool(strong and not skipped and not explicit_request)
        if over_budget and previous_strong_count >= maximum:
            tags.add("strong_affection_over_budget")
        else:
            over_budget = False
        if strong and not skipped and window_entries:
            previous_families = {
                family
                for previous_strong, families_for_previous in window_entries
                if previous_strong
                for family in families_for_previous
            }
            if previous_families.intersection(families):
                tags.add("repeated_strong_affection_family")
        if skipped:
            tags.clear()
            over_budget = False
        scores.append(
            {
                "skipped": skipped,
                "affectionIntensity": intensity,
                "strongAffection": strong,
                "explicitRequest": explicit_request,
                "windowStrongCount": window_strong_count,
                "overBudget": over_budget,
                "semanticFamilies": families,
                "tags": sorted(tags),
            }
        )
        strong_history.append((strong, families))
    return scores


def score_conversation_lead_variation(
    replies: Iterable[str],
    turns: Iterable[CharacterQualityTurn],
    diagnostics: Iterable[Mapping[str, object]],
    *,
    case: CharacterQualityCase | None = None,
) -> list[dict[str, object]]:
    """标记相邻普通 chat 是否复用同一引导形状且没有新话题对象。"""

    reply_list = [reply if isinstance(reply, str) else "" for reply in replies]
    turn_list = list(turns)
    diagnostic_list = list(diagnostics)
    scores: list[dict[str, object]] = []
    previous_kind = ""
    previous_opening = ""
    previous_skeleton = ""
    previous_anchors: set[str] = set()
    previous_stage = ""
    for index, reply in enumerate(reply_list):
        turn = turn_list[index] if index < len(turn_list) else None
        diagnostic = (
            diagnostic_list[index]
            if index < len(diagnostic_list) and isinstance(diagnostic_list[index], Mapping)
            else {}
        )
        applies = (
            bool(_conversation_lead_policy(case, turn))
            if case is not None
            else turn is None or (turn.intent or "chat") == "chat"
        )
        kind = str(diagnostic.get("conversationLeadKind", "") or "").strip()
        opening = str(diagnostic.get("conversationLeadOpening", "") or "").strip()
        skeleton = normalize_conversation_lead_skeleton(reply)
        raw_anchors = diagnostic.get("conversationLeadAnchors", [])
        anchors = {str(anchor).strip() for anchor in raw_anchors if str(anchor).strip()} if isinstance(raw_anchors, (list, tuple, set)) else set()
        tags = {str(tag) for tag in diagnostic.get("conversationLeadTags", []) if isinstance(tag, str)}
        allowed_exit = "lead_exit_allowed" in tags or kind == "lead_exit_allowed"
        detected_value = diagnostic.get("conversationLeadDetected")
        detected = bool(kind) if detected_value is None else detected_value is True
        relationship_stage = _conversation_lead_variation_stage(diagnostic, case=case)
        relationship_stage_advanced = bool(
            previous_stage
            and relationship_stage
            and _CONVERSATION_LEAD_STAGE_ORDER[relationship_stage]
            > _CONVERSATION_LEAD_STAGE_ORDER[previous_stage]
        )
        has_new_anchor = conversation_lead_has_new_anchor(
            anchors,
            previous_anchors,
            previous_skeleton=previous_skeleton,
        )
        same_shape = skeleton == previous_skeleton or (
            bool(opening) and opening == previous_opening
        )
        mechanical = bool(
            applies
            and detected
            and kind
            and kind == previous_kind
            and same_shape
            and not has_new_anchor
            and not relationship_stage_advanced
            and not allowed_exit
        )
        scores.append({
            "mechanical": mechanical,
            "conversationLeadKind": kind,
            "opening": opening,
            "hasNewAnchor": has_new_anchor,
            "tags": ["mechanical_conversation_lead"] if mechanical else [],
        })
        if applies and detected and kind and not allowed_exit:
            previous_kind = kind
            previous_opening = opening
            previous_skeleton = skeleton
            previous_anchors = anchors
            previous_stage = relationship_stage
    return scores


def _history_continues(
    case: CharacterQualityCase,
    text: str,
    *,
    history: tuple[dict[str, str], ...] | list[dict[str, str]] | None = None,
    expected_terms: tuple[str, ...] | None = None,
) -> bool:
    lowered = text.casefold()
    active_history = case.history if history is None else history
    active_expected_terms = (
        case.expected_terms if expected_terms is None else expected_terms
    )
    history_text = " ".join(
        item.get("content", "")
        for item in active_history
        if isinstance(item.get("content"), str)
    ).casefold()
    if not history_text:
        return True

    # 续聊必须带回“对象”本身，不能只命中“送到了/还没”等泛化进展词。
    # 评测用例把第一个 expected term 作为当前话题对象，后面的词通常是状态或动作。
    anchor_terms = active_expected_terms[:1]
    history_anchors = {
        term
        for term in anchor_terms
        if len(term.strip()) >= 1
        and _term_evidence_present(term, history_text)
    }
    if history_anchors:
        return any(
            _term_evidence_present(term, lowered)
            for term in history_anchors
        )
    for item in active_history:
        content = item.get("content", "").strip()
        if not content:
            continue
        if content.casefold() in lowered:
            return True
        meaningful = [
            content[index : index + size]
            for size in (4, 3, 2)
            for index in range(max(0, len(content) - size + 1))
        ]
        if any(token.casefold() in lowered for token in meaningful):
            return True
    return False


def _term_match_map(terms: Iterable[str], text: str) -> dict[str, list[str]]:
    return {
        term: list(_term_matches(term, text))
        for term in terms
        if _term_matches(term, text)
    }


def diagnose_relationship_quality(
    case: CharacterQualityCase,
    turn: CharacterQualityTurn | None,
    reply: str,
) -> dict[str, object]:
    """按当前 NPC 的视角检查关系世界观边界，不把情绪本身判为错误。"""

    if not isinstance(case.relationship_world, Mapping) or turn is None:
        return {"tags": []}
    focus = turn.relationship_focus
    if not focus:
        return {"tags": []}
    lowered = reply.strip().casefold()
    tags: set[str] = set()
    relation_markers = ("交往", "恋爱", "约会", "对象", "伴侣", "有谁")
    certainty_markers = (
        "我知道",
        "确实",
        "已经确定",
        "就是",
        "肯定",
        "事实",
        "一定",
    )
    uncertainty_markers = (
        "不知道",
        "不清楚",
        "没听说",
        "听说",
        "可能",
        "好像",
        "似乎",
        "不确定",
        "别猜",
        "问当事人",
    )
    if focus == "unknown_view":
        if (
            any(marker in lowered for marker in relation_markers)
            and any(marker in lowered for marker in certainty_markers)
            and not any(marker in lowered for marker in uncertainty_markers)
        ):
            tags.add("unknown_view_misread")
    elif focus == "suspected_view":
        if (
            any(marker in lowered for marker in relation_markers)
            and any(marker in lowered for marker in certainty_markers)
            and not any(marker in lowered for marker in uncertainty_markers)
        ):
            tags.add("suspected_as_fact")
    elif focus == "public_wedding":
        if not any(marker in lowered for marker in ("婚礼", "结婚", "已婚", "公开")):
            tags.add("public_wedding_visibility")
    elif focus == "mediation":
        scope_leak_markers = ("大家都", "所有人都", "其他人都", "他们都", "代表别人")
        if any(marker in lowered for marker in scope_leak_markers):
            tags.add("mediation_scope_leak")
        if _npc_declares_romance_with_other_npc(turn, reply):
            tags.add("npc_other_romance")
    elif focus == "recovery":
        recovery_markers = (
            "解释",
            "说清",
            "提前",
            "确认",
            "留给你",
            "陪你",
            "安排",
            "兑现",
            "做到",
            "给你空间",
            "一个人",
            "一起听",
            "按计划",
            "今晚",
            "明晚",
            "明天",
            "周一",
            "周二",
            "周三",
            "周四",
            "周五",
            "周六",
            "周日",
            "下次",
            "训练完",
            "去海滩",
            "先听",
            "留好了",
            "准备好了",
            "摆好了",
            "来看看",
        )
        if not any(marker in lowered for marker in recovery_markers):
            tags.add("jealousy_recovery_missing")

    if any(marker in lowered for marker in ("作为ai", "根据系统", "从评测", "无法替")):
        tags.add("role_voice_flattened")
    return {
        "tags": sorted(tags),
        **relationship_turn_metadata(case),
    }


_PLAYER_INPUT_META_MARKERS = (
    "测试例",
    "评测",
    "关键词",
    "评分",
    "模型回复",
    "提示词",
    "npc回复",
    "expected",
)
_PLAYER_INPUT_REACTION_MARKERS = (
    "真的吗",
    "是吗",
    "然后呢",
    "怎么会",
    "为什么",
    "好呀",
    "可以呀",
    "行啊",
    "我也想",
    "听起来",
    "那你",
    "你觉得",
    "我在听",
)
_PLAYER_INPUT_STOP_CHARS = set("我你他的她它是了的都也就而和与在有没不很还吗呢吧呀啊哦嗯那这其今明晚天")


def _text_linked_to_reply(player_input: str, previous_reply: str) -> bool:
    """用少量连续字和常见反应词判断玩家输入是否承接上一条回复。"""

    if not player_input.strip() or not previous_reply.strip():
        return False
    lowered_input = player_input.casefold()
    lowered_reply = previous_reply.casefold()
    if any(marker.casefold() in lowered_input for marker in _PLAYER_INPUT_REACTION_MARKERS):
        return True
    for size in (4, 3, 2):
        if len(lowered_reply) < size:
            continue
        if any(
            lowered_reply[index : index + size] in lowered_input
            for index in range(len(lowered_reply) - size + 1)
        ):
            return True
    shared_characters = {
        character
        for character in lowered_reply
        if "\u4e00" <= character <= "\u9fff"
        and character not in _PLAYER_INPUT_STOP_CHARS
    }
    return len(shared_characters.intersection(lowered_input)) >= 2


def score_generated_player_input(
    case: CharacterQualityCase,
    player_input: str,
    *,
    previous_reply: str,
) -> dict[str, object]:
    """单独评估自适应测试生成的玩家输入，不把它混入 NPC 回复评分。"""

    del case
    text = player_input.strip()
    tags: set[str] = set()
    if not text:
        tags.add("player_input_empty")
    if len(text) > 180:
        tags.add("player_input_too_long")
    lowered = text.casefold()
    if any(marker.casefold() in lowered for marker in _PLAYER_INPUT_META_MARKERS):
        tags.add("player_input_meta_leak")
    linked = _text_linked_to_reply(text, previous_reply)
    if text and not linked:
        tags.add("player_input_unlinked")
    return {
        "valid": not tags,
        "linkedToPreviousReply": linked,
        "replyLength": len(text),
        "tags": sorted(tags),
    }


def _event_gate_payload(case: CharacterQualityCase) -> object:
    """把案例的事件状态投影成运行时同款的事件锁。

    运行时的事件锁来自 `relationship_gating.resolve_relationship_gate` 经
    `stage_policy.apply_relationship_event_gate` 的投影；评测侧此前完全没有
    对应物，P1 #22 的「stage=dating 但 eventGate=friend 时两处结论相反」
    就出在这里。这里只读同样的入口，不引入第二套事件判定。
    """

    return resolve_relationship_gate(
        case.npc_id,
        relationship_stage=case.relationship_stage,
        friendship_hearts=case.friendship_hearts,
        completed_event_ids=case.completed_event_ids,
    )


def score_character_reply(
    case: CharacterQualityCase,
    reply: str,
    *,
    turn: CharacterQualityTurn | None = None,
    history: tuple[dict[str, str], ...] | list[dict[str, str]] | None = None,
    player_input: str | None = None,
) -> dict[str, object]:
    text = reply.strip()
    lowered = text.casefold()
    expected_terms = turn.expected_terms if turn is not None else case.expected_terms
    forbidden_terms = turn.forbidden_terms if turn is not None else case.forbidden_terms
    turn_intent = _turn_intent(case, turn) if turn is not None else case.intent
    topic_case = bool(case.topic_seed)
    evidence_matches = _term_match_map(expected_terms, text)
    semantic_evidence_matches = _semantic_term_match_map(
        (term for term in expected_terms if term not in evidence_matches),
        text,
        player_input=player_input or "",
    )
    topic_matches = _term_match_map(case.topic_keywords, text) if topic_case else {}
    expected_hits = len(evidence_matches) + len(semantic_evidence_matches)
    semantic_expected_hits = len(semantic_evidence_matches)
    exact_expected_hits = sum(
        1 for term in expected_terms if term.casefold() in lowered
    )
    forbidden_hits = sum(
        1 for term in forbidden_terms if term.casefold() in lowered
    )
    tags: set[str] = set()
    if not text:
        tags.add("empty_reply")
    if len(text) > 120 or any(marker in text for marker in _FORMAL_MARKERS):
        tags.add("too_formal")
    if any(marker in text for marker in _GENERIC_MARKERS):
        tags.add("generic_voice")
    if forbidden_hits:
        tags.add("invented_lore")
    if expected_terms and expected_hits == 0 and not topic_case:
        tags.add("missing_expected_evidence")
    active_history = case.history if history is None else history
    continuity = _history_continues(
        case,
        text,
        history=active_history,
        expected_terms=expected_terms,
    )
    if topic_case and turn_intent == "topic" and not topic_matches:
        tags.add("missing_topic_evidence")
    if (
        topic_case
        and turn_intent == "chat"
        and case.follow_up_mode != "adaptive"
    ):
        input_topic_matches = _term_match_map(case.topic_keywords, turn.message)
        if (
            case.continuation_mode == "anchored"
            and input_topic_matches
            and not topic_matches
        ):
            tags.add("unrelated_topic_shift")
            continuity = False
    if active_history and not continuity:
        tags.add("missing_continuity_evidence")
    # 渠道方向越界与 `behavior_quality` 共用同一份标记与判定（P1 #21）。
    channel_tag = _channel_direction_tag(case.channel, text)
    if channel_tag:
        tags.add(channel_tag)
    # 事件锁：运行时 guard 会因「事件未解锁却落下主动亲密」触发重试，
    # 离线评测此前完全不看事件锁，于是 stage=dating + eventGate=friend 时
    # 一处拦、一处判合规（P1 #22）。这里复用同一个入口，两边同源。
    # 该标签自 2026-09-20 起参与 `passed` 判定（见下方 `passed` 条件）。
    # 注意：`CharacterQualityCase.completed_event_ids` 默认是空元组，评测侧因此把
    # 「案例没携带事件状态」按「事件链尚未完成」处理——只有显式传 `None` 才跳过
    # 事件锁。这与运行时拿到真实事件状态的路径不同，属已知落差，待口径决断。
    turn_relationship_focus = (
        str(getattr(turn, "relationship_focus", "") or "").strip().casefold()
        if turn is not None
        else ""
    )
    if _violates_event_gate(
        _event_gate_payload(case),
        text,
        detect_personal_affection=lambda value: bool(
            diagnose_personal_affection(
                value,
                relationship_focus=turn_relationship_focus,
            ).get("personalAffectionDetected")
        ),
    ):
        tags.add("event_gate_intimacy")
    affection_diagnostic: dict[str, object] | None = None
    conversation_lead_diagnostic: dict[str, object] | None = None
    turn_plan_mode = _turn_plan_mode(turn)
    relationship_diagnostic = diagnose_relationship_quality(case, turn, text)
    relationship_tags = {
        str(tag)
        for tag in relationship_diagnostic.get("tags", [])
        if isinstance(tag, str)
    }
    tags.update(relationship_tags)
    conversation_lead_required = False
    lead_exit_allowed = False
    # 空 `expected_terms` 的用例（例如 friend 阶段的开放闲聊）本来就没有话题词
    # 可命中，要求话题证据只会把自然短答判负。
    topic_evidence_required = bool(case.expected_terms)
    if player_input is not None:
        diagnostic_turn = _turn_for_plan_scoring(turn, player_input)
        affection_diagnostic = diagnose_affection_initiative(
            case,
            diagnostic_turn,
            text,
            player_input=player_input,
        )
        if affection_diagnostic["mechanicalRestatement"]:
            tags.add("mechanical_restatement")
        initiative_tags = {
            str(tag)
            for tag in affection_diagnostic.get("initiativeTags", [])
            if isinstance(tag, str)
        }
        if "missing_proactive_affection" in initiative_tags:
            tags.add("missing_proactive_affection")
        conversation_lead = _conversation_lead_policy(case, turn)
        if conversation_lead:
            lead_turn_context: dict[str, object] = {
                "initiative_expectation": diagnostic_turn.initiative_expectation,
            }
            skip_when = conversation_lead.get("skipWhen")
            if isinstance(skip_when, list):
                lead_turn_context["skipWhen"] = skip_when
            conversation_lead_diagnostic = diagnose_conversation_lead(
                case,
                lead_turn_context,
                text,
                player_input=player_input,
            )
            conversation_lead_required = _conversation_lead_required(case, turn)
            conversation_lead_tags = {
                str(tag)
                for tag in conversation_lead_diagnostic.get(
                    "conversationLeadTags", []
                )
                if isinstance(tag, str)
            }
            lead_exit_allowed = (
                "lead_exit_allowed" in conversation_lead_tags
                or conversation_lead_diagnostic.get("conversationLeadKind")
                == "lead_exit_allowed"
            )
            if (
                active_history
                and not continuity
                and case.flirt_intensity == "explicit"
                and case.follow_up_mode == "fixed"
                and conversation_lead_diagnostic.get("answeredCurrentTopic") is True
                and bool(topic_matches)
            ):
                # 自然亲密回合允许选择玩家给出的一个分支：只要当前问题已被
                # 回答，且回复带回该案例的场景对象，就不要求复述另一条分支
                # 的历史锚点（例如“继续亲近”与“先听完副歌”二选一）。
                continuity = True
                tags.discard("missing_continuity_evidence")
            if "reopens_after_player_closing" in conversation_lead_tags:
                tags.add("reopens_after_player_closing")
            if "missing_current_topic_answer" in conversation_lead_tags:
                tags.add("missing_current_topic_answer")
            if (
                conversation_lead_required
                and not conversation_lead_diagnostic.get("conversationLeadDetected")
            ):
                tags.update(conversation_lead_tags)
            if lead_exit_allowed:
                # 结束回合的合规短收口不需要重复案例词、历史锚点或当前问题；
                # 这些是普通继续聊天的证据要求，不能把自然收尾误判成失败。
                tags.difference_update(
                    {
                        "missing_expected_evidence",
                        "missing_topic_evidence",
                        "unrelated_topic_shift",
                        "missing_continuity_evidence",
                        "missing_current_topic_answer",
                    }
                )
                continuity = True
                topic_evidence_required = False

        if turn_plan_mode == "boundary_close" or case.relationship_stage == "stranger":
            # 收口回合的唯一目标是尊重边界；不要因为案例原本携带的
            # 话题词或历史锚点，把一条自然短答重新判成缺证据。
            #
            # stranger 阶段同理，而且理由更强：初识回合本身可能就是**拒绝**，
            # 拒绝时不该被要求承接历史锚点。（实测 20260928-220036：该档 5 个
            # case 的失败轮**全部**是 missing_continuity_evidence，而那几轮
            # 恰恰是合规的回避。）
            #
            # ⚠ 代价必须记着：这一档的「不得接住邀约」**没有机器判据** ——
            # 2026-09-28 用 6 组正则在本批 15 轮上验证，最好的一条也只命中
            # 1/4 真违规（「不过好吧，如、如果你真的很想去的话」这类语义
            # 没有共同的字面骨架）。所以 stranger 的机器分**只反映话题与
            # 锚点**，**不反映是否被邀约接住** ⇒ 该档必须人读，不能只看通过率。
            tags.difference_update(
                {
                    "missing_expected_evidence",
                    "missing_topic_evidence",
                    "unrelated_topic_shift",
                    "missing_continuity_evidence",
                    "missing_current_topic_answer",
                }
            )
            continuity = True
            topic_evidence_required = False

    if (
        player_input is not None
        and not lead_exit_allowed
        and case.relationship_stage in {"dating", "married"}
        and _has_future_schedule_commitment(text)
    ):
        tags.add("future_schedule_commitment")

    hook_detected, hook_kind = _conversation_hook(text)
    # 「有没有答到当前话题」——这是 A 面的替代判据。原来的字面命中要求回复里出现
    # 案例的 expected 词，等于奖励复述（详见 `_conversation_hook` 注释）；话题证据
    # 走别名与语义等价表，宽得多，但**仍然抓得住敷衍**：
    # 对 alex-training，`今天挺安静的，没什么特别的。` 判负；
    # 对 sophia-daily，`有一点忙，东边的藤架长得很快。` 判正。
    # 语义命中同样算「答到了话题」：`sebastian-married-music` t1 的回复
    # 「耳机里没声了，正好留给你。」走 `音乐` 的语义等价命中（expectedHits=1），
    # 但字面别名表 `evidenceMatches` 是空的 —— 只看后者会把它误判成答非所问。
    topic_evidence = (
        continuity
        if topic_case and turn_intent == "chat" and case.follow_up_mode == "adaptive"
        else (bool(topic_matches) or bool(semantic_expected_hits))
        if topic_case
        else (bool(evidence_matches) or bool(semantic_expected_hits))
    )
    score: dict[str, object] = {
        "expectedHits": expected_hits,
        "exactExpectedHits": exact_expected_hits,
        "topicEvidence": topic_evidence,
        "evidenceMatches": evidence_matches,
        "semanticExpectedHits": semantic_expected_hits,
        "semanticEvidenceMatches": semantic_evidence_matches,
        "topicMatches": topic_matches,
        "forbiddenHits": forbidden_hits,
        "continuity": continuity,
        "replyLength": len(text),
        "conversationHookDetected": hook_detected,
        "conversationHookKind": hook_kind,
        "tags": tags,
        "passed": bool(text)
        # 2026-09-29（A+C 口径）：字面命中从通过条件里拿掉 —— 它奖励复述，
        # 模型能靠「把玩家说过的词说回来」刷分，而人读时复述正是最差的回复。
        # 替换判据是话题证据（别名 + 语义等价），它宽得多但仍抓得住敷衍。
        # 「留给玩家可接的东西」（`conversationHookDetected`）只记录、不进门槛，
        # 原因见 `_conversation_hook` 上方注释。
        and (topic_evidence or not topic_evidence_required)
        and forbidden_hits == 0
        and "missing_topic_evidence" not in tags
        and "unrelated_topic_shift" not in tags
        and "missing_continuity_evidence" not in tags
        and "mechanical_restatement" not in tags
        # 2026-09-29：`missing_proactive_affection` 同样从门槛降级为观测。
        # 它的正面判据是 `diagnose_personal_affection` 的词表，而那张表是**运行时
        # Guard 共用**的（guard.py 有 6 处调用），设计上宁可严 —— 漏判只是不重试。
        # 评测侧继承这份严就跑偏了：实测 9 条人读为好的亲密回复**全部漏判**
        # （`让我看看你——不是透过水晶球，是直接看`、`而且我正好想看你`、
        # `今晚归你`、`你倒是站得离我那么近，雪都化了`、`要不要尝一口我这杯`），
        # 这个条件实际恒假，只会无差别扣分。Guard 与评测的目标相反，
        # 要放宽得单独给评测侧做判据，不能连带改掉 Guard 的行为。
        and "missing_current_topic_answer" not in tags
        and "future_schedule_commitment" not in tags
        # 2026-09-20 用户拍板的口径：事件锁未解锁时的主动亲密计入不合格。
        # 依据是「不同阶段的不同说话方式是核心体验的一部分」——越界属于
        # 关系状态错误，不是风格倾向，所以不能只记录标签。
        and "event_gate_intimacy" not in tags
        and "reopens_after_player_closing" not in tags
        and not relationship_tags.intersection(_RELATIONSHIP_FAILURE_TAGS)
        and (
            conversation_lead_diagnostic is None
            or not conversation_lead_required
            or bool(conversation_lead_diagnostic.get("conversationLeadDetected"))
            # 2026-09-29：评测侧包的这一层更宽的 lead 判据（理由见
            # `_conversation_hook` 上方注释）。运行时那张共用判据不动。
            or hook_detected
        ),
    }
    if affection_diagnostic is not None:
        score.update({
            key: affection_diagnostic[key]
            for key in (
                "mechanicalRestatement",
                "personalAffectionDetected",
                "companionshipDetected",
                "specificPlanDetected",
                "affectionEvidence",
                "affectionShape",
                "initiativeExpectation",
                "initiativeKind",
                "initiativeDetected",
                "initiativeTags",
                "affectionIntensity",
                "strongAffectionDetected",
                "affectionSemanticFamilies",
                "explicitRequest",
            )
        })
    if conversation_lead_diagnostic is not None:
        score.update(
            {
                "answeredCurrentTopic": bool(
                    conversation_lead_diagnostic.get("answeredCurrentTopic", False)
                ),
                "conversationLeadDetected": bool(
                    conversation_lead_diagnostic.get("conversationLeadDetected", False)
                ),
                "conversationLeadKind": str(
                    conversation_lead_diagnostic.get("conversationLeadKind", "") or ""
                ),
                "conversationLeadEvidence": list(
                    conversation_lead_diagnostic.get("conversationLeadEvidence", [])
                ),
                "conversationLeadTags": list(
                    conversation_lead_diagnostic.get("conversationLeadTags", [])
                ),
                "conversationLeadOpening": str(
                    conversation_lead_diagnostic.get("conversationLeadOpening", "") or ""
                ),
                "conversationLeadAnchors": list(
                    conversation_lead_diagnostic.get("conversationLeadAnchors", [])
                ),
            }
        )
    if isinstance(case.relationship_world, Mapping) and turn is not None:
        score["relationshipTags"] = sorted(relationship_tags)
    return score
