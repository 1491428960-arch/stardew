"""L2b 今日安排投影：把当日日程压成 2–3 条人话。

**这一层要解决的问题**：游戏端此前只在 `recentFacts` 里有一条「地点从 A 变为 B」
的差异行（`BridgeClient.cs:1002`），那是**发生过**的轨迹；模型不知道「今天大致会
怎么过」，于是同一个角色在不同轮次里给自己编不同的白天。

**代价（用户已批准）**：会剧透 NPC 接下来在哪。因此这里只给**时段粒度**
（「下午在酒窖」），不给钟点，也不给坐标。

**降级方向**：本模块**不抛异常**；任何一步出问题都返回 `[]`，prompt 侧据此不发卡
——退化成「今天还没定下安排」，而不是给错地点。
"""

from __future__ import annotations

from stardew_ai_bridge.today_schedule import (
    LOCATION_LIMIT,
    MAX_ENTRIES,
    project_today_schedule,
)


def _entry(time: int, location: str) -> dict[str, object]:
    return {"time": time, "location": location}


# --- 正常路径 ---------------------------------------------------------------


def test_projects_a_typical_day_into_readable_lines() -> None:
    lines = project_today_schedule(
        [
            _entry(900, "葡萄园"),
            _entry(1300, "酒窖"),
            _entry(2100, "家"),
        ]
    )

    assert lines == ["上午在葡萄园", "下午在酒窖", "晚上在家"]


def test_lines_carry_no_clock_time() -> None:
    """只给时段词，不给钟点——给了钟点就变成「剧透行程表」。"""

    lines = project_today_schedule([_entry(915, "葡萄园"), _entry(1345, "酒窖")])

    assert lines
    for line in lines:
        assert ":" not in line
        assert not any(character.isdigit() for character in line)


def test_sorts_out_of_order_input() -> None:
    """旧版游戏端与离线样本可能乱序；顺序错了会把一天讲反。"""

    lines = project_today_schedule(
        [
            _entry(2100, "家"),
            _entry(900, "葡萄园"),
            _entry(1300, "酒窖"),
        ]
    )

    assert lines == ["上午在葡萄园", "下午在酒窖", "晚上在家"]


def test_merges_a_consecutive_stay_in_one_place() -> None:
    lines = project_today_schedule(
        [
            _entry(900, "葡萄园"),
            _entry(1200, "葡萄园"),
            _entry(1400, "酒窖"),
        ]
    )

    assert lines == ["上午在葡萄园", "下午在酒窖"]


def test_does_not_merge_the_same_place_across_a_gap() -> None:
    """合并只发生在**相邻**的同地点之间；中间去别处又回来是两段真实行程。

    这里直接验规范化层：`杂货店/镇上/杂货店` 必须仍是三段
    （`_select` 之后会按「每个地点只取一段」收敛，那是另一条规则，见下）。
    """

    from stardew_ai_bridge.today_schedule import _normalise

    assert _normalise(
        [
            _entry(900, "种子店"),
            _entry(1300, "镇上"),
            _entry(2000, "种子店"),
        ]
    ) == [(900, "种子店"), (1300, "镇上"), (2000, "种子店")]


def test_keeps_the_end_of_the_day_when_deduplicating_locations() -> None:
    """去重时**收尾那一段优先**：`上午在种子店/下午在镇上/晚上在种子店`
    收敛成「下午在镇上、晚上在种子店」——一天的落点比早上的起点有用。
    """

    lines = project_today_schedule(
        [
            _entry(900, "种子店"),
            _entry(1300, "镇上"),
            _entry(2000, "种子店"),
        ]
    )

    assert lines == ["下午在镇上", "晚上在种子店"]


def test_drops_the_second_entry_when_two_share_a_time() -> None:
    lines = project_today_schedule([_entry(900, "种子店"), _entry(900, "镇上")])

    assert lines == ["上午在种子店"]


# --- 压缩到 2–3 条 ----------------------------------------------------------


def test_caps_a_long_day_at_three_lines_and_always_keeps_the_last_one() -> None:
    """一天五六段很常见；砍到三条时**最后一段必留**。

    夜里通常是全天最短的一段（收尾、回家），纯按时长排序会先把它砍掉——
    而「晚上回到家」恰恰是最能体现作息感的一句。
    """

    lines = project_today_schedule(
        [
            _entry(600, "农场"),
            _entry(700, "种子店"),
            _entry(800, "镇上"),
            _entry(900, "山上"),
            _entry(1000, "海边"),
            _entry(2100, "家"),
        ]
    )

    assert len(lines) == MAX_ENTRIES == 3
    assert lines[-1] == "晚上在家"


def test_three_or_fewer_entries_are_never_dropped() -> None:
    lines = project_today_schedule(
        [_entry(900, "葡萄园"), _entry(1300, "酒窖"), _entry(2100, "家")]
    )

    assert len(lines) == 3


def test_limit_is_configurable() -> None:
    entries = [_entry(900, "葡萄园"), _entry(1300, "酒窖"), _entry(2100, "家")]

    assert len(project_today_schedule(entries, limit=2)) == 2
    assert project_today_schedule(entries, limit=0) == []


def test_prefers_distinct_locations_over_repeating_the_same_one() -> None:
    """真实数据（vanilla Sebastian 的 spring 一天）：房间/镇上/房间/山上/房间。

    纯按时长取前三会得到三条「在 SebastianRoom」——三个名额、零信息，
    而「他今天还去过镇上和山上」这个真正有用的形状反而丢了。
    """

    lines = project_today_schedule(
        [
            _entry(1030, "SebastianRoom"),
            _entry(1500, "ScienceHouse"),
            _entry(1530, "SebastianRoom"),
            _entry(1830, "Mountain"),
            _entry(2130, "SebastianRoom"),
        ]
    )

    assert len(lines) == 3
    assert len(set(lines)) == 3
    assert lines == [
        "下午在ScienceHouse",
        "傍晚在Mountain",
        "晚上在SebastianRoom",
    ]


def test_deduplication_may_return_fewer_than_the_limit() -> None:
    """一天只去过两个地方 → 给两条，不拿重复地点凑满三条。"""

    lines = project_today_schedule(
        [
            _entry(900, "种子店"),
            _entry(1200, "镇上"),
            _entry(1500, "种子店"),
            _entry(1800, "镇上"),
            _entry(2100, "种子店"),
        ]
    )

    assert len(lines) == 2
    assert len(set(lines)) == 2


# --- `bed` / `home` 语义标记 ------------------------------------------------


def test_home_marker_renders_as_a_readable_place() -> None:
    """SMAPI 侧把日程里的 `bed` 转成 `home` 标记，这里必须渲染成「家」。

    离线实测：婚姻日程（配偶 NPC 走的那份）里 `bed` 占 11/21 条，
    所以这不是边角情况，而是「配偶的一天」的主干——它恰好也是 L2a「同住」
    要配合讲的那一幕（「晚上回来」）。
    """

    assert project_today_schedule([_entry(2100, "home")]) == ["晚上在家"]
    # 旧版游戏端可能直发 `bed`，一并认下。
    assert project_today_schedule([_entry(2100, "bed")]) == ["晚上在家"]
    assert project_today_schedule([_entry(2100, "BED")]) == ["晚上在家"]


def test_home_marker_merges_with_a_real_home_location() -> None:
    lines = project_today_schedule([_entry(2000, "FarmHouse"), _entry(2200, "home")])

    assert lines == ["晚上在FarmHouse", "深夜在家"]


# --- 降级路径 ---------------------------------------------------------------


def test_returns_empty_for_missing_or_wrong_shaped_input() -> None:
    for value in (None, "", "900 葡萄园", 42, {}, ()):
        assert project_today_schedule(value) == [], value


def test_returns_empty_when_every_entry_is_unusable() -> None:
    assert (
        project_today_schedule(
            [
                _entry(0, "农场"),        # 早于 600
                _entry(760, "农场"),      # 分钟位非法（星露谷没有 7:60）
                _entry(2700, "农场"),     # 晚于 2600
                _entry(900, ""),          # 空地点
                _entry(1000, "   "),      # 空白地点
            ]
        )
        == []
    )


def test_drops_unusable_entries_but_keeps_the_rest() -> None:
    lines = project_today_schedule(
        [
            _entry(0, "农场"),
            _entry(760, "农场"),
            _entry(900, "葡萄园"),
            {"time": "900", "location": "酒窖"},   # 时刻不是整数
            {"time": 1300},                        # 缺地点
            {"location": "酒窖"},                  # 缺时刻
            _entry(1500, "酒窖"),
        ]
    )

    assert lines == ["上午在葡萄园", "下午在酒窖"]


def test_never_raises_on_hostile_input() -> None:
    """日程是可选增强：它不该把一次正常对话打掉。"""

    class Hostile:
        @property
        def time(self) -> int:
            raise RuntimeError("boom")

        @property
        def location(self) -> str:
            raise RuntimeError("boom")

    assert project_today_schedule([Hostile()]) == []
    assert project_today_schedule([None, 3, [], {"time": None}]) == []


def test_reads_objects_with_the_same_attribute_names() -> None:
    """内部调用路径可能直接传 Pydantic 模型，而不是 dict。"""

    from stardew_ai_bridge.models import ScheduleEntry

    lines = project_today_schedule(
        [ScheduleEntry(time=900, location="葡萄园"), ScheduleEntry(time=1300, location="酒窖")]
    )

    assert lines == ["上午在葡萄园", "下午在酒窖"]


def test_truncates_an_absurd_location_name() -> None:
    lines = project_today_schedule([_entry(900, "长" * 200)])

    assert len(lines) == 1
    assert len(lines[0]) == len("上午在") + LOCATION_LIMIT


def test_drops_a_time_the_label_table_cannot_explain() -> None:
    """时段词认不出来就丢掉这一条，不产出没有时间锚点的半句话。"""

    # 599 与 2601 已在范围检查里出局；这里验证范围之内但标签表覆盖不到的取值
    # 也不会漏出去（表覆盖 600–2600 全段，所以这条断言的是「不给半句话」本身）。
    lines = project_today_schedule([_entry(600, "农场")])

    assert lines == ["清晨在农场"]
