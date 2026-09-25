"""晨间预设对话的加载、校验与渲染。

重点在**两条硬约束的回归**：开场白不能空（内容会被永久写死），
以及渲染出的卡**不能含开场白**（否则模型会以为要再确认一遍）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stardew_ai_bridge.morning_scenario import (
    MorningScenarioError,
    MorningScenarioStore,
    parse_scenario,
    render_direction_card,
)

ROOT = Path(__file__).resolve().parents[2]
REAL_DATA = ROOT / "data" / "scenarios" / "morning.json"


def _scenario(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "day1-lewis",
        "trigger": {"kind": "absoluteDay", "dayIndex": 1},
        "npcId": "Lewis",
        "displayName": "刘易斯",
        "opening": "你在那个破屋里过的第一晚怎么样？",
        "direction": "绕着「第一晚」和你爷爷展开。",
        "boundaries": ["不要提继承和遗产"],
        "closingHook": "两三句之后把话头交给玩家。",
        "allowedKinds": ["self_share"],
    }
    base.update(overrides)
    return base


def _store(tmp_path: Path, items: list[dict[str, object]]) -> MorningScenarioStore:
    path = tmp_path / "morning.json"
    path.write_text(
        json.dumps({"schemaVersion": 1, "scenarios": items}, ensure_ascii=False),
        encoding="utf-8",
    )
    return MorningScenarioStore.load(path)


class TestLoading:
    def test_missing_file_is_empty_store_not_error(self, tmp_path: Path) -> None:
        """预设是可选内容：没有它时链路应照常工作（退化成现在的行为）。"""
        store = MorningScenarioStore.load(tmp_path / "nope.json")
        assert len(store) == 0
        assert store.for_day(1) is None

    def test_loads_valid_scenario(self, tmp_path: Path) -> None:
        store = _store(tmp_path, [_scenario()])
        assert len(store) == 1
        scenario = store.for_day(1)
        assert scenario is not None
        assert scenario.npc_id == "Lewis"
        assert scenario.day_index == 1

    def test_rejects_empty_opening(self, tmp_path: Path) -> None:
        """开场白为空等于这条预设没有内容——必须在加载期拦住。"""
        with pytest.raises(MorningScenarioError, match="opening"):
            _store(tmp_path, [_scenario(opening="   ")])

    def test_rejects_empty_direction(self, tmp_path: Path) -> None:
        """中档约束的全部价值就在 direction；空了就退化成弱档。"""
        with pytest.raises(MorningScenarioError, match="direction"):
            _store(tmp_path, [_scenario(direction="")])

    def test_rejects_missing_npc_id(self, tmp_path: Path) -> None:
        with pytest.raises(MorningScenarioError, match="npcId"):
            _store(tmp_path, [_scenario(npcId="")])

    def test_rejects_duplicate_ids(self, tmp_path: Path) -> None:
        with pytest.raises(MorningScenarioError, match="重复"):
            _store(tmp_path, [_scenario(), _scenario()])

    def test_rejects_non_object_root(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(MorningScenarioError, match="顶层"):
            MorningScenarioStore.load(path)

    def test_reports_broken_json(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(MorningScenarioError, match="无法读取"):
            MorningScenarioStore.load(path)


class TestLookup:
    def test_for_day_returns_none_when_no_trigger_matches(self, tmp_path: Path) -> None:
        store = _store(tmp_path, [_scenario()])
        assert store.for_day(2) is None

    def test_for_day_ignores_non_absolute_triggers(self, tmp_path: Path) -> None:
        """非 absoluteDay 的触发不该被当成天数匹配——否则 dayIndex 缺失会被读成 0 天。"""
        store = _store(tmp_path, [_scenario(trigger={"kind": "festival", "id": "egg"})])
        assert store.for_day(0) is None
        assert len(store) == 1

    def test_for_npc_is_case_insensitive(self, tmp_path: Path) -> None:
        store = _store(tmp_path, [_scenario()])
        assert len(store.for_npc("lewis")) == 1
        assert len(store.for_npc("LEWIS")) == 1
        assert len(store.for_npc("Sophia")) == 0


class TestDirectionCard:
    def test_card_omits_opening(self, tmp_path: Path) -> None:
        """开场白已在对话记录里；放进 system 卡会让模型以为要再确认一遍。"""
        store = _store(tmp_path, [_scenario()])
        scenario = store.for_day(1)
        assert scenario is not None
        card = render_direction_card(scenario)
        assert "opening" not in card
        assert scenario.opening not in json.dumps(card, ensure_ascii=False)

    def test_card_carries_direction_and_boundaries(self, tmp_path: Path) -> None:
        store = _store(tmp_path, [_scenario()])
        scenario = store.for_day(1)
        assert scenario is not None
        card = render_direction_card(scenario)
        assert card["direction"] == "绕着「第一晚」和你爷爷展开。"
        assert card["boundaries"] == ["不要提继承和遗产"]
        assert card["closing"] == "两三句之后把话头交给玩家。"
        assert card["allowedKinds"] == ["self_share"]

    def test_card_omits_empty_optional_fields(self) -> None:
        scenario = parse_scenario(_scenario(boundaries=[], closingHook="", allowedKinds=[]))
        card = render_direction_card(scenario)
        assert "boundaries" not in card
        assert "closing" not in card
        assert "allowedKinds" not in card


class TestRealData:
    """真实 `data/scenarios/morning.json` 必须能加载——写坏的数据会一直写在那里。"""

    def test_real_file_loads(self) -> None:
        store = MorningScenarioStore.load(REAL_DATA)
        assert len(store) >= 1

    def test_day1_scenario_exists_and_is_lewis(self) -> None:
        store = MorningScenarioStore.load(REAL_DATA)
        scenario = store.for_day(1)
        assert scenario is not None
        assert scenario.npc_id == "Lewis"

    def test_opening_traces_back_to_corpus(self) -> None:
        """开场白必须能在原版原文里找到——**不许自由创作**。

        2026-09-25 的教训：「藤」「标签」「果霜」在原话里一次都没出现过。
        预设对话是人工写死的，写错了会永远留在那里，所以这条要机器守。
        """
        store = MorningScenarioStore.load(REAL_DATA)
        scenario = store.for_day(1)
        assert scenario is not None
        corpus = (
            ROOT
            / "artifacts"
            / "corpus"
            / "20260923-extra-dialogue"
            / "vanilla-sve-rasmodia-dialogue-corpus.json"
        )
        if not corpus.exists():  # pragma: no cover - 语料是生成物，缺了不阻断
            pytest.skip("语料文件不存在")
        payload = json.loads(corpus.read_text(encoding="utf-8"))
        lewis_text = " ".join(
            str(record.get("text") or "")
            for record in payload["records"]
            if record.get("npcId") == scenario.npc_id
        )
        # 取开场白里最长的几个片段逐一核对，避免整句比对被标点差异卡住
        fragments = [
            part.strip("。，？！！…… ")
            for part in scenario.opening.replace("？", "？|").replace("。", "。|").split("|")
            if len(part.strip()) >= 6
        ]
        assert fragments, "开场白里没有可核对的长片段"
        missing = [part for part in fragments if part not in lewis_text]
        assert not missing, f"这些片段在原话里找不到，疑似自由创作：{missing}"
