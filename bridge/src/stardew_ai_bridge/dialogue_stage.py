"""对白样本「关系阶段条件」的单一权威实现（语义层审计 P1 第 25 条）。

同一个问题此前有三套判定：

- `profile_index._relationship_stage_matches`：在 `conditions` 缺失时用
  `corpus.infer_dialogue_conditions` 推断，`allow_lower_stage` 时按 rank 宽放；
- `speech._stage_matches`：严格相等 + 婚后视同 parent——**全仓没有生产调用方**，
  只有测试钉着一个已经断线的实现；
- `speech._stage_distance` 与 `profile_index._relationship_specificity_priority`：
  同一件事的两种排序写法（一个用距离、一个用优先级）。

三处任何一处改口径，另外两处都不会跟着变。这里把「阶段提示怎么读」「它能
不能用在当前请求里」「它在候选里排多前」三件事各收成一份实现，调用方只声明
自己用的是哪种应用方式：

- `exact`：严格相等。阶段锚点（生成侧）的语义。
- `at_most_present`：允许更早阶段。检索侧「当前话题没有当前阶段命中时，
  借用早期日常对白」的语义。
- `parent_widens`：`married` 同时满足 `parent`。婚后对白也是 parent 阶段的原文。

`stranger` 一律走严格相等：它在两个旧实现里口径不同（一个严格相等、
一个要求实际 rank > 0），而「陌生期口吻」本来就不该放宽到任何更近的阶段。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from .relationship_gating import STAGE_RANK

# 阶段顺序**派生**自 `relationship_gating.STAGE_RANK`（2026-09-20 第 192 项已经
# 把两份一字不差的阶段表下沉到那里，这里不再抄第二份）。
#
# 样本阶段域是权威表**去掉 `parent`** 的有意子集：对白样本不会标注 parent——
# 它是「与玩家有孩子」这种关系状态，不是对白来源的标注。相对顺序与 STAGE_RANK
# 天然一致，将来那边新增阶段时这份子集也会跟着变。
SAMPLE_STAGE_ORDER: tuple[str, ...] = tuple(
    sorted(
        (stage for stage in STAGE_RANK if stage != "parent"),
        key=STAGE_RANK.__getitem__,
    )
)
_STAGE_RANK = {stage: index for index, stage in enumerate(SAMPLE_STAGE_ORDER)}
# 「更早一档」在排序里的步长：精确命中 0，下一档 2（1 留给「没有阶段条件」）。
_STAGE_STEP = 2
_UNCONDITIONED_SPECIFICITY = 1

StagePolicy = Literal["exact", "at_most_present", "parent_widens"]
_STAGE_POLICIES: frozenset[str] = frozenset({"exact", "at_most_present", "parent_widens"})


def sample_stage_hint(
    sample: Mapping[str, Any],
    *,
    infer: bool = False,
) -> str:
    """读取样本自己的关系阶段，归一化为小写；读不到就返回空串。

    `relationshipStage` 优先于 `relationship_stage`。`infer=True` 时才在
    `conditions` 缺失或为空时按 `sourceKey` 推断——生成侧只读显式条件，
    检索侧允许推断，这个差别现在是一个显式开关，而不是两套读取代码。
    """

    if not isinstance(sample, Mapping):
        return ""
    conditions = sample.get("conditions")
    actual = ""
    if isinstance(conditions, Mapping):
        value = conditions.get("relationshipStage", conditions.get("relationship_stage"))
        actual = value.strip().casefold() if isinstance(value, str) else ""
    if actual or not infer:
        return actual
    from .corpus import infer_dialogue_conditions

    inferred = infer_dialogue_conditions(
        str(sample.get("sourcePath", "")),
        str(sample.get("sourceKey", "")),
    ).get("relationshipStage")
    return inferred.strip().casefold() if isinstance(inferred, str) else ""


def _matches_or_is_earlier(
    actual: str,
    requested: str,
    *,
    include_stranger: bool,
) -> bool:
    """`at_most_present` 的准入：精确命中，或严格更早的阶段。

    三个边界：

    - `stranger` 是排序表的起点，没有「更早」可言，所以它能否进来只由
      `include_stranger` 决定——检索侧的头一次尝试**排除**它（避免 Shane
      这类角色在朋友阶段退回陌生期口吻），只有明确的「借用更早阶段」回退
      才把它算进候选；
    - `parent` 请求只认 `married`：样本域里没有 parent 标注，而 `married`
      是权威顺序里它的相邻前一档；更早的 `close` / `friend` 是「恋爱前
      日常口吻」，不能当「有孩子」阶段的原文；
    - 其余阶段按 rank 接受严格更早的阶段，所以婚后请求可以用朋友期日常
      对白补节奏（`allow_lower_stage` 的原意），而不会把恋爱期原文当婚后来源。

    `married` 与 `parent` 的**互认**属于 `parent_widens` 策略，不在这里——
    否则「婚后借日常对白」和「婚后只认婚后原文」会混成一条规则。
    """

    if actual == requested:
        return True
    if actual == "stranger":
        # stranger 没有「更早」可言：只有请求本身就是 stranger（上面已命中）、
        # 或调用方明确打开 `include_stranger` 时才适用。
        return bool(include_stranger)
    if requested == "stranger":
        return False
    if requested == "parent":
        # 「有孩子」阶段的来源只有已婚原文：样本域里没有 parent 标注，
        # 而 `married` 在权威顺序里是它的相邻前一档。更早的 `close` / `friend`
        # 属于「恋爱前日常口吻」，不能当 parent 阶段的原文。
        return actual == "married"
    actual_rank = _STAGE_RANK.get(actual)
    requested_rank = _STAGE_RANK.get(requested)
    if actual_rank is None or requested_rank is None:
        return False
    return actual_rank < requested_rank


def stage_hint_applies(
    sample: Mapping[str, Any],
    requested_stage: object,
    *,
    policy: StagePolicy = "exact",
    infer: bool = False,
    include_stranger: bool = False,
) -> bool:
    """这条样本能不能用在当前关系阶段的请求里。

    样本没写阶段、或这次请求不指定阶段时一律**保留**：缺条件不等于不适用。
    `include_stranger` 只对 `at_most_present` 有意义：`parent_widens` 的宽放
    范围由 `married` / `parent` 互认决定，与 stranger 无关——见
    `_matches_or_is_earlier`（`married` / `parent` 的互认也收在它里面，
    不在本函数里再写一遍）。
    """

    if policy not in _STAGE_POLICIES:
        raise ValueError(f"未知的阶段应用方式：{policy!r}")
    requested = str(requested_stage or "").strip().casefold()
    if not requested:
        return True
    actual = sample_stage_hint(sample, infer=infer)
    if not actual:
        return True
    if policy == "exact":
        # 严格相等：阶段锚点（生成侧）的语义，不借用任何更早或更近的阶段。
        # `married` / `parent` 的互认同样不在这里生效——见下面 parent_widens。
        return actual == requested
    if policy == "at_most_present":
        return _matches_or_is_earlier(
            actual, requested, include_stranger=include_stranger
        )
    if requested in {"married", "parent"}:
        # 婚后视同 parent，反向也成立：`parent` 是「与玩家有孩子」的关系状态，
        # 它不是对白样本的标注，所以样本域里只有 `married` 能当它的来源，
        # 而「请求 married、样本是 parent」同样是同一段婚姻关系的原文。
        return actual in {"parent", "married"}
    return actual == requested


def sample_stage_distance(
    sample: Mapping[str, Any],
    requested_stage: object,
) -> int | None:
    """阶段锚点排序：越小越贴近当前阶段；不适用则为 `None`。

    精确命中 0；`dating` 允许借用恋爱前阶段（越早越远，stranger 为 4）。
    `married` 与 `parent` 互相命中、同级；排序刻度与 `sample_stage_specificity`
    一致（更早一档加 `_STAGE_STEP`）。
    """

    requested = str(requested_stage or "").strip().casefold()
    if not requested:
        return None
    actual = sample_stage_hint(sample)
    if not actual:
        return None
    # `married` 与 `parent` 互相命中，同级（见 `_matches_or_is_earlier`）。
    if requested in {"married", "parent"}:
        return 0 if actual in {"married", "parent"} else None
    if not _matches_or_is_earlier(actual, requested, include_stranger=True):
        return None
    if actual == requested:
        return 0
    if requested == "dating":
        # 恋爱前阶段借用顺序：越接近 dating 越先进入锚点窗口。
        return {
            "close": 1,
            "friend": 2,
            "acquaintance": 3,
            "stranger": 4,
        }.get(actual)
    return (_STAGE_RANK[requested] - _STAGE_RANK[actual]) * _STAGE_STEP


def sample_stage_specificity(
    sample: Mapping[str, Any],
    requested_stage: object,
    *,
    infer: bool = True,
) -> int:
    """检索侧排序：0 是精确命中，1 是没有阶段条件，更早阶段按 rank 递增。

    只描述「多贴近当前阶段」，不做准入——准入请用 `stage_hint_applies`。
    排序口径与 `sample_stage_distance` 一致：更早一档加 `_STAGE_STEP`，
    `married` / `parent` 互相命中、同级。
    """

    requested = str(requested_stage or "").strip().casefold()
    if not requested:
        return 0
    actual = sample_stage_hint(sample, infer=infer)
    if not actual:
        return _UNCONDITIONED_SPECIFICITY
    if requested in {"married", "parent"}:
        # `married` 与 `parent` 互相命中，同级——`parent` 是「与玩家有孩子」的
        # 关系状态，样本域里没有它的标注，婚后对白就是它在索引里的全部来源。
        return 0 if actual in {"married", "parent"} else _UNCONDITIONED_SPECIFICITY
    if not _matches_or_is_earlier(actual, requested, include_stranger=True):
        return _UNCONDITIONED_SPECIFICITY
    if actual == requested:
        return 0
    return _UNCONDITIONED_SPECIFICITY + (
        _STAGE_RANK[requested] - _STAGE_RANK[actual]
    ) * _STAGE_STEP
