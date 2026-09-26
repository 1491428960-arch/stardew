# -*- coding: utf-8 -*-
"""钉住 `collect_stage_candidates` 的来源判据：**角色日常对白文件的全部已知形态
都要收，事件与兼容层文件仍要挡**。

## 背景（2026-09-27 零请求探针实测，索引 speechEvidence 11391 条）

带 `relationshipStage` 的样本 **3661** 条，其中 **1664** 条被
`"Characters/Dialogue/" not in sample_id` 挡掉 —— 而 **1525 条其实是角色日常对白**：
SVE 把人物对白放在 `assets/CharacterFiles/Dialogue/<NPC>/Dialogue.json`，
路径里不含 `Characters/Dialogue/`。

后果（被挡 / 通过）：Olivia 175/0、Victor 172/0、Sophia 163/0、Claire 136/0、
Lance 132/0、Apples 122/0、Scarlett 111/0、Susan 71/0、Andy 64/0、Morris 59/0、
Marlon 57/0、Morgan 51/0 —— **这些 SVE 角色的阶段锚点整批为空**，
`select_stage_voice_anchors` 拿不到候选，只能退回静态卡。

其中 553 条的 sourceKey **本来就够格**进「阶段专属」层（358 条 `季节_星期+数字`、
195 条 `星期+数字`），所以这不是"素材不够"，纯粹是路径判据挡错了。

探针：`.tmp/collect-stage-path-probe.py`、`.tmp/diag-stage-candidates.py`。

## 写夹具时的两个坑（都被实测踩到）

1. **sampleId 必须是 `mod:path:key` 三段**。既有夹具用裸字符串（`"calm"`、`"daily-0"`），
   冒号数 < 2 会走 "只在能确定来源时才排除" 那条，于是判据从来没被测到。
2. **文本长度必须 ≥ `speech.VOICE_ANCHOR_MIN_TEXT`（6 字）**，否则样本会因为
   "太短不能当锚点" 被丢掉 —— 那样事件样本会**假通过**（被挡的原因是长度而不是路径）。
   本文件所有文本都写成真实长度（16 字上下）。
"""

from __future__ import annotations

import json
from pathlib import Path

from stardew_ai_bridge.profile_index import ProfileIndexStore

#: SVE 的人物日常对白（本次要收的形态）
SVE_DAILY = (
    "FlashShifter.StardewValleyExpandedCP:"
    "assets/CharacterFiles/Dialogue/Sophia/Dialogue.json:Mon"
)
#: SVE 的婚后对白，同目录另一个文件名
SVE_MARRIAGE = (
    "FlashShifter.StardewValleyExpandedCP:"
    "assets/CharacterFiles/Dialogue/Sophia/MarriageDialogue.json:Tue4"
)
#: 原版 / CP 覆盖（既有行为，必须不回归）
VANILLA_DAILY = "vanilla:Characters/Dialogue/Sophia.json:Fri"
#: 事件台词：无法从 sourceKey 判断说话对象，必须继续挡
EVENT_LINE = (
    "FlashShifter.StardewValleyExpandedCP:Data/Events/Town.json:53/e 55"
)
#: 兼容层喊话键 / 节日脚本：不是角色日常口吻文件，必须继续挡
COMPAT_FILE = "Nom0ri.RomRas:data/compatibility/Juna.json:ReadyToRumble"
FESTIVAL_FILE = "FlashShifter.StardewValleyExpandedCP:code/Festivals/Summer.json:Sat6"

#: 全部 ≥ 6 字、带语气助词，确保「被挡」只可能因为路径判据。
TEXTS = {
    "sve_daily": "夏天真好啊，酒窖里的空气都是甜的。",
    "sve_marriage": "今天我把画具都收好了呢，孩子们没乱动。",
    "vanilla": "明天镇上有集市，你要不要一起去看看吧？",
    "event": "好了！大家安静吧！镇长有话要说了！",
    "compat": "兼容层喊话内容，这条不该进锚点呢。",
    "festival": "节日脚本台词呀，这条也不该进锚点。",
}


def _sample(sample_id: str, text: str, stage: str = "close") -> dict:
    return {
        "sampleId": sample_id,
        "npcId": "Sophia",
        "sourceMod": "FlashShifter.StardewValleyExpandedCP",
        "sourceKey": sample_id.rsplit(":", 1)[-1],
        "conditions": {"relationshipStage": stage},
        "text": text,
    }


def _store(tmp_path: Path, samples: list[dict]) -> ProfileIndexStore:
    index_path = tmp_path / "profile-index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "voiceCards": {
                    "Sophia": {
                        "npcId": "Sophia",
                        "voiceAnchors": [
                            {
                                "sampleId": "static",
                                "sourceMod": "vanilla",
                                "sourceKey": "Mon",
                                "text": "静态卡不该盖住阶段重选的结果。",
                            }
                        ],
                    }
                },
                "speechEvidence": samples,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ProfileIndexStore(index_path)


def test_stage_anchors_accept_sve_daily_dialogue_paths(tmp_path: Path) -> None:
    """SVE 的 `assets/CharacterFiles/Dialogue/<NPC>/*.json` 是角色日常对白，必须收。"""

    store = _store(
        tmp_path,
        [_sample(SVE_DAILY, TEXTS["sve_daily"])],
    )

    card = store.voice_card("Sophia", relationship_stage="close")
    ids = [item["sampleId"] for item in card["voiceAnchors"]]

    assert ids == [SVE_DAILY], f"SVE Dialogue.json 被误挡，实际锚点={ids}"


def test_sve_marriage_dialogue_path_is_accepted(tmp_path: Path) -> None:
    """同目录的 `MarriageDialogue.json` 同样是角色日常对白。"""

    store = _store(
        tmp_path,
        [_sample(SVE_MARRIAGE, TEXTS["sve_marriage"])],
    )

    card = store.voice_card("Sophia", relationship_stage="close")
    ids = [item["sampleId"] for item in card["voiceAnchors"]]

    assert ids == [SVE_MARRIAGE], f"SVE MarriageDialogue.json 被误挡，实际锚点={ids}"


def test_vanilla_dialogue_path_still_accepted(tmp_path: Path) -> None:
    """原版 `Characters/Dialogue/<NPC>.json` 不回归。"""

    store = _store(tmp_path, [_sample(VANILLA_DAILY, TEXTS["vanilla"])])

    card = store.voice_card("Sophia", relationship_stage="close")
    assert [item["sampleId"] for item in card["voiceAnchors"]] == [VANILLA_DAILY]


def test_stage_anchors_still_reject_events_and_compat_files(tmp_path: Path) -> None:
    """事件台词与兼容层文件仍要挡：它们的说话对象无法从 sourceKey 判断。

    既有注释记录过混入的代价：Lewis 的 8 条锚点里 5 条是错的
    （开场序列、在展览上对莉亚说的话、别的 mod 的喊话键）。
    这几条的文本都够长，所以「不在锚点里」只能是路径判据生效。
    """

    store = _store(
        tmp_path,
        [
            _sample(SVE_DAILY, TEXTS["sve_daily"]),
            _sample(EVENT_LINE, TEXTS["event"]),
            _sample(COMPAT_FILE, TEXTS["compat"]),
            _sample(FESTIVAL_FILE, TEXTS["festival"]),
        ],
    )

    card = store.voice_card("Sophia", relationship_stage="close")
    ids = {item["sampleId"] for item in card["voiceAnchors"]}

    assert SVE_DAILY in ids
    assert EVENT_LINE not in ids, "事件台词不该进阶段锚点"
    assert COMPAT_FILE not in ids, "兼容层文件不该进阶段锚点"
    assert FESTIVAL_FILE not in ids, "节日脚本不该进阶段锚点"


def test_bare_sample_ids_are_still_tolerated(tmp_path: Path) -> None:
    """测试夹具与旧索引里有裸 sampleId；看不出形态时不该判死。"""

    store = _store(
        tmp_path,
        [
            {
                "sampleId": "bare",
                "npcId": "Sophia",
                "sourceMod": "SVE",
                "sourceKey": "Mon",
                "conditions": {"relationshipStage": "close"},
                "text": "裸 sampleId 的样本也要能进锚点。",
            }
        ],
    )

    card = store.voice_card("Sophia", relationship_stage="close")
    assert [item["sampleId"] for item in card["voiceAnchors"]] == ["bare"]


def test_sve_and_vanilla_daily_coexist(tmp_path: Path) -> None:
    """两种日常对白形态混排时都要在（key 错开分桶，避免多样性去重干扰）。"""

    sve_variant = (
        "FlashShifter.StardewValleyExpandedCP:"
        "assets/CharacterFiles/Dialogue/Sophia/Dialogue.json:Tue4"
    )
    store = _store(
        tmp_path,
        [
            _sample(sve_variant, TEXTS["sve_marriage"]),
            _sample(VANILLA_DAILY, TEXTS["vanilla"]),
            _sample(EVENT_LINE, TEXTS["event"]),
        ],
    )

    anchors = store.voice_card("Sophia", relationship_stage="close")["voiceAnchors"]
    ids = {item["sampleId"] for item in anchors}

    assert sve_variant in ids, "SVE 变体 key 应进锚点"
    assert VANILLA_DAILY in ids, "原版日常应进锚点"
    assert EVENT_LINE not in ids
