"""晨间预设对话的加载、校验与渲染。

重点在**两条硬约束的回归**：开场白不能空（内容会被永久写死），
以及渲染出的卡**不能含开场白**（否则模型会以为要再确认一遍）。
"""

from __future__ import annotations

import json
import re
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

    def test_day2_scenario_exists_and_is_lewis(self) -> None:
        """第 2 天（过完第一晚）而不是第 1 天——第 1 天早上玩家还压在开场动画里。"""
        store = MorningScenarioStore.load(REAL_DATA)
        scenario = store.for_day(2)
        assert scenario is not None
        assert scenario.npc_id == "Lewis"

    def test_day1_has_no_scenario(self) -> None:
        store = MorningScenarioStore.load(REAL_DATA)
        assert store.for_day(1) is None

    def test_opening_traces_back_to_corpus(self) -> None:
        """开场白必须能在原版原文里找到——**不许自由创作**。

        2026-09-25 的教训：「藤」「标签」「果霜」在原话里一次都没出现过。
        预设对话是人工写死的，写错了会永远留在那里，所以这条要机器守。
        """
        store = MorningScenarioStore.load(REAL_DATA)
        scenario = store.for_day(2)
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

    def test_closing_hook_is_conditional_not_turn_counted(self) -> None:
        """收尾条件**不能写成「第 N 轮」**——模型数不清轮次。

        2026-09-26 云端实测（㊲）：原文案是「聊到第 2~3 轮时把话头交给玩家一次」，
        实际它在**玩家第一次回应时就把这个问题问掉了**，之后第 5、6 轮又开始抛新问题。
        收尾条件必须写成**玩家那边的信号**（他只回了一句应声、或者话已经说完），
        而不是「聊了几轮」——判据要落在模型能直接看到的东西上。

        另一半是**范本**：㊳ 的结论是「禁令单独用会削掉表达力（回复变短、还跑题），
        配上范本才恢复」。只写「不要用问句结尾」它不敢写，给一句例子才落地。
        """
        store = MorningScenarioStore.load(REAL_DATA)
        scenario = store.for_day(2)
        assert scenario is not None
        hook = scenario.closing_hook
        assert not re.search(r"第\s*\d+", hook), (
            f"收尾条件里出现了轮次表述，模型数不清轮次：{hook}"
        )
        examples = re.findall(r"「([^」]+)」", hook)
        assert any(len(item) >= 6 for item in examples), (
            f"收尾条件必须带一个引号里的示例句（只有禁令没有范本时模型会不敢展开）：{hook}"
        )


class TestVariantUniqueness:
    """同一角色的多条预设不得逐字相同。

    2026-09-26 用户口径：「预设对话触发过一次之后就不要再触发了，
    **可以有小巧思变体，但是不能一模一样**」。
    """

    def test_rejects_identical_openings_for_the_same_npc(self, tmp_path: Path) -> None:
        with pytest.raises(MorningScenarioError, match="逐字相同"):
            _store(
                tmp_path,
                [_scenario(id="day2-lewis"), _scenario(id="day5-lewis")],
            )

    def test_allows_a_real_variant_for_the_same_npc(self, tmp_path: Path) -> None:
        store = _store(
            tmp_path,
            [
                _scenario(id="day2-lewis"),
                _scenario(
                    id="day5-lewis",
                    opening="上次那场雨把南边的篱笆冲歪了，你看见了吗？",
                ),
            ],
        )
        assert len(store) == 2

    def test_whitespace_difference_is_still_a_duplicate(self, tmp_path: Path) -> None:
        """归一必须与运行期认人的口径一致：只差空格的两条，运行期会认成同一条，
        玩家看到的也确实是同一句话。"""
        with pytest.raises(MorningScenarioError, match="逐字相同"):
            _store(
                tmp_path,
                [
                    _scenario(id="a"),
                    _scenario(id="b", opening="你在那个破屋里过的第一晚怎么样？\n"),
                ],
            )

    def test_different_npcs_may_share_a_line(self, tmp_path: Path) -> None:
        """口径是「同一角色的变体不能重复」；跨角色撞句是内容审查的事，
        不在这一层拦——那会拦住有意复用的通用问候。"""
        store = _store(
            tmp_path,
            [
                _scenario(id="a", npcId="Lewis"),
                _scenario(id="b", npcId="Pierre"),
            ],
        )
        assert len(store) == 2

    def test_real_data_file_passes_the_uniqueness_check(self) -> None:
        store = MorningScenarioStore.load(REAL_DATA)
        assert len(store) >= 1
