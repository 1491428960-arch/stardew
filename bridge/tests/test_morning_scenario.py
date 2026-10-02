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
    season_of,
)

ROOT = Path(__file__).resolve().parents[2]
REAL_DATA = ROOT / "data" / "scenarios" / "morning.json"

#: 控制码：`#$e#` `#$b#` 分段、`$h` `$s` 情绪、`@` 玩家名、`^` 性别变体、`%noturn`。
#: 与 `scripts/extract_morning_candidates.py` 里那份保持一致 —— 那边用它裁切，
#: 这边用它检查裁切结果。
_CONTROL_CODE = re.compile(r"#\$[a-zA-Z]#|\$[a-zA-Z0-9]|%[a-zA-Z]+|\^|@")
_I18N_TEMPLATE = "{{i18n:"
_LATIN_RUN = re.compile(r"[A-Za-z]{2,}")

#: 中文技术圈的通用词，**不算**「没翻译干净的英文标识」。
#: `bug` 是 persona 自己用的（Sebastian 的 topicPool 写着「代码和 bug」），
#: `AI` 是 `reply_scrub` 里既有的保留词。真正的英文标识是 `Abigail`
#: 这种游戏内 id —— 它本该显示成「阿比盖尔」。
_LATIN_ALLOWED = frozenset({"ai", "bug", "api", "mod"})

#: 比对「是否原话照搬」时先抹掉的字符。少抹一个，只差一个标点的照搬就混过去了。
_SQUASH_CHARS = re.compile(r"[\s。，？！！……、；：\"'（）()「」『』]")


def _find_control_code(opening: str) -> str | None:
    match = _CONTROL_CODE.search(opening)
    return match.group(0) if match else None


def _find_i18n_template(opening: str) -> str | None:
    return _I18N_TEMPLATE if _I18N_TEMPLATE in opening else None


def _find_latin(opening: str) -> list[str]:
    """找「没翻译干净的英文标识」。

    ⚠ 白名单不是图省事，是**误报**：`bug` 这种词 persona 自己就在用
    （Sebastian 的 `topicPool` 原文是「代码和 bug」），拦它等于说 persona
    写错了。`AI` 则是 `reply_scrub` 里既有的保留词。
    这类中文技术圈的通用词**不是**英文标识，真正的英文标识是 `Abigail`
    这种游戏内 id —— 它本该显示成「阿比盖尔」。
    """
    return [
        word for word in _LATIN_RUN.findall(opening)
        if word.lower() not in _LATIN_ALLOWED
    ]


def _squash(text: str) -> str:
    return _SQUASH_CHARS.sub("", text)


def _scenario(**overrides: object) -> dict[str, object]:
    # ⚠ 默认放在第 2 天，不放第 1 天：第 1 天早上玩家还压在开场动画里，
    # `for_day` 会直接返回 None（见 `test_pool_never_fires_on_day_one`）。
    # 而且这句开场白问的就是「第一晚怎么样」，本来就该第 2 天问。
    base: dict[str, object] = {
        "id": "day2-lewis",
        "trigger": {"kind": "absoluteDay", "dayIndex": 2},
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
        scenario = store.for_day(2)
        assert scenario is not None
        assert scenario.npc_id == "Lewis"
        assert scenario.day_index == 2

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
        # 场景挂在第 2 天，所以第 9 天不该有任何东西 —— 顺手也证明了
        # `for_day` 不会因为「有任意一条预设」就随便返回一条。
        store = _store(tmp_path, [_scenario()])
        assert store.for_day(2) is not None
        assert store.for_day(9) is None

    def test_for_day_ignores_non_absolute_triggers(self, tmp_path: Path) -> None:
        """非 absoluteDay 的触发不该被当成天数匹配——否则 dayIndex 缺失会被读成 0 天。

        ⚠ 原先这里用的 `{"kind": "festival"}` 是个**从未存在过**的 kind：
        它只是碰巧没被任何分支认领，于是「被正确忽略」这个结论是**假绿**。
        2026-09-27 加事件型时把未知 kind 改成加载期报错，这条 fixture 立刻炸了 ——
        正说明它守的从来不是「合法的非 absoluteDay 触发」。
        现在换成两种**真实存在**的 kind，且都不该在第 9 天（春季）命中。
        """
        store = _store(
            tmp_path,
            [
                _scenario(trigger={"kind": "season", "season": "winter"}),
                _scenario(
                    id="event-one",
                    npcId="Shane",
                    displayName="谢恩",
                    opening="昨天那事……算了。",
                    trigger={"kind": "event", "eventId": "384882"},
                ),
            ],
        )
        assert store.for_day(9) is None
        assert len(store) == 2

    def test_for_npc_is_case_insensitive(self, tmp_path: Path) -> None:
        store = _store(tmp_path, [_scenario()])
        assert len(store.for_npc("lewis")) == 1
        assert len(store.for_npc("LEWIS")) == 1
        assert len(store.for_npc("Sophia")) == 0


class TestSeasonTrigger:
    """季节触发：**不需要任何新请求字段**。

    季节由 `day_index` 推算 —— 星露谷 1 季 28 天、1 年 4 季（112 天），
    而 `DayStarted` 早就把 `dayIndex` 送进来了。所以这一层能扩事件库，
    却**完全不碰 DLL 契约**；`MorningPlanRequest` 的注释明写
    「需要那些信息（好感度 / 关系阶段）时另开端点」——那条留给第二阶段。

    为什么值得单独开一类触发：绝对天数只适合「第 N 天」这种一次性节点，
    而**季节更替是可重复的、每年都会发生的**节点。同一个由头每年来一次是合理的，
    写死成绝对天数反而第二年就失效了。
    """

    def test_season_of_maps_day_index_to_season_and_day(self) -> None:
        assert season_of(1) == ("spring", 1)
        assert season_of(28) == ("spring", 28)
        assert season_of(29) == ("summer", 1)
        assert season_of(56) == ("summer", 28)
        assert season_of(57) == ("fall", 1)
        assert season_of(85) == ("winter", 1)
        assert season_of(113) == ("spring", 1)  # 第 2 年春季第 1 天

    def test_season_of_clamps_non_positive_day(self) -> None:
        """`dayIndex` 是 ge=0 的 0 基计数器，减 1 后可能落到 0 或负数。"""
        assert season_of(0) == ("spring", 1)

    def test_matches_exact_day_in_season(self, tmp_path: Path) -> None:
        store = _store(
            tmp_path,
            [_scenario(trigger={"kind": "season", "season": "spring", "dayInSeason": 3})],
        )
        assert store.for_day(3) is not None
        assert store.for_day(4) is None
        # 第 2 年同一季节的同一天同样命中——季节节点可重复
        assert store.for_day(3 + 112) is not None

    def test_matches_day_range_in_season(self, tmp_path: Path) -> None:
        store = _store(
            tmp_path,
            [
                _scenario(
                    trigger={
                        "kind": "season",
                        "season": "winter",
                        "minDayInSeason": 1,
                        "maxDayInSeason": 7,
                    }
                )
            ],
        )
        assert store.for_day(85) is not None  # 冬季第 1 天
        assert store.for_day(91) is not None  # 冬季第 7 天
        assert store.for_day(92) is None      # 冬季第 8 天

    def test_season_alone_matches_the_whole_season(self, tmp_path: Path) -> None:
        store = _store(tmp_path, [_scenario(trigger={"kind": "season", "season": "fall"})])
        assert store.for_day(57) is not None
        assert store.for_day(84) is not None
        assert store.for_day(85) is None

    def test_absolute_day_wins_over_season(self, tmp_path: Path) -> None:
        """绝对天数更具体，必须压过季节——否则「第 2 天」会被春季规则抢走。"""
        store = _store(
            tmp_path,
            [
                _scenario(
                    id="season-spring",
                    npcId="Pierre",
                    displayName="皮埃尔",
                    opening="春天到了，种子该备齐了吧？",
                    trigger={"kind": "season", "season": "spring"},
                ),
                _scenario(id="day2", trigger={"kind": "absoluteDay", "dayIndex": 2}),
            ],
        )
        picked = store.for_day(2)
        assert picked is not None
        assert picked.id == "day2"

    def test_rejects_unknown_season_at_load(self, tmp_path: Path) -> None:
        """季节名写错必须在**加载期**炸掉。

        配置是人工写死的，写错了在游戏里的表现是「这条预设永远不触发」——
        静默，而且离现场很远。加载期报错离现场只有一次重启的距离。
        """
        with pytest.raises(MorningScenarioError, match="season"):
            _store(tmp_path, [_scenario(trigger={"kind": "season", "season": "autumn"})])

    def test_rejects_season_trigger_without_season(self, tmp_path: Path) -> None:
        with pytest.raises(MorningScenarioError, match="season"):
            _store(tmp_path, [_scenario(trigger={"kind": "season"})])

    def test_exact_day_beats_whole_season_regardless_of_file_order(
        self, tmp_path: Path
    ) -> None:
        """泛季节规则写在前面也不能抢走精确日——**文件顺序不该决定语义**。

        真实场景：`spring_12` 是节日前一天的专属台词，而某角色可能还有一条
        「春天来了」的泛季节预设。谁写在前面纯属编辑偶然，语义上必须是
        「第 12 天」赢。
        """
        store = _store(
            tmp_path,
            [
                _scenario(
                    id="whole-spring",
                    npcId="Pierre",
                    displayName="皮埃尔",
                    opening="春天到了，该备种子了。",
                    trigger={"kind": "season", "season": "spring"},
                ),
                _scenario(
                    id="day12",
                    npcId="Abigail",
                    displayName="阿比盖尔",
                    opening="我明天一定会去参加彩蛋大寻宝。你呢？",
                    trigger={"kind": "season", "season": "spring", "dayInSeason": 12},
                ),
            ],
        )
        picked = store.for_day(12)
        assert picked is not None
        assert picked.id == "day12", "精确日被泛季节规则抢走了"
        # 其他日子仍由泛季节规则接住
        other = store.for_day(5)
        assert other is not None
        assert other.id == "whole-spring"

    def test_range_beats_whole_season(self, tmp_path: Path) -> None:
        store = _store(
            tmp_path,
            [
                _scenario(
                    id="whole-winter",
                    npcId="Pierre",
                    displayName="皮埃尔",
                    opening="冬天生意清淡啊。",
                    trigger={"kind": "season", "season": "winter"},
                ),
                _scenario(
                    id="winter-week1",
                    npcId="Abigail",
                    displayName="阿比盖尔",
                    opening="外面雪下得真大，你出门小心点。",
                    trigger={
                        "kind": "season",
                        "season": "winter",
                        "minDayInSeason": 1,
                        "maxDayInSeason": 7,
                    },
                ),
            ],
        )
        picked = store.for_day(85)  # 冬季第 1 天
        assert picked is not None
        assert picked.id == "winter-week1"
        later = store.for_day(90)  # 冬季第 6 天
        assert later is not None
        assert later.id == "winter-week1"
        after = store.for_day(95)  # 冬季第 11 天，落在范围外
        assert after is not None
        assert after.id == "whole-winter"


class TestEventTrigger:
    """事件后触发：**关键剧情发生的第二天早上**，由当事 NPC 开口提那件事。

    这是第四种 trigger（`kind == "event"`）。前三种都只看日历，这一种看的是
    **玩家昨天刚经历完什么** —— 所以「昨天完成了哪个事件」必须由游戏端送进来，
    Bridge 自己推不出来（`completedEventIds` 是**累积全集**，不含完成时间）。

    ## 为什么事件型要排在最高优先级

    同一天可能既命中事件型、又命中 `absoluteDay` 或季节日。让日历赢会浪费掉
    事件型：**事件只会发生一次，日历每年都会再来**。而且刚经历完的剧情是玩家
    眼下最具体的东西，比「今天几号」更该被提起。

    ## 大小写为什么必须敏感

    `EventAuditRules` 里写死了一条与 NPC ID **恰好相反**的规则：事件 ID 是精确
    字符串，`"A"` 与 `"a"` 都要保留（`ShareFriendshipLedger` 忽略大小写是因为
    合并昵称无害，而合并事件 ID 会掩盖真实差异）。所以这里**不能 casefold**。
    """

    @staticmethod
    def _mixed(tmp_path: Path):
        """一天里同时挂着事件型、absoluteDay 与季节池，用来验优先级。"""
        return _store(
            tmp_path,
            [
                _scenario(
                    id="pool-generic",
                    npcId="Pierre",
                    displayName="皮埃尔",
                    opening="今天店里的货又堆到门口了。",
                    trigger={"kind": "season", "season": "winter"},
                ),
                _scenario(
                    id="absolute-day",
                    npcId="Lewis",
                    displayName="刘易斯",
                    opening="你在那个破屋里过的第一晚怎么样？",
                    trigger={"kind": "absoluteDay", "dayIndex": 85},
                ),
                _scenario(
                    id="after-event-shane",
                    npcId="Shane",
                    displayName="谢恩",
                    opening="昨天那事……算了，没什么好说的。",
                    trigger={"kind": "event", "eventId": "384882"},
                ),
            ],
        )

    def test_event_trigger_fires_when_the_event_was_just_completed(
        self, tmp_path: Path
    ) -> None:
        store = self._mixed(tmp_path)

        assert store.for_day(85, recent_event_ids=["384882"]).id == "after-event-shane"

    def test_event_trigger_stays_silent_without_the_signal(self, tmp_path: Path) -> None:
        """没送事件信号时，事件型**完全不参与**，不能让日历被它顶掉。"""

        store = self._mixed(tmp_path)

        assert store.for_day(85).id == "absolute-day"

    def test_event_trigger_outranks_absolute_day_and_the_pool(
        self, tmp_path: Path
    ) -> None:
        """三种同时命中时事件型赢 —— 事件只发生一次，日历每年都来。"""

        store = self._mixed(tmp_path)

        picked = store.for_day(85, recent_event_ids=["384882"])

        assert picked.id == "after-event-shane"
        assert picked.npc_id == "Shane"

    def test_an_unrelated_event_does_not_fire_it(self, tmp_path: Path) -> None:
        """玩家完成的是别的事件时，这条不该冒出来。"""

        store = self._mixed(tmp_path)

        assert store.for_day(85, recent_event_ids=["999999"]).id == "absolute-day"

    def test_event_ids_are_case_sensitive(self, tmp_path: Path) -> None:
        """`"ABC"` 与 `"abc"` 是两个不同的事件（与 NPC ID 的规则相反）。"""

        store = self._mixed(tmp_path)

        assert store.for_day(85, recent_event_ids=["abc"]).id == "absolute-day"

    def test_several_recent_events_pick_deterministically(self, tmp_path: Path) -> None:
        """一天完成多个事件时按 id 取定 —— **文件顺序不该决定行为**。"""

        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        items = [
            _scenario(
                id=f"after-event-{name}",
                npcId="Shane",
                displayName="谢恩",
                opening=f"昨天那件关于 {name} 的事……",
                trigger={"kind": "event", "eventId": event_id},
            )
            for name, event_id in (("b", "E-B"), ("a", "E-A"))
        ]
        forward = _store(tmp_path / "a", items)
        backward = _store(tmp_path / "b", list(reversed(items)))

        assert forward.for_day(85, recent_event_ids=["E-A", "E-B"]).id == "after-event-a"
        assert (
            forward.for_day(85, recent_event_ids=["E-A", "E-B"]).id
            == backward.for_day(85, recent_event_ids=["E-A", "E-B"]).id
        )

    def test_a_stale_event_signal_keeps_matching(self, tmp_path: Path) -> None:
        """信号还在就会一直命中 —— 这是**有意的**，去重责任在游戏端。

        Bridge 无从判断「这个事件是昨天完成的还是三个月前完成的」：
        `completedEventIds` 是累积全集且不含时间戳，`recentEventIds` 里也没有日期。
        所以游戏端必须只送**昨天**那一批；Bridge 自己再猜只会猜错。

        这条钉的是那个分工：哪天有人想在这里加「只认最近 N 天」的启发式，
        会看到这条失败，并读到为什么不该加。
        """

        store = self._mixed(tmp_path)

        first = store.for_day(85, recent_event_ids=["384882"])
        later = store.for_day(86, recent_event_ids=["384882"])

        assert first.id == "after-event-shane"
        assert later.id == "after-event-shane"

    def test_event_trigger_requires_an_event_id(self, tmp_path: Path) -> None:
        """缺 `eventId` 的事件型会**永远不触发**，必须在加载期炸掉。"""

        with pytest.raises(MorningScenarioError):
            _store(
                tmp_path,
                [
                    _scenario(
                        id="broken",
                        trigger={"kind": "event"},
                    )
                ],
            )

    def test_unknown_trigger_kind_is_rejected_at_load_time(self, tmp_path: Path) -> None:
        """`kind` 拼错（`"even"`/`"Event"`）的后果是**静默永不触发**。

        这与季节名拼错同型，而且离现场更远 —— 季节至少还能靠「怎么这季没词」
        察觉，事件型只在那一件事之后才该出现，玩家根本不会发现它没来。
        """

        with pytest.raises(MorningScenarioError):
            _store(
                tmp_path,
                [
                    _scenario(
                        id="typo",
                        trigger={"kind": "even", "eventId": "384882"},
                    )
                ],
            )


class TestDirectionCard:
    def test_card_omits_opening(self, tmp_path: Path) -> None:
        """开场白已在对话记录里；放进 system 卡会让模型以为要再确认一遍。"""
        store = _store(tmp_path, [_scenario()])
        scenario = store.for_day(2)
        assert scenario is not None
        card = render_direction_card(scenario)
        assert "opening" not in card
        assert scenario.opening not in json.dumps(card, ensure_ascii=False)

    def test_card_carries_direction_and_boundaries(self, tmp_path: Path) -> None:
        store = _store(tmp_path, [_scenario()])
        scenario = store.for_day(2)
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


class TestEventAfterRealData:
    """真实数据里的事件型必须**真的能触发** —— 对着语料库核 `eventId`。

    最危险的失效方式是 `eventId` 拼错：数据加载不报错、页面上看得见、
    单元测试全绿，但在游戏里**永远不会出现**，因为没有任何事件会产出那个 id。

    这与「季节名拼错」同型，却更难察觉：季节至少还能靠「这一季怎么没词」
    发现，事件型只在那一件事之后才该开口，玩家根本不会注意到它没来。

    语料库是游戏 `Data/Events` 的投影，用它当权威。它位于 `artifacts/` 下、
    可能被清理，所以**缺失时 skip 而不是 fail** —— 但只要在，就必须全中。
    """

    @staticmethod
    def _corpus_event_ids() -> dict[str, set[str]]:
        root = Path(__file__).resolve().parents[2]
        candidates = sorted(
            (root / "artifacts" / "corpus").glob("*/*dialogue-corpus.json")
        )
        for path in reversed(candidates):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            records = payload.get("records") if isinstance(payload, dict) else payload
            if not isinstance(records, list):
                continue
            found: dict[str, set[str]] = {}
            for record in records:
                if not isinstance(record, dict):
                    continue
                if record.get("evidenceKind") != "event_dialogue":
                    continue
                event_id = str(record.get("eventId") or "").strip()
                if not event_id:
                    continue
                found.setdefault(event_id, set()).add(str(record.get("npcId") or ""))
            if found:
                return found
        return {}

    @staticmethod
    def _real_store() -> MorningScenarioStore:
        root = Path(__file__).resolve().parents[2]
        return MorningScenarioStore.load(root / "data" / "scenarios" / "morning.json")

    # 测试夹具的事件 id —— 由 `tools/event-probe` 往 `Data/Events/Farm` 注入，
    # **不在游戏数据里**，所以核对时必须豁免。
    #
    # ⚠ 豁免是有代价的：一旦允许某些 id 缺席，**写错一位数字的 eventId 也会安静通过**，
    # 然后在游戏里永不触发 —— 与「数据写对但永不生效」是同一类失败。
    # 所以 `test_probe_ids_are_fixtures_only` 要求用它的预设自己声明测试用途。
    PROBE_EVENT_IDS = frozenset({"9990001"})

    def test_every_event_id_exists_in_the_game_data(self) -> None:
        known = self._corpus_event_ids()
        if not known:
            pytest.skip("语料库不在本地（artifacts/ 已被清理），跳过事件 ID 核对")

        store = self._real_store()
        after_events = [s for s in store.scenarios if s.event_id is not None]

        assert after_events, "事件型一条都没有 —— 要么数据丢了，要么触发方式没被认出来"
        assert [
            s.id
            for s in after_events
            if s.event_id not in known and s.event_id not in self.PROBE_EVENT_IDS
        ] == []

    def test_probe_ids_are_fixtures_only(self) -> None:
        """用了夹具 id 的预设必须自己声明，否则豁免就成了后门。"""

        undeclared = [
            s.id
            for s in self._real_store().scenarios
            if s.event_id in self.PROBE_EVENT_IDS and "测试夹具" not in s.opening_source
        ]
        assert not undeclared, (
            f"这些预设用了测试夹具的事件 id，但 `_openingSource` 里没声明测试用途：{undeclared}"
        )

    def test_the_npc_matches_the_event_it_follows(self) -> None:
        """预设挂的 NPC 必须真的参与那个事件，否则就是「张冠李戴」。

        `eventId` 对得上但 NPC 挂错时，触发会成功、开口的却是**没经历那件事的人**——
        比不触发更糟，因为看起来一切正常。
        """

        known = self._corpus_event_ids()
        if not known:
            pytest.skip("语料库不在本地（artifacts/ 已被清理），跳过事件归属核对")

        store = self._real_store()
        wrong = [
            (s.id, s.npc_id, sorted(known[s.event_id]))
            for s in store.scenarios
            if s.event_id in known and s.npc_id not in known[s.event_id]
        ]

        assert wrong == []

    def test_after_event_ids_are_unique_per_npc(self) -> None:
        """同一个 NPC 对同一个事件只能有一条 —— 否则同一天两条都命中，取谁看 id 排序。"""

        store = self._real_store()
        pairs = [
            (s.event_id, s.npc_id) for s in store.scenarios if s.event_id is not None
        ]

        assert sorted(pairs) == sorted(set(pairs))


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

    def test_every_opening_traces_back_to_corpus(self) -> None:
        """标了「逐字取自原版」的开场白，必须真的能在语料里找到——不许自由创作。

        2026-09-25 的教训：「藤」「标签」「果霜」在原话里一次都没出现过。
        预设对话是人工写死的，写错了会永远留在那里，所以这条要机器守。

        2026-09-27 从「只查 day2 那一条」改成遍历全部场景：那天预设扩到 4 条
        （3 条季节触发），只守一条等于新写的三条全靠人眼 —— 而开场白恰恰是
        全部字段里最该守的一个（它是唯一由人手写、又被玩家逐字看到的东西）。
        比对也是逐条记录做的，不把同一角色的台词拼成一个大字符串，
        免得跨记录拼出来的「巧合命中」把自由创作放过去。

        ⚠ 2026-09-27 二次调整：**只守 `vanilla:` 来源的场景**。用户当天指出
        「你全是复用的现有对话当开场白的吗」—— 复用原话有两个解不掉的问题：
        素材上限等于游戏本体写过的句子数（spring 只有 27 条，填不满 28 天），
        而且玩家**已经在游戏里听过那些句子**。于是新增 `persona:` 来源，
        由 `TestCreatedOpenings` 用另一套规则守。**本源仍然守得很严**：
        标了 `vanilla:` 就必须真能追溯，想省事改标 `persona:` 会被下面那条
        来源合法性的检查抓住（见 `TestOpeningSourceIsDeclared`）。
        """
        store = MorningScenarioStore.load(REAL_DATA)
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

        checked = 0
        for scenario in store.scenarios:
            if not scenario.opening_source.startswith("vanilla:"):
                continue
            # ⚠ 取 `resolvedText` 优先，回退 `text`（2026-09-27 扩池子时发现）：
            # SVE / RomRas 角色的 `text` 是 **Content Patcher 的 i18n 模板**
            # （`{{i18n:Sophia.CharacterDialogue.061}}`），中文在 `resolvedText` 里，
            # 而 `text` 保留模板是**设计**（见 `corpus._apply_i18n_resolution`）。
            # 只认 `text` 的话，所有 mod 角色的开场白都会「查无此句」——
            # 而扩池子的候选里恰恰以 mod 角色为主。原版角色 `text` 本身就是中文，
            # `resolvedText` 为空，回退到 `text` 仍然正确。
            lines = [
                str(record.get("resolvedText") or record.get("text") or "")
                for record in payload["records"]
                if record.get("npcId") == scenario.npc_id
            ]
            assert lines, (
                f"{scenario.id}：语料里找不到 {scenario.npc_id} 的任何台词，无法核对"
            )
            # 取开场白里最长的几个片段逐一核对，避免整句比对被标点差异卡住
            fragments = [
                part.strip("。，？！！…… ")
                for part in scenario.opening.replace("？", "？|").replace("。", "。|").split("|")
                if len(part.strip()) >= 6
            ]
            assert fragments, f"{scenario.id}：开场白里没有可核对的长片段"
            missing = [
                part for part in fragments if not any(part in line for line in lines)
            ]
            assert not missing, (
                f"{scenario.id}（{scenario.npc_id}）这些片段在原话里找不到，"
                f"疑似自由创作：{missing}"
            )
            checked += 1
        vanilla_count = sum(
            1 for item in store.scenarios if item.opening_source.startswith("vanilla:")
        )
        assert checked == vanilla_count, (
            f"有 {vanilla_count - checked} 条 vanilla 来源的场景没被核对到 —— "
            "守卫写成 >= 1 的话，漏检和新场景都能悄悄通过"
        )

    def test_closing_hook_is_conditional_not_turn_counted(self) -> None:
        """收尾条件**不能写成「第 N 轮」**——模型数不清轮次。

        2026-09-26 云端实测（㊲）：原文案是「聊到第 2~3 轮时把话头交给玩家一次」，
        实际它在**玩家第一次回应时就把这个问题问掉了**，之后第 5、6 轮又开始抛新问题。
        收尾条件必须写成**玩家那边的信号**（他只回了一句应声、或者话已经说完），
        而不是「聊了几轮」——判据要落在模型能直接看到的东西上。

        另一半是**范本**：㊳ 的结论是「禁令单独用会削掉表达力（回复变短、还跑题），
        配上范本才恢复」。只写「不要用问句结尾」它不敢写，给一句例子才落地。

        ⚠ **但 2026-09-27 实测发现「给完整例句」这一步走过头了**：Alex 那条的
        `closingHook` 里写着「比如「我去跑两圈」」，云端生成时模型把它**原样当台词说了出来**
        （玩家说「我知道」，Alex 回「行啊，冬天出门确实得有点劲。**我先去跑两圈了**」）。
        这与 `direction` 的作者规则第①条（不要把可直接说出口的台词写进方向）是同一个坑，
        只是我当时以为 `closingHook` 是「给人看的元数据」就安全。

        ⇒ 范本的正确形态是**句式骨架**（带 `+` 占位符，内容必须由模型按角色自己填），
        不是**成品句子**。骨架既给了落脚点（模型敢展开），又没有可逐字照抄的东西。
        """

        store = MorningScenarioStore.load(REAL_DATA)
        scenario = store.for_day(2)
        assert scenario is not None
        hook = scenario.closing_hook
        assert not re.search(r"第\s*\d+", hook), (
            f"收尾条件里出现了轮次表述，模型数不清轮次：{hook}"
        )
        examples = re.findall(r"「([^」]+)」", hook)
        # ① 必须给落脚点：一个带占位符的句式骨架
        assert any("+" in item for item in examples), (
            f"收尾条件必须给一个句式骨架（只有禁令时模型会不敢展开）：{hook}"
        )
        # ② 且不得给成品句子 —— 完整台词会被模型原样说出来
        copied = [item for item in examples if "+" not in item and len(item) > 6]
        assert not copied, (
            f"收尾条件里出现了可直接照抄的成品台词，模型会把它当自己的话说出来：{copied}"
        )

    def test_closing_hook_matches_the_npc_pronoun(self) -> None:
        """收尾骨架里的自称必须跟角色性别一致。

        2026-09-27 事件后预设验证时发现：163 条里 **154 条写「他自己」，
        只有 9 条写「她自己」**。而 `vanilla.json` 里 36 个 persona 全都带
        `pronouns`，其中 14 个是 `she` —— 这 14 个角色共 63 条预设，
        有人改过其中 5 个角色的部分条目（9 条），剩下 54 条**全用「他自己」**，
        于是同一个角色身上两种写法并存（Abigail / Emily / Haley / Leah / Maru
        都是「两者兼有」）。

        这不是纯注释文案：`render_direction_card` 会把 `closing_hook` 放进
        `card["closing"]`，**模型看得到**。同类坑已经踩过一次 ——
        Alex 那条 `closingHook` 里的例句被模型原样当台词说了出来。

        判据取 persona 自己的 `pronouns`，**不另立一份性别名单**：
        名单会跟 persona 漂移，而 `pronouns` 是同一份数据源的字段。
        """

        # ⚠ 2026-10-02 扩源：SVE / Rasmodia 的 persona **不在** `vanilla.json` 里。
        # 原先只读 vanilla.json，第一批 SVE 晨间预设刚加进去时这里就红了 ——
        # 而那次红是**对的**：它正说明那些 npcId 的性别没被任何数据源覆盖。
        # 所以扩的是**覆盖面**，不是把断言放软。
        #
        # 覆盖顺序 = 字典字面量顺序，后写的赢：
        #   sve.json -> rasmodia.json -> vanilla.json
        #
        # ⚠ `vanilla.json` 必须放最后：`rasmodia.json` 把 `Wizard` 定义成 she
        # （那是女性版的法师），而 morning.json 里 Wizard 走的是原版男性线。
        # 若让 rasmodia 覆盖 vanilla，现有那几条 Wizard 预设会集体误判。
        # （`sve.json` 里 `Wizard` 的 pronouns 干脆是 `null`，同样得靠 vanilla 兜。）
        #
        # ⚠ **不并入 `female-bachelors.json`**：那是性别转换的**变体层**
        # （`Alex` 在那里是 she），而 morning.json 里的 Alex 是原版男性。
        # 把它并进来，现有的 Alex 预设会立刻判错。
        personas: dict = {}
        for _name in ("sve.json", "rasmodia.json", "vanilla.json"):
            personas.update(
                json.loads(
                    (ROOT / "data" / "personas" / _name).read_text(encoding="utf-8")
                )["personas"]
            )
        store = MorningScenarioStore.load(REAL_DATA)

        # ⚠ 先挡住「悄悄跳过」：不在 persona 表里的 npcId 会让下面的比对漏过它，
        # 而漏过的表现和「全部通过」一模一样（同 ㊾ 那次空集通过的教训）。
        used = {scenario.npc_id for scenario in store.scenarios}
        missing = sorted(used - set(personas))
        assert not missing, (
            f"这些 npcId 不在 data/personas/ 的任何 persona 文件里，"
            f"下面的比对会漏过它们：{missing}"
        )

        wrong = []
        for scenario in store.scenarios:
            pronouns = personas[scenario.npc_id].get("pronouns") or {}
            subject = str(pronouns.get("subject") or "").casefold()
            hook = scenario.closing_hook
            if subject == "she" and "他自己" in hook:
                wrong.append((scenario.id, scenario.npc_id, "他自己"))
            elif subject == "he" and "她自己" in hook:
                wrong.append((scenario.id, scenario.npc_id, "她自己"))
        assert not wrong, (
            f"收尾骨架的自称和角色性别不符（场景 id, npcId, 用错的词）：{wrong}"
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


class TestSeasonPool:
    """「整个季节」型**不再天天命中**，而是进池子按天数轮转（2026-09-27 用户口径）。

    改之前：`matches_season` 让一条 `{"kind":"season","season":"winter"}` 在冬季
    **每一天**都命中。如果某一季只有它一条，那就是**整个季节每天发同一句**。
    跨年更糟——`season_of()` 用 `(offset // 28) % 4`，第 2 年 spring_1 得到的
    仍是 `(spring, 1)`，于是第二年一字不差地重播。

    用户的原话是「不可能说第一年和第二年同一天触发同一个预设，这也太蠢了」。
    定下的做法是**池子轮换**（零 DLL 改动）：

        pool[(day_index - 1) % len(pool)]

    `day_index` 是**累计**天数（第 2 年 spring_1 = 113），所以取模天然跨年错开；
    池子越大撑得越久（313 条 ≈ 6 年不撞同一句）。

    另一条同样重要的选择：**池子按 `id` 排序，不按文件顺序**。模块既有原则是
    「文件顺序不该决定行为」，池子轮转尤其不能例外——否则往文件中间插一条预设，
    会把其后所有日期的排期整体挪位。
    """

    @staticmethod
    def _pool(tmp_path: Path, size: int, *, reverse: bool = False):
        items = [
            _scenario(
                id=f"pool-{index:02d}",
                npcId="Pierre",
                displayName="皮埃尔",
                opening=f"今天店里进了第 {index} 批货。",
                trigger={"kind": "season", "season": "winter"},
            )
            for index in range(size)
        ]
        return _store(tmp_path, list(reversed(items)) if reverse else items)

    def test_pool_never_repeats_within_one_season(self, tmp_path: Path) -> None:
        """冬季 28 天（85..112）应取到 28 条**互不相同**的预设。"""

        store = self._pool(tmp_path, 40)

        picked = [store.for_day(day).id for day in range(85, 113)]

        assert len(set(picked)) == 28

    def test_pool_does_not_replay_the_same_day_next_year(self, tmp_path: Path) -> None:
        """用户点名的那个问题：第 2 年 spring_1 不能和第 1 年撞。"""

        store = self._pool(tmp_path, 40)

        first_year = store.for_day(85)
        second_year = store.for_day(85 + 112)

        assert first_year is not None and second_year is not None
        assert first_year.id != second_year.id

    def test_pool_selection_ignores_file_order(self, tmp_path: Path) -> None:
        """同一批预设，文件里正序反序写，选中结果必须一致。"""

        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        forward = self._pool(tmp_path / "a", 40)
        backward = self._pool(tmp_path / "b", 40, reverse=True)

        assert [forward.for_day(d).id for d in range(85, 113)] == [
            backward.for_day(d).id for d in range(85, 113)
        ]

    def test_pool_cycles_when_smaller_than_the_season(self, tmp_path: Path) -> None:
        """池子比一季短时如实循环 —— 不报错、不返回 None。"""

        store = self._pool(tmp_path, 7)

        picked = [store.for_day(day) for day in range(85, 113)]

        assert all(item is not None for item in picked)
        assert len({item.id for item in picked}) == 7

    def test_dated_scenario_still_beats_the_pool(self, tmp_path: Path) -> None:
        """有日期约束的照旧优先，池子只填它没覆盖的日子。"""

        store = _store(
            tmp_path,
            [
                _scenario(
                    id="pool-a",
                    npcId="Pierre",
                    displayName="皮埃尔",
                    opening="冬天生意清淡啊。",
                    trigger={"kind": "season", "season": "winter"},
                ),
                _scenario(
                    id="festival-eve",
                    npcId="Abigail",
                    displayName="阿比盖尔",
                    opening="明天就是冬星节了，你准备礼物了吗？",
                    trigger={"kind": "season", "season": "winter", "dayInSeason": 24},
                ),
            ],
        )

        assert store.for_day(108).id == "festival-eve"   # 冬季第 24 天
        assert store.for_day(100).id == "pool-a"         # 冬季第 16 天，池子接手

    def test_pool_never_replays_when_its_size_divides_the_year(self, tmp_path: Path) -> None:
        """⚠ 池子大小整除 112 时最容易翻车 —— 而 28 正好整除。

        2026-09-27 实测：spring 凑到 28 条池子型之后，第 2 年的**每一天**
        都和第 1 年同一天一模一样。根因是 `112 = 4 × 28`，而 `offset` 里只有
        `dayIndex - 1` —— 跨年时它对 28 取模分毫不差地回到原位。

        这个坑之前没被发现，是因为既有的池子测试都用小池子（7 条、10 条），
        它们的 `112 % size` 不为 0，天然躲过。**得拿 112 的约数当池子大小才测得出。**
        """

        store = self._pool(tmp_path, 28)  # 28 = 112 ÷ 4，最坏情况

        # 池子的 trigger 是冬季（第 85–112 天），所以要拿冬季的日子验。
        for day in (85, 90, 100, 105, 112):
            this_year = store.for_day(day)
            next_year = store.for_day(day + 112)
            assert this_year is not None and next_year is not None
            assert this_year.id != next_year.id, (
                f"第 {day} 天与第 {day + 112} 天取到了同一条（{this_year.id}）——"
                "池子大小整除 112 时跨年会原样重播"
            )

    def test_pool_never_fires_on_day_one(self, tmp_path: Path) -> None:
        """第 1 天早上玩家还压在开场动画里，池子型也不能在那天冒出来。

        ⚠ 这条守的是**调度**，不是数据。池子型匹配整个季节，所以「整个春季」
        这个词天然覆盖第 1 天 —— 数据作者就算一个日期都没写错，第 1 天照样会
        冒出预设。2026-09-27 加第一条池子型预设时就是这么撞上的。
        """

        store = self._pool(tmp_path, 10)

        # 池子的 trigger 是冬季，所以要拿冬季的天数验；春季第 1 天只用来验排除。
        assert store.for_day(0) is None
        assert store.for_day(1) is None
        assert store.for_day(85) is not None

    def test_single_item_pool_behaves_exactly_as_before(self, tmp_path: Path) -> None:
        """退化情形：池子只有一条时，行为与改之前完全一致。

        这条是给既有两个用例（`test_season_alone_matches_the_whole_season`、
        `test_range_beats_whole_season`）兜底的 —— 它们能继续通过不是巧合，
        而是因为池子大小为 1 时 `% 1` 恒为 0。
        """

        store = self._pool(tmp_path, 1)

        assert store.for_day(85).id == "pool-00"
        assert store.for_day(112).id == "pool-00"
        assert store.for_day(85 + 112).id == "pool-00"


class TestCreatedOpenings:
    """`persona:` 来源的开场白 —— 2026-09-27 新增的第二条合法来源。

    用户当天问「你全是复用的现有对话当开场白的吗」，问出了原约束的一个混淆：
    **「不许编造语言指纹」和「开场白只能是游戏原话」是两件事**，被写成了一条。
    后果是素材上限 = 游戏本体在季节键里写过的句子数（spring 只有 27 条，
    撑不满 28 天），而且玩家**已经在游戏里听过那些句子** —— 复用原话必然撞车。

    拆开后，「逐字取自原版」照旧由 `test_every_opening_traces_back_to_corpus`
    严加追溯；本类守新来源，守的仍然是当初真正要守的东西：**不编造**。
    """

    @staticmethod
    def _created() -> list:
        store = MorningScenarioStore.load(REAL_DATA)
        return [s for s in store.scenarios if s.opening_source.startswith("persona:")]

    @staticmethod
    def _corpus_lines() -> dict[str, list[str]]:
        corpus = (
            ROOT
            / "artifacts"
            / "corpus"
            / "20260923-extra-dialogue"
            / "vanilla-sve-rasmodia-dialogue-corpus.json"
        )
        if not corpus.exists():  # pragma: no cover
            return {}
        payload = json.loads(corpus.read_text(encoding="utf-8"))
        grouped: dict[str, list[str]] = {}
        for record in payload["records"]:
            text = str(record.get("resolvedText") or record.get("text") or "")
            if text:
                grouped.setdefault(str(record.get("npcId") or ""), []).append(text)
        return grouped

    def test_every_scenario_declares_its_opening_source(self) -> None:
        """来源必须声明，且只能是这两种之一。

        这是**两套守卫的分流开关**：写个别的值，两边都会跳过它 ——
        等于一条开场白谁也不守。所以它自己也得被守。
        """

        allowed = ("vanilla:", "persona:")
        bad = [
            (item.id, item.opening_source[:40])
            for item in MorningScenarioStore.load(REAL_DATA).scenarios
            if not item.opening_source.startswith(allowed)
        ]
        assert not bad, (
            f"这些场景的 _openingSource 没有声明来源（必须是 "
            f"{' 或 '.join(allowed)} 开头），两套守卫都会漏过它们：{bad}"
        )

    def test_created_openings_carry_no_control_codes(self) -> None:
        """控制码是给游戏引擎读的，留在开场白里玩家会直接看到 `$h`。

        原话型的开场白靠「裁到第一个控制码之前」保证这点（见
        `scripts/extract_morning_candidates.py`）；创作型的没有那道工序，
        所以在这里单独守。
        """

        bad = [(item.id, _find_control_code(item.opening)) for item in self._created()
               if _find_control_code(item.opening)]
        assert not bad, f"创作型开场白里残留了控制码，会被玩家看到：{bad}"

    def test_created_openings_carry_no_i18n_templates(self) -> None:
        """`{{i18n:...}}` 是**没解析成功的模板**，玩家会原样看到这一串。"""

        bad = [item.id for item in self._created() if _find_i18n_template(item.opening)]
        assert not bad, f"创作型开场白里有未解析的 i18n 模板：{bad}"

    def test_created_openings_have_no_latin_letters(self) -> None:
        """中文对白里混进英文 id（`Abigail` 而不是「阿比盖尔」）是没翻译干净。"""

        bad = [(item.id, _find_latin(item.opening)) for item in self._created()
               if _find_latin(item.opening)]
        assert not bad, f"创作型开场白里混了英文标识：{bad}"

    def test_created_openings_are_not_verbatim_copies(self) -> None:
        """标了「创作」就不能是原话照搬 —— 否则是标错了来源。

        标错来源比写差一条开场白更麻烦：它会让「原话型必须可追溯」这条守卫
        形同虚设（谁都可以把照抄的句子标成 `persona:` 绕过追溯）。
        比对前去掉标点和空白，免得只差一个标点就蒙混过去。
        """

        grouped = self._corpus_lines()
        if not grouped:  # pragma: no cover
            pytest.skip("语料文件不存在")

        bad = []
        for item in self._created():
            squashed = _squash(item.opening)
            if not squashed:
                continue
            for line in grouped.get(item.npc_id, []):
                if squashed and squashed in _squash(line):
                    bad.append(item.id)
                    break
        assert not bad, (
            f"这些场景标了 persona: 来源，但开场白是原话照搬，"
            f"应该改标 vanilla: 并接受追溯检查：{bad}"
        )


class TestTheOpeningGuardsThemselves:
    """守守卫。

    `TestCreatedOpenings` 里那几条在这个数据文件上都是**空集通过** ——
    当前还没有 `persona:` 来源的场景，所以它们的判定逻辑一次都没真正执行过。
    空集通过是假绿：检查写反了、正则敲错了，测试照样一片绿。

    所以把判定抽成模块级函数，在这里喂**已知的坏输入**，确认它们真的会红。
    """

    @pytest.mark.parametrize(
        "opening, expected",
        [
            ("今天天气不错。", None),
            ("你看到我的新鞋了吗？", None),
            ("他说这话时笑了一下$h。", "$h"),
            ("这句里有分页#$b#符。", "#$b#"),
            ("事件分隔#$e#在这里。", "#$e#"),
            ("这是给@看的。", "@"),
            ("变体^分隔。", "^"),
            ("%noturn 不该出现。", "%noturn"),
        ],
    )
    def test_control_code_detector(self, opening: str, expected: str | None) -> None:
        found = _find_control_code(opening)
        assert found == expected

    @pytest.mark.parametrize(
        "opening, expected",
        [
            ("今天天气不错。", None),
            ("{{i18n:Abigail.Dialogue.01}}", "{{i18n:"),
            ("前缀 {{i18n:X}} 后缀", "{{i18n:"),
        ],
    )
    def test_i18n_template_detector(self, opening: str, expected: str | None) -> None:
        assert _find_i18n_template(opening) == expected

    @pytest.mark.parametrize(
        "opening, expected",
        [
            ("今天天气不错。", []),
            ("Abigail 说她明天要去镇上。", ["Abigail"]),
            ("我买了 Pierre 的种子。", ["Pierre"]),
            ("AI 这个词是白名单。", []),  # 两字母以下不算，且 AI 是既有的保留词
        ],
    )
    def test_latin_detector(self, opening: str, expected: list[str]) -> None:
        assert _find_latin(opening) == expected

    @pytest.mark.parametrize(
        "left, right, expected",
        [
            ("今天天气不错", "今天天气不错", True),
            ("今天天气不错。", "今天天气不错！", True),   # 只差标点也算照搬
            ("今天天气不错", "今天 天气 不错", True),     # 只差空白也算
            ("今天天气不错", "今天天气真好", False),      # 改了词就不算
            ("今天", "今天天气不错", True),               # 是子串也算
        ],
    )
    def test_verbatim_detector(self, left: str, right: str, expected: bool) -> None:
        assert (_squash(left) in _squash(right)) is expected


class TestDisplayNames:
    """预设里写的角色中文名，必须和游戏官方译名一致。

    2026-09-27 加第一批池子型预设时我凭记忆把 `Pam` 写成「帕姆」，
    从游戏解包数据里查出来官方是「潘姆」。这类错误靠记性防不住——
    而它一旦写进去，玩家在游戏里看到的就是错的名字。

    所以把官方译名固化进 `data/npc-display-names.json`（不直接读游戏目录：
    CI 或别的机器上不一定有解包后的游戏数据），在这里逐条比对。
    """

    @staticmethod
    def _table() -> dict[str, str]:
        path = ROOT / "data" / "npc-display-names.json"
        if not path.exists():  # pragma: no cover - 表是仓库文件，缺了说明被误删
            pytest.skip("译名表不存在")
        return dict(json.loads(path.read_text(encoding="utf-8"))["names"])

    def test_every_used_npc_has_an_official_name(self) -> None:
        """用到的 NPC 必须都在译名表里。

        ⚠ 这条不能省：下一条守卫只能比对**表里有的** NPC，
        一个不在表里的 npcId 会让它悄悄跳过 —— 又是空集通过。
        """

        names = self._table()
        used = {s.npc_id for s in MorningScenarioStore.load(REAL_DATA).scenarios}
        missing = sorted(n for n in used if n not in names)
        assert not missing, (
            f"这些 npcId 不在 data/npc-display-names.json 里，下面的比对会漏过它们：{missing}"
        )

    def test_display_names_match_the_game(self) -> None:
        names = self._table()
        bad = [
            (s.id, s.npc_id, s.display_name, names[s.npc_id])
            for s in MorningScenarioStore.load(REAL_DATA).scenarios
            if s.npc_id in names and s.display_name != names[s.npc_id]
        ]
        assert not bad, (
            "这些预设的 displayName 和游戏官方译名不一致（场景 id, npcId, 预设里写的, 官方）："
            f"{bad}"
        )
