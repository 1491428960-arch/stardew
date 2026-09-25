"""晨间预设的方向卡必须**真的进入 prompt**。

这个文件存在的理由就是 ㉑ 那类事故：数据写对、测试全绿、日志无异常，
而那个值**从来没有到达 prompt**（`roleGuidance` 上限、键白名单、`[:2]` 截断……）。
所以这里不看数据结构，只看**最终 messages 里有没有那张卡、卡里有没有那句话**。
"""

from __future__ import annotations

import json

from stardew_ai_bridge.app import _build_context
from stardew_ai_bridge.morning_scenario import MorningScenarioStore

# 与 `data/scenarios/morning.json` 里的 opening 逐字一致。
# 刻意抄一份在这里：如果数据文件被改动，这个测试会失败——
# 那正是提醒「两端必须同步」的信号（`prompts.py` 靠逐字比对认人）。
LEWIS_OPENING = (
    "你在那个破屋里过的第一晚怎么样？"
    "你爷爷以前总是抱怨那张晃晃悠悠的旧床。但我觉得，他心里其实是爱着那间房子的。"
)


def _payload(history: list[dict[str, str]]) -> dict[str, object]:
    return {
        "npcId": "Lewis",
        "displayName": "刘易斯",
        "message": "还行，就是那张床一翻身就响。",
        "intent": "chat",
        "compactPrompt": True,
        "sourceMods": [],
        "history": history,
    }


def _morning_cards(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [item for item in messages if item.get("name") == "morning_direction"]


class TestDirectionReachesPrompt:
    def test_card_is_present_when_history_starts_with_the_opening(self) -> None:
        _, messages = _build_context(
            _payload([{"role": "assistant", "content": LEWIS_OPENING}]),
            compact_prompt=True,
        )
        cards = _morning_cards(messages)
        assert len(cards) == 1, "认出了晨间对话，却没挂方向卡"

    def test_card_carries_the_actual_direction_text(self) -> None:
        """只看「卡在不在」不够——㉑ 的六个闸门都是「卡在、内容是空的」。"""
        _, messages = _build_context(
            _payload([{"role": "assistant", "content": LEWIS_OPENING}]),
            compact_prompt=True,
        )
        cards = _morning_cards(messages)
        assert cards
        payload = json.loads(cards[0]["content"])
        assert payload["direction"]
        assert "爷爷" in payload["direction"]
        assert payload["boundaries"], "边界条件没进卡"
        assert any("继承" in item for item in payload["boundaries"])
        assert payload["closing"]

    def test_no_card_without_a_matching_opening(self) -> None:
        _, messages = _build_context(
            _payload([{"role": "assistant", "content": "早上好呀，今天天气不错。"}]),
            compact_prompt=True,
        )
        assert _morning_cards(messages) == []

    def test_no_card_for_empty_history(self) -> None:
        _, messages = _build_context(_payload([]), compact_prompt=True)
        assert _morning_cards(messages) == []

    def test_opening_survives_whitespace_differences(self) -> None:
        """游戏端写进记录时可能过一遍清洗（换行/首尾空格）。

        去空白比对要能容忍这个；容忍不了会**静默退化**成没有方向约束。
        """
        squashed = LEWIS_OPENING.replace("。", "。\n").strip()
        _, messages = _build_context(
            _payload([{"role": "assistant", "content": squashed}]),
            compact_prompt=True,
        )
        assert len(_morning_cards(messages)) == 1

    def test_only_the_first_assistant_message_is_considered(self) -> None:
        """晨间消息永远是这段对话的开头；后面的轮次只是延续，不该改变判据。"""
        _, messages = _build_context(
            _payload(
                [
                    {"role": "assistant", "content": LEWIS_OPENING},
                    {"role": "user", "content": "还行。"},
                    {"role": "assistant", "content": "那就好。"},
                ]
            ),
            compact_prompt=True,
        )
        assert len(_morning_cards(messages)) == 1

    def test_player_speaking_first_is_not_a_morning_thread(self) -> None:
        """玩家先开口、且她的话不是预设开场——不该被认成晨间对话。"""
        _, messages = _build_context(
            _payload(
                [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "你好呀。"},
                ]
            ),
            compact_prompt=True,
        )
        assert _morning_cards(messages) == []


class TestOpeningStaysInSyncWithData:
    def test_constant_matches_the_data_file(self) -> None:
        """上面那个常量和数据文件必须一致——不一致时这个测试先炸，
        而不是等到游戏里方向约束静默失效。"""
        store = MorningScenarioStore.load(
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "data"
            / "scenarios"
            / "morning.json"
        )
        scenario = store.for_day(2)
        assert scenario is not None
        assert scenario.opening == LEWIS_OPENING
