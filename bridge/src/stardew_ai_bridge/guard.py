from __future__ import annotations

import re
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

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
        r"系统提示词|开发者消息|忽略(?:之前|上面)的指令)"
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


def retry_for_format_noise(
    result: ProviderResult,
    prompt: list[dict[str, str]],
    generate: Callable[[list[dict[str, str]]], ProviderResult],
    *,
    skip: bool = False,
) -> ProviderResult:
    """对真实上游做有限格式重试，供 Bridge 和评测共用。"""

    current = result
    retry_counts: dict[str, int] = {}
    for _ in range(3):
        issue = ResponseGuard.format_issue(current.reply)
        retry_kind = "format"
        retry_content = FORMAT_RETRY_CONTENT
        if issue is None and _has_repeated_opening(prompt, current.reply):
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
        elif issue is None and _repeats_history_speech_particle(
            prompt,
            current.reply,
        ):
            issue = "repeated_speech_particle"
            retry_kind = "voice_particle"
            retry_content = VOICE_PARTICLE_RETRY_CONTENT
        if issue is None or current.fallback or skip:
            return current
        retry_limit = 2 if retry_kind in {"format", "continuity"} else 1
        if retry_counts.get(retry_kind, 0) >= retry_limit:
            return current
        if retry_kind == "format" and retry_counts.get(retry_kind, 0) >= 1:
            retry_content = FORMAT_RETRY_FINAL_CONTENT
        retry_counts[retry_kind] = retry_counts.get(retry_kind, 0) + 1

        retry_messages = [
            *prompt,
            {
                "role": "system",
                "name": f"{retry_kind}_retry",
                "content": retry_content,
            },
        ]
        try:
            retried = generate(retry_messages)
        except Exception:  # noqa: BLE001 - 重试失败交给调用方现有兜底链路
            return current.model_copy(
                update={
                    "warnings": [
                        *current.warnings,
                        f"response_{retry_kind}_retry: {issue}",
                        f"response_{retry_kind}_retry_failed: provider_error",
                    ]
                }
            )
        current = retried.model_copy(
            update={
                "warnings": [
                    *current.warnings,
                    f"response_{retry_kind}_retry: {issue}",
                    *retried.warnings,
                ]
            }
        )
    return current


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
