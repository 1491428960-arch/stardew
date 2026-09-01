"""对白语气的确定性、低风险统计。

这里的输出是提示词辅助信息，不是剧情事实，也不替代人工审阅。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .evidence import (
    has_dialogue_control_residue,
    is_stable_voice_evidence_record,
)
from .source_aliases import source_family


_MARKER_GROUPS: dict[str, tuple[str, ...]] = {
    "uncertaintyMarkers": ("也许", "或许", "可能", "不确定", "无法断言"),
    "magicMarkers": ("魔法", "星界", "法术", "仪式", "能量"),
    "boundaryMarkers": ("秘密", "风险", "边界", "同意"),
    "dryHumorMarkers": ("当然", "显然", "可惜", "真是"),
}
_CHINESE_LOCALE = re.compile(
    r"(?:^|[._/-])zh(?:-[a-z]{2})?(?:[._/-]|$)", re.IGNORECASE
)
_LOCALE_SUFFIX = re.compile(r"\.[a-z]{2}(?:-[a-z]{2})?\.json$", re.IGNORECASE)
_VOICE_ANCHOR_CONTROL = re.compile(
    r"\{\{|\}\}|\$\{|#\$|inputSeparator=|\bi18n\s*:",
    re.IGNORECASE,
)
# 语气锚点应是一小句游戏对白；过长的资料型句子会稀释角色的句式信号。
_VOICE_ANCHOR_MAX_TEXT = 80
_VOICE_ANCHOR_MAX_COUNT = 8


def _count_markers(text: str, markers: Iterable[str]) -> int:
    folded = text.casefold()
    return sum(folded.count(marker.casefold()) for marker in markers)


def _topic_hints(features: Mapping[str, int]) -> list[str]:
    hints: list[str] = []
    if features.get("magicMarkers", 0):
        hints.append("魔法与星界")
    if features.get("boundaryMarkers", 0):
        hints.append("风险与边界")
    if features.get("uncertaintyMarkers", 0):
        hints.append("明确不确定性")
    if features.get("dryHumorMarkers", 0):
        hints.append("克制的干燥幽默")
    return hints


def _anchor_category(sample: Mapping[str, Any]) -> str:
    """给正向语气锚点分桶，避免窗口被同一类对白占满。"""

    key = str(sample.get("sourceKey", "")).strip().casefold()
    if key == "introduction":
        return "introduction"
    if key in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
        return "weekday"
    if re.fullmatch(r"(?:mon|tue|wed|thu|fri|sat|sun)\d+", key):
        return "weekday_variant"
    if re.fullmatch(r"(?:neutral|good|bad)_\d+", key):
        return "relationship"
    return "other"


def _voice_anchor_candidates(
    samples: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """提取短、可读、来源可追溯的原文语气片段。"""

    candidates: list[tuple[tuple[int, int, int, int], dict[str, str]]] = []
    for original_index, sample in enumerate(samples):
        if not isinstance(sample, Mapping):
            continue
        if not is_stable_voice_evidence_record(sample):
            continue
        sample_id = sample.get("sampleId")
        source_mod = sample.get("sourceMod")
        text = sample.get("text")
        if not all(isinstance(value, str) and value.strip() for value in (sample_id, text)):
            continue
        cleaned_text = text.strip()
        if not 6 <= len(cleaned_text) <= _VOICE_ANCHOR_MAX_TEXT:
            continue
        if has_dialogue_control_residue(cleaned_text):
            continue
        if _VOICE_ANCHOR_CONTROL.search(cleaned_text):
            continue
        anchor = {
            "sampleId": sample_id.strip(),
            "sourceMod": source_mod.strip() if isinstance(source_mod, str) else "",
            "text": cleaned_text,
        }
        source_key = sample.get("sourceKey")
        if isinstance(source_key, str) and source_key.strip():
            anchor["sourceKey"] = source_key.strip()
        evidence_kind = sample.get("evidenceKind")
        if isinstance(evidence_kind, str) and evidence_kind.strip():
            anchor["evidenceKind"] = evidence_kind.strip()
        # 中文本地化优先；随后保证不同来源和不同日常结构都能留下一个样本。
        candidates.append(
            (
                (
                    _evidence_priority(sample, original_index)[0],
                    0 if source_family(source_mod) != "vanilla" else 1,
                    0 if _anchor_category(sample) == "introduction" else 1,
                    original_index,
                ),
                anchor,
            )
        )

    ranked = sorted(candidates, key=lambda item: item[0])
    selected: list[dict[str, str]] = []
    selected_sources: set[str] = set()
    selected_categories: set[str] = set()
    selected_texts: set[str] = set()

    def add(anchor: dict[str, str], category: str, *, require_new: bool) -> None:
        source = source_family(anchor.get("sourceMod", ""))
        text = anchor["text"].casefold()
        if text in selected_texts or len(selected) >= _VOICE_ANCHOR_MAX_COUNT:
            return
        if require_new and source in selected_sources and category in selected_categories:
            return
        selected.append(anchor)
        selected_sources.add(source)
        selected_categories.add(category)
        selected_texts.add(text)

    # 第一遍优先保证来源与表达结构多样，第二遍再按稳定顺序补齐。
    for _, anchor in ranked:
        sample = next(
            (
                item
                for item in samples
                if isinstance(item, Mapping)
                and item.get("sampleId") == anchor["sampleId"]
            ),
            {},
        )
        category = _anchor_category(sample)
        if source_family(anchor.get("sourceMod", "")) not in selected_sources:
            add(anchor, category, require_new=False)
    for _, anchor in ranked:
        sample = next(
            (
                item
                for item in samples
                if isinstance(item, Mapping)
                and item.get("sampleId") == anchor["sampleId"]
            ),
            {},
        )
        add(anchor, _anchor_category(sample), require_new=True)
    for _, anchor in ranked:
        sample = next(
            (
                item
                for item in samples
                if isinstance(item, Mapping)
                and item.get("sampleId") == anchor["sampleId"]
            ),
            {},
        )
        add(anchor, _anchor_category(sample), require_new=False)
        if len(selected) >= _VOICE_ANCHOR_MAX_COUNT:
            break
    return selected


def _evidence_priority(
    sample: Mapping[str, Any], original_index: int
) -> tuple[int, int]:
    """让中文本地化样本优先作为引用，但保持其余样本的原始顺序。"""

    source_path = str(sample.get("sourcePath", "")).replace("\\", "/")
    if _CHINESE_LOCALE.search(source_path):
        return (0, original_index)
    # 未带语言后缀的基础对白通常比其他语言本地化更适合作为次选证据。
    if not _LOCALE_SUFFIX.search(source_path):
        return (1, original_index)
    return (2, original_index)


def derive_speech_profile(
    npc_id: str,
    samples: Iterable[Mapping[str, Any]],
    *,
    max_evidence: int = 6,
    max_anchors: int = _VOICE_ANCHOR_MAX_COUNT,
) -> dict[str, Any]:
    """从对白样本生成可复现的受限语气卡。"""

    try:
        evidence_limit = max(0, min(int(max_evidence), 6))
    except (TypeError, ValueError):
        evidence_limit = 6

    materialized_samples = [
        sample for sample in samples if isinstance(sample, Mapping)
    ]
    features = {group: 0 for group in _MARKER_GROUPS}
    evidence_candidates: list[tuple[tuple[int, int], str]] = []
    for original_index, sample in enumerate(materialized_samples):
        if not isinstance(sample, Mapping):
            continue
        if not is_stable_voice_evidence_record(sample):
            continue
        text = sample.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        if has_dialogue_control_residue(text):
            continue
        for group, markers in _MARKER_GROUPS.items():
            features[group] += _count_markers(text, markers)
        sample_id = sample.get("sampleId")
        if isinstance(sample_id, str) and sample_id.strip():
            evidence_candidates.append(
                (_evidence_priority(sample, original_index), sample_id.strip())
            )

    evidence_candidates.sort(key=lambda item: item[0])
    evidence_refs = [
        sample_id for _, sample_id in evidence_candidates[:evidence_limit]
    ]

    try:
        anchor_limit = max(0, min(int(max_anchors), _VOICE_ANCHOR_MAX_COUNT))
    except (TypeError, ValueError):
        anchor_limit = _VOICE_ANCHOR_MAX_COUNT
    voice_anchors = _voice_anchor_candidates(materialized_samples)[:anchor_limit]

    return {
        "npcId": str(npc_id).strip(),
        "features": features,
        "topicHints": _topic_hints(features),
        "evidenceRefs": evidence_refs,
        "voiceAnchors": voice_anchors,
    }
