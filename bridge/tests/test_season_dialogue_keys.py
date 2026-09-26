"""季节前缀日常键（`summer_Mon4`）的准入与季节优先（2026-09-27）。

原版与 SVE 都把大量日常对白按季节写（`Characters/Dialogue/<NPC>.json` 里
`summer_Mon` / `winter_Fri4` 这种键）。零请求探针（`.tmp/season-key-probe.py`）实测：
语料 14063 条里 **1283 条**是「季节前缀 + 星期」形状（占 9%），
但索引构建关口把它们一律当成"键里编码了触发条件的非日常口吻"拒掉 ——
`is_model_evidence_record` 放行 **0/1283**，把季节前缀剥掉后放行 1224 条。

后果不是边角料：Linus 的季节独白（`summer_Mon`「今早有些起雾，我看见一只鹭鸟
优雅地踏着雾气飞去」、`winter_Fri4`「树会在冬天的时候休眠，这会让我感觉有些寂寞」）
**从来没进过素材池**，而它们恰好是用户说的"文艺哲理那一批"。
同一批被拒的还有 22 个角色的季节素材（Victor 83 / Olivia 70 / Sophia 68 / Haley 48…）。

判据收在**形状**上：季节前缀 + 星期键 = 日常独白（放行，但**带季节条件**）；
`spring_13`（节日日期）、`winterstar`（冬日星节）、`summer_Mon_dance`（复合分支键）
仍算特殊。季节键**不进**全局静态锚点（那张卡没有季节参数，收进来就是"夏天说冬天的话"），
只在带条件的阶段锚点里按 `gameState.season` 优先。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.evidence import (
    dialogue_key_season,
    is_model_evidence_record,
    is_stable_voice_evidence_record,
)
from stardew_ai_bridge.profile_index import (
    ProfileIndexStore,
    _dialogue_key_priority,
    _representative_category,
)
from stardew_ai_bridge.speech import (
    _anchor_category,
    _stage_conditioned_voice_sample,
    select_stage_voice_anchors,
)

_LINUS_LINE = "今早有些起雾，我看见一只鹭鸟优雅地踏着雾气飞去。"


def _record(
    key: str,
    text: str = _LINUS_LINE,
    kind: str = "dialogue",
    path: str = "Characters/Dialogue/Linus.zh-CN.json",
) -> dict[str, object]:
    return {
        "sourceKey": key,
        "text": text,
        "evidenceKind": kind,
        "sourcePath": path,
    }


def _sample(
    key: str,
    text: str,
    stage: str = "close",
    season: str = "",
) -> dict[str, object]:
    conditions: dict[str, str] = {"relationshipStage": stage}
    if season:
        conditions["season"] = season
    return {
        "sampleId": f"vanilla:Characters/Dialogue/Linus.zh-CN.json:{key}",
        "npcId": "Linus",
        "sourceKey": key,
        "sourcePath": "Characters/Dialogue/Linus.zh-CN.json",
        "text": text,
        "evidenceKind": "dialogue",
        "conditions": conditions,
    }


# --- 索引收录关口（evidence）------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "summer_mon",
        "summer_Mon",
        "summer_Mon4",
        "winter_Fri4",
        "fall_wed4",
        "spring_Sun8",
        "Winter_tue10",
    ],
)
def test_season_weekday_keys_reach_the_model_evidence_window(key: str) -> None:
    assert is_model_evidence_record(_record(key)) is True


@pytest.mark.parametrize(
    "key",
    [
        "summer_festival",  # 小写节日词，不在人名形状里
        "winterstar",  # 冬日星节
        "summer_Mon_dance",  # 复合分支键，形状不合法
        "winter_Mon4_x",
        "summer_",
        "fall_Mon4Mon",  # 星期键后面又挂了一段
        "spring_13_2",  # 多段
    ],
)
def test_season_keys_that_are_not_daily_shapes_stay_special(key: str) -> None:
    assert is_model_evidence_record(_record(key)) is False


@pytest.mark.parametrize("key", ["summer_Mon4", "WINTER_fri", "spring_sun8"])
def test_dialogue_key_season_reads_the_season_of_seasonal_daily_keys(key: str) -> None:
    assert dialogue_key_season(key) in {"spring", "summer", "fall", "winter"}


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        # 婚后对白的季节序号（`MarriageDialogue*.json`，实测 340 条样本 / 118 键）
        ("spring_1", "spring"),
        ("winter_25", "winter"),
        ("fall_13", "fall"),
        ("summer_28", "summer"),
        # SVE 婚后对白的「季节_人名」形状
        ("spring_Olivia", "spring"),
        ("winter_Lance", "winter"),
        ("fall_Abigail", "fall"),
        ("Summer_Sophia", "summer"),
    ],
)
def test_dialogue_key_season_reads_marriage_season_shapes(
    key: str, expected: str
) -> None:
    """2026-09-27 扩形状：此前婚后季节句完全拿不到季节优先。"""

    assert dialogue_key_season(key) == expected


@pytest.mark.parametrize(
    "key",
    ["summer_festival", "spring_festival", "fall_Mon4Mon", "spring_13_2"],
)
def test_named_season_shape_needs_a_capitalised_name(key: str) -> None:
    """人名形状必须首字母大写，否则小写节日键会被顺手收进来。"""

    assert dialogue_key_season(key) == ""


@pytest.mark.parametrize(
    "key",
    [
        "Mon4",
        "mon",
        "introduction",
        "winterstar",
        "",
        "summer_Mon_dance",
        "summer_festival",
        "fall_Mon4Mon",
    ],
)
def test_dialogue_key_season_is_empty_for_anything_else(key: str) -> None:
    assert dialogue_key_season(key) == ""


def test_season_weekday_keys_are_still_not_unconditional_stable_anchors() -> None:
    # 全局静态 voice card 没有季节参数：收进来就是"夏天说冬天的话"。
    # 它们只该进带条件的检索（阶段锚点 / 模型证据窗口）。
    assert is_stable_voice_evidence_record(_record("summer_mon")) is False
    assert is_stable_voice_evidence_record(_record("summer_Mon4")) is False


# --- 阶段锚点准入（speech）--------------------------------------------------


def test_stage_conditioned_gate_accepts_seasonal_heart_keys() -> None:
    assert _stage_conditioned_voice_sample(_sample("summer_Mon4", _LINUS_LINE)) is True


def test_stage_conditioned_gate_needs_the_stage_condition() -> None:
    sample = _sample("summer_Mon4", _LINUS_LINE)
    sample["conditions"] = {}
    assert _stage_conditioned_voice_sample(sample) is False


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("summer_Mon4", "weekday_variant"),
        ("summer_mon", "weekday"),
        ("Mon4", "weekday_variant"),
        ("mon", "weekday"),
        ("spring_13", "scene"),
    ],
)
def test_anchor_category_buckets_seasonal_keys_with_their_plain_twins(
    key: str, expected: str
) -> None:
    assert _anchor_category(_sample(key, _LINUS_LINE)) == expected


# --- 选择顺序：当前季节优先 --------------------------------------------------


def test_current_season_anchors_outrank_offseason_and_unseasoned_ones() -> None:
    # 三条文本长度相近、都没有语气词与感叹号（energy 同档），只有键不同。
    offseason = _sample("winter_Mon4", "树会在冬天的时候休眠这会让我感觉有些寂寞")
    inseason = _sample("summer_Mon4", "今早有些起雾我看见一只鹭鸟踏着雾气飞过去")
    unseasoned = _sample("Mon4", "我一个人住在这里已经很多年了我有自己的理由")

    anchors = select_stage_voice_anchors(
        [offseason, unseasoned, inseason],
        "Linus",
        "close",
        season="summer",
    )

    assert [anchor["sourceKey"] for anchor in anchors][0] == "summer_Mon4"


def test_unknown_season_does_not_let_seasonal_keys_jump_the_queue() -> None:
    # 没给季节信息时，季节键不能凭"更具体"插队；通用键保持领先。
    offseason = _sample("winter_Mon4", "树会在冬天的时候休眠这会让我感觉有些寂寞")
    inseason = _sample("summer_Mon4", "今早有些起雾我看见一只鹭鸟踏着雾气飞过去")
    unseasoned = _sample("Mon4", "我一个人住在这里已经很多年了我有自己的理由")

    anchors = select_stage_voice_anchors(
        [offseason, unseasoned, inseason],
        "Linus",
        "close",
    )

    assert [anchor["sourceKey"] for anchor in anchors][0] == "Mon4"


def test_region_of_the_stage_beats_the_season() -> None:
    # 阶段优先于季节：更早阶段的当前季节句不能挤掉当前阶段的通用句。
    closer_stage = _sample(
        "winter_Mon4", "我一个人住在这里已经很多年了我有自己的理由", stage="close"
    )
    earlier_stage = _sample(
        "summer_Mon4", "今早有些起雾我看见一只鹭鸟踏着雾气飞过去", stage="acquaintance"
    )

    anchors = select_stage_voice_anchors(
        [earlier_stage, closer_stage], "Linus", "close", season="summer"
    )

    assert [anchor["sourceKey"] for anchor in anchors][0] == "winter_Mon4"


def test_a_non_string_season_is_tolerated() -> None:
    samples = [_sample("summer_Mon4", _LINUS_LINE)]
    for odd in (None, 42, ["summer"]):
        assert select_stage_voice_anchors(
            samples, "Linus", "close", season=odd  # type: ignore[arg-type]
        )


# --- 代表区与键优先级（profile_index）---------------------------------------


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("summer_Mon4", "weekday_variant"),
        ("summer_mon", "weekday"),
        ("winter_Fri4", "weekday_variant"),
    ],
)
def test_representative_category_places_seasonal_keys_in_daily_buckets(
    key: str, expected: str
) -> None:
    assert _representative_category(_record(key)) == expected


def test_season_prefix_with_non_daily_shape_keeps_its_own_bucket() -> None:
    """季节前缀但形状不是日常键的仍是 4 档。

    `spring_13` 自 2026-09-27 起归入日常档（实测身份是 Linus 的春季第 13 句，
    不是节日日期），所以改用多段的 `spring_13_2` 守住这个档位。
    """

    assert _dialogue_key_priority(_record("spring_13_2")) == 4


def test_seasonal_daily_keys_are_no_longer_special_in_the_representative_ranking() -> None:
    # 3 = 日常变体（与 `Mon4` 同级）；4 = 季节类非日常（形状不是日常键）；5 = 事件/节日。
    assert _dialogue_key_priority(_record("summer_Mon4")) == 3
    assert _dialogue_key_priority(_record("summer_Mon4")) == _dialogue_key_priority(
        _record("Mon4")
    )
    assert _dialogue_key_priority(_record("spring_13")) == 3
    # `winterstar` 是冬日星节，被事件判据先接走（比季节判据更专指）。
    assert _dialogue_key_priority(_record("winterstar")) == 5


# --- 检索窗口的季节闸门 ------------------------------------------------------


def _window_sample(sample_id: str, key: str, text: str) -> dict[str, object]:
    return {
        "sampleId": sample_id,
        "npcId": "Linus",
        "sourceMod": "vanilla",
        "sourcePath": "Characters/Dialogue/Linus.zh-CN.json",
        "sourceKey": key,
        "text": text,
    }


def test_style_window_gates_seasonal_lines_by_the_current_season(
    tmp_path: Path,
) -> None:
    """检索窗口的季节口径与全局静态锚点一致 —— 没给季节就不收季节素材。

    锚点窗口（`voice_card`）用的是**降级**（当季优先、异季垫底）：它只有 8 条，
    且空窗口会退回静态 voice card。检索窗口（`style_samples` / `speech_evidence`）
    候选多，改用**闸门**更安全 —— 异季素材根本不进来，避免"夏天满口冬天的话"。
    """

    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "styleSamples": [
                    _window_sample("vanilla:in-season", "summer_Mon4", "当季的夏季独白。"),
                    _window_sample("vanilla:off-season", "winter_Mon4", "异季的冬季独白。"),
                    _window_sample("vanilla:plain", "Mon4", "没有季节限定的日常句。"),
                ],
                "speechEvidence": [],
                "voiceCards": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = ProfileIndexStore(index_path)

    def keys(**kwargs: object) -> list[str]:
        return [
            str(item["sourceKey"])
            for item in store.style_samples("Linus", ["vanilla"], limit=8, **kwargs)
        ]

    assert set(keys(season="summer")) == {"summer_Mon4", "Mon4"}
    assert set(keys(season="winter")) == {"winter_Mon4", "Mon4"}
    # 中文季节字与英文等价（`gameState.season` 是英文，评测页用中文）。
    assert set(keys(season="夏")) == {"summer_Mon4", "Mon4"}
    # 没有季节信息时季节素材一律不进窗口（放行之前的行为），通用键照旧。
    assert keys() == ["Mon4"]
