from __future__ import annotations

import re
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher

from .behavior_quality import diagnose_personal_affection
from .evaluation_budget import EvaluationBudgetExceeded
from .models import ProviderResult


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
    "不要逐字改写玩家原话；直接说 NPC 自己的反应、感受或回答，保留当前话题和角色语气。"
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

AFFECTION_RETRY_CONTENT = (
    "上一条回复虽然回应了话题，但没有让已经确认亲密关系的玩家感到被在乎。"
    "只重新回答最后一条玩家消息：直接接住当前的具体对象或情境，"
    "让爱意在前一两句或同一句中自然指向玩家本人，从 NPC 自己的真实感受、偏爱、想念、等待或想陪伴中落下一句，"
    "不要套固定的‘先爱意、再话题、最后安排’顺序，也不要让天气、地点、工作、物品或安排占满开场，"
    "不要先复述、总结或改写玩家原话，"
    "不要把‘有空来’‘一起安排’这类功能性邀约单独当作爱意，"
    "不要写成长篇告白，不要主动升级成人内容，保持角色语气和渠道边界。"
)

AFFECTION_RETRY_FINAL_CONTENT = (
    "这是第二次亲密表达重写。不要再只写地点、天气、工作或‘有空来’这类安排，也不要套固定开场顺序；"
    "必须明确指向玩家本人，直接写出 NPC 对玩家的想念、偏爱、舍不得、等待或想陪伴中的至少一种，"
    "让这份爱意在前一两句自然出现，优先使用陈述句，例如‘我想你了’或‘我想和你待在一起’，不要用反问（例如‘你会不会也想我’）代替爱意；"
    "再自然接住当前话题。不要先复述或总结玩家原话，不要解释规则，不要使用模板化的‘你说得对’开场，"
    "只输出一小段角色自然会说的中文对白，保持角色个性，不主动升级成人内容。"
)

VARIATION_RETRY_CONTENT = (
    "上一条回复复用了最近一轮的个人亲近形状。只重新回答最后一条玩家消息，"
    "换一种个人亲近形状，例如从专属分享改成因玩家而起的期待、个人化照顾、脆弱分享或符合角色的轻微回撩；"
    "仍要自然接住当前话题和渠道边界。不要套用同一个爱意开场或同一种邀约顺序，"
    "不要求把话说得更甜，也不要升级亲密强度、成人内容或替玩家作决定。"
)

_WARMTH_SIGNAL_MARKERS = (
    "想你",
    "想念你",
    "想念",
    "想起你",
    "想到你",
    "惦记你",
    "等你",
    "等着你",
    "等你忙完",
    "盼着你",
    "舍不得你",
    "只想和你",
    "想和你",
    "想跟你",
    "想陪你",
    "陪着你",
    "可惜你不在",
    "希望你在",
    "希望你能来",
    "有你在",
    "给你留",
    "为你留",
    "在乎你",
    "喜欢你",
    "偏爱你",
    "巴不得你来",
    "见到你",
    "因为你",
    "期待你",
    "期待和你",
    "期待与你",
    "与你一同",
    "与你共度",
)
# 这些词必须表达“我对你有明确愿望/情绪”，不能只因为出现“有你在”或
# “陪我”就把事务性邀约判成爱意。direct/explicit 质量场景和主动找话题
# 首轮使用这组更严格的信号；普通聊天仍保留上面的角色化宽松信号。
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
_GUARDED_WARMTH_MARKERS = (
    *_WARMTH_SIGNAL_MARKERS,
    "陪我",
    "陪你",
    "陪着",
    "一起坐",
    "一起待",
    "一起吃",
    "一起休息",
    "吃点东西",
    "带点吃的",
    "先休息",
    "需要空间",
    "不想聊",
    "我会陪",
    "我陪你",
    "照看",
    "帮你",
    "留给我",
)
_CLOSE_INPUT_MARKERS = (
    "不打扰",
    "先休息",
    "先睡",
    "晚安",
    "先走",
    "下次再聊",
    "改天再聊",
    "不想聊",
    "不用陪",
    "别过来",
)
_CLOSE_REPLY_MARKERS = (
    "明天再聊",
    "下次再聊",
    "改天再聊",
    "先睡了",
    "晚安",
    "先休息",
    "不打扰你",
    "不想聊",
    "先这样",
    "到这吧",
)
_GUARDED_BOUNDARY_REPLY_MARKERS = (
    "想一个人待",
    "需要一点空间",
    "需要空间",
    "别过来",
    "不想见人",
    "今天状态很差",
    "真撑不住",
    "累得不行",
    "今天太累",
    "想静一静",
    "别等我",
    "让我缓缓",
)


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


def _affection_mode(prompt: list[dict[str, str]]) -> str:
    payload = _prompt_payload(prompt, "affection_initiative")
    affection = payload.get("affectionInitiative")
    if not isinstance(affection, Mapping):
        return ""
    mode = affection.get("initiativeMode")
    return mode.strip().casefold() if isinstance(mode, str) else ""


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


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in markers)


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


_MIRROR_RESTATEMENT_MARKERS = (
    "你是说",
    "听起来你",
    "所以你的意思",
    "也就是说",
    "换句话说",
    "你刚才提到",
    "你刚才说",
    "你说的",
    "刚才提到",
    "前面说",
)


def _is_mirror_restatement(prompt: list[dict[str, str]], reply: object) -> bool:
    """识别先复述玩家原话、再给答案的模板开场。"""

    if not isinstance(reply, str):
        return False
    player_input = _last_player_input(prompt)
    if not player_input:
        return False
    first_sentence = re.split(r"[。！？!?；;]", reply.strip(), maxsplit=1)[0]
    if not _contains_marker(first_sentence, _MIRROR_RESTATEMENT_MARKERS):
        return False
    normalize = lambda value: re.sub(
        r"[\s，。！？、；：,.!?;:…‘’“”\"'（）()]+", "", value.casefold()
    )
    reply_text = normalize(first_sentence)
    player_text = normalize(player_input)
    if not reply_text or not player_text:
        return False
    match = SequenceMatcher(
        None,
        reply_text,
        player_text,
        autojunk=False,
    ).find_longest_match(0, len(reply_text), 0, len(player_text))
    return match.size >= 3 and match.size / min(len(reply_text), len(player_text)) >= 0.35


def _missing_proactive_affection(
    prompt: list[dict[str, str]],
    reply: object,
) -> bool:
    """判断高亲密回复是否只完成了事务回应，没有落下爱意。"""

    mode = _affection_mode(prompt)
    if mode not in {"proactive", "guarded"} or not isinstance(reply, str):
        return False
    text = reply.strip()
    if not text:
        return False
    player_input = _last_player_input(prompt)
    if _contains_marker(player_input, _CLOSE_INPUT_MARKERS):
        return False
    if _contains_marker(text, _CLOSE_REPLY_MARKERS):
        return False
    if mode == "guarded" and _contains_marker(
        text,
        _GUARDED_BOUNDARY_REPLY_MARKERS,
    ):
        return False
    return not bool(diagnose_personal_affection(text)["personalAffectionDetected"])


def _warmth_score(prompt: list[dict[str, str]], reply: object) -> int:
    """给重试结果排序，避免后续格式重试把已经变热的对白覆盖掉。"""

    if not isinstance(reply, str) or not reply.strip():
        return 0
    if _affection_mode(prompt) in {"proactive", "guarded"}:
        if not diagnose_personal_affection(reply)["personalAffectionDetected"]:
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
    required_clean = int(not _missing_required_term(prompt, reply))
    continuity_clean = int(not _missing_history_anchor(prompt, reply))
    priority_opening = int(
        _has_affection_priority_final(prompt)
        and isinstance(reply, str)
        and _has_affection_priority_opening(prompt, reply)
    )
    restatement_clean = int(not _is_mirror_restatement(prompt, reply))
    style_clean = int(
        not _has_repeated_opening(prompt, reply)
        and not _repeats_history_speech_particle(prompt, reply)
    )
    variation_clean = int(not _repeats_personal_affection_shape(prompt, reply))
    return (
        format_clean,
        restatement_clean,
        required_clean,
        priority_opening,
        continuity_clean,
        _warmth_score(prompt, reply),
        variation_clean,
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
    # 不同问题可能交替出现（例如格式噪声修掉后又变回冷回复）；
    # 总预算要足够让各自的有限重试完成，但每类问题仍受 retry_limit 限制。
    for _ in range(5):
        issue = ResponseGuard.format_issue(current.reply)
        retry_kind = "format"
        retry_content = FORMAT_RETRY_CONTENT
        if issue is None and ResponseGuard.is_topic_prompt_echo(current.reply):
            issue = "prompt_echo"
            retry_kind = "topic_leakage"
            retry_content = TOPIC_LEAKAGE_RETRY_CONTENT
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
        elif issue is None and _is_mirror_restatement(prompt, current.reply):
            issue = "mechanical_restatement"
            retry_kind = "restatement"
            retry_content = RESTATEMENT_RETRY_CONTENT
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
        if issue is None or current.fallback or skip:
            return _best_retry_result(best, current)
        if max_retries is not None and total_retries >= max_retries:
            return _best_retry_result(best, current)
        retry_limit = (
            2
            if retry_kind in {
                "format",
                "continuity",
                "topic_leakage",
                "affection",
                "restatement",
            }
            else 1
        )
        if retry_counts.get(retry_kind, 0) >= retry_limit:
            return _best_retry_result(best, current)
        if retry_kind == "format" and retry_counts.get(retry_kind, 0) >= 1:
            retry_content = FORMAT_RETRY_FINAL_CONTENT
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
        except EvaluationBudgetExceeded:
            # 经济模式可能在初始回复后耗尽批次预算；保留已有回复，
            # 不把“预算停止”伪装成 ProviderError。
            return _best_retry_result(best, current)
        except Exception:  # noqa: BLE001 - 重试失败交给调用方现有兜底链路
            current = current.model_copy(
                update={
                    "warnings": [
                        *current.warnings,
                        f"response_{retry_kind}_retry: {issue}",
                        f"response_{retry_kind}_retry_failed: provider_error",
                    ]
                }
            )
            return _best_retry_result(best, current)
        current = retried.model_copy(
            update={
                "warnings": [
                    *current.warnings,
                    f"response_{retry_kind}_retry: {issue}",
                    *retried.warnings,
                ]
            }
        )
        if _retry_quality_key(prompt, current.reply) > _retry_quality_key(
            prompt,
            best.reply,
        ):
            best = current
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


def _has_repeated_opening(prompt: list[dict[str, str]], reply: object) -> bool:
    if not isinstance(reply, str):
        return False
    payload = _prompt_payload(prompt, "post_history_voice_guard")
    openings = _string_values(payload.get("avoidOpenings"))
    prefixes = _string_values(payload.get("avoidOpeningPrefixes"))
    text = reply.strip()
    return any(text.startswith(value) for value in (*openings, *prefixes))


def _affection_opening(value: str) -> str:
    first_clause = re.split(r"[，,、。！？!?；;：:]", value.strip(), maxsplit=1)[0]
    return re.sub(r"[\s，,、。！？!?；;：:]", "", first_clause.casefold())[:12]


def _repeats_personal_affection_shape(
    prompt: list[dict[str, str]],
    reply: object,
) -> bool:
    """仅在相邻回复复用同一专属形状和开场时触发变化重试。"""

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
    return bool(
        previous["personalAffectionDetected"]
        and previous["affectionShape"] == current_shape
        and _affection_opening(previous_reply) == current_opening
    )


def _missing_history_anchor(prompt: list[dict[str, str]], reply: object) -> bool:
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
    if not isinstance(reply, str):
        return False
    payload = _prompt_payload(prompt, "voice_execution_card")
    particles = _string_values(payload.get("avoidSpeechParticles"))
    if not particles:
        return False
    return any(
        re.search(
            rf"(?:^|[。！？!?；;：:，,\s…]){re.escape(particle)}",
            reply.strip(),
        )
        for particle in particles
    )


def guard_response(reply: object, max_chars: int = 1000) -> GuardResult:
    return ResponseGuard(max_chars=max_chars).check(reply)
