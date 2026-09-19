"""`speech._stage_matches` 的直测。

这个函数决定"某个原文样本能不能用在当前关系阶段的请求里"，
此前整段没有覆盖。它的两条规则值得钉住：婚后视同 parent，
以及样本或请求缺阶段时**不筛掉**样本。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.speech import (
    _stage_matches,
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


@pytest.mark.parametrize(
    ("stage", "requested", "expected"),
    [
        # 婚后同时满足 parent 与 married
        ("married", "parent", True),
        ("parent", "parent", True),
        ("parent", "married", False),
        ("married", "married", True),
        # 大小写与空白会被归一化
        ("  Married ", "married", True),
        ("FRIEND", "friend", True),
        # 阶段不符时筛掉
        ("friend", "married", False),
        ("friend", "parent", False),
    ],
)
def test_stage_matches_normalises_and_treats_married_as_parent(
    stage: str, requested: str, expected: bool
) -> None:
    sample = {"conditions": {"relationshipStage": stage}}

    assert _stage_matches(sample, requested) is expected


def test_missing_stage_on_either_side_keeps_the_sample() -> None:
    # 样本没写阶段，或这次请求不指定阶段时，都不应该把样本筛掉。
    assert _stage_matches({"conditions": {}}, "married") is True
    assert _stage_matches({"conditions": {"relationshipStage": "married"}}, "") is True
    assert _stage_matches({"conditions": {"relationshipStage": None}}, "parent") is True


def test_missing_or_malformed_conditions_keep_the_sample() -> None:
    assert _stage_matches({}, "married") is True
    assert _stage_matches({"conditions": "married"}, "married") is True


def test_select_stage_voice_anchors_returns_nothing_without_a_requested_stage() -> None:
    # 刻意用**无阶段条件**的样本：这样一旦把实现里的 `if not requested_stage: return []`
    # 提前返回删掉，它们就会作为回退被采纳、断言立刻失败。
    # （若用带阶段样本，删掉提前返回后会被下游的 stage_distance 过滤掉，测试反而抓不住。）
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
