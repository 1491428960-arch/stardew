"""`build_group_voice_cards` 的群聊声线卡装配。

按**缺失行数**排序挑出来的（缺 7/38，比例高）。docstring 写明两条设计约束：

- “复用单 NPC 的 persona 与资料索引管线（不新写一套画像），只保留群聊真正需要的几项”；
- “**单个参与者取不到资料时跳过，不影响整场群聊**”。

而代码里还有一条注释值得钉住：

    只带短句锚点；长段关系对白会把群聊对白带成范文。

所以下面既测“取不到就跳过”，也测“长锚点被丢掉”。

**2026-09-20（P1 第 26 条）**：这里的阈值此前是独立写死的 `len(text) > 60`，
与生成侧 6–80 的窗口不一致，于是 61–80 字之间合格的锚点在群聊侧被静默丢弃。
现在两者共用同一个窗口，所以下面「长锚点被丢掉」用的样本必须**超过 80 字**
才仍然成立。
"""

from __future__ import annotations

from typing import Any

from stardew_ai_bridge.prompts import build_group_voice_cards


class _Builder:
    """最小 context_builder 替身：记录调用、可返回任意对象或抛异常。"""

    def __init__(self, context: Any) -> None:
        self._context = context
        self.calls: list[dict[str, Any]] = []

    def build(self, payload: dict[str, Any]) -> Any:
        self.calls.append(payload)
        if isinstance(self._context, Exception):
            raise self._context
        if callable(self._context):
            return self._context(payload)
        return self._context


def _context(**voice_style: Any) -> dict[str, Any]:
    return {"npcIdentity": {"voiceStyle": voice_style}}


# --- 跳过与容错 -------------------------------------------------------------


def test_non_mapping_participants_are_skipped() -> None:
    builder = _Builder(_context(tone="温和"))

    assert build_group_voice_cards(builder, ["not-a-mapping", 42, None]) == {}
    assert builder.calls == []  # 连 build 都不该调


def test_a_participant_without_an_npc_id_is_skipped() -> None:
    builder = _Builder(_context(tone="温和"))

    assert build_group_voice_cards(builder, [{"npcId": "   "}, {}]) == {}
    assert builder.calls == []


def test_a_failing_context_builder_does_not_break_the_others() -> None:
    # “单个参与者取不到资料时跳过，不影响整场群聊”。
    def per_participant(payload: dict[str, Any]) -> Any:
        if payload["npcId"] == "Shane":
            raise RuntimeError("索引炸了")
        return _context(tone="温和")

    builder = _Builder(per_participant)

    cards = build_group_voice_cards(builder, [{"npcId": "Shane"}, {"npcId": "Emily"}])

    assert set(cards) == {"emily"}


def test_a_non_mapping_context_is_skipped() -> None:
    assert build_group_voice_cards(_Builder("不是映射"), [{"npcId": "Shane"}]) == {}


def test_non_mapping_sub_sections_are_treated_as_empty() -> None:
    # identity / voiceStyle / voiceCard 结构意外时不该崩，只是没有内容。
    builder = _Builder({"npcIdentity": "x", "voiceCard": 42})

    assert build_group_voice_cards(builder, [{"npcId": "Shane"}]) == {}


# --- sourceMods 归一 --------------------------------------------------------


def test_source_mods_are_filtered_to_non_blank_strings() -> None:
    builder = _Builder(_context(tone="温和"))

    build_group_voice_cards(
        builder, [{"npcId": "Shane", "sourceMods": ["SVE", "", "  ", 42, "Vanilla"]}]
    )

    assert builder.calls[0]["sourceMods"] == ["SVE", "Vanilla"]


def test_source_mods_of_the_wrong_shape_become_empty() -> None:
    builder = _Builder(_context(tone="温和"))

    build_group_voice_cards(builder, [{"npcId": "Shane", "sourceMods": "SVE"}])

    assert builder.calls[0]["sourceMods"] == []


def test_the_snake_case_key_is_also_accepted() -> None:
    builder = _Builder(_context(tone="温和"))

    build_group_voice_cards(builder, [{"npc_id": "Shane", "source_mods": ["SVE"]}])

    assert builder.calls[0]["npcId"] == "Shane"
    assert builder.calls[0]["sourceMods"] == ["SVE"]


# --- 锚点筛选 ---------------------------------------------------------------


def _with_anchors(*texts: Any) -> dict[str, Any]:
    return {"voiceCard": {"voiceAnchors": [{"text": t} for t in texts]}}


def test_short_anchors_are_kept_and_long_ones_dropped() -> None:
    # 长样本要**超过 80 字**（生成侧窗口的上限）才应被丢弃；
    # 61–80 字是合格锚点，见 `test_dialogue_evidence_window.py`。
    builder = _Builder(_with_anchors("今天鸡舍那边挺忙的。", "很长的一句" * 20))

    cards = build_group_voice_cards(builder, [{"npcId": "Shane"}])

    assert cards["shane"]["voiceAnchors"] == ["今天鸡舍那边挺忙的。"]


def test_at_most_two_anchors_are_kept() -> None:
    builder = _Builder(_with_anchors("第一句台词。", "第二句台词。", "第三句台词。", "第四句台词。"))

    cards = build_group_voice_cards(builder, [{"npcId": "Shane"}])

    assert cards["shane"]["voiceAnchors"] == ["第一句台词。", "第二句台词。"]


def test_non_mapping_or_blank_anchors_are_ignored() -> None:
    builder = _Builder({"voiceCard": {"voiceAnchors": ["不是映射", {"text": "   "}, {"text": "好的，我知道了。"}]}})

    cards = build_group_voice_cards(builder, [{"npcId": "Shane"}])

    assert cards["shane"]["voiceAnchors"] == ["好的，我知道了。"]


def test_a_non_sequence_anchor_field_is_ignored() -> None:
    # 给一个 tone 让卡片非空——否则整个参与者会因为“卡片全空”被丢弃（见上面另一条测试）。
    # 我最初写这条时就踩了这个坑：只给 voiceAnchors 一个非序列值，结果 KeyError 'shane'。
    builder = _Builder(
        {"npcIdentity": {"voiceStyle": {"tone": "温和"}}, "voiceCard": {"voiceAnchors": "不是序列"}}
    )

    card = build_group_voice_cards(builder, [{"npcId": "Shane"}])["shane"]

    assert card == {"tone": "温和"}


# --- 卡片精简 ---------------------------------------------------------------


def test_empty_fields_are_dropped_from_the_card() -> None:
    builder = _Builder(_context(tone="温和"))

    card = build_group_voice_cards(builder, [{"npcId": "Shane"}])["shane"]

    # 只留下有内容的字段；空字符串与空列表都不出现
    assert card == {"tone": "温和"}


def test_a_participant_with_no_content_at_all_is_dropped() -> None:
    builder = _Builder({"npcIdentity": {"voiceStyle": {}}, "voiceCard": {}})

    assert build_group_voice_cards(builder, [{"npcId": "Shane"}]) == {}


def test_sentence_patterns_and_moves_are_capped_at_two() -> None:
    builder = _Builder(
        _context(
            tone="温和",
            sentencePattern=["一", "二", "三"],
            signatureMoves=["甲", "乙", "丙"],
        )
    )

    card = build_group_voice_cards(builder, [{"npcId": "Shane"}])["shane"]

    assert card["sentencePattern"] == ["一", "二"]
    assert card["signatureMoves"] == ["甲", "乙"]


def test_topic_hints_are_capped_at_three_and_must_be_strings() -> None:
    builder = _Builder({"voiceCard": {"topicHints": ["一", 42, "二", "三", "四"]}})

    card = build_group_voice_cards(builder, [{"npcId": "Shane"}])["shane"]

    assert card["topicHints"] == ["一", "二", "三"]


# --- 命名 -------------------------------------------------------------------


def test_the_card_key_is_case_folded() -> None:
    builder = _Builder(_context(tone="温和"))

    cards = build_group_voice_cards(builder, [{"npcId": "  Shane  "}])

    assert list(cards) == ["shane"]
