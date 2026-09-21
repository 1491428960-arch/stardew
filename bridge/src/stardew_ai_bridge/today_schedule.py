"""L2b 今日安排的投影：把游戏端的当日日程压成 2–3 条「今天大概在忙什么」。

**数据来源**：SMAPI 侧 `GameStateCollector.ReadTodaySchedule` 读的
`NPC.Schedule`（游戏已按季节/星期/日期/天气/节日/好感/事件解析好的当天那一份），
地点名优先取 `GameLocation.DisplayName`（游戏内语言），取不到回退地图标识符。

**为什么压缩放在 Bridge 而不是 C#**：时段词表只有一份，在
`scene.py::time_of_day_label`。C# 侧再写一张就会立刻漂移（这正是本项目
「同概念多实现」审计反复抓到的模式），所以 C# 只做确定性整理，人话在这里生成。

**失效方向（写死在实现里）**：任何一步出问题都返回**空列表**，prompt 侧据此
**不发卡**。空列表等于「今天还没定下安排」，比一条编造的地点安全得多；
这个模块**不抛异常**。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .scene import time_of_day_label

#: 进 prompt 的条数上限。2–3 条足够讲清「一天的大致形状」，
#: 再多就变成把日程表念一遍——那既费预算，也会剧透到「几点在哪」的粒度。
MAX_ENTRIES = 3

#: 地点名长度上限（中文地点名通常 2–6 字；40 已在 C# 侧截过，这里再兜一层）。
LOCATION_LIMIT = 24

#: 星露谷 `timeOfDay` 的合法范围（与 `scene.py` 同一把尺子）。
MIN_TIME = 600
MAX_TIME = 2600

_ONLY_KEYS = ("time", "location")

#: 游戏端发来的**语义标记** → 中文。目前只有 `home`：日程里的 `bed`（回家睡觉）
#: 在 SMAPI 侧被转成这个标记（见 `TodayScheduleRules.HomeLocationMarker`）。
#: 它是**翻译**不是猜测——`bed` 的含义由游戏数据确定；用 `DefaultMap` 顶替会
#: 把「夜里在家」写成「夜里在哈维的诊所」（已婚 NPC 的 `DefaultMap` 仍记着原住址）。
_LOCATION_ALIASES = {
    "home": "家",
}

#: 没被 `_LOCATION_ALIASES` 命中、但语义明确的拼写也一并接受（旧版游戏端直发 `bed`）。
_LOCATION_ALIAS_FALLBACKS = {"bed": "家"}


def _entry(item: object) -> tuple[int, str] | None:
    """从一条原始条目里取出 `(time, location)`；形态不对或取值不可用时返回 None。

    只认 Mapping 与**带同名属性**的对象两种形态：`todaySchedule` 在 HTTP 上是 JSON
    数组，但离线用例、评测样本与将来的调用方可能直接传 Pydantic 模型或命名元组。
    """

    if isinstance(item, Mapping):
        raw_time = item.get("time")
        raw_location = item.get("location")
    else:
        if not all(hasattr(item, key) for key in _ONLY_KEYS):
            return None
        raw_time = getattr(item, "time", None)
        raw_location = getattr(item, "location", None)

    # `bool` 是 `int` 的子类，`True` 会被当成 1 通过 `isinstance` 检查——挡掉。
    if isinstance(raw_time, bool) or not isinstance(raw_time, int):
        return None
    if not MIN_TIME <= raw_time <= MAX_TIME:
        return None
    # 分钟位非法的取值（760 这种）不是星露谷的时间写法，`time_of_day_label` 也认不出。
    if raw_time % 100 > 59:
        return None

    if not isinstance(raw_location, str):
        return None
    location = raw_location.strip()
    if not location:
        return None

    folded = location.casefold()
    location = _LOCATION_ALIASES.get(
        folded, _LOCATION_ALIAS_FALLBACKS.get(folded, location)
    )

    return raw_time, location[:LOCATION_LIMIT]


def _normalise(entries: object) -> list[tuple[int, str]]:
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        return []

    parsed: list[tuple[int, str]] = []
    for item in entries:
        entry = _entry(item)
        if entry is not None:
            parsed.append(entry)
    if not parsed:
        return []

    # C# 侧已经排过序；这里再排一次是因为**旧版游戏端**或离线样本可能乱序，
    # 而「上午/下午/晚上」的顺序错了会让模型把一天讲反。
    # `list.sort` 稳定，所以同一时刻的两条仍保持原相对顺序。
    parsed.sort(key=lambda item: item[0])

    # 去重与合并放在**排序之后**：乱序输入下「相邻」才有意义，
    # 否则同一地点的两段会因为中间隔着一条更早的条目而漏合并。
    normalised: list[tuple[int, str]] = []
    for entry in parsed:
        if normalised and normalised[-1][0] == entry[0]:
            # 同一时刻登记了两段：保留先出现的那条（与 C# 侧 `TodayScheduleRules`
            # 同口径），避免同一时段出现两个地点。
            continue
        if normalised and normalised[-1][1] == entry[1]:
            # 相邻同地点合并：`900 葡萄园 / 1200 葡萄园` 是「从 9 点起一直在葡萄园」。
            continue
        normalised.append(entry)
    return normalised


def _duration(index: int, entries: list[tuple[int, str]]) -> int:
    """第 `index` 段持续了多久（用于「今天主要在忙什么」的取舍）。

    **最后一段恒为最大值**：夜里那一段通常最短（收尾、回家、睡觉），
    纯按时长排会被砍掉——而「晚上回到家」恰恰是最能体现作息感的一段。
    """

    if index >= len(entries) - 1:
        return MAX_TIME
    return max(1, entries[index + 1][0] - entries[index][0])


def _select(entries: list[tuple[int, str]], limit: int) -> list[tuple[int, str]]:
    """挑出最有信息量的几段：按停留时长降序，**每个地点只取一段**。

    地点去重对**所有**长度都生效，不只是超过 `limit` 的那种。真实数据里
    Abigail 的 spring 一天合并后正好三段 `杂货店/镇上/杂货店`——不去重就会输出
    「上午在杂货店、下午在镇上、下午在杂货店」，读起来像渲染 bug，
    而模型拿到的净信息只有两个地点。

    优先级由 `_duration` 决定：**最后一段恒为最大**，所以「一天的收尾在哪」
    总是先被保住（那通常就是回家），其余按停留时长排。

    去重可能让结果少于 `limit`（一天只去过两个地方），**不补齐**：
    「2 条准确的安排」比「3 条里有一条是重复地点」好。
    """

    if limit <= 0 or not entries:
        return []

    ranked = sorted(
        range(len(entries)),
        key=lambda index: (-_duration(index, entries), index),
    )

    keep: list[int] = []
    seen: set[str] = set()
    for index in ranked:
        if len(keep) >= limit:
            break
        location = entries[index][1]
        if location in seen:
            continue
        seen.add(location)
        keep.append(index)

    return [entries[index] for index in sorted(keep)]


def project_today_schedule(entries: object, *, limit: int = MAX_ENTRIES) -> list[str]:
    """把当日日程压成「上午在葡萄园」这样的短行。

    输入是 `gameState.todaySchedule` 的原始值（形态任意），输出是**可以直接进
    prompt 的中文短句列表**。取不到、形态不认识、时段词认不出来时返回 `[]`。
    """

    try:
        normalised = _normalise(entries)
        if not normalised:
            return []

        selected = _select(normalised, int(limit))
        lines: list[str] = []
        for time_value, location in selected:
            label = time_of_day_label(time_value, include_clock=False)
            if not label:
                # 认不出时段就不编一个：宁可少一条，也不要「在葡萄园」这种
                # 没有时间锚点的半句话。
                continue
            lines.append(f"{label}在{location}")
        return lines
    except Exception:  # noqa: BLE001 —— 见模块 docstring：这个函数不抛异常
        return []


#: 今日安排卡的说明。三个约束：
#:   ① 这是**计划快照**，会因天气/节日/事件临时变动，不能说成「一定」；
#:   ② 不得当成「此刻在哪」——它给的是时段粒度，不是实时坐标；
#:   ③ 不给精确钟点（本模块产出的行里本来就没有钟点，这条是防止模型自己补）。
_DAILY_CONTEXT_INSTRUCTION = (
    "这是今天的大致安排，是**计划快照**：可能因天气、节日或事件临时变动，"
    "只能说「今天大概/本来打算」。它只是时段粒度，**不是此时此刻的位置**"
    "——不要据此断言对方现在就在某处，也不要补出具体钟点；"
    "当前时间与地点以场景卡为准。话题不相关时不必主动报。"
)

#: `livesWithPlayer` 的说明。语义边界就一句话：**住处不等于行踪**。
_HOME_INSTRUCTION = (
    "「同住」只表示住处相同（配偶或室友），**不代表对方此刻在家**："
    "白天照样按自己的日程外出，只在夜里回屋；可以说「晚上回来」，"
    "但不要当成一直在家或刚从家出来。"
)

#: 两张子卡同时出现时，谁管「现在」这件事必须在卡里说清，否则模型会拿日程
#: 反推此刻位置——那正是这一层最容易出的错。
_PRECEDENCE_INSTRUCTION = (
    "同时有「今日安排」和「通常作息」时以今日安排为准；两者对不上就不要提作息。"
)


def build_daily_context_card(
    *,
    lives_with_player: object = None,
    today_schedule: object = None,
) -> dict[str, Any]:
    """组装 `daily_context` 卡的内容；没有任何可用数据时返回空字典（调用方据此不发卡）。

    `livesWithPlayer` 只在**明确为 True** 时才写进卡里：
    `False` 是「玩家有配偶/室友但不是这个 NPC」，模型知道这件事没有叙事价值，
    写出来反而容易被读成「关系疏远」；`None` 是未知，更不能写。
    """

    card: dict[str, Any] = {}
    instructions: list[str] = []

    if lives_with_player is True:
        card["同住"] = True
        instructions.append(_HOME_INSTRUCTION)

    plan = project_today_schedule(today_schedule)
    if plan:
        card["今日安排"] = plan
        instructions.append(_DAILY_CONTEXT_INSTRUCTION)

    if not card:
        return {}

    if len(instructions) > 1:
        instructions.append(_PRECEDENCE_INSTRUCTION)
    card["instruction"] = "".join(instructions)
    return card
