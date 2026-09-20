"""对白样本「阶段条件是否适用」的单一权威实现（语义层审计 P1 第 25 条）。

## 背景

同一个问题——「这条原文样本能不能用在当前关系阶段的请求里」——此前有**三套判定**：

1. `profile_index._relationship_stage_matches`：按 rank 宽放（`allow_lower_stage`
   允许更早阶段），缺 `conditions` 时还会用 `corpus.infer_dialogue_conditions` 推断；
2. `speech._stage_matches`：严格相等＋「婚后视同 parent」，**全仓没有生产调用方**，
   只有 10 条测试钉着一个已经断线的实现；
3. `speech._stage_distance` / `profile_index._relationship_specificity_priority`：
   同一件事的两种排序写法（一个用「距离」，一个用「优先级」）。

三处只要有一处改口径，另外两处不会跟着变。

## 本次建立的语义

阶段判定下沉到 `dialogue_stage`，**只有一份实现**，三种「应用方式」显式命名：

- `exact`：严格相等（generation 侧「阶段锚点」的语义）；
- `at_most_present`：允许更早阶段（检索侧「话题没有当前阶段命中时借用早期日常对白」的语义）；
- `parent_widens`：`married` 同时满足 `parent`（婚后对白也算 parent 阶段原文）。

阶段顺序**派生**自 `relationship_gating.STAGE_RANK`（第 192 项已把两份一字不差的
阶段表下沉到那里），样本阶段域是它去掉 `parent` 的有意子集——对白样本不会标注
parent，那是「与玩家有孩子」的关系状态，不是对白来源的标注。本文件同时钉住
`parent_widens` / 请求本身是 `parent` 时的距离与排序取值。

同时钉住一处**曾经真的漂移过**的地方：`requested="stranger"` 在三套实现里
分别是「严格相等」（speech）、「rank 0 且实际 rank > 0 才算命中」（profile_index
的普通路径，它把 stranger 样本排除在外）。统一后 stranger 只走严格相等。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.dialogue_stage import (
    SAMPLE_STAGE_ORDER,
    sample_stage_distance,
    sample_stage_hint,
    sample_stage_specificity,
    stage_hint_applies,
)
from stardew_ai_bridge.relationship_gating import STAGE_RANK

# --- 阶段提示的提取 ---------------------------------------------------------


@pytest.mark.parametrize(
    ("conditions", "expected"),
    [
        ({"relationshipStage": "Married"}, "married"),
        ({"relationshipStage": "  Friend  "}, "friend"),
        ({"relationship_stage": "close"}, "close"),
        # relationshipStage 优先于 relationship_stage（两处旧实现都这样）
        ({"relationshipStage": "dating", "relationship_stage": "friend"}, "dating"),
        ({}, ""),
        (None, ""),
        ("married", ""),  # conditions 本身不是映射
        ({"relationshipStage": None}, ""),
        ({"relationshipStage": 42}, ""),
        ({"relationshipStage": "   "}, ""),
    ],
)
def test_stage_hint_is_extracted_once_for_every_caller(
    conditions: object, expected: str
) -> None:
    assert sample_stage_hint({"conditions": conditions}) == expected


def test_stage_hint_of_a_sample_without_conditions_is_empty() -> None:
    assert sample_stage_hint({}) == ""


def test_stage_hint_can_be_inferred_for_records_without_conditions() -> None:
    # `profile_index` 的检索路径允许在样本没写阶段时按 sourceKey 推断；
    # 这条能力必须是**同一个函数的一个开关**，不是第二套实现。
    sample = {"sourcePath": "characters.json", "sourceKey": "Mon8"}

    assert sample_stage_hint(sample) == ""
    assert sample_stage_hint(sample, infer=True) == "close"


def test_inference_only_fills_in_a_missing_stage() -> None:
    sample = {
        "conditions": {"relationshipStage": "friend"},
        "sourcePath": "characters.json",
        "sourceKey": "Mon8",
    }

    assert sample_stage_hint(sample, infer=True) == "friend"


# --- 三种应用方式 -----------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "requested", "policy", "expected"),
    [
        # exact：严格相等
        ("married", "married", "exact", True),
        ("married", "friend", "exact", False),
        ("friend", "friend", "exact", True),
        # stranger 只走严格相等（这是统一后的口径）
        ("stranger", "stranger", "exact", True),
        ("close", "stranger", "exact", False),
        # at_most_present：允许更早阶段
        ("close", "dating", "at_most_present", True),
        ("friend", "dating", "at_most_present", True),
        ("dating", "dating", "at_most_present", True),
        ("married", "friend", "at_most_present", False),
        ("stranger", "acquaintance", "at_most_present", False),
        # parent_widens：婚后视同 parent
        ("married", "parent", "parent_widens", True),
        ("parent", "parent", "parent_widens", True),
        ("parent", "married", "parent_widens", True),
        ("friend", "parent", "parent_widens", False),
    ],
)
def test_each_application_policy_is_explicit(
    actual: str, requested: str, policy: str, expected: bool
) -> None:
    sample = {"conditions": {"relationshipStage": actual}}

    assert stage_hint_applies(sample, requested, policy=policy) is expected


@pytest.mark.parametrize("policy", ["exact", "at_most_present", "parent_widens"])
def test_missing_stage_on_either_side_keeps_the_sample(policy: str) -> None:
    # 样本没写阶段、或这次请求不指定阶段时，都不应该把样本筛掉。
    assert stage_hint_applies({"conditions": {}}, "married", policy=policy) is True
    assert stage_hint_applies({}, "married", policy=policy) is True
    assert stage_hint_applies({"conditions": "married"}, "married", policy=policy) is True
    assert (
        stage_hint_applies(
            {"conditions": {"relationshipStage": "married"}}, "   ", policy=policy
        )
        is True
    )


def test_an_unknown_policy_is_rejected_loudly() -> None:
    # 静默回落到某个默认策略，正是「三套判定各自演化」的成因。
    with pytest.raises(ValueError):
        stage_hint_applies({"conditions": {}}, "married", policy="whatever")


# --- 排序：同一件事的距离与优先级 -------------------------------------------


def test_stage_order_is_the_single_rank_source() -> None:
    # 派生自 `relationship_gating.STAGE_RANK`：那边新增阶段时这份子集跟着变，
    # 不会留下第二份需要人工同步的顺序表。
    assert SAMPLE_STAGE_ORDER == (
        "stranger",
        "acquaintance",
        "friend",
        "close",
        "dating",
        "married",
    )
    assert SAMPLE_STAGE_ORDER == tuple(
        stage
        for stage, _ in sorted(STAGE_RANK.items(), key=lambda item: item[1])
        if stage != "parent"
    )


def test_the_two_rankings_agree_on_where_a_sample_sits() -> None:
    # 距离（生成侧锚点）与优先级（检索侧排序）是同一件事的两种刻度：
    # 精确命中与「不适用」的边界必须一致，否则同一个样本在两条路径上排序不同。
    for requested in ("stranger", "acquaintance", "friend", "close", "dating", "parent"):
        for actual in ("stranger", "acquaintance", "friend", "close", "dating", "married"):
            sample = {"conditions": {"relationshipStage": actual}}
            distance = sample_stage_distance(sample, requested)
            specificity = sample_stage_specificity(sample, requested)
            assert (distance is None) == (specificity == 1), (requested, actual)
            assert (distance == 0) == (specificity == 0), (requested, actual)
            if distance is None:
                assert specificity == 1, (requested, actual)
            elif distance == 0:
                assert specificity <= 1, (requested, actual)
            else:
                assert specificity > 1, (requested, actual)


def test_stage_distance_matches_the_shared_order() -> None:
    # 阶段锚点排序：精确命中 0，越早的阶段越大；`dating` 允许借用恋爱前阶段。
    assert sample_stage_distance({"conditions": {"relationshipStage": "dating"}}, "dating") == 0
    assert sample_stage_distance({"conditions": {"relationshipStage": "close"}}, "dating") == 1
    assert sample_stage_distance({"conditions": {"relationshipStage": "friend"}}, "dating") == 2
    assert (
        sample_stage_distance(
            {"conditions": {"relationshipStage": "acquaintance"}}, "dating"
        )
        == 3
    )
    assert sample_stage_distance({"conditions": {"relationshipStage": "stranger"}}, "dating") == 4
    # 请求 stranger 时只有 stranger 命中
    assert sample_stage_distance({"conditions": {"relationshipStage": "friend"}}, "stranger") is None
    # parent 请求：married 是唯一可用来源，与精确命中同级；更早阶段不适用
    assert sample_stage_distance({"conditions": {"relationshipStage": "married"}}, "parent") == 0
    assert sample_stage_distance({"conditions": {"relationshipStage": "parent"}}, "parent") == 0
    assert sample_stage_distance({"conditions": {"relationshipStage": "close"}}, "parent") is None


def test_stage_specificity_is_zero_for_the_current_stage() -> None:
    # 检索侧排序：精确命中 0、无阶段 1、更早阶段每远一档加 2。
    assert sample_stage_specificity({"conditions": {"relationshipStage": "friend"}}, "friend") == 0
    assert sample_stage_specificity({}, "friend") == 1
    assert (
        sample_stage_specificity(
            {"conditions": {"relationshipStage": "acquaintance"}}, "friend"
        )
        == 3
    )
    assert sample_stage_specificity({"conditions": {"relationshipStage": "close"}}, "friend") == 1


def test_parent_requests_rank_married_samples_first() -> None:
    # 样本域里没有 parent 标注（它是「与玩家有孩子」的关系状态），所以
    # `married` 是「有孩子」阶段唯一可用的对白来源，与精确命中同级。
    assert sample_stage_specificity({"conditions": {"relationshipStage": "married"}}, "parent") == 0
    assert sample_stage_specificity({"conditions": {"relationshipStage": "parent"}}, "parent") == 0
    # 更早阶段不是 parent 的可用来源——在权威顺序里 close 与 married 之间
    # 还隔着 dating 一档，不是相邻阶段。
    assert sample_stage_specificity({"conditions": {"relationshipStage": "close"}}, "parent") == 1


def test_parent_requests_accept_married_only() -> None:
    married = {"conditions": {"relationshipStage": "married"}}
    close = {"conditions": {"relationshipStage": "close"}}

    for policy in ("parent_widens", "at_most_present"):
        assert stage_hint_applies(married, "parent", policy=policy) is True, policy
        assert stage_hint_applies(close, "parent", policy=policy) is False, policy


def test_stranger_is_never_widened() -> None:
    # `stranger` 是排序表的起点：`at_most_present` 对它不产生任何宽放。
    assert stage_hint_applies(
        {"conditions": {"relationshipStage": "close"}}, "stranger", policy="at_most_present"
    ) is False
    assert stage_hint_applies(
        {"conditions": {"relationshipStage": "stranger"}}, "stranger", policy="at_most_present"
    ) is True


def test_stranger_samples_need_an_explicit_opt_in() -> None:
    # 检索侧头一次尝试**排除** stranger 原文（避免角色在朋友阶段退回无心级
    # 初识寒暄），只有明确的「借用更早阶段」回退才放开——`include_stranger`
    # 就是这个开关，而不是两处各写一遍判断。它只对 `at_most_present` 有意义：
    # `parent_widens` 仍然只认 married / parent。
    sample = {"conditions": {"relationshipStage": "stranger"}}

    assert stage_hint_applies(sample, "friend", policy="at_most_present") is False
    assert (
        stage_hint_applies(
            sample, "friend", policy="at_most_present", include_stranger=True
        )
        is True
    )
    assert (
        stage_hint_applies(
            sample, "friend", policy="parent_widens", include_stranger=True
        )
        is False
    )
    # 请求本身就是 stranger 时，stranger 原文当然适用。
    assert stage_hint_applies(sample, "stranger", policy="at_most_present") is True
