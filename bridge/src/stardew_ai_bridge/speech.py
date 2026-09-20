"""对白语气的确定性、低风险统计。

这里的输出是提示词辅助信息，不是剧情事实，也不替代人工审阅。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .dialogue_stage import (
    sample_stage_distance,
    sample_stage_hint,
    stage_hint_applies,
)
from .evidence import (
    has_dialogue_control_residue,
    is_model_evidence_record,
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
#
# 2026-09-20（语义层审计 P1 第 26 条）：这对窗口此前被三处各写一遍——
# 生成侧 6–80、群聊声线卡 `> 60` 直接丢弃、私聊证据文本截断到 100。
# 于是 61–80 字之间**完全合格**的锚点在群聊侧被静默丢弃（实测真实索引：
# 622 条 voiceAnchors 里 34 条落在该区间）。现在窗口与裁剪只在这里定义，
# 其余调用点引用 `voice_anchor_text_fits` / `clip_voice_anchor_text`。
VOICE_ANCHOR_MIN_TEXT = 6
VOICE_ANCHOR_MAX_TEXT = 80
_VOICE_ANCHOR_MAX_COUNT = 8
_STAGE_VOICE_ANCHOR_MAX_COUNT = 8
_ENERGY_EXCITEMENT_MARKERS: tuple[str, ...] = (
    "嘿",
    "耶",
    "呀",
    "噫",
    "哎呀",
    "哇",
    "哦哦",
    "天哪",
    "太好了",
    "好棒",
    "好喜欢",
    "爱你",
)
_ENERGY_CONTINUATION_MARKERS: tuple[str, ...] = (
    "还有",
    "而且",
    "然后",
    "哦对了",
    "对了",
    "另外",
    "以及",
)
_ENERGY_EXCLAMATION_MARKERS: tuple[str, ...] = ("!", "！")
_RELATION_RESPONSE_KEY = re.compile(r"^(?:neutral|good|bad)(?:_\d+)?$", re.IGNORECASE)
_STAGE_CONDITIONAL_VOICE_KEY = re.compile(
    r"^(?:(?:mon|tue|wed|thu|fri|sat|sun)\d+|"
    r"(?:neutral|good|bad)(?:_\d+)?|outdoor_\d+)$",
    re.IGNORECASE,
)


def _count_markers(text: str, markers: Iterable[str]) -> int:
    folded = text.casefold()
    return sum(folded.count(marker.casefold()) for marker in markers)


def voice_anchor_text_fits(
    text: object,
    *,
    min_length: int = VOICE_ANCHOR_MIN_TEXT,
    max_length: int = VOICE_ANCHOR_MAX_TEXT,
) -> bool:
    """窗口判定：这段文本能不能当作语气锚点（长度口径的唯一权威）。

    比较的是 **strip 之后**的长度——生成侧就是先 `strip` 再比，调用方若自己
    用原始长度判断，会在带首尾空白的样本上得出不同答案。

    `min_length=0` 表示调用点不设下限：自然纹理卡历史上接受极短原文，
    本次不改它的口径；**上限一律是同一个 80**——那才是三处漂移的地方。
    """

    if not isinstance(text, str):
        return False
    length = len(text.strip())
    return min_length <= length <= max_length


def _voice_energy(text: str) -> tuple[str, dict[str, int]]:
    """从短对白中提取可解释的表达能量信号。"""

    signals = {
        "excitementMarkers": _count_markers(text, _ENERGY_EXCITEMENT_MARKERS),
        "exclamationMarkers": _count_markers(text, _ENERGY_EXCLAMATION_MARKERS),
        "continuationMarkers": _count_markers(text, _ENERGY_CONTINUATION_MARKERS),
    }
    exclamations = signals["exclamationMarkers"]
    excitement = signals["excitementMarkers"]
    continuations = signals["continuationMarkers"]
    if (
        exclamations >= 2
        or excitement >= 2
        or (exclamations and excitement)
        or continuations >= 2
    ):
        return "high", signals
    if exclamations or excitement or continuations:
        return "medium", signals
    return "low", signals


def _sample_relationship_stage(sample: Mapping[str, Any]) -> str:
    """样本自己的阶段条件；读取规则统一在 `dialogue_stage`。

    这里只读**显式**条件、不做推断：生成侧的锚点是「原文自带的阶段」，
    推断留给检索侧（`profile_index` 传 `infer=True`）。
    """

    return sample_stage_hint(sample)


def _stage_distance(sample: Mapping[str, Any], requested_stage: str) -> int | None:
    """阶段锚点排序；实现见 `dialogue_stage.sample_stage_distance`。"""

    return sample_stage_distance(sample, requested_stage)


def _stage_conditioned_voice_sample(sample: Mapping[str, Any]) -> bool:
    """允许带阶段条件的日常键作为阶段锚点，但不引入婚后/事件对白。"""

    if not _sample_relationship_stage(sample):
        return False
    evidence_kind = str(sample.get("evidenceKind", "dialogue")).strip().casefold()
    if evidence_kind in {"marriage_dialogue", "roommate_dialogue"}:
        return False
    source_path = str(sample.get("sourcePath", "")).replace("\\", "/").casefold()
    # 与 evidence._is_special_dialogue_record 对齐（B18）：索引里的 sourcePath 是相对
    # Mod 根的、**不带前导斜杠**，所以只查 "/events/" 会漏掉顶层的 events/ 与 code/。
    # 实测：真实索引里这两类路径的样本有 3525 个，但**没有一个**符合阶段锚点的其他
    # 条件——所以这次对齐不改变任何现有结果，只是把两处规则统一。
    if (
        source_path.startswith("events/")
        or "/events/" in source_path
        or source_path.startswith("code/")
        or "/code/" in source_path
        or source_path.endswith("festivaldialogue.json")
    ):
        return False
    return bool(
        _STAGE_CONDITIONAL_VOICE_KEY.fullmatch(
            str(sample.get("sourceKey", "")).strip()
        )
    )


def _stage_voice_anchor(
    sample: Mapping[str, Any],
    *,
    voice_energy: str,
    energy_signals: Mapping[str, int],
) -> dict[str, Any]:
    sample_id = str(sample.get("sampleId", "")).strip()
    source_mod = sample.get("sourceMod")
    text = str(sample.get("text", "")).strip()
    anchor: dict[str, Any] = {
        "sampleId": sample_id,
        "text": text,
        "voiceEnergy": voice_energy,
        "energySignals": dict(energy_signals),
    }
    if isinstance(source_mod, str) and source_mod.strip():
        anchor["sourceMod"] = source_mod.strip()
    for key in ("sourceKey", "evidenceKind"):
        value = sample.get(key)
        if isinstance(value, str) and value.strip():
            anchor[key] = value.strip()
    conditions = sample.get("conditions")
    if isinstance(conditions, Mapping):
        anchor["conditions"] = dict(conditions)
    return anchor


def select_stage_voice_anchors(
    samples: Iterable[Mapping[str, Any]],
    npc_id: str,
    relationship_stage: str,
    max_count: int = _STAGE_VOICE_ANCHOR_MAX_COUNT,
) -> list[dict[str, Any]]:
    """为当前角色选择当前关系阶段的普通和高能量语气锚点。

    只有存在带阶段条件的高质量原文时才会改变静态 voice card；调用方会在
    没有阶段候选时保留原有静态窗口。每条返回的锚点都保留能量信号计数，
    便于离线检查当前角色的表达节奏由哪些原文特征触发。
    """

    requested_stage = str(relationship_stage).strip().casefold()
    if not requested_stage:
        return []
    try:
        capped_count = max(
            0,
            min(int(max_count), _STAGE_VOICE_ANCHOR_MAX_COUNT),
        )
    except (TypeError, ValueError):
        capped_count = _STAGE_VOICE_ANCHOR_MAX_COUNT
    if capped_count == 0:
        return []

    sample_list = [dict(sample) for sample in samples if isinstance(sample, Mapping)]

    # 阶段准入顺序（P1 第 25 条统一到 dialogue_stage）：
    #   ① 精确命中当前阶段的原文；
    #   ② 一条精确命中都没有时，借更早阶段的（dating 才允许，越早越靠后）；
    #   ③ 连带阶段的原文都没有时，才用无条件日常样本兜底；
    #   ④ 最后才轮到 stranger 原文——SVE 的 Sophia 没有更近阶段键时，
    #      陌生期介绍句仍比完全没有原文可用。
    def collect_candidates(
        *,
        stage_policy: Literal["exact", "at_most_present"] = "exact",
        unconditioned_samples: bool = False,
        stranger_samples: bool = False,
    ) -> list[tuple[tuple[int, int, int, int], dict[str, Any]]]:
        """按给定阶段策略收集候选；两个开关决定放宽到哪一档。"""

        candidates: list[tuple[tuple[int, int, int, int], dict[str, Any]]] = []
        seen_texts: set[str] = set()
        for original_index, raw_sample in enumerate(sample_list):
            sample = dict(raw_sample)
            actual_stage = _sample_relationship_stage(sample)
            stage_distance = _stage_distance(sample, requested_stage)
            if actual_stage:
                if not stage_hint_applies(
                    sample,
                    requested_stage,
                    policy=stage_policy,
                    include_stranger=stranger_samples,
                ):
                    continue
            elif not unconditioned_samples:
                # 有明确阶段原文时，不能让无条件 Introduction 抢走窗口。
                continue
            sample_id = sample.get("sampleId")
            text = sample.get("text")
            if not isinstance(sample_id, str) or not sample_id.strip():
                continue
            if not isinstance(text, str):
                continue
            cleaned_text = text.strip()
            if not voice_anchor_text_fits(cleaned_text):
                continue
            if has_dialogue_control_residue(cleaned_text):
                continue
            if _VOICE_ANCHOR_CONTROL.search(cleaned_text):
                continue

            # 当前阶段的关系回应可以是 Good_0 等特殊键；它们在全局静态卡
            # 中会被排除，但有显式阶段条件时可以作为 Sophia 的高能量证据。
            relation_stage_anchor = bool(
                _RELATION_RESPONSE_KEY.fullmatch(
                    str(sample.get("sourceKey", "")).strip()
                )
                and _sample_relationship_stage(sample)
            )
            # ⚠️ 已知「四选一证据门」实际上几乎拦不住任何样本（第 146 项用实验确认）：
            # 实测 is_model_evidence_record 连普通 dialogue 记录都返回 True，
            # 所以这个 continue 极难触发。**保留为防御性下限**——万一上游索引
            # 改了证据标记的口径，这里仍能兜住；不要因为“测不到”就删掉。
            if not is_stable_voice_evidence_record(sample) and not (
                relation_stage_anchor
                or is_model_evidence_record(sample)
                or _stage_conditioned_voice_sample(sample)
            ):
                continue

            folded_text = " ".join(cleaned_text.split()).casefold()
            if folded_text in seen_texts:
                continue
            seen_texts.add(folded_text)
            voice_energy, energy_signals = _voice_energy(cleaned_text)
            # 高能量句应先进入少量 few-shot 窗口，避免当前阶段已有的
            # 跳拍、停顿或直接反应被低能量陈述压平。
            energy_rank = {"high": 0, "medium": 1, "low": 2}[voice_energy]
            stage_rank = stage_distance if stage_distance is not None else 5
            evidence_priority = _evidence_priority(sample, original_index)
            anchor = _stage_voice_anchor(
                {**sample, "text": cleaned_text},
                voice_energy=voice_energy,
                energy_signals=energy_signals,
            )
            candidates.append(
                (
                    (stage_rank, energy_rank, evidence_priority[0], original_index),
                    anchor,
                )
            )
        return candidates

    # 四级回退：精确阶段 → 更早阶段（dating 借用恋爱前原文）→ 无条件日常样本
    # → stranger 原文。只有前一级**一条候选都凑不出**时才会放开下一级，
    # 所以有精确阶段原文时，早期阶段与无阶段样本都不会抢走窗口。
    candidates = collect_candidates()
    if not candidates:
        candidates = collect_candidates(stage_policy="at_most_present")
    if not candidates:
        candidates = collect_candidates(
            stage_policy="at_most_present",
            unconditioned_samples=True,
        )
    if not candidates:
        candidates = collect_candidates(
            stage_policy="at_most_present",
            unconditioned_samples=True,
            stranger_samples=True,
        )

    if not candidates:
        return []
    ranked = [anchor for _, anchor in sorted(candidates, key=lambda item: item[0])]
    high = [item for item in ranked if item["voiceEnergy"] == "high"]
    low_or_medium = [item for item in ranked if item["voiceEnergy"] != "high"]
    selected: list[dict[str, Any]] = []
    # 先放高能量原文，让自然模式的小窗口保留当前角色的明显节奏；只有
    # 高能量样本不足时才回填中低能量句，避免声线被平直说明腔吞掉。
    for anchor in high:
        if len(selected) >= capped_count:
            break
        selected.append(anchor)
    for anchor in low_or_medium:
        if len(selected) >= capped_count:
            break
        if anchor not in selected:
            selected.append(anchor)
    # ⚠️ 下面这一段**不可达**（第 146 项，已做变异验证）：high 与 low_or_medium 是按
    # voiceEnergy 互补划分的，两者之并就是 ranked，所以前两个循环已经把全部候选
    # 考虑过一遍；删掉本段后相关 31 条测试仍全绿。**保留为防御**——若将来有人改动
    # 上面的分桶方式（例如新增一个 voiceEnergy 取值），这里仍能兜底。
    for anchor in ranked:
        if len(selected) >= capped_count:
            break
        if anchor not in selected:
            selected.append(anchor)
    return selected[:capped_count]


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
        if not voice_anchor_text_fits(cleaned_text):
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
