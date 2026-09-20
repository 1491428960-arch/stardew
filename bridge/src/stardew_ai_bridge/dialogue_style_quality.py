"""对生成对白做轻量、只读的表达质量提示。

这个模块不改写回复，也不把回复重新拼接成训练资料；它只返回适合评测
结果和网页展示的短标签，避免把“自动提示”误当成角色质量结论。

「重复 History 里的口头颗粒」与「以历史开场起句」两条判定与运行时
`guard` 同源（`dialogue_boundaries.reply_avoids_speech_particle` /
`reply_opens_with_marker`）：此前两处各写一套，同一个概念两个名字，
运行时重试与离线标签可能给出相反结论（P1 #23）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .dialogue_boundaries import (
    reply_avoids_speech_particle,
    reply_opens_with_marker,
)


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


def _repeated_opening_markers(previous_openings: list[str]) -> tuple[str, ...]:
    """把历史开场折成「短签名」标记，供共享的起句判定使用。

    `今天还行` 与 `今天挺忙` 共享 `今天` 这个签名——这是本模块原有的
    短签名口径（不比整段正文，也不要求逐字相同）。
    """

    markers: list[str] = []
    for item in previous_openings:
        signature = _opening_signature(item)
        if signature and signature not in markers:
            markers.append(signature)
    return tuple(markers)


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

    # 同一条回复内重复的颗粒：与「历史里已经用过」是两个维度，但都收敛到
    # 同一个判定函数，运行时 guard 与这里的结论不会再分叉（P1 #23）。
    repeated_in_reply = tuple(
        sorted(particle for particle, count in counts.items() if count >= 2)
    )
    if reply_avoids_speech_particle(text, repeated_in_reply):
        tags.add("repeated_speech_particle")

    previous_replies = _assistant_replies(history)
    previous_openings = [_opening(item) for item in previous_replies]
    previous_particles = tuple(
        sorted(
            {
                match.group(1)
                for item in previous_openings
                if (match := _OPENING_PARTICLE.match(item))
            }
        )
    )
    if reply_avoids_speech_particle(opening, previous_particles):
        tags.add("repeated_speech_particle")

    markers = _repeated_opening_markers(previous_openings)
    if markers and reply_opens_with_marker(opening, markers):
        tags.add("repeated_opening")

    return {
        "tags": sorted(tags),
        "speechParticleCounts": counts,
        "opening": opening[:80],
    }
