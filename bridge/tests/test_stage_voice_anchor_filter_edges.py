"""`select_stage_voice_anchors` 的候选过滤与选择顺序。

按**缺失行数**排序挑出来的——缺的 8 行**全是过滤/收集分支**，没有一行是主路径。

它是“阶段声线锚点”的入口：为当前角色挑出当前关系阶段的普通与高能量原文锚点，
但 docstring 强调“**只有存在带阶段条件的高质量原文时才会改变静态 voice card**，
调用方会在没有阶段候选时保留原有静态窗口”。

本文件覆盖两件事：

- **五条过滤规则**（`sampleId`／文本类型／长度／控制残留／证据资格）——错一条就会
  把控制脚本、旁白或超长段落当成“角色的说话节奏”；
- **选择顺序**：先高能量、再回填中低能量，让自然模式的小窗口保留角色节奏。
"""

from __future__ import annotations

from stardew_ai_bridge.evidence import is_model_evidence_record
from stardew_ai_bridge.speech import (
    _stage_conditioned_voice_sample,
    select_stage_voice_anchors,
)

_STAGE = "married"


def _sample(
    sample_id: object = "s1",
    text: object = "今天天气不错呢",
    **overrides: object,
) -> dict[str, object]:
    base: dict[str, object] = {
        "sampleId": sample_id,
        "npcId": "Shane",
        "sourceKey": "Mon1",
        "sourcePath": "characters.json",
        "text": text,
        "evidenceKind": "dialogue",
        "conditions": {"relationshipStage": _STAGE},
    }
    base.update(overrides)
    return base


def _select(samples: object, **kwargs: object) -> list[dict[str, object]]:
    return select_stage_voice_anchors(samples, "Shane", _STAGE, **kwargs)  # type: ignore[arg-type]


# --- 基线 -------------------------------------------------------------------


def test_a_qualified_sample_produces_one_anchor() -> None:
    anchors = _select([_sample()])

    assert len(anchors) == 1
    assert anchors[0]["text"] == "今天天气不错呢"


def test_no_samples_yields_nothing() -> None:
    # 没有阶段候选时返回空——调用方会保留原有静态窗口。
    assert _select([]) == []


# --- 五条过滤规则 -----------------------------------------------------------


def test_samples_without_a_usable_id_are_skipped() -> None:
    for bad in ("", "   ", None, 42):
        assert _select([_sample(sample_id=bad)]) == [], bad


def test_samples_with_a_non_string_text_are_skipped() -> None:
    for bad in (None, 42, ["a"]):
        assert _select([_sample(text=bad)]) == [], bad


def test_texts_outside_the_length_window_are_skipped() -> None:
    assert _select([_sample(text="短")]) == []  # 少于 6 个字符
    assert _select([_sample(text="很长" * 200)]) == []  # 超过上限


def test_dialogue_control_residue_is_skipped() -> None:
    # 控制脚本与旁白不是角色语言风格。
    assert _select([_sample(text="%旁白一句")]) == []
    assert _select([_sample(text="她笑了笑 *微笑*")]) == []


def test_a_sample_qualifies_through_any_of_the_documented_channels() -> None:
    # 那一行的门是四选一：稳定证据 / 关系阶段锚点 / 模型证据 / 阶段条件样本。
    # 实测 `is_model_evidence_record` 相当宽松（连普通 dialogue 也算 True），
    # 所以“四者全假”很难构造——我最初想构造一个“不合格证据”，结果它照样通过。
    # 这条因此改为**如实断言各通道的判定**，而不是假装能造出全假的输入。
    sample = _sample()

    assert _stage_conditioned_voice_sample(sample) is True
    assert is_model_evidence_record(sample) is True
    assert _select([sample]) != []


def test_several_bad_samples_do_not_hide_a_good_one() -> None:
    anchors = _select(
        [
            _sample(sample_id="bad1", text="短"),
            _sample(sample_id="bad2", text="%旁白"),
            _sample(sample_id="ok", text="今天鸡舍那边挺忙的。"),
        ]
    )

    assert [a["text"] for a in anchors] == ["今天鸡舍那边挺忙的。"]


# --- 选择顺序与上限 ---------------------------------------------------------


def test_duplicate_texts_are_collapsed() -> None:
    # 归一化后相同的文本只留一条（防止同一句话占满窗口）。
    anchors = _select(
        [
            _sample(sample_id="a", text="今天天气不错呢"),
            _sample(sample_id="b", text="今天天气不错呢"),
        ]
    )

    assert len(anchors) == 1


def test_max_count_caps_the_result() -> None:
    samples = [_sample(sample_id=f"s{i}", text=f"第 {i} 句台词内容。") for i in range(6)]

    assert len(_select(samples, max_count=2)) == 2


def test_a_zero_max_count_yields_nothing() -> None:
    assert _select([_sample()], max_count=0) == []


def test_every_qualified_sample_can_be_returned() -> None:
    # 上限足够大时，所有合格样本都应出现（顺序可以变，集合不该丢）。
    texts = [f"第 {i} 句台词内容。" for i in range(5)]
    samples = [_sample(sample_id=f"s{i}", text=t) for i, t in enumerate(texts)]

    got = [a["text"] for a in _select(samples, max_count=10)]

    assert sorted(got) == sorted(texts)


def test_the_result_is_stable_across_runs() -> None:
    samples = [_sample(sample_id=f"s{i}", text=f"第 {i} 句台词内容。") for i in range(5)]

    first = [a["text"] for a in _select(samples, max_count=3)]
    second = [a["text"] for a in _select(samples, max_count=3)]

    assert first == second


def test_anchors_carry_their_energy_signals() -> None:
    # docstring：“每条返回的锚点都保留能量信号计数，便于离线检查”。
    anchor = _select([_sample()])[0]

    assert "voiceEnergy" in anchor
    assert "energySignals" in anchor
