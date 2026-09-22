"""「阶段条件在什么情况下适用」的边界。

## 这个文件为什么还在

它此前叫 `speech._stage_matches` 的直测——那个函数决定「某条原文样本能不能用在
当前关系阶段的请求里」，但**全仓没有生产调用方**（`profile_index` 与 `speech`
各自另有一套），10 条用例钉着一个已经断线的实现。

2026-09-20（语义层审计 P1 第 25 条）把三套判定收成 `dialogue_stage` 的一份实现
之后，这些用例**没有被删掉**：它们覆盖的边界（严格相等、婚后视同 parent、
`stranger` 不放宽、样本或请求缺阶段时不筛掉）正是新实现三种 policy 要负责的东西。
钉住的实现换成了权威实现，覆盖一条没少。

同时补上两处旧测试照不到、但统一后必须明确的边界：

- `married` 视同 `parent` 只在请求 `parent` 时成立，反向不成立；
- 只有 `at_most_present` 才允许更早阶段，`exact` 不放宽。

「阶段自身的读取与推断规则」在 `test_dialogue_stage_authority.py`，
「窗口长度」在 `test_dialogue_evidence_window.py`，这里只管适用性边界。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.dialogue_stage import sample_stage_hint, stage_hint_applies
from stardew_ai_bridge.speech import (
    derive_speech_profile,
    select_stage_voice_anchors,
)


def _sample(**overrides: object) -> dict[str, object]:
    """一条“会被阶段锚点接受”的真实样本。

    必要条件（见 `speech._stage_conditioned_voice_sample`）：
    `conditions.relationshipStage` 非空、`evidenceKind` 不是婚姻/室友对白、
    `sourcePath` 不在 events 目录、**`sourceKey` 要匹配日常键**（`Mon1` 这类），
    以及 strip 后 6 个字以上的 `text`。有了它，下面几条断言才不是空转。
    """

    base: dict[str, object] = {
        "sampleId": "s1",
        "sourceKey": "Mon1",
        "text": "今天天气不错呢",
        "conditions": {"relationshipStage": "married"},
        "evidenceKind": "dialogue",
        "sourcePath": "assets/dialogue.json",
    }
    base.update(overrides)
    return base


def _samples(count: int) -> list[dict[str, object]]:
    return [
        _sample(sampleId=f"s{index}", text=f"今天天气真好呀第{index}句")
        for index in range(1, count + 1)
    ]


# --- 适用性：严格相等 + 婚后视同 parent -------------------------------------


@pytest.mark.parametrize(
    ("stage", "requested", "expected"),
    [
        # 婚后与 parent 是同一段婚姻关系的两种状态，互相命中；
        # 但恋爱不等于婚姻，反向不成立。
        ("married", "parent", True),
        ("parent", "parent", True),
        ("parent", "married", True),
        ("dating", "married", False),
        ("married", "married", True),
        # 大小写与空白会被归一化
        ("  Married ", "married", True),
        ("FRIEND", "friend", True),
        # 阶段不符时筛掉
        ("friend", "married", False),
        ("friend", "parent", False),
    ],
)
def test_parent_widening_applies_only_when_parent_is_requested(
    stage: str, requested: str, expected: bool
) -> None:
    sample = {"conditions": {"relationshipStage": stage}}

    assert stage_hint_applies(sample, requested, policy="parent_widens") is expected


@pytest.mark.parametrize(
    ("stage", "requested", "expected"),
    [
        # 婚后请求同样接受更早阶段的日常对白：这是 `allow_lower_stage`
        # 的原意——婚后可以用朋友期的口语节奏补 few-shot，不退回陌生期腔。
        ("friend", "married", True),
        ("close", "dating", True),  # 只有 at_most_present 才借用更早阶段
        ("stranger", "acquaintance", False),  # 默认不回退到无心级初识对白
        ("close", "stranger", False),  # stranger 是排序表起点，不放宽
        ("dating", "married", True),  # 恋爱期原文比陌生期介绍句更贴近婚后语气
        # 但「请求 parent」只认已婚原文：parent 的来源只有它。
        ("close", "parent", False),
        ("married", "parent", True),
    ],
)
def test_only_at_most_present_borrows_earlier_stages(
    stage: str, requested: str, expected: bool
) -> None:
    sample = {"conditions": {"relationshipStage": stage}}

    assert stage_hint_applies(sample, requested, policy="at_most_present") is expected
    if not expected:
        assert stage_hint_applies(sample, requested, policy="exact") is False


def test_stranger_samples_come_back_only_through_the_explicit_fallback() -> None:
    # 「借用更早阶段」的回退（`allow_lower_stage=True`）才把 stranger 算进来；
    # 这是 profile_index 检索侧的两级尝试，不是两套判定。
    sample = {"conditions": {"relationshipStage": "stranger"}}

    assert (
        stage_hint_applies(sample, "friend", policy="at_most_present")
        is False
    )
    assert (
        stage_hint_applies(
            sample, "friend", policy="at_most_present", include_stranger=True
        )
        is True
    )


def test_exact_never_widens() -> None:
    sample = {"conditions": {"relationshipStage": "married"}}

    assert stage_hint_applies(sample, "married", policy="exact") is True
    assert stage_hint_applies(sample, "parent", policy="exact") is False
    assert stage_hint_applies(sample, "dating", policy="exact") is False


# --- 缺条件一律保留 ---------------------------------------------------------


@pytest.mark.parametrize("policy", ["exact", "at_most_present", "parent_widens"])
def test_missing_stage_on_either_side_keeps_the_sample(policy: str) -> None:
    # 样本没写阶段，或这次请求不指定阶段时，都不应该把样本筛掉。
    assert stage_hint_applies({"conditions": {}}, "married", policy=policy) is True
    assert (
        stage_hint_applies(
            {"conditions": {"relationshipStage": "married"}}, "", policy=policy
        )
        is True
    )
    assert (
        stage_hint_applies(
            {"conditions": {"relationshipStage": None}}, "parent", policy=policy
        )
        is True
    )


@pytest.mark.parametrize("policy", ["exact", "at_most_present", "parent_widens"])
def test_missing_or_malformed_conditions_keep_the_sample(policy: str) -> None:
    assert stage_hint_applies({}, "married", policy=policy) is True
    assert stage_hint_applies({"conditions": "married"}, "married", policy=policy) is True


def test_a_non_string_stage_is_treated_as_missing() -> None:
    assert sample_stage_hint({"conditions": {"relationshipStage": 42}}) == ""
    assert stage_hint_applies({"conditions": {"relationshipStage": 42}}, "married") is True


# --- 锚点选择仍然走同一套适用性 ---------------------------------------------


def test_select_stage_voice_anchors_returns_nothing_without_a_requested_stage() -> None:
    # 刻意用**无阶段条件**的样本：这样一旦把实现里的 `if not requested_stage: return []`
    # 提前返回删掉，它们就会作为回退被采纳、断言立刻失败。
    # （若用带阶段样本，删掉提前返回后会被下游的阶段过滤掉，测试反而抓不住。）
    plain = [
        _sample(conditions={}),
        _sample(sampleId="s2", conditions={}, text="另一句没有阶段的闲聊"),
    ]

    assert select_stage_voice_anchors(plain, "Shane", "   ") == []
    assert select_stage_voice_anchors(plain, "Shane", "") == []


def test_select_stage_voice_anchors_returns_nothing_when_count_is_zero_or_negative() -> None:
    samples = _samples(5)

    assert select_stage_voice_anchors(samples, "Shane", "married", max_count=0) == []
    assert select_stage_voice_anchors(samples, "Shane", "married", max_count=-3) == []


def test_select_stage_voice_anchors_tolerates_a_non_numeric_max_count() -> None:
    # 非法值会**回落到默认上限 8**，因此这里应当拿到全部 5 条——而不是空列表。
    # 断言 `== []` 恰恰证明不了“回落”，那正是这条测试原先的毛病（恒真）。
    samples = _samples(5)

    assert len(select_stage_voice_anchors(samples, "Shane", "married", max_count="oops")) == 5
    assert len(select_stage_voice_anchors(samples, "Shane", "married", max_count=None)) == 5
    # 对照：显式给 3 会被截断到 3，说明上面的 5 来自“默认上限”而非“忽略参数”。
    assert len(select_stage_voice_anchors(samples, "Shane", "married", max_count=3)) == 3


def test_select_stage_voice_anchors_prefers_staged_samples_over_unconditioned_ones() -> None:
    # 队列里**存在**带阶段样本时，无阶段样本不得抢占窗口。
    staged = _sample(sampleId="staged")
    plain = _sample(sampleId="plain", conditions={}, text="一句没有阶段条件的闲聊")

    anchors = select_stage_voice_anchors([staged, plain], "Shane", "married")

    assert [item["sampleId"] for item in anchors] == ["staged"]


def test_select_stage_voice_anchors_falls_back_to_unconditioned_samples() -> None:
    # 反过来：队列里一条带阶段样本都没有时，无阶段样本**会**作为回退被采用——这是设计意图。
    # （我最初把这条断言写成了“一律忽略”，被测试当场纠正。）
    anchors = select_stage_voice_anchors([_sample(conditions={})], "Shane", "married")

    assert [item["sampleId"] for item in anchors] == ["s1"]


def test_select_stage_voice_anchors_borrows_earlier_stages_only_when_the_window_is_short() -> None:
    """2026-09-22（用户拍板走 B）：**整级回退**改成**候选不足时补足**。

    口径变化：以前是"有精确阶段样本就绝不看更早阶段"（哪怕窗口里只有 1 条），
    现在是"窗口没填满就借更早阶段的原文"。
    关键区别在**数量**——够满就不借，不足才借。

    起因：Sophia 的 `friend` 档索引里**总共只有 2 条**阶段原文，
    且两条都落在布料/面料，整个语气窗口被同一面占满。
    """

    exact = _sample(sampleId="exact", conditions={"relationshipStage": "dating"})
    earlier = _sample(sampleId="earlier", conditions={"relationshipStage": "friend"})

    # 窗口够满（max_count=1）→ 更早阶段不进入窗口
    assert [
        item["sampleId"]
        for item in select_stage_voice_anchors(
            [earlier, exact], "Sophia", "dating", max_count=1
        )
    ] == ["exact"]

    # 窗口不满（max_count=8）→ 更早阶段补进来（精确阶段仍排在前面）
    assert [
        item["sampleId"]
        for item in select_stage_voice_anchors(
            [earlier, exact], "Sophia", "dating", max_count=8
        )
    ] == ["exact", "earlier"]


def test_top_up_never_borrows_later_stages() -> None:
    """补足只借**更早**阶段：恋爱档不得拿婚后原文。"""

    exact = _sample(sampleId="exact", conditions={"relationshipStage": "friend"})
    later = _sample(sampleId="later", conditions={"relationshipStage": "married"})

    anchors = select_stage_voice_anchors([exact, later], "Sophia", "friend", max_count=8)

    assert [item["sampleId"] for item in anchors] == ["exact"]


def test_top_up_excludes_event_dialogue_keys() -> None:
    """补足只接受日常对白键（`_anchor_category != "other"`）。

    实测踩到：没有这道闸时补进来的是**事件对白**——sourceKey 形如
    `3691380/f Scarlett 125/t 600 1800/w sunny/…`，那是角色在事件里**对别人**
    说的话（"加油，斯嘉丽！"），把 stranger 档原有的 4 条锚点挤掉 3 条，
    **比不补更差**。
    """

    exact = _sample(sampleId="exact", conditions={"relationshipStage": "friend"})
    event = _sample(
        sampleId="event",
        sourceKey="3691380/f Scarlett 125/t 600 1800/w sunny/z spring/z summer",
        conditions={"relationshipStage": "acquaintance"},
    )

    anchors = select_stage_voice_anchors([exact, event], "Sophia", "friend", max_count=8)

    assert [item["sampleId"] for item in anchors] == ["exact"]


def test_top_up_respects_max_count() -> None:
    """上限由调用方的 `max_count` 决定，补足不会越过它。"""

    exact = _sample(sampleId="exact", conditions={"relationshipStage": "friend"})
    earlier = [
        _sample(
            sampleId=f"earlier{index}",
            sourceKey=f"Tue{index}",
            text=f"以前那些日常闲聊第{index}句",
            conditions={"relationshipStage": "acquaintance"},
        )
        for index in range(1, 6)
    ]

    anchors = select_stage_voice_anchors(
        [exact, *earlier], "Sophia", "friend", max_count=3
    )

    assert len(anchors) == 3
    assert anchors[0]["sampleId"] == "exact"


def test_top_up_leaves_a_full_window_untouched() -> None:
    """窗口本来就满时，补足逻辑一步都不许动它（回归保护）。"""

    full = [
        _sample(
            sampleId=f"exact{index}",
            sourceKey=f"Mon{index}",
            text=f"恋爱阶段的日常第{index}句",
            conditions={"relationshipStage": "dating"},
        )
        for index in range(1, 9)
    ]
    earlier = [
        _sample(
            sampleId="earlier",
            sourceKey="Tue1",
            text="朋友阶段的日常一句话",
            conditions={"relationshipStage": "friend"},
        )
    ]

    anchors = select_stage_voice_anchors(
        [*full, *earlier], "Sophia", "dating", max_count=8
    )

    assert [item["sampleId"] for item in anchors] == [f"exact{i}" for i in range(1, 9)]


def test_select_stage_voice_anchors_borrows_earlier_stage_when_nothing_exact_exists() -> None:
    earlier = _sample(sampleId="earlier", conditions={"relationshipStage": "friend"})

    anchors = select_stage_voice_anchors([earlier], "Sophia", "dating")

    assert [item["sampleId"] for item in anchors] == ["earlier"]


# --- 生成入口的其余容错 -----------------------------------------------------


def test_derive_speech_profile_tolerates_non_numeric_limits() -> None:
    # max_evidence / max_anchors 同样要能容忍非法输入（各自回落到默认上限）。
    profile = derive_speech_profile("Shane", _samples(3), max_evidence="oops", max_anchors=None)

    # 断言“返回的键集合”而不是恒真的 `assert profile`——键变了才算契约变化。
    assert set(profile) == {
        "npcId",
        "features",
        "topicHints",
        "evidenceRefs",
        "voiceAnchors",
    }
    assert profile["npcId"] == "Shane"


def test_derive_speech_profile_accepts_zero_and_negative_limits() -> None:
    samples = _samples(3)

    zero = derive_speech_profile("Shane", samples, max_evidence=0, max_anchors=0)
    assert zero["evidenceRefs"] == []
    assert zero["voiceAnchors"] == []

    negative = derive_speech_profile("Shane", samples, max_evidence=-1, max_anchors=-5)
    assert negative["evidenceRefs"] == []
    assert negative["voiceAnchors"] == []
