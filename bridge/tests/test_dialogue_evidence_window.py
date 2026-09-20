"""对白证据长度窗口的单一权威定义（语义层审计 P1 第 26 条）。

## 背景

同一件「什么长度的原文锚点合格」，此前在三处各写一遍：

- 生成侧（`speech`）：6–80 字才收进 `voiceAnchors`；
- 群聊声线卡（`prompts.build_group_voice_cards`）：`len(text) > 60` 直接丢弃；
- 私聊证据文本（`prompts._dialogue_evidence_text`）：截断到 100 字。

于是 **61–80 字之间完全合格的锚点在群聊侧被静默丢弃**——同一份索引，
单聊和群聊看到不同的角色声音。实测真实索引
（`vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json`）：
622 条 `voiceAnchors` 里 34 条落在 61–80 字，群聊侧不可见。

## 本次建立的语义

窗口只有一份实现 `speech.voice_anchor_text_fits`（6–80，比较 strip 之后的长度），
三个调用点都引用它：

- 生成侧 `_voice_anchor_candidates` / `select_stage_voice_anchors`；
- 群聊声线卡 `build_group_voice_cards`；
- 私聊声线卡 `_safe_voice_card` 与自然纹理卡 `_build_natural_role_texture_card`。

窗口之外的锚点**一律丢弃**，不裁剪成半句——锚点会被模型当作「角色说过的话」，
半截句子比长句更容易被逐字照搬成病句。下限只对生成侧与群聊声线卡生效（6 字），
自然纹理卡保持它历史上的口径（只排除空串）。
"""

from __future__ import annotations

from typing import Any

import pytest

from stardew_ai_bridge import prompts
from stardew_ai_bridge.speech import (
    VOICE_ANCHOR_MAX_TEXT,
    VOICE_ANCHOR_MIN_TEXT,
    select_stage_voice_anchors,
    voice_anchor_text_fits,
)


class _Builder:
    """最小 context_builder 替身（与 `test_group_voice_cards_edges` 同形）。"""

    def __init__(self, context: Any) -> None:
        self._context = context

    def build(self, payload: dict[str, Any]) -> Any:
        return self._context


def _length_text(length: int) -> str:
    """构造恰好 `length` 个字符的对白（不含会被清理掉的控制字符）。"""

    if length <= 0:
        return ""
    assert length >= 2
    return ("ab" * length)[:length]


def _group_anchors(*texts: str) -> list[str]:
    builder = _Builder(
        {
            "npcIdentity": {"voiceStyle": {"tone": "温和"}},
            "voiceCard": {"voiceAnchors": [{"text": text} for text in texts]},
        }
    )
    card = prompts.build_group_voice_cards(builder, [{"npcId": "Shane"}])
    return card.get("shane", {}).get("voiceAnchors", [])


# --- 窗口本身 ---------------------------------------------------------------


def test_the_window_has_exactly_one_definition() -> None:
    assert VOICE_ANCHOR_MIN_TEXT == 6
    assert VOICE_ANCHOR_MAX_TEXT == 80


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (0, False),
        (5, False),
        (6, True),
        (60, True),
        (61, True),  # 旧群聊阈值之外、生成窗口之内
        (80, True),
        (81, False),
    ],
)
def test_window_predicate_boundaries(length: int, expected: bool) -> None:
    assert voice_anchor_text_fits(_length_text(length)) is expected


def test_window_predicate_measures_the_cleaned_text() -> None:
    # 生成侧是「先 strip、再比长度」；判定函数必须同源，否则同一个字符串
    # 在两处得到不同答案（这正是本次要消除的漂移）。
    assert voice_anchor_text_fits("  " + _length_text(6) + "  ") is True


def test_the_lower_bound_can_be_disabled_per_call_site() -> None:
    # 自然纹理卡历史上接受很短的原文碎片，本次不改它的口径。
    assert voice_anchor_text_fits("好的。", min_length=0) is True
    assert voice_anchor_text_fits("好的。") is False


# --- 生成侧仍然使用同一窗口 -------------------------------------------------


def test_generation_side_uses_the_same_window() -> None:
    def sample(sample_id: str, text: str) -> dict[str, Any]:
        return {
            "sampleId": sample_id,
            "sourceKey": "Mon1",
            "sourcePath": "characters.json",
            "text": text,
            "evidenceKind": "dialogue",
            "conditions": {"relationshipStage": "married"},
        }

    anchors = select_stage_voice_anchors(
        [
            sample("too-short", _length_text(5)),
            sample("inside", _length_text(61)),
            sample("too-long", _length_text(81)),
        ],
        "Shane",
        "married",
    )

    assert [item["sampleId"] for item in anchors] == ["inside"]


# --- 群聊声线卡：61–80 字的锚点不再被丢弃 -----------------------------------


def test_group_voice_card_keeps_a_61_to_80_character_anchor() -> None:
    # 这一条是本次修复的核心：旧实现 `len(text) > 60` 会在这里静默丢弃。
    assert _group_anchors(_length_text(61)) == [_length_text(61)]


def test_group_voice_card_still_drops_text_outside_the_window() -> None:
    assert _group_anchors(_length_text(81), "短", _length_text(40)) == [_length_text(40)]


def test_group_voice_card_anchor_count_is_still_capped() -> None:
    assert _group_anchors(_length_text(70), _length_text(71), _length_text(72)) == [
        _length_text(70),
        _length_text(71),
    ]


# --- 私聊：同一窗口，同样是丢弃而不是裁剪 -----------------------------------


def test_private_voice_card_drops_an_anchor_outside_the_window() -> None:
    # 旧实现把它截断到 100 字——同一段文本在群聊 80、私聊 100，两处口径不同。
    card = prompts._safe_voice_card({"voiceAnchors": [{"text": _length_text(120)}]})

    assert "voiceAnchors" not in card


def test_private_voice_card_keeps_in_window_text() -> None:
    card = prompts._safe_voice_card({"voiceAnchors": [{"text": _length_text(80)}]})

    assert card["voiceAnchors"][0]["text"] == _length_text(80)


def test_private_voice_card_keeps_a_short_fragment() -> None:
    # 私聊路径一直接受很短的语气碎片；6 字下限只对生成侧与群聊声线卡生效，
    # 上限 80 才是三条路径共用的那一个。
    card = prompts._safe_voice_card({"voiceAnchors": [{"text": "好的。"}]})

    assert card["voiceAnchors"][0]["text"] == "好的。"


def test_private_natural_texture_anchor_shares_the_upper_bound() -> None:
    card = prompts._build_natural_role_texture_card(
        {"npcId": "Shane", "voiceStyle": {}},
        voice_card={"voiceAnchors": [{"text": _length_text(120)}]},
    )

    assert "voiceAnchors" not in card


def test_private_natural_texture_keeps_a_short_fragment() -> None:
    # 自然纹理卡的下限保持历史口径：短碎片仍然可用。
    card = prompts._build_natural_role_texture_card(
        {"npcId": "Shane", "voiceStyle": {}},
        voice_card={"voiceAnchors": [{"text": "好的。"}]},
    )

    assert card["voiceAnchors"][0]["text"] == "好的。"
