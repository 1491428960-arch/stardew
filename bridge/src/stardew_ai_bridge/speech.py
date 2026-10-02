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
    dialogue_key_season,
    has_dialogue_control_residue,
    is_model_evidence_record,
    is_stable_voice_evidence_record,
    normalise_season,
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

# 锚点窗口的语气词密度上限（相对该角色原文全库的倍数）。
#
# 2026-09-24（`docs/report-kimi-filler-diagnosis-2026-09-24.md`）：
# 修 prompt 措辞之前，窗口的语气词密度是全库的 1.80x（中位）、最高 3.59x。
# 根因在下面的排序键把 `introduction` 排在前面，而介绍句恰好是语气词最密集
# 的一类（「呃……你好。」「噢。你是刚搬进来的，对吧？」）。
#
# 模型把这个被放大的窗口当模板复现：同一批 prompt 下 Kimi 输出是全库的
# 2.48x，DeepSeek 反过来压到 0.67x。**改 prompt 措辞实测拉不住**
# （每角色 100 轮、共 600 轮、0/3 角色显著变化），所以均衡只能做在选样这一侧。
#
# 1.25 是留了余量的上限：窗口只有 8 条，要求它精确等于全库密度会让候选
# 稍有不符就选不满。这里只挡住「明显偏高」，不追求精确配平。
_VOICE_ANCHOR_PARTICLE_RATIO_CAP = 1.25

# 窗口允许的语气词数下限。
#
# 语料很短（或该角色本来就极少用语气词）时，`比例 × 窗口字数` 会小到 1 以下，
# 于是任何一句带「嗯」的正常对白都被拒——选出来的窗口完全无菌，既不自然，
# 也让「这个角色本来怎么说话」这个信号整个消失。给一个下限，保证预算
# 只挡「过量」，不变成「禁用」。
_VOICE_ANCHOR_MIN_PARTICLES = 1

# 只数**停顿/迟疑类**语气词（「呃……」「嗯，」这种）。
#
# 刻意**不含**「吧」「呢」「嘛」这类句末助词：它们在原版对白里本来就大量使用
# （「你就是新来的农场主吧？」），是正常汉语，不构成结巴感。真正让角色变成
# 一种结巴的是句首那串停顿词，所以口径必须收在这里，否则一条完全正常的
# 问句会被算成两个语气词而被预算拒掉。
#
# 与 `dialogue_style_quality._SPEECH_PARTICLES` 用途不同：那份判定「够不够格
# 算一个口语颗粒」（含「好吧」「行吧」这样的词），这里只需要「数密度」。
_VOICE_ANCHOR_SPEECH_PARTICLES = frozenset("嗯呃哦噢啊唉呀哎诶嘿哈唔")
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
    r"^(?:(?:spring|summer|fall|winter)_)?"
    r"(?:(?:mon|tue|wed|thu|fri|sat|sun)\d+|"
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
    season: str = "",
) -> list[dict[str, Any]]:
    """为当前角色选择当前关系阶段的普通和高能量语气锚点。

    只有存在带阶段条件的高质量原文时才会改变静态 voice card；调用方会在
    没有阶段候选时保留原有静态窗口。每条返回的锚点都保留能量信号计数，
    便于离线检查当前角色的表达节奏由哪些原文特征触发。

    `season` 是当前季节（`gameState.season`，小写英文或中文季节字）。
    季节前缀的日常键（`summer_Mon4`，语料里 1283 条）只在**季节吻合**时优先；
    没给季节信息、或季节不吻合时，它们排在无季节限定的通用键之后 ——
    否则放行这批素材就等于"夏天满口冬天的话"。**阶段仍然优先于季节**：
    更早阶段的当前季节句不能挤掉当前阶段的通用句。
    """

    requested_stage = str(relationship_stage).strip().casefold()
    if not requested_stage:
        return []
    requested_season = normalise_season(season)
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
    ) -> list[tuple[tuple[int, int, int, int, int], dict[str, Any]]]:
        """按给定阶段策略收集候选；两个开关决定放宽到哪一档。"""

        candidates: list[tuple[tuple[int, int, int, int, int], dict[str, Any]]] = []
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
            # 季节优先只排在阶段之后：阶段比季节更根本（陌生人阶段的夏季句
            # 不能挤掉当前阶段的通用句）。没有季节限定的通用键恒为 1，
            # 于是"给不出季节"时谁都不插队，行为回到放行之前。
            sample_season = dialogue_key_season(sample.get("sourceKey", ""))
            if not sample_season:
                season_rank = 1
            elif requested_season and sample_season == requested_season:
                season_rank = 0
            else:
                season_rank = 2
            evidence_priority = _evidence_priority(sample, original_index)
            anchor = _stage_voice_anchor(
                {**sample, "text": cleaned_text},
                voice_energy=voice_energy,
                energy_signals=energy_signals,
            )
            candidates.append(
                (
                    (
                        stage_rank,
                        season_rank,
                        energy_rank,
                        evidence_priority[0],
                        original_index,
                    ),
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

    # 2026-09-22（用户拍板走 B）：**候选不足**时从更早阶段 / 无阶段标注的日常样本补足。
    #
    # 上面那条四级回退是**整级**的（`if not candidates`）：只要当前阶段有**一条**原文，
    # 就再也不看别的来源。实测后果：Sophia 的 `friend` 档索引里**总共只有 2 条**
    # 阶段原文，而且两条都落在布料/面料（`Thu6`「那是什么面料的？」、
    # `Tue6`「艾米丽…高级布料」）——整个语气窗口被同一个生活面占满；
    # `stranger` 档 4 条里 3 条是戒备句（「你需要点什么吗」「你想要干什么」），
    # 第 4 条才是「画了眼线」。
    #
    # 补足来源与闸门（②③ 都是实测踩出来的）：
    #   ① `at_most_present` = 允许**更早阶段**的原文（friend 可借 acquaintance）。
    #      ⚠ 这里**刻意不开 `unconditioned_samples`**（第一版开了，实测出问题）：
    #      无阶段标注的样本没有阶段信息，能漏进**任意**阶段 —— 抽查发现
    #      Linus 的 `married` 档被补进「陌生人？……你好。不要在意我。这里就只有
    #      我一个人住。」，那是明确的初识语气，放在婚后明显违和。
    #      只借"有阶段标注且不晚于当前阶段"的原文，语义一致性才有保障。
    #      （Sophia 的 `friend` 借 acquaintance 的 8 条，已经足够解决"两条都是布料"。）
    #   ② ⚠ **只接受 `_anchor_category != "other"` 的样本**。样本里混着
    #      **事件对白**（sourceKey 形如 `3691380/f Scarlett 125/t 600 1800/w sunny/…`），
    #      那是她在事件里**对别人**说的话（"加油，斯嘉丽！""今天早上斯嘉丽开着她
    #      爸爸的车来到这里"）——没加这道闸时 stranger 的 4 条锚点被挤掉 3 条，
    #      **比修之前更差**。
    #   ③ 优先补当前窗口里**还没有出现过的类别**（`_anchor_category` 的分桶本来就是
    #      为"避免窗口被同一类对白占满"而存在的）。
    # 条数上限仍由调用方的 `max_count`（当前 8）决定。
    if len(candidates) < capped_count:
        existing = {anchor["sampleId"] for _, anchor in candidates}
        seen_categories = {_anchor_category(anchor) for _, anchor in candidates}
        supplement: list[tuple[tuple[int, int, int, int, int], dict[str, Any]]] = []
        # ⚠️ 2026-09-26 实测记录 —— 这里和 `_anchor_category` 的桶判别**必须成对改**，
        # 只改一个都**完全无效**（两次都实测过，新进 0 条）：
        #
        #   ① 本行的 `unconditioned_samples=True`：无阶段标注的样本占原版语料的
        #      九成以上（Lewis 118/126、Robin 154/164、Marnie 78/90），
        #      而第一/二级会因 `elif not unconditioned_samples: continue`
        #      把它们全部跳过 ⇒ 补足池等于空的。
        #   ② `_anchor_category`（本文件上方）：它原本把事件键一律归 `other`，
        #      于是本循环下面那道 `== "other"` 闸门又把进来的样本滤光。
        #
        #   只改 ① → 样本进了池子却被 `other` 闸门滤掉；
        #   只改 ② → 样本根本到不了闸门。
        #   两处一起改后，Lewis 的窗口才第一次拿到"对玩家说的"日常素材。
        #   诊断：`.tmp/anchor-pool-debug2.txt`、`.tmp/anchor-category-probe.txt`。
        for key, anchor in collect_candidates(
            stage_policy="at_most_present",
            unconditioned_samples=True,
        ):
            if anchor["sampleId"] in existing:
                continue
            # `introduction` 也要挡：注释 ① 记录的正是这个坑 —— Linus 的 married 档
            # 被补进「陌生人？……你好。不要在意我。这里就只有我一个人住。」
            # （`.tmp/anchor-daily-only-probe.txt` 里 Linus 的 Introduction 仍是它。）
            # 同一个键在别的角色身上可能是叙事句（Lewis 的 Introduction 讲的是
            # 玩家爷爷的旧床），但逐个角色判不划算，保守排除。
            if _anchor_category(anchor) in {"other", "introduction"}:
                continue
            existing.add(anchor["sampleId"])
            supplement.append((key, anchor))
        supplement.sort(
            key=lambda item: (
                0 if _anchor_category(item[1]) not in seen_categories else 1,
                item[0],
            )
        )
        candidates.extend(supplement)

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


# `/f <Name> <n>` —— 星露谷对话键里的条件段。名字是**本角色**时表示「好感 ≥ n」
# （台词仍然是对玩家说的）；名字是**别人**时表示这段是事件里对那个人的台词。
_F_SEGMENT = re.compile(r"/f\s+([A-Za-z][A-Za-z0-9_]*)\s+\d+")


def _speaks_to_third_party(sample: Mapping[str, Any]) -> bool:
    """判断这段台词是不是「在事件里对某个 NPC 说的」，而不是对玩家说的。

    典型反例来自注释 ②：`6497428/e 6497423/f Leo 1500` 是 Linus 对 Leo 说的话
    （「你好，雷欧……我叫莱纳斯」）、`639373/f Lewis 1500/f Marnie` 是 Lewis
    对 Marnie 说的话、`3910674/f Shane 1000` 是 Marnie 对 Shane 说的。
    这些放进锚点窗口会让角色"对着玩家说别人的事"，必须排除。
    """

    key = str(sample.get("sourceKey", ""))
    if not key:
        return False
    npc = str(sample.get("npcId", "")).strip().casefold()
    for match in _F_SEGMENT.finditer(key):
        name = match.group(1).casefold()
        if name and name != npc:
            return True
    return False


def _anchor_category(sample: Mapping[str, Any]) -> str:
    """给正向语气锚点分桶，避免窗口被同一类对白占满。

    2026-09-26 改（与补足循环处成对，见那里的说明）：`other` 原本是「其余全部」
    的兜底桶，实测它把绝大多数可用素材一起挡在窗口外，Lewis 这类角色每轮
    只拿到 1 条锚点（`.tmp/anchor-pool-debug2.txt`）。放宽后又发现**单纯按内容判
    「对玩家说」不够** —— 溯源 Lewis 放宽后的 8 条锚点，**5 条有问题**
    （`.tmp/anchor-sourcekey-trace.txt`）：

      · `Data/Events/BusStop.json:60367/u 0:event-line-6` —— 开场序列（玩家第一天）
      · `Data/Events/Town.json:53/e 55:…:event-line-12` —— 在展览上**对莉亚**说话
      · `Nom0ri.RomRas:…/Juna.json:ReadyToRumble` —— 别的 mod 的喊话键「好了！大家安静！」

    `Data/Events/*` 的 `event-line-N` **无法从 sourceKey 判断说话对象**，
    所以来源要收窄到**角色日常对话文件**（`Characters/Dialogue/<NPC>.json`）——
    那里的台词按定义都是对玩家说的、也没有事件上下文。收窄后各角色仍有 4~8 条
    （`Lewis 12→5`、`Linus 17→8`、`Marnie 15→4`、`Robin 14→4`、`Wizard 17→4`，
    见 `.tmp/anchor-daily-only-probe.txt`），且 Lewis 的窗口里第一次出现
    「旧社区中心不见了……我不禁有一点失落感」这种私人层素材。

    ⚠ 这道**来源**筛选放在数据层 `profile_index.collect_stage_candidates()` 里，
    本函数只管分桶。放在这里会让测试的合成样本（sampleId 是 `"exact"` 这种）
    被误判成非日常对话而全落进 `other`，补足逻辑就没法单独测了。
    """

    key = str(sample.get("sourceKey", "")).strip().casefold()
    if key == "introduction":
        return "introduction"
    # 季节前缀的日常键（`summer_Mon4` / `winter_fri`）与它们的无季节孪生键同桶：
    # 它们本来就是"这个角色平时怎么说话"，只是换季换了一批。分成新桶会让
    # 补足循环的类别多样性判据把同一类素材当成两类，反而挤掉真正的多样性。
    weekday = re.fullmatch(
        r"(?:(?:spring|summer|fall|winter)_)?"
        r"(?:mon|tue|wed|thu|fri|sat|sun)(\d*)",
        key,
    )
    if weekday:
        return "weekday_variant" if weekday.group(1) else "weekday"
    if re.fullmatch(r"(?:neutral|good|bad)_\d+", key):
        return "relationship"
    # 日常对话文件里仍可能有 `/f <别人>`（在事件中段对第三方说的话）。
    if _speaks_to_third_party(sample):
        return "other"
    return "scene"


def _speech_particle_counts(text: str) -> tuple[int, int]:
    """返回 `(语气词数, 汉字数)`，供锚点窗口做语气词密度均衡。

    只数汉字做分母：标点、空格和拉丁字符不参与，这样跨来源的样本可比。
    """

    particles = sum(1 for char in text if char in _VOICE_ANCHOR_SPEECH_PARTICLES)
    chinese = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return particles, chinese


def _voice_anchor_candidates(
    samples: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """提取短、可读、来源可追溯的原文语气片段。

    窗口除了来源与结构多样性，还受**语气词密度**约束——理由与阈值见
    `_VOICE_ANCHOR_PARTICLE_RATIO_CAP`。
    """

    # 先物化：下面要遍历三次（算密度、排序、回查 sample），
    # 直接把 `samples` 当可重复序列用会在传生成器时静默出错。
    sample_list = [item for item in samples if isinstance(item, Mapping)]

    # 基准取该角色原文**全库**的语气词密度（分母是全库汉字数，
    # 样本量足够大，比按条平均更稳）。
    corpus_particles = 0
    corpus_chinese = 0
    for sample in sample_list:
        text = sample.get("text")
        if isinstance(text, str):
            particles, chinese = _speech_particle_counts(text)
            corpus_particles += particles
            corpus_chinese += chinese
    particle_cap = (
        corpus_particles / corpus_chinese * _VOICE_ANCHOR_PARTICLE_RATIO_CAP
        if corpus_chinese
        else float("inf")
    )

    candidates: list[tuple[tuple[int, int, int, int], dict[str, str]]] = []
    for original_index, sample in enumerate(sample_list):
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
        # 事件对白锚点必须带上 `eventId`：运行时 `ProfileIndexStore.voice_card`
        # 靠它判断该事件是否已完成（`_voice_anchor_is_available`）。
        # 2026-09-29 之前这里漏了这个字段，导致 60 个角色的锚点**无法门控**
        # —— 未完成事件的台词照样进 `voice_card` 卡。实测见
        # `.scratch/probe-voice-card-gate.py`。
        event_id = sample.get("eventId")
        if isinstance(event_id, str) and event_id.strip():
            anchor["eventId"] = event_id.strip()
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
    selected_particles = 0
    selected_chinese = 0

    def add(anchor: dict[str, str], category: str, *, require_new: bool) -> None:
        nonlocal selected_particles, selected_chinese
        source = source_family(anchor.get("sourceMod", ""))
        text = anchor["text"].casefold()
        if text in selected_texts or len(selected) >= _VOICE_ANCHOR_MAX_COUNT:
            return
        if require_new and source in selected_sources and category in selected_categories:
            return
        # 语气词预算：宁可让窗口留空位，也不把它拉成一种结巴。
        # 这条挡在最后，是为了让来源与结构多样性先决定「选谁」，
        # 只有当选中的样本开始推高密度时才有候选被跳过。
        particles, chinese = _speech_particle_counts(anchor["text"])
        allowed = max(
            _VOICE_ANCHOR_MIN_PARTICLES,
            particle_cap * (selected_chinese + chinese),
        )
        if chinese and selected_particles + particles > allowed:
            return
        selected.append(anchor)
        selected_particles += particles
        selected_chinese += chinese
        selected_sources.add(source)
        selected_categories.add(category)
        selected_texts.add(text)

    # 第一遍优先保证来源与表达结构多样，第二遍再按稳定顺序补齐。
    for _, anchor in ranked:
        sample = next(
            (
                item
                for item in sample_list
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
                for item in sample_list
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
                for item in sample_list
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
