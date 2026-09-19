"""`evidence` 里“这条对白能不能当证据”的四条判定。

它们决定**哪些对白能进 Prompt 的证据窗口**——判错了就是坏证据静默进 Prompt：
把 `*动作*`／`%旁白`／控制标记当成台词，或者让高好感对白泄漏到陌生阶段。
此前没有专门的测试文件。

三条最精妙的规则（都由探针实测确认，不是读代码猜的）：

- **NPC 前缀只有在与 `sourceKey` 不一致时才算残留**：`"Abigail1 你好"` 配 key `Abigail1`
  是合法的自家前缀，配 `Shane1` 才是解包时混入的脏数据。
- **`old` 要作为独立段才算**：`old_dialogue`／`dialogue_old`／`dialogue-old` 命中，
  而 `older`／`gold` 不命中。
- **稳定语气锚点只接受不带数字的星期键**：`mon` 通过，`mon4`／`mon8` 被拒——
  后者是高好感对白，不能泄漏到陌生阶段。

另外记一条实测结论：**`evidenceKind` 才是权威判据，键名只是辅助**。例如
`{"evidenceKind": "runtime_dialogue"}` 即使配上一个看起来“特殊”的键也会无条件通过，
因为运行时样本的额外条件由运行时归属另行处理。
"""

from __future__ import annotations

import pytest

from stardew_ai_bridge.evidence import (
    has_dialogue_control_residue,
    has_dialogue_source_residue,
    is_model_evidence_record,
    is_stable_voice_evidence_record,
)


def _record(
    key: str,
    text: object = "今天天气不错",
    kind: str = "dialogue",
    path: str = "characters.json",
) -> dict[str, object]:
    return {"sourceKey": key, "text": text, "evidenceKind": kind, "sourcePath": path}


# --- has_dialogue_control_residue -------------------------------------------


@pytest.mark.parametrize("value", ["今天天气不错", "", "   ", None, 42, ["x"]])
def test_plain_text_has_no_control_residue(value: object) -> None:
    # 注意空白串**不算**残留——它是空内容，不是控制标记。
    assert has_dialogue_control_residue(value) is False


@pytest.mark.parametrize(
    "value",
    ["她笑了笑 *微笑*", "%旁白", "前文 %旁白", "（笑了笑）说"],
)
def test_action_and_narration_markers_are_detected(value: str) -> None:
    assert has_dialogue_control_residue(value) is True


# --- has_dialogue_source_residue --------------------------------------------


def test_own_npc_prefix_is_not_residue() -> None:
    # 文本前缀与 sourceKey 一致 → 这是合法的自家前缀，不是解包混入的脏数据。
    assert has_dialogue_source_residue(_record("Abigail1", "Abigail1 你好啊")) is False


def test_foreign_npc_prefix_is_residue() -> None:
    assert has_dialogue_source_residue(_record("Shane1", "Abigail1 你好啊")) is True


def test_numeric_prefix_is_residue() -> None:
    assert has_dialogue_source_residue(_record("Mon1", "12 你好")) is True


@pytest.mark.parametrize("key", ["old_dialogue", "dialogue_old", "dialogue-old", "Old"])
def test_old_marker_as_a_standalone_segment_is_residue(key: str) -> None:
    assert has_dialogue_source_residue(_record(key)) is True


@pytest.mark.parametrize("key", ["older", "gold", "holder"])
def test_old_inside_a_longer_word_is_not_residue(key: str) -> None:
    # 边界规则：`old` 必须是独立的一段（开头/结尾或被 `_`/`-` 包住）。
    assert has_dialogue_source_residue(_record(key)) is False


def test_non_string_text_still_checks_the_key_and_path() -> None:
    assert has_dialogue_source_residue(_record("old_dialogue", text=None)) is True
    assert has_dialogue_source_residue(_record("Mon1", text=None)) is False


# --- is_stable_voice_evidence_record ----------------------------------------


@pytest.mark.parametrize("key", ["mon", "Mon", "introduction"])
def test_unconditional_keys_can_be_stable_voice_anchors(key: str) -> None:
    assert is_stable_voice_evidence_record(_record(key)) is True


@pytest.mark.parametrize("key", ["mon4", "mon8", "tue10"])
def test_numbered_weekday_keys_are_rejected_as_stable_anchors(key: str) -> None:
    # 这些是高好感对白，只能留在带阶段的检索里，不能泄漏到陌生阶段。
    assert is_stable_voice_evidence_record(_record(key)) is False


@pytest.mark.parametrize("key", ["gift_like", "spring_mon", "Mon_2"])
def test_compound_keys_with_underscores_are_rejected(key: str) -> None:
    # 带下划线的复合键通常是地点、事件或分支对白。
    assert is_stable_voice_evidence_record(_record(key)) is False


@pytest.mark.parametrize("kind", ["marriage_dialogue", "roommate_dialogue"])
def test_marriage_and_roommate_samples_are_never_stable_anchors(kind: str) -> None:
    assert is_stable_voice_evidence_record(_record("mon", kind=kind)) is False


def test_only_the_fallback_branch_checks_text_residue() -> None:
    # 实测发现的一处**不一致**：`mon`／`introduction` 这类键会**提前返回**，
    # 不再检查 text 的控制残留；只有走到最后那行的普通键才查。
    #
    # 实际影响为零——索引构建阶段（`profile_index` 里三处 `has_dialogue_control_residue`）
    # 已经过滤过文本。写在这里是为了避免误以为这里是双重防护。
    dirty = "她笑了笑 *微笑*"

    assert is_stable_voice_evidence_record(_record("mon", text=dirty)) is True
    assert is_stable_voice_evidence_record(_record("introduction", text=dirty)) is True
    assert is_stable_voice_evidence_record(_record("greeting", text=dirty)) is False


# --- is_model_evidence_record -----------------------------------------------


@pytest.mark.parametrize(
    "kind",
    ["runtime_dialogue", "marriage_dialogue", "roommate_dialogue", "event_dialogue"],
)
def test_special_evidence_kinds_pass_unconditionally(kind: str) -> None:
    # kind 是权威判据：这些样本的额外条件（运行时归属、关系阶段、completedEventIds）
    # 由后续检索处理，不能在索引构建阶段就丢掉。
    assert is_model_evidence_record(_record("MarriageDialogue", kind=kind)) is True


def test_event_paths_are_rejected_for_plain_dialogue() -> None:
    assert is_model_evidence_record(_record("Mon1", path="events/spring13.json")) is False
    assert is_model_evidence_record(_record("Mon1", path="code/Characters.json")) is False


def test_source_residue_beats_everything() -> None:
    # 无论 kind 是什么，脏数据都不能进证据窗口。
    assert is_model_evidence_record(_record("old_dialogue", kind="event_dialogue")) is False


def test_plain_daily_dialogue_is_accepted() -> None:
    assert is_model_evidence_record(_record("Mon1")) is True
