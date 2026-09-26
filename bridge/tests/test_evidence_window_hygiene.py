# -*- coding: utf-8 -*-
"""钉住「进入模型证据窗口的素材卫生」的两条判据。

## ① 未解析的 i18n 引用必须被过滤（含**单花括号**形态）

现有 `_UNRESOLVED_I18N` 只认 Content Patcher 的**双花括号** `{{i18n:...}}`，
而别的 mod 会把占位符原样留在单花括号里：

    data/compatibility/Wellwick.json  key='Mon8'
    text='{i18n:Wellwick.dialogue.Mon8}'          ← 是键名，不是台词

它的 `evidenceKind='dialogue'`、`_dialogue_path_priority=3`（不降权）、
事件门控对它返回 True —— 于是**一路进到检索池发给模型**。
探针：`.tmp/retrieval-junk-audit.py`（实测 15 条，全部来自 Wellwick）。

## ② 当季键必须在窗口里有席位（婚后阶段的核心缺口）

实测（`.tmp/married-season-diagnose.py`，`limit=200`）：

| NPC     | married/summer 返回 | 其中当季键 |
|---------|--------------------|-----------|
| Sophia  | 94                 | **21**    |
| Olivia  | 106                | **22**    |
| Claire  | 87                 | **15**    |

素材一点都不缺。但 `_dialogue_key_priority` 里无季节的平日键（`Mon4`）返回
**0**、当季键（`summer_Mon4`）返回 **3**，于是窗口（`_SPEECH_EVIDENCE_CANDIDATES`）
一截就把季节键切光 —— 预览端点实测只剩 2–5 条，婚后角色的季节感因此明显弱于
close 阶段（close 有 18 条当季键）。游戏端还会传入已触发事件 ID 让事件台词
排到 -1，进一步压缩。

修法：当季键与平日键**同级**（都 0）。跨季键已被季节闸门（`sample_season !=
requested_season`）拒掉，池子里只剩「当季键」与「无季节键」，同级后由
`_evidence_order_key`（内容分档）自然混合，不破坏日常节奏。
"""

from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.profile_index import ProfileIndexStore

SOPHIA_DAILY = "vanilla:Characters/Dialogue/Sophia.json:{}"
WELLWICK = "vanilla:data/compatibility/Wellwick.json:Mon8"
BROKEN_I18N = "{i18n:Wellwick.dialogue.Mon8}"

#: 全部 ≥ `speech.VOICE_ANCHOR_MIN_TEXT`（6 字），确保被挡只可能因为判据本身。
PLAIN_TEXT = "这是平日里的普通对白内容，长度足够。"
SUMMER_TEXT = "夏天的日常对白内容，同样足够长。"
SUMMER_ONLY_TEXT = "夏天专属的季节台词内容在这里。"


def _sample(source_key: str, text: str, sample_id: str | None = None) -> dict:
    return {
        "sampleId": sample_id or SOPHIA_DAILY.format(source_key),
        "npcId": "Sophia",
        "sourceMod": "vanilla",
        "sourcePath": "Characters/Dialogue/Sophia.json",
        "sourceKey": source_key,
        "conditions": {"relationshipStage": "close"},
        "text": text,
    }


def _store(tmp_path: Path, samples: list[dict]) -> ProfileIndexStore:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {"schemaVersion": 2, "voiceCards": {}, "speechEvidence": samples},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ProfileIndexStore(index_path)


def test_single_brace_i18n_placeholder_is_filtered(tmp_path: Path) -> None:
    """单花括号的 `{i18n:...}` 是键名而非台词，不能进证据窗口。"""

    store = _store(
        tmp_path,
        [
            _sample("Mon4", PLAIN_TEXT),
            _sample(
                "Mon8",
                BROKEN_I18N,
                sample_id="vanilla:data/compatibility/Wellwick.json:Mon8",
            ),
        ],
    )

    got = store.speech_evidence("Sophia", ["vanilla"], limit=8)
    texts = [item["text"] for item in got]

    assert BROKEN_I18N not in texts, f"单花括号 i18n 占位符漏进窗口：{texts}"
    assert PLAIN_TEXT in texts, "正常对白被误伤"


def test_double_brace_i18n_still_filtered(tmp_path: Path) -> None:
    """Content Patcher 的双花括号形态不回归。"""

    store = _store(
        tmp_path,
        [_sample("Mon4", PLAIN_TEXT), _sample("Mon8", "{{i18n:Sophia.Mon8.Nope}}")],
    )

    texts = [item["text"] for item in store.speech_evidence("Sophia", ["vanilla"], limit=8)]

    assert "{{i18n:Sophia.Mon8.Nope}}" not in texts


def test_in_season_keys_reach_a_small_window(tmp_path: Path) -> None:
    """窗口被平日键占满时，当季键仍要有一席之地。

    这是婚后阶段季节感变弱的直接原因：素材够（21 条当季键），但排序把它们
    推到窗口之外。
    """

    # 每条文本必须不同：`_select_evidence_candidates` 会按文本去重，
    # 同文本会被压成一条，窗口就装得下季节键，判据反而测不到。
    weekdays = ("Mon4", "Tue4", "Wed4", "Thu4", "Fri4", "Sat4", "Sun4",
                "Mon6", "Tue6", "Wed6", "Thu6", "Fri6", "Sat6", "Sun6")
    samples = [
        _sample(key, f"这是平日里的第{index}条普通对白，每条都不一样。")
        for index, key in enumerate(weekdays)
    ]
    samples.append(_sample("summer_Mon4", SUMMER_TEXT))
    samples.append(_sample("summer_1", SUMMER_ONLY_TEXT))

    store = _store(tmp_path, samples)
    got = store.speech_evidence("Sophia", ["vanilla"], limit=4, season="summer")
    keys = [item["sourceKey"] for item in got]

    assert any(key.startswith("summer_") for key in keys), (
        f"限 4 条的窗口里一条当季键都没有，季节感无从谈起：{keys}"
    )


def test_other_season_keys_are_still_rejected(tmp_path: Path) -> None:
    """跨季键仍须被季节闸门拒掉，不因为排序同级而混入。"""

    store = _store(
        tmp_path,
        [
            _sample("Mon4", PLAIN_TEXT),
            _sample("winter_Mon4", "冬天的日常对白内容，也不短。"),
        ],
    )

    got = store.speech_evidence("Sophia", ["vanilla"], limit=8, season="summer")
    keys = [item["sourceKey"] for item in got]

    assert "winter_Mon4" not in keys, f"跨季键混进了夏天的窗口：{keys}"
    assert "Mon4" in keys, "无季节键应保留（它任何季节都成立）"


def test_plain_keys_still_present_when_no_season_given(tmp_path: Path) -> None:
    """不传季节时行为不变：平日键照常进窗口。"""

    store = _store(tmp_path, [_sample("Mon4", PLAIN_TEXT)])

    got = store.speech_evidence("Sophia", ["vanilla"], limit=8)

    assert [item["sourceKey"] for item in got] == ["Mon4"]
