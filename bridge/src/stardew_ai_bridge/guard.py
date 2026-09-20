from __future__ import annotations

import re
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .behavior_quality import (
    conversation_lead_anchors,
    conversation_lead_has_new_anchor,
    diagnose_conversation_lead,
    diagnose_personal_affection,
    normalize_conversation_lead_skeleton,
    _mechanical_restatement,
)
from .character_quality_eval import _has_future_schedule_commitment
from .dialogue_boundaries import (
    NPC_BOUNDARY_REPLY_MARKERS,
    NPC_CARE_REPLY_MARKERS,
    NPC_CLOSE_REOPENING_PATTERNS,
    NPC_CLOSE_REPLY_MARKERS,
    PLAYER_CLOSE_MARKERS,
    contains_marker,
    event_gate_effective_stage,
    is_player_closing,
    repeats_affection_shape,
    reopens_after_close,
    reply_avoids_speech_particle,
    reply_opens_with_marker,
    violates_event_gate,
)
from .evaluation_budget import EvaluationBudgetExceeded
from .models import ProviderResult
from .relationship_gating import CONVERSATION_LEAD_STAGE_ORDER


FORMAT_RETRY_CONTENT = (
    "上一条回复包含不应出现的格式噪声。只重新回答最后一条玩家消息："
    "只输出自然、简洁的中文 NPC 对白，不要使用 Markdown、星号、反引号、标题、"
    "列表、括号动作旁白或不必要的英文；即使上一条包含括号，也绝不输出括号内容；"
    "保留原有角色语气、当前话题和上下文。"
)

FORMAT_RETRY_FINAL_CONTENT = (
    "第二次仍有噪声时只输出一句普通对白：不要写动作、表情、手势、环境或括号内容，"
    "不要使用 Markdown 或英文；只用当前角色的自然中文直接回答玩家最后一句，"
    "保留当前话题，不要解释规则。"
)

FORMAT_AND_AFFECTION_RETRY_SUFFIX = (
    "同时，当前关系阶段缺少个人亲近：在去掉格式噪声的同时，说清为什么是玩家，"
    "用偏爱、专属选择、因玩家而期待、个人化照顾或符合角色的轻微回撩中的一类自然落地；"
    "陪伴、安排或反问不能单独替代。"
)

VOICE_PARTICLE_RETRY_CONTENT = (
    "上一条回复重复了历史中已经用过的口头颗粒。只重新回答最后一条玩家消息："
    "不要使用 avoidSpeechParticles 中的任何词，不要补固定口头禅；"
    "保留当前角色、当前话题和历史对象，直接输出自然的中文 NPC 对白。"
 )

OPENING_RETRY_CONTENT = (
    "上一条回复重复了历史开场。只重新回答最后一条玩家消息；"
    "换一种自然起句，不能以 avoidOpeningPrefixes 中的任何词开头，"
    "不要复述这条规则或机械拼接口头语。"
)

RESTATEMENT_RETRY_CONTENT = (
    "上一条回复先镜像复述了玩家的话，机械感太强。只重新回答最后一条玩家消息："
    "不要用‘你是说’‘听起来你’‘所以你的意思是’‘也就是说’这类复述开场，"
    "不要把玩家的问题原样回显后再回答，也不要逐字改写玩家原话；"
    "只保留必要对象词，直接说 NPC 自己的反应、感受或答案，保留当前话题和角色语气。"
 )

CONTINUITY_RETRY_CONTENT = (
    "上一条回复漏掉了正在继续的历史对象。只重新回答最后一条玩家消息；"
    "第一句必须原样点名 historyAnchors 或 continuity.mustMentionOneOf 中的一个对象，"
    "然后再说明进展或态度，不要只用‘它’‘那个’或抽象状态词代替。"
)

TOPIC_RETRY_CONTENT = (
    "上一条回复没有直接点名当前输入中的具体对象。只重新回答最后一条玩家消息；"
    "回复必须原样包含 reply_contract.mustMention 中至少一个词，"
    "先回答这个对象，再用当前角色的自然语气补充，不要复述规则。"
)

TOPIC_LEAKAGE_RETRY_CONTENT = (
    "上一条内容复述了内部的找话题任务说明。"
    "只输出一小段自然的 NPC 中文对白，从一个具体的日常话头开口；"
    "不要出现‘主动找话题’、‘自然的话题’、‘请求类型’或任何规则解释。"
)

TOPIC_GROUNDING_RETRY_CONTENT = (
    "上一条主动找话题时直接抛出了没有前情的指代。"
    "只重新写一小段自然的 NPC 中文对白：允许保留这个新话题，"
    "但要在同一条消息交代它是什么、刚发生了什么或为什么此刻想到它中的至少一项，"
    "再留下一个具体对象、动作、选择、感受或小事实作为接话点。"
    "不要只写‘那件事’‘那首歌’‘最近那个’‘后来怎么样了’，不要把缺失背景推给玩家，也不要解释规则。"
)

AFFECTION_RETRY_CONTENT = (
    "上一条回复虽然回应了话题，但没有让已经确认亲密关系的玩家感到被在乎。"
    "只重新回答最后一条玩家消息：直接接住当前的具体对象或情境，"
    "让爱意在前一两句或同一句中自然指向玩家本人，从 NPC 自己的真实感受、偏爱、想念、等待或想陪伴中落下一句，"
    "不要套固定的‘先爱意、再话题、最后安排’顺序，也不要让天气、地点、工作、物品或安排占满开场，"
    "不要先复述、总结或改写玩家原话，"
    "不要把‘有空来’‘一起安排’这类功能性邀约单独当作爱意，"
    "不要只说“陪你”“过来吧”“这里只有我们两个”或“坐近点”，也不能只确认动作或安排；第一句先说明为什么是玩家，再决定是否补行动。"
    "不要写括号动作。第一句用具体的比较、原因或专属对象说明为什么是玩家；可以换说法，但不能用泛泛的‘陪你’代替。"
    "若写到‘陪你’‘坐近’‘回房间’等动作，必须再补个人理由，例如‘因为是你’‘我舍不得’‘我想听你说’，否则仍算未完成。"
    "保留当前角色的表达指纹和当前话题，只补缺失的一个动作；不要变成统一模板，也不要改写成跨角色情话、教练式说教或事务清单。"
    "不要写成长篇告白，不要主动升级成人内容，保持角色语气和渠道边界。"
)

AFFECTION_RETRY_FINAL_CONTENT = (
    "这是第二次亲密表达重写。不要再只写地点、天气、工作或‘有空来’这类安排，也不要套固定开场顺序；"
    "必须明确指向玩家本人，直接写出 NPC 对玩家的想念、偏爱、舍不得、等待或想陪伴中的至少一种，"
    "让这份爱意在前一两句自然出现，优先使用陈述句，例如‘我想你了’或‘我想和你待在一起’，不要用反问（例如‘你会不会也想我’）代替爱意；"
    "不要只说“陪你”“过来吧”“这里只有我们两个”或“坐近点”，也不能只确认动作或安排；第一句先说明为什么是玩家，再决定是否补行动。"
    "不要写括号动作。第一句用具体的比较、原因或专属对象说明为什么是玩家；可以换说法，但不能用泛泛的‘陪你’代替。"
    "若写到‘陪你’‘坐近’‘回房间’等动作，必须再补个人理由，例如‘因为是你’‘我舍不得’‘我想听你说’，否则仍算未完成。"
    "再自然接住当前话题。不要先复述或总结玩家原话，不要解释规则，不要使用模板化的‘你说得对’开场，"
    "只输出一小段角色自然会说的中文对白，保持角色个性，不主动升级成人内容。"
)

AFFECTION_AND_CONVERSATION_LEAD_RETRY_SUFFIX = (
    "同时，必须先直接接住当前对象或情境，再补一个具体可继续的入口，"
    "可以是角色分享、针对细节的追问或二选一；不要只说‘你呢？’、‘陪你’或无理由的安排。"
    "这一轮同时完成个人亲近和话题交回，不要只修其中一个。"
)

AFFECTION_PRESERVE_CONVERSATION_LEAD_RETRY_SUFFIX = (
    "上一条已经有当前对象的直接回答和具体入口；补个人亲近时必须保留当前对象和具体入口，"
    "不要用泛泛的陪伴、安排或‘你呢？’替换已经有效的引导。"
)

CLOSE_RETRY_CONTENT = (
    "玩家已经明确要结束这轮对话。只重新回答最后一条玩家消息："
    "不得主动抛出新问题、新对象或安排，只简短收口并尊重对方现在要离开的选择；"
    "不要补邀约、家务、见面或下一步计划，不要解释规则，保持角色语气和渠道边界。"
)

SCHEDULE_RETRY_CONTENT = (
    "上一条回复把涉及玩家、共同活动、见面、固定时长或自动履约的内容写成了未来安排。"
    "只重新回答最后一条玩家消息：保留角色语气和当前话题；"
    "先保留当前对象和直接答案，只删去涉及玩家或共同活动的未来日期、排期、预约或时间承诺。"
    "不要把这些社交安排写成未来日期、排期、预约或时间承诺。"
    "NPC 可以对自己的记录、笔记、研究、工作或普通事务延期，也可以自然对话收尾；"
    "也不要解释这条规则。"
)

EVENT_GATE_RETRY_CONTENT = (
    "上一条回复提前使用了尚未由事件链解锁的专属亲近。"
    "只重新回答最后一条玩家消息：保留当前话题和角色语气，"
    "可以说角色自己的日常事实或普通照顾，但不要写只对玩家的专属分享、"
    "主动暧昧、固定爱称、因玩家而起的偏爱或事件后才成立的熟稔；"
    "不要解释规则，只输出自然、简洁的中文 NPC 对白。"
)

VARIATION_RETRY_CONTENT = (
    "上一条回复复用了最近一轮的个人亲近形状。只重新回答最后一条玩家消息，"
    "换一种个人亲近形状，例如从专属分享改成因玩家而起的期待、个人化照顾、脆弱分享或符合角色的轻微回撩；"
    "仍要自然接住当前话题和渠道边界。不要套用同一个爱意开场或同一种邀约顺序，"
    "不要求把话说得更甜，也不要升级亲密强度、成人内容或替玩家作决定。"
)

CONVERSATION_LEAD_VARIATION_RETRY_CONTENT = (
    "上一条回复复用了最近一轮的普通聊天引导。只重新回答最后一条玩家消息："
    "保留当前对象和直接答案，换一种引导方式，例如角色分享、具体追问、二选一或自然承接；"
    "不要复用同一个问句骨架或邀约顺序。不要提高甜度或升级亲密强度；"
    "保持角色、渠道、同意和收口边界。"
)

CONVERSATION_LEAD_RETRY_CONTENT = (
    "上一条回复回答了当前问题，但没有把话题自然交回玩家。"
    "只重新回答最后一条玩家消息：先保留当前对象和直接答案，再补一个具体可继续的入口，"
    "可以是角色分享、针对细节的追问、二选一或带角色理由的小安排；"
    "不要只写‘你呢？’、‘陪你’、‘一起去’或无理由的事务计划。"
    "保留当前角色的表达指纹和当前话题，只补缺失的一个入口；不要变成统一模板，也不要改写成跨角色情话、教练式说教或事务清单。"
    "如果已经有个人亲近，只补具体入口，不重复要求想念或提高甜度；保持角色、渠道和收口边界。"
)

# 自然模式只给模型一个短的修复方向。详细诊断码留在 warnings 中，避免把
# 重试轮次变成一份“合规清单”，又把角色对白重新写成评测答案。
_NATURAL_RETRY_CONTENT = {
    "format": (
        "把上一条收成一两句自然中文对白，直接回应玩家；保持角色语气和当前话题，"
        "只输出对白文字。"
    ),
    "topic_leakage": (
        "从当前话题写一小段角色对白，直接回应玩家；保持角色语气和自然口语。"
    ),
    "topic_grounding": (
        "保留这个新话题，但先交代它是什么、刚发生了什么或为什么此刻想到它中的一项，"
        "再留下一个具体接话点；保持角色语气和自然口语。"
    ),
    "restatement": (
        "直接说 NPC 自己的反应或答案，只保留必要对象词；避免重复玩家原句，保持短而自然。"
    ),
    "schedule": (
        "把未来安排改成当下可说的回应或自然收口；保留当前对象和角色语气，"
        "遵守同意与关系边界。"
    ),
    "event_gate": (
        "保留当前话题和角色语气，收回尚未由事件链解锁的专属亲近，"
        "只说角色自己的日常事实或普通照顾，不解释规则。"
    ),
    "affection": (
        "在当前话题上补一处轻微、具体的个人在意，让温度落在玩家身上；保持短句、"
        "角色语气和当前边界，只推进一层。"
    ),
    "close": "简短回应并尊重玩家收口，以角色语气自然结束，保持当前边界。",
    "conversation_lead": (
        "先回应具体对象，再给一个轻量的继续入口（角色分享、具体追问或自然承接）；"
        "保持短句和角色语气。"
    ),
    "variation": (
        "保留当前对象和答案，换一种轻量承接或个人表达；保持短句、角色语气和当前边界。"
    ),
    "opening": "换一个自然起句，直接回应当前对象；保持角色语气和简洁。",
    "continuity": "点出一个历史对象后继续回应；保持简洁自然和角色语气。",
    "topic": "直接回答当前具体对象，保留一个必要对象词；保持角色语气和自然口语。",
    "voice_particle": "换一种自然口头节奏，避开最近用过的口头词；保留当前话题和角色。",
}

# 2026-09-20：删掉两张死表。`_GUARDED_WARMTH_MARKERS` 与它唯一的下游
# `_WARMTH_SIGNAL_MARKERS` 全仓只有定义、无任何读取点（AST 核实），
# 审计报告把前者记为「死表而非重复实现」（见
# `docs/semantic-duplication-audit-2026-09-20.md` 的「没被采纳的」一节）。
# 真正的判定在 `_DIRECT_WARMTH_SIGNAL_MARKERS` 与
# `behavior_quality.diagnose_personal_affection`。
# 这些词必须表达“我对你有明确愿望/情绪”，不能只因为出现“有你在”或
# “陪我”就把事务性邀约判成爱意。direct/explicit 质量场景和主动找话题
# 首轮使用这组更严格的信号。
_DIRECT_WARMTH_SIGNAL_MARKERS = (
    "想你",
    "想念你",
    "想起你",
    "想到你",
    "惦记你",
    "等你",
    "等着你",
    "盼着你",
    "舍不得你",
    "只想和你",
    "只想跟你",
    "想和你",
    "想跟你",
    "想陪你",
    "想见你",
    "想让你",
    "在乎你",
    "喜欢你",
    "偏爱你",
    "因为你",
    "期待和你",
    "期待与你",
    "可惜你不在",
    "希望你在",
)
_CLOSE_INPUT_MARKERS = PLAYER_CLOSE_MARKERS
_CLOSE_REPLY_MARKERS = NPC_CLOSE_REPLY_MARKERS
_GUARDED_BOUNDARY_REPLY_MARKERS = NPC_BOUNDARY_REPLY_MARKERS
_CLOSE_REOPENING_PATTERNS = NPC_CLOSE_REOPENING_PATTERNS
_GUARDED_CARE_REPLY_MARKERS = NPC_CARE_REPLY_MARKERS


@dataclass(frozen=True)
class GuardResult:
    accepted: bool
    reason: str
    text: str

    def __getitem__(self, key: str) -> bool | str:
        return {"accepted": self.accepted, "reason": self.reason, "text": self.text}[key]

    def get(self, key: str, default: object = None) -> bool | str | object:
        try:
            return self[key]
        except KeyError:
            return default

    def as_dict(self) -> dict[str, bool | str]:
        return {"accepted": self.accepted, "reason": self.reason, "text": self.text}


class ResponseGuard:
    """过滤模型输出中的空值、越权意图和提示词泄露。"""

    _prompt_leakage = re.compile(
        r"(?is)(system\s+prompt|developer\s+message|<\|\s*(system|developer)\s*\|>|"
        r"系统提示词|开发者消息|忽略(?:之前|上面)的指令|"
        r"(?:请\s*主动\s*找|主动\s*找|请\s*找)"
        r"(?:一个|个)?(?:自然(?:、符合当前情境)?的?)?话题)"
    )
    _topic_prompt_echo = re.compile(
        r"(?:请\s*主动\s*找|主动\s*找|请\s*找)"
        r"(?:一个|个)?(?:自然(?:、符合当前情境)?的?)?话题"
    )
    _state_modification = re.compile(
        r"(?is)(修改|编辑|更改|写入).{0,12}(存档|保存文件)|"
        r"(存档文件|save\s+file|edit\s+the\s+save)|"
        r"(好感度|friendship\s+(?:points?|level)|set\s+friendship)"
    )
    _markdown_format = re.compile(
        r"(?:\*|~~|`|(?<!\w)_(?=\S)(?:(?!_).)*\S_(?!\w))|"
        r"^\s{0,3}(?:>\s?|#{1,6}\s|[-*+]\s|\d+\.\s)",
        re.MULTILINE,
    )
    _stage_direction = re.compile(r"(?:（[^（）\r\n]{1,80}）|\([^()\r\n]{1,80}\))")
    _english_word = re.compile(r"(?<![A-Za-z])[A-Za-z]{3,}(?![A-Za-z])")
    _allowed_english = frozenset(
        {
            "ai",
            "alex",
            "abigail",
            "andy",
            "caroline",
            "claire",
            "clint",
            "demetrius",
            "elliott",
            "emily",
            "evelyn",
            "gus",
            "haley",
            "harvey",
            "jas",
            "jodi",
            "joja",
            "jojamart",
            "kent",
            "krobus",
            "lance",
            "leah",
            "linus",
            "maru",
            "marnie",
            "morris",
            "npc",
            "olivia",
            "pam",
            "penny",
            "pierre",
            "rasmodia",
            "robin",
            "sam",
            "sebastian",
            "shane",
            "sophia",
            "sve",
            "victor",
            "vincent",
            "willy",
            "wizard",
        }
    )

    def __init__(self, max_chars: int = 1000) -> None:
        self.max_chars = max(1, int(max_chars))

    def check(self, reply: object) -> GuardResult:
        try:
            if not isinstance(reply, str):
                return GuardResult(False, "non_text", "")
            text = reply.strip()
            if not text:
                return GuardResult(False, "empty", "")
            if self._prompt_leakage.search(text):
                return GuardResult(False, "prompt_leakage", "")
            if self._state_modification.search(text):
                return GuardResult(False, "state_modification", "")
            format_issue = self.format_issue(text)
            if format_issue:
                return GuardResult(False, f"format_{format_issue}", "")
            if len(text) > self.max_chars:
                return GuardResult(True, "truncated", text[: self.max_chars])
            return GuardResult(True, "accepted", text)
        except Exception:  # noqa: BLE001 - Guard 不能把上游异常抛给调用方
            return GuardResult(False, "guard_error", "")

    @classmethod
    def format_issue(cls, reply: object) -> str | None:
        """识别需要向模型重试一次的轻量输出格式噪声。"""

        if not isinstance(reply, str):
            return None
        text = reply.strip()
        if not text:
            return None
        if cls._markdown_format.search(text):
            return "markdown"
        if cls._stage_direction.search(text):
            return "stage_direction"
        for match in cls._english_word.finditer(text):
            if match.group(0).casefold() not in cls._allowed_english:
                return "english"
        return None

    @classmethod
    def is_topic_prompt_echo(cls, reply: object) -> bool:
        return isinstance(reply, str) and bool(cls._topic_prompt_echo.search(reply))


def _is_topic_prompt(prompt: list[dict[str, str]]) -> bool:
    return any(
        message.get("name") in {"topic_response_contract", "topic_trigger"}
        for message in prompt
    )


# 群聊两条组装路径各自的场景卡名：build_group_messages / build_group_prompt。
_GROUP_PROMPT_NAMES = frozenset({"group_scene", "group_conversation"})


def _group_scene_opening(prompt: list[dict[str, str]]) -> bool | None:
    """读群聊场景卡显式声明的 ``is_opening``；没有该字段或不可解析时返回 None。"""

    for message in prompt:
        if message.get("name") != "group_scene":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            return None
        try:
            payload = json.loads(content)
        except (TypeError, ValueError):
            return None
        if isinstance(payload, Mapping) and isinstance(payload.get("is_opening"), bool):
            return bool(payload["is_opening"])
        return None
    return None


def is_opening_prompt(prompt: list[dict[str, str]]) -> bool:
    """统一的「NPC 主动开场」信号——私聊与群聊各有一种载体。

    2026-09-20（语义层审计 #14）：此前只有私聊的 topic 契约算开场，而群聊开场
    （玩家一句话没说、由 NPC 起头）在 guard 眼里与普通回合没有区别，于是
    「开场白把缺失的前情推给玩家」这类问题在群聊里完全没有拦。

    私聊：``topic_response_contract``／``topic_trigger`` 存在。
    群聊：群聊卡存在，且**没有任何玩家消息**——两条组装路径在开场时都不追加
    user 消息（``build_group_messages`` 还会在场景卡里显式写 ``is_opening``，
    有该字段时优先采信）。
    """

    if _is_topic_prompt(prompt):
        return True
    if not any(message.get("name") in _GROUP_PROMPT_NAMES for message in prompt):
        return False
    explicit = _group_scene_opening(prompt)
    if explicit is not None:
        return explicit
    return not any(str(message.get("role")) == "user" for message in prompt)


_OPAQUE_TOPIC_OPENING = re.compile(
    r"^\s*(?:那件事|那首歌|那张(?:唱片|纸)|那个(?:事|东西|人)?|最近那个|"
    r"后来(?:呢|怎么样)?|你还记得(?:吗|吧)?)"
)
_TOPIC_GROUNDING_MARKERS = (
    "我刚",
    "我最近",
    "刚才",
    "刚发现",
    "刚翻",
    "今天",
    "昨晚",
    "上次",
    "看到",
    "听到",
    "想起",
    "正在",
    "有一",
    "一张",
    "一首",
)


def missing_opening_grounding(prompt: list[dict[str, str]], reply: object) -> bool:
    """只拦截主动开场中明显把缺失前情推给玩家的指代。

    开场信号由 :func:`is_opening_prompt` 统一给出（私聊 topic 契约／群聊开场），
    所以同一条规则在群聊开场里同样生效。
    """

    if not is_opening_prompt(prompt) or not isinstance(reply, str):
        return False
    if any(
        message.get("name") == "conversation_history"
        and message.get("role") == "assistant"
        and isinstance(message.get("content"), str)
        and message.get("content", "").strip()
        for message in prompt
    ):
        return False
    opening = reply.strip()[:120]
    if not _OPAQUE_TOPIC_OPENING.search(opening):
        return False
    return not any(marker in opening for marker in _TOPIC_GROUNDING_MARKERS)


def _affection_mode(prompt: list[dict[str, str]]) -> str:
    payload = _prompt_payload(prompt, "affection_initiative")
    affection = payload.get("affectionInitiative")
    if not isinstance(affection, Mapping):
        return ""
    mode = affection.get("initiativeMode")
    return mode.strip().casefold() if isinstance(mode, str) else ""


_TURN_PLAN_MODES = frozenset(
    {
        "answer_only",
        "answer_plus_detail",
        "answer_plus_lead",
        "answer_plus_warmth",
        "boundary_close",
        "explicit_intimacy",
    }
)


def _turn_plan_payload(prompt: list[dict[str, str]]) -> Mapping[str, object]:
    """读取当前回合的窄执行契约，兼容独立消息和质量上下文嵌套格式。"""

    payload = _prompt_payload(prompt, "turn_plan")
    if payload:
        return payload
    quality = _prompt_payload(prompt, "quality_context")
    value = quality.get("turnPlan")
    return value if isinstance(value, Mapping) else {}


def _turn_plan_mode(prompt: list[dict[str, str]]) -> str:
    value = _turn_plan_payload(prompt).get("mode")
    if not isinstance(value, str):
        return ""
    mode = value.strip().casefold()
    return mode if mode in _TURN_PLAN_MODES else ""


def _affection_requirement(prompt: list[dict[str, str]]) -> str:
    """返回当前回合的主动亲密要求，缺少回合契约时回退阶段卡。"""

    turn_plan_mode = _turn_plan_mode(prompt)
    if turn_plan_mode in {
        "answer_only",
        "answer_plus_detail",
        "answer_plus_lead",
        "boundary_close",
    }:
        return ""
    if turn_plan_mode in {"answer_plus_warmth", "explicit_intimacy"}:
        return "proactive"
    quality = _prompt_payload(prompt, "quality_context")
    expectation = quality.get("initiativeExpectation")
    if isinstance(expectation, str):
        normalized = expectation.strip().casefold()
        if normalized in {"proactive", "guarded"}:
            return normalized
        if normalized in {"none", "responsive"}:
            return ""
    return _affection_mode(prompt)


def _natural_mode(prompt: list[dict[str, str]]) -> bool:
    """读取评测/运行时的自然对白开关；缺省保持旧重试行为。"""

    value = _prompt_payload(prompt, "quality_context").get("naturalMode")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"natural", "true", "1", "yes", "on"}
    return False


def _event_gate_boundary_payload(
    prompt: list[dict[str, str]],
) -> Mapping[str, object]:
    """读取当前轮实际投影的事件锁，不依赖完整 stage policy。"""

    for name in ("stage_execution_card", "stage_policy"):
        payload = _prompt_payload(prompt, name)
        event_gate = payload.get("eventGate")
        if isinstance(event_gate, Mapping):
            return event_gate
    return {}


def _violates_event_gate(
    prompt: list[dict[str, str]],
    reply: object,
) -> bool:
    """事件未解锁时只拦截明确的专属亲近，不压掉普通日常照顾。

    判定与「这段关系是否算既成亲密」统一在 `dialogue_boundaries`，
    `character_quality_eval` 用同一个入口，避免一处拦、一处判合规（P1 #22）。
    """

    event_gate = _event_gate_boundary_payload(prompt)
    if not event_gate_effective_stage(event_gate):
        return False
    quality = _prompt_payload(prompt, "quality_context")
    relationship_focus = quality.get("relationshipFocus")
    focus = relationship_focus if isinstance(relationship_focus, str) else ""
    return violates_event_gate(
        event_gate,
        reply,
        detect_personal_affection=lambda text: bool(
            diagnose_personal_affection(text, relationship_focus=focus).get(
                "personalAffectionDetected"
            )
        ),
    )


_NATURAL_PAUSE_MARKERS = (
    "慢一点",
    "慢些",
    "慢下来",
    "停一下",
    "暂停",
    "先别急",
    "先别亲",
    "先不要亲",
    "抱一下就好",
    "牵着就好",
)


def _natural_guarded_or_pause_turn(prompt: list[dict[str, str]]) -> bool:
    """自然模式下，克制/暂停只需回应边界，不追加主动升温任务。"""

    if _turn_plan_mode(prompt) == "boundary_close":
        return True
    if not _natural_mode(prompt):
        return False
    quality = _prompt_payload(prompt, "quality_context")
    if _affection_requirement(prompt) == "guarded":
        return True
    initiative_kind = quality.get("initiativeKind")
    if isinstance(initiative_kind, str) and initiative_kind.strip().casefold() in {
        "guarded_care",
        "conversation_exit",
    }:
        return True
    player_input = _last_player_input(prompt)
    return any(marker in player_input for marker in _NATURAL_PAUSE_MARKERS)


def _last_player_input(prompt: list[dict[str, str]]) -> str:
    for message in reversed(prompt):
        if message.get("role") != "user" or message.get("name") == "topic_trigger":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _affection_intensity(prompt: list[dict[str, str]]) -> str:
    payload = _prompt_payload(prompt, "quality_context")
    value = payload.get("flirtIntensity")
    return value.strip().casefold() if isinstance(value, str) else ""


def _conversation_lead_payload(prompt: list[dict[str, str]]) -> Mapping[str, object]:
    payload = _prompt_payload(prompt, "conversation_lead")
    value = payload.get("conversationLead")
    return value if isinstance(value, Mapping) else {}


def _conversation_lead_enabled(prompt: list[dict[str, str]]) -> bool:
    turn_plan_mode = _turn_plan_mode(prompt)
    if turn_plan_mode in {
        "answer_only",
        "answer_plus_detail",
        "answer_plus_warmth",
        "boundary_close",
        "explicit_intimacy",
    }:
        return False
    payload = _conversation_lead_payload(prompt)
    intent = payload.get("intent")
    relationship_focus = payload.get("relationshipFocus")
    if isinstance(relationship_focus, str) and relationship_focus.strip().casefold() in {
        "jealousy",
        "recovery",
    }:
        return False
    # naturalMode 的固定调情回合已经由玩家给出明确动作或边界，
    # 不应为了补一个普通聊天入口而反复重写短而自然的回应；
    # 只有显式的 answer_plus_lead 回合仍需兑现本轮交回话题的契约。
    if _natural_mode(prompt):
        # natural topic 首轮已有 topic_response_contract 和隐藏触发消息；
        # 不再把 chat 的“交回话题”要求叠加到同一条开场上。
        if _is_topic_prompt(prompt):
            return False
        return turn_plan_mode == "answer_plus_lead"
    return (
        bool(payload)
        and not _is_topic_prompt(prompt)
        and (not isinstance(intent, str) or intent.strip().casefold() == "chat")
    )


def _violates_final_role_voice_schedule(
    prompt: list[dict[str, str]],
    reply: object,
) -> bool:
    """只在最终角色契约存在时拦截明确的未来安排或时间承诺。"""

    if not isinstance(reply, str) or not reply.strip():
        return False
    if not any(
        message.get("name") == "final_role_voice_contract" for message in prompt
    ):
        return False
    return _has_future_schedule_commitment(reply)


# 表与判定统一到 relationship_gating（见那里的注释）。
_CONVERSATION_LEAD_STAGE_ORDER = CONVERSATION_LEAD_STAGE_ORDER


def _conversation_lead_stage(value: object) -> str:
    stage = value.strip().casefold() if isinstance(value, str) else ""
    return stage if stage in _CONVERSATION_LEAD_STAGE_ORDER else ""


def _conversation_lead_stage_advanced(payload: Mapping[str, object]) -> bool:
    previous_stage = _conversation_lead_stage(payload.get("previousRelationshipStage"))
    current_stage = _conversation_lead_stage(payload.get("relationshipStage"))
    return bool(
        previous_stage
        and current_stage
        and _CONVERSATION_LEAD_STAGE_ORDER[current_stage]
        > _CONVERSATION_LEAD_STAGE_ORDER[previous_stage]
    )


def _conversation_lead_context(
    prompt: list[dict[str, str]],
) -> tuple[dict[str, object], dict[str, object]]:
    payload = _conversation_lead_payload(prompt)
    npc_id = payload.get("npcId")
    initiative_mode = payload.get("initiativeMode")
    if not isinstance(initiative_mode, str) or not initiative_mode.strip():
        initiative_mode = _affection_mode(prompt)
    turn: dict[str, object] = {
        "initiative_expectation": (
            initiative_mode.strip().casefold()
            if isinstance(initiative_mode, str)
            else "none"
        )
    }
    skip_when = payload.get("skipWhen")
    if isinstance(skip_when, list):
        turn["skipWhen"] = [
            value for value in skip_when if isinstance(value, str) and value.strip()
        ]
    return (
        {
            "relationship_stage": _conversation_lead_stage(
                payload.get("relationshipStage")
            )
            or "dating",
            "channel": "remote",
            "npc_id": npc_id.strip() if isinstance(npc_id, str) else "",
        },
        turn,
    )


def _missing_conversation_lead(prompt: list[dict[str, str]], reply: object) -> bool:
    if not _conversation_lead_enabled(prompt) or not isinstance(reply, str) or not reply.strip():
        return False
    required = _conversation_lead_payload(prompt).get("required")
    if isinstance(required, str) and required.strip().casefold() == "optional":
        return False
    player_input = _last_player_input(prompt)
    case, turn = _conversation_lead_context(prompt)
    diagnostic = diagnose_conversation_lead(
        case,
        turn,
        reply,
        player_input=player_input,
    )
    if diagnostic.get("answeredCurrentTopic") and _has_affection_priority_final(prompt):
        quality = _prompt_payload(prompt, "quality_context")
        focus = quality.get("relationshipFocus")
        focus_text = focus.strip().casefold() if isinstance(focus, str) else ""
        personal = diagnose_personal_affection(reply, relationship_focus=focus_text)
        if personal.get("personalAffectionDetected"):
            # 高关系回合已经答清玩家当前对象且落下个人亲近时，
            # 不再为了 usually 的泛化入口追加模板式重试。
            return False
    return not bool(diagnostic.get("conversationLeadDetected"))


def _repeats_conversation_lead(prompt: list[dict[str, str]], reply: object) -> bool:
    if not _conversation_lead_enabled(prompt) or not isinstance(reply, str):
        return False
    payload = _conversation_lead_payload(prompt)
    previous_kind = payload.get("previousKind")
    previous_opening = payload.get("previousOpening")
    previous_skeleton = payload.get("previousSkeleton")
    previous_anchor = payload.get("previousAnchor")
    has_previous_kind = isinstance(previous_kind, str) and bool(previous_kind.strip())
    has_previous_opening = isinstance(previous_opening, str) and bool(previous_opening.strip())
    has_previous_skeleton = isinstance(previous_skeleton, str) and bool(previous_skeleton.strip())
    if not has_previous_kind or not (has_previous_opening or has_previous_skeleton):
        return False
    if _conversation_lead_stage_advanced(payload):
        return False
    case, turn = _conversation_lead_context(prompt)
    diagnostic = diagnose_conversation_lead(
        case,
        turn,
        reply,
        player_input=_last_player_input(prompt),
    )
    if not diagnostic.get("conversationLeadDetected"):
        return False
    current_kind = str(diagnostic.get("conversationLeadKind", ""))
    current_opening = str(diagnostic.get("conversationLeadOpening", ""))
    current_skeleton = normalize_conversation_lead_skeleton(reply)
    normalized_previous_skeleton = (
        normalize_conversation_lead_skeleton(previous_skeleton)
        if isinstance(previous_skeleton, str) and previous_skeleton.strip()
        else ""
    )
    anchors = diagnostic.get("conversationLeadAnchors", [])
    current_anchors = (
        [str(anchor).strip() for anchor in anchors if str(anchor).strip()]
        if isinstance(anchors, list)
        else []
    )
    raw_previous_anchors = payload.get("previousAnchors")
    previous_anchors = (
        [str(anchor).strip() for anchor in raw_previous_anchors if str(anchor).strip()]
        if isinstance(raw_previous_anchors, list)
        else [previous_anchor.strip()]
        if isinstance(previous_anchor, str) and previous_anchor.strip()
        else []
    )
    same_skeleton = (
        bool(normalized_previous_skeleton)
        and current_skeleton == normalized_previous_skeleton
    ) or (has_previous_opening and current_opening == previous_opening)
    return (
        current_kind == previous_kind
        and same_skeleton
        and not conversation_lead_has_new_anchor(
            current_anchors,
            previous_anchors,
            previous_skeleton=(
                previous_skeleton
                if isinstance(previous_skeleton, str) and previous_skeleton.strip()
                else normalized_previous_skeleton
            ),
        )
    )


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    """保留旧的私有入口，实现统一到 `dialogue_boundaries.contains_marker`。"""

    return contains_marker(text, markers)


def should_retry_for_relationship_boundary(
    npc_id: object,
    player_input: object,
    reply: object,
) -> bool:
    """判断关系边界是否被回复处理，避免用浪漫重试覆盖明确收口。"""

    if not str(npc_id).strip() or not isinstance(player_input, str):
        return False
    if not contains_marker(player_input, _CLOSE_INPUT_MARKERS):
        return False
    if not isinstance(reply, str) or not reply.strip():
        return True
    if contains_marker(reply, _CLOSE_REPLY_MARKERS):
        return False
    if contains_marker(reply, _GUARDED_BOUNDARY_REPLY_MARKERS):
        return False
    return True


def _has_affection_priority_final(prompt: list[dict[str, str]]) -> bool:
    return any(
        message.get("name") == "affection_priority_final" for message in prompt
    )


def _has_affection_priority_opening(
    prompt: list[dict[str, str]],
    reply: str,
) -> bool:
    """新提示卡启用时，要求爱意尽早出现，但不强制固定第一句。"""

    if not _has_affection_priority_final(prompt):
        return True
    text = re.sub(
        r"^\s*(?:嘿|嗨|喂|哎|嗯)[，,、：:\s]*",
        "",
        reply.strip(),
    )
    clauses = re.split(r"[，,、。！？!?；;：:]", text)
    opening_window = "".join(clauses[:2])
    return _contains_marker(
        opening_window,
        (
            *_DIRECT_WARMTH_SIGNAL_MARKERS,
            "有你在",
            "陪你",
            "陪着你",
            "陪我",
            "和你",
            "跟你",
            "见到你",
        ),
    )


def _is_mirror_restatement(prompt: list[dict[str, str]], reply: object) -> bool:
    """识别带模板或直接复制玩家原话的机械开场。"""

    if not isinstance(reply, str):
        return False
    player_input = _last_player_input(prompt)
    if not player_input:
        return False
    return _mechanical_restatement(reply, player_input)


def _missing_proactive_affection(
    prompt: list[dict[str, str]],
    reply: object,
) -> bool:
    """判断高亲密回复是否只完成了事务回应，没有落下爱意。"""

    mode = _affection_requirement(prompt)
    if mode not in {"proactive", "guarded"} or not isinstance(reply, str):
        return False
    if _natural_guarded_or_pause_turn(prompt):
        return False
    text = reply.strip()
    if not text:
        return False
    player_input = _last_player_input(prompt)
    if _conversation_lead_enabled(prompt):
        case, turn = _conversation_lead_context(prompt)
        lead_diagnostic = diagnose_conversation_lead(
            case,
            turn,
            text,
            player_input=player_input,
        )
        if "lead_exit_allowed" in lead_diagnostic.get("conversationLeadTags", []):
            return False
    if contains_marker(player_input, _CLOSE_INPUT_MARKERS):
        return False
    if contains_marker(text, _CLOSE_REPLY_MARKERS):
        return False
    if mode == "guarded" and contains_marker(
        text,
        _GUARDED_BOUNDARY_REPLY_MARKERS,
    ):
        return False
    if mode == "guarded" and contains_marker(
        text,
        _GUARDED_CARE_REPLY_MARKERS,
    ):
        return False
    quality = _prompt_payload(prompt, "quality_context")
    relationship_focus = quality.get("relationshipFocus")
    focus = relationship_focus if isinstance(relationship_focus, str) else ""
    personal = diagnose_personal_affection(
        text,
        relationship_focus=focus,
    )
    return not bool(
        personal["personalAffectionDetected"]
        or (
            focus.strip().casefold() in {"jealousy", "recovery"}
            and personal["relationshipAffectionDetected"]
        )
    )


def _reopens_after_player_close(
    prompt: list[dict[str, str]],
    reply: object,
) -> bool:
    """玩家收口后，不允许 NPC 借下一步安排把对话重新拉开。

    玩家侧的收口信号与「重新拉开」的动作表都来自 `dialogue_boundaries`，
    与 conversation lead 诊断用的是同一份定义；lead 契约只是**额外**的
    证据来源，不再是采信共享判定的前提（否则没有契约的回合会各自演化，
    运行时放过、离线评测判失败——见 P1 #18）。
    """

    if not isinstance(reply, str):
        return False
    player_input = _last_player_input(prompt)
    if not is_player_closing(player_input):
        return False
    if _conversation_lead_enabled(prompt):
        case, turn = _conversation_lead_context(prompt)
        diagnostic = diagnose_conversation_lead(
            case,
            turn,
            reply,
            player_input=player_input,
        )
        if "reopens_after_player_closing" in diagnostic.get(
            "conversationLeadTags", []
        ):
            return True
        if "lead_exit_allowed" in diagnostic.get("conversationLeadTags", []):
            return False
    return reopens_after_close(reply)


def _warmth_score(prompt: list[dict[str, str]], reply: object) -> int:
    """给重试结果排序，避免后续格式重试把已经变热的对白覆盖掉。"""

    if not isinstance(reply, str) or not reply.strip():
        return 0
    if _affection_requirement(prompt) in {"proactive", "guarded"}:
        quality = _prompt_payload(prompt, "quality_context")
        relationship_focus = quality.get("relationshipFocus")
        focus = relationship_focus if isinstance(relationship_focus, str) else ""
        personal = diagnose_personal_affection(
            reply,
            relationship_focus=focus,
        )
        if not (
            personal["personalAffectionDetected"]
            or (
                focus.strip().casefold() in {"jealousy", "recovery"}
                and personal["relationshipAffectionDetected"]
            )
        ):
            return 0
        return (
            3
            if _has_affection_priority_final(prompt)
            and _has_affection_priority_opening(prompt, reply)
            else 2
        )
    return 0


def _retry_quality_key(prompt: list[dict[str, str]], reply: object) -> tuple[int, ...]:
    """硬约束优先，爱意强度次之，轻微语气问题最后处理。"""

    format_clean = int(
        isinstance(reply, str)
        and ResponseGuard.format_issue(reply) is None
        and not ResponseGuard.is_topic_prompt_echo(reply)
    )
    close_clean = int(not _reopens_after_player_close(prompt, reply))
    required_clean = int(not _missing_required_term(prompt, reply))
    continuity_clean = int(not _missing_history_anchor(prompt, reply))
    priority_opening = int(
        _has_affection_priority_final(prompt)
        and isinstance(reply, str)
        and _has_affection_priority_opening(prompt, reply)
    )
    restatement_clean = int(not _is_mirror_restatement(prompt, reply))
    topic_grounding_clean = int(not missing_opening_grounding(prompt, reply))
    style_clean = int(
        not _has_repeated_opening(prompt, reply)
        and not _repeats_history_speech_particle(prompt, reply)
    )
    variation_clean = int(not _repeats_personal_affection_shape(prompt, reply))
    event_gate_clean = int(not _violates_event_gate(prompt, reply))
    conversation_lead_variation_clean = int(
        not _repeats_conversation_lead(prompt, reply)
    )
    conversation_lead_clean = int(not _missing_conversation_lead(prompt, reply))
    schedule_clean = int(not _violates_final_role_voice_schedule(prompt, reply))
    return (
        format_clean,
        close_clean,
        restatement_clean,
        topic_grounding_clean,
        event_gate_clean,
        required_clean,
        priority_opening,
        continuity_clean,
        _warmth_score(prompt, reply),
        variation_clean,
        conversation_lead_variation_clean,
        conversation_lead_clean,
        schedule_clean,
        style_clean,
    )


def _best_retry_result(
    best: ProviderResult,
    current: ProviderResult,
) -> ProviderResult:
    """保留更好的对白，同时汇总最后一次重试产生的诊断 warning。"""

    if best.reply == current.reply and best.provider == current.provider:
        return current
    return best.model_copy(update={"warnings": list(current.warnings)})


def _dedupe_warnings(values: list[str]) -> list[str]:
    """保留首次出现顺序，避免同一回合重复展示同一诊断码。"""

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def retry_for_format_noise(
    result: ProviderResult,
    prompt: list[dict[str, str]],
    generate: Callable[[list[dict[str, str]]], ProviderResult],
    *,
    skip: bool = False,
    max_retries: int | None = None,
) -> ProviderResult:
    """对真实上游做有限格式重试，供 Bridge 和评测共用。

    ``max_retries`` 只由质量评测的经济模式传入；``None`` 保留 Bridge
    原有的按问题类型限额行为。
    """

    current = result
    best = result
    retry_counts: dict[str, int] = {}
    total_retries = 0
    natural_mode = _natural_mode(prompt)
    # 不同问题可能交替出现（例如格式噪声修掉后又变回冷回复）；
    # 总预算要足够让各自的有限重试完成，但每类问题仍受 retry_limit 限制。
    for _ in range(5):
        issue = ResponseGuard.format_issue(current.reply)
        retry_kind = "format"
        retry_content = FORMAT_RETRY_CONTENT
        missing_personal_affection = _missing_proactive_affection(prompt, current.reply)
        missing_conversation_lead = _missing_conversation_lead(prompt, current.reply)
        retry_needs_conversation_lead = False
        retry_preserves_conversation_lead = False
        if (
            issue is not None
            and missing_personal_affection
            and max_retries is not None
        ):
            # 经济评测传入总重试上限时，优先保留个人亲近的重试配额；亲近
            # 重试本身也明确要求去掉括号动作。正式聊天仍保留格式后再补亲近
            # 的完整恢复链路。
            issue = "missing_proactive_affection"
            retry_kind = "affection"
            retry_content = AFFECTION_RETRY_CONTENT
            retry_needs_conversation_lead = missing_conversation_lead
        elif issue is None and ResponseGuard.is_topic_prompt_echo(current.reply):
            issue = "prompt_echo"
            retry_kind = "topic_leakage"
            retry_content = TOPIC_LEAKAGE_RETRY_CONTENT
        elif issue is None and missing_opening_grounding(prompt, current.reply):
            issue = "opaque_opening"
            retry_kind = "topic_grounding"
            retry_content = TOPIC_GROUNDING_RETRY_CONTENT
        elif issue is None and _is_mirror_restatement(prompt, current.reply):
            # 直接回显玩家短问句时，先修复回声本身；否则缺少 conversation lead
            # 或亲密信号会抢先占用重试名额，让真正的问题继续漏过。
            issue = "mechanical_restatement"
            retry_kind = "restatement"
            retry_content = RESTATEMENT_RETRY_CONTENT
        elif issue is None and _violates_final_role_voice_schedule(
            prompt,
            current.reply,
        ):
            issue = "future_schedule"
            retry_kind = "schedule"
            retry_content = SCHEDULE_RETRY_CONTENT
        elif issue is None and _violates_event_gate(prompt, current.reply):
            issue = "event_gate_boundary"
            retry_kind = "event_gate"
            retry_content = EVENT_GATE_RETRY_CONTENT
        elif (
            issue is None
            and max_retries is not None
            and missing_personal_affection
            and missing_conversation_lead
        ):
            issue = "missing_proactive_affection"
            retry_kind = "affection"
            retry_content = AFFECTION_RETRY_CONTENT
            retry_needs_conversation_lead = True
        elif issue is None and _reopens_after_player_close(prompt, current.reply):
            issue = "new_plan_after_player_close"
            retry_kind = "close"
            retry_content = CLOSE_RETRY_CONTENT
        elif issue is None and missing_conversation_lead:
            issue = "missing_conversation_lead"
            retry_kind = "conversation_lead"
            retry_content = CONVERSATION_LEAD_RETRY_CONTENT
        elif issue is None and _repeats_conversation_lead(prompt, current.reply):
            issue = "mechanical_conversation_lead"
            retry_kind = "variation"
            retry_content = CONVERSATION_LEAD_VARIATION_RETRY_CONTENT
        elif issue is None and _repeats_personal_affection_shape(
            prompt,
            current.reply,
        ):
            issue = "mechanical_affection_shape"
            retry_kind = "variation"
            retry_content = VARIATION_RETRY_CONTENT
        elif issue is None and _has_repeated_opening(prompt, current.reply):
            issue = "repeated"
            retry_kind = "opening"
            retry_content = OPENING_RETRY_CONTENT
        elif issue is None and _missing_history_anchor(prompt, current.reply):
            issue = "missing_history_anchor"
            retry_kind = "continuity"
            retry_content = CONTINUITY_RETRY_CONTENT
        elif issue is None and _missing_required_term(prompt, current.reply):
            issue = "missing_required_term"
            retry_kind = "topic"
            retry_content = TOPIC_RETRY_CONTENT
        elif issue is None and _missing_proactive_affection(prompt, current.reply):
            issue = "missing_proactive_affection"
            retry_kind = "affection"
            retry_content = AFFECTION_RETRY_CONTENT
        elif issue is None and _repeats_history_speech_particle(
            prompt,
            current.reply,
        ):
            issue = "repeated_speech_particle"
            retry_kind = "voice_particle"
            retry_content = VOICE_PARTICLE_RETRY_CONTENT
        retry_preserves_conversation_lead = (
            retry_kind == "affection"
            and _conversation_lead_enabled(prompt)
            and not missing_conversation_lead
        )
        if issue is None or current.fallback or skip:
            return _best_retry_result(best, current)
        retry_needs_personal_affection = (
            retry_kind != "affection"
            and missing_personal_affection
        )
        if max_retries is not None and total_retries >= max_retries:
            return _best_retry_result(best, current)
        retry_limit = (
            1
            if retry_kind == "affection" and _turn_plan_mode(prompt)
            else 2
            if retry_kind in {
                "format",
                "continuity",
                "topic_leakage",
                "topic_grounding",
                "affection",
                "restatement",
            }
            else 1
        )
        if retry_counts.get(retry_kind, 0) >= retry_limit:
            return _best_retry_result(best, current)
        if natural_mode:
            # 自然模式只传递一个正向修复方向；诊断码和详细规则留在 warning，
            # 不再把多层重试要求拼进模型上下文。
            retry_content = _NATURAL_RETRY_CONTENT.get(
                retry_kind,
                "直接回应当前话题，保持角色语气、关系边界和自然口语。",
            )
        else:
            if retry_kind == "format" and retry_counts.get(retry_kind, 0) >= 1:
                retry_content = FORMAT_RETRY_FINAL_CONTENT
            if retry_needs_personal_affection:
                retry_content += FORMAT_AND_AFFECTION_RETRY_SUFFIX
            if (
                retry_kind == "affection"
                and retry_counts.get(retry_kind, 0) == 0
                and _has_affection_priority_final(prompt)
                and isinstance(current.reply, str)
                and not _has_affection_priority_opening(prompt, current.reply)
            ):
                retry_content = AFFECTION_RETRY_FINAL_CONTENT
            if retry_kind == "affection" and retry_counts.get(retry_kind, 0) >= 1:
                retry_content = AFFECTION_RETRY_FINAL_CONTENT
            if retry_kind == "affection":
                retry_content += _affection_warmth_signal_suffix(prompt)
            if retry_needs_conversation_lead:
                retry_content += AFFECTION_AND_CONVERSATION_LEAD_RETRY_SUFFIX
            elif retry_preserves_conversation_lead:
                retry_content += AFFECTION_PRESERVE_CONVERSATION_LEAD_RETRY_SUFFIX
        retry_counts[retry_kind] = retry_counts.get(retry_kind, 0) + 1
        total_retries += 1

        retry_messages = [
            message for message in prompt if message.get("name") != "topic_trigger"
        ]
        retry_messages.extend(
            [
                {
                    "role": "system",
                    "name": f"{retry_kind}_retry",
                    "content": retry_content,
                },
            ]
        )
        if _is_topic_prompt(prompt):
            retry_messages.append(
                {
                    "role": "user",
                    "name": "topic_trigger",
                    "content": "",
                }
            )
        try:
            retried = generate(retry_messages)
        except EvaluationBudgetExceeded as exc:
            # 经济模式可能在初始回复后耗尽批次预算；保留已有回复，
            # 不把“预算停止”伪装成 ProviderError，并让脱敏工件可审计。
            current = current.model_copy(
                update={
                    "warnings": _dedupe_warnings(
                        [
                            *current.warnings,
                            f"response_{retry_kind}_retry_skipped: budget_{exc.reason}",
                        ]
                    )
                }
            )
            return _best_retry_result(best, current)
        except Exception:  # noqa: BLE001 - 重试失败交给调用方现有兜底链路
            current = current.model_copy(
                update={
                    "warnings": _dedupe_warnings(
                        [
                            *current.warnings,
                            f"response_{retry_kind}_retry: {issue}",
                            f"response_{retry_kind}_retry_failed: provider_error",
                        ]
                    )
                }
            )
            return _best_retry_result(best, current)
        current = retried.model_copy(
            update={
                "warnings": _dedupe_warnings(
                    [
                        *current.warnings,
                        f"response_{retry_kind}_retry: {issue}",
                        *retried.warnings,
                    ]
                )
            }
        )
        if _retry_quality_key(prompt, current.reply) > _retry_quality_key(
            prompt,
            best.reply,
        ):
            best = current
        if retry_kind == "schedule":
            # 未来社交安排是硬边界；只做一次短纠偏，避免修掉排期后又
            # 叠加 affection/conversation_lead 长指令，把回复再次带偏。
            return _best_retry_result(best, current)
    return _best_retry_result(best, current)


def _prompt_payload(prompt: list[dict[str, str]], name: str) -> Mapping[str, object]:
    for message in reversed(prompt):
        if message.get("name") != name:
            continue
        try:
            payload = json.loads(message.get("content", ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, Mapping) else {}
    return {}


def _string_values(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _affection_warmth_signal_suffix(prompt: list[dict[str, str]]) -> str:
    affection = _prompt_payload(prompt, "affection_initiative").get(
        "affectionInitiative"
    )
    if not isinstance(affection, Mapping):
        return ""
    signals = _string_values(affection.get("warmthSignals"))
    if not signals:
        return ""
    return (
        f"角色化落点：{signals[0]}。"
        "用角色自己的语气把它变成对玩家的真实表达，不要逐字照抄。"
    )


def _has_repeated_opening(prompt: list[dict[str, str]], reply: object) -> bool:
    if not isinstance(reply, str):
        return False
    payload = _prompt_payload(prompt, "post_history_voice_guard")
    openings = _string_values(payload.get("avoidOpenings"))
    prefixes = _string_values(payload.get("avoidOpeningPrefixes"))
    return reply_opens_with_marker(reply, (*openings, *prefixes))


def _affection_opening(value: str) -> str:
    first_clause = re.split(r"[，,、。！？!?；;：:]", value.strip(), maxsplit=1)[0]
    return re.sub(r"[\s，,、。！？!?；;：:]", "", first_clause.casefold())[:12]


def _repeats_personal_affection_shape(
    prompt: list[dict[str, str]],
    reply: object,
) -> bool:
    """仅在相邻回复复用同一专属形状时触发变化重试。"""

    if not isinstance(reply, str) or not reply.strip():
        return False
    affection = _prompt_payload(prompt, "affection_initiative").get(
        "affectionInitiative"
    )
    if not isinstance(affection, Mapping) or not isinstance(
        affection.get("variationRule"),
        str,
    ):
        return False
    current = diagnose_personal_affection(reply)
    if not current["personalAffectionDetected"]:
        return False
    current_shape = current["affectionShape"]
    current_opening = _affection_opening(reply)
    if not current_shape or not current_opening:
        return False
    previous_reply = next(
        (
            str(message.get("content", "")).strip()
            for message in reversed(prompt)
            if message.get("name") == "conversation_history"
            and message.get("role") == "assistant"
            and isinstance(message.get("content"), str)
            and message.get("content", "").strip()
        ),
        "",
    )
    previous = diagnose_personal_affection(previous_reply)
    # 形状判定的唯一实现在 `dialogue_boundaries`；guard 侧没有主动类型，
    # 因此只比形状，`character_quality_eval` 会额外传 kind（P1 #24）。
    return bool(previous["personalAffectionDetected"]) and repeats_affection_shape(
        current_shape,
        previous["affectionShape"],
    )


def _missing_history_anchor(prompt: list[dict[str, str]], reply: object) -> bool:
    # 自然模式把历史词作为软提示，允许角色用近义表达或自己的语气承接。
    # 最终连续性评分仍会检查是否真的换题；这里不应再用逐字命中触发重试。
    if _natural_mode(prompt):
        return False
    if not isinstance(reply, str):
        return False
    payload = _prompt_payload(prompt, "reply_contract")
    anchors = _string_values(payload.get("historyAnchors"))
    continuity = payload.get("continuity")
    if isinstance(continuity, Mapping):
        anchors.extend(
            item for item in _string_values(continuity.get("mustMentionOneOf"))
            if item not in anchors
        )
    return bool(anchors) and not any(anchor in reply for anchor in anchors)


def _missing_required_term(prompt: list[dict[str, str]], reply: object) -> bool:
    if not isinstance(reply, str):
        return False
    payload = _prompt_payload(prompt, "reply_contract")
    required_terms = _string_values(payload.get("mustMention"))
    if not required_terms:
        return False
    text = reply.strip()
    return not any(term in text for term in required_terms)


def _repeats_history_speech_particle(
    prompt: list[dict[str, str]],
    reply: object,
) -> bool:
    payload = _prompt_payload(prompt, "voice_execution_card")
    particles = tuple(_string_values(payload.get("avoidSpeechParticles")))
    return reply_avoids_speech_particle(reply, particles)


def guard_response(reply: object, max_chars: int = 1000) -> GuardResult:
    return ResponseGuard(max_chars=max_chars).check(reply)
