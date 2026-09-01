"""对生成对白做轻量、只读的表达质量提示。

这个模块不改写回复，也不把回复重新拼接成训练资料；它只返回适合评测
结果和网页展示的短标签，避免把“自动提示”误当成角色质量结论。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_SPEECH_PARTICLES = ("好吧", "行吧", "嗯", "哦", "啊", "唔", "呃", "嘿")
_SENTENCE_BOUNDARY = r"[。！？!?；;，,、\n]"
_OPENING_SPLIT = re.compile(_SENTENCE_BOUNDARY)
_PARTICLE_AT_OPENING = re.compile(
    r"(?:^|[。！？!?；;，,、\n])(" + "|".join(map(re.escape, _SPEECH_PARTICLES)) + r")(?:\s|[，。！？!?；;、:：]|$)"
)
_OPENING_PARTICLE = re.compile(
    r"^(" + "|".join(map(re.escape, _SPEECH_PARTICLES)) + r")(?:\s|[，。！？!?；;、:：]|$)"
)


def _reply_text(reply: Any) -> str:
    return reply.strip() if isinstance(reply, str) else ""


def _speech_particle_counts(reply: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not reply:
        return counts
    for match in _PARTICLE_AT_OPENING.finditer(reply):
        particle = match.group(1)
        counts[particle] = counts.get(particle, 0) + 1
    return counts


def _opening(reply: str) -> str:
    if not reply:
        return ""
    return _OPENING_SPLIT.split(reply, maxsplit=1)[0].strip()


def _assistant_replies(history: Any) -> list[str]:
    if not isinstance(history, (list, tuple)):
        return []
    replies: list[str] = []
    for item in history:
        if not isinstance(item, Mapping) or item.get("role") != "assistant":
            continue
        content = _reply_text(item.get("content"))
        if content:
            replies.append(content)
    return replies


def _opening_signature(opening: str) -> str:
    """取短签名，既能抓住“今天还行/今天挺忙”也不比较整段正文。"""

    normalized = opening.casefold().strip()
    particle = _OPENING_PARTICLE.match(normalized)
    if particle:
        normalized = normalized[particle.end() :].lstrip(" ，,、:：")
    if not normalized:
        return ""
    chinese = "".join(char for char in normalized if "\u4e00" <= char <= "\u9fff")
    if len(chinese) >= 2:
        return chinese[:2]
    return normalized.split()[0][:24]


def analyze_dialogue_style(
    reply: str,
    history: object = None,
) -> dict[str, object]:
    """返回不改写原回复的表达风险标签。

    只读取 assistant 历史，并只输出颗粒计数、短开场和稳定标签；不会
    返回 prompt、请求、配置或凭据等上下文内容。
    """

    text = _reply_text(reply)
    counts = _speech_particle_counts(text)
    opening = _opening(text)
    tags: set[str] = set()

    if any(count >= 2 for count in counts.values()):
        tags.add("repeated_speech_particle")

    previous_replies = _assistant_replies(history)
    previous_openings = [_opening(item) for item in previous_replies]
    current_particle = _OPENING_PARTICLE.match(opening)
    previous_particles = {
        match.group(1)
        for item in previous_openings
        if (match := _OPENING_PARTICLE.match(item))
    }
    if current_particle and current_particle.group(1) in previous_particles:
        tags.add("repeated_speech_particle")

    current_signature = _opening_signature(opening)
    if current_signature and any(
        current_signature == _opening_signature(item)
        for item in previous_openings
        if item
    ):
        tags.add("repeated_opening")

    return {
        "tags": sorted(tags),
        "speechParticleCounts": counts,
        "opening": opening[:80],
    }
