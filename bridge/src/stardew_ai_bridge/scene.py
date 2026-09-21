"""当前场景（季节/天气/时段）的共享语义标签。

这个模块存在的理由：场景硬事实此前在两个地方各写了一份、而且**只有一份进了 prompt**。

* `providers.py::FakeProvider._time_label` 把 `600 → "早上"`，
  但它只服务本地演示 provider，生产渲染路径（`prompts.PromptBuilder`）拿不到；
* 生产路径的 `game_state` 卡在紧凑模式下被整块跳过，
  于是游戏内模型看不到季节/日期/天气/时段/地点，
  而 `safety_rules` 却承诺「天气、时间和地点是当前场景的硬事实」。

所以这里把「场景语义」收敛成一处，供 `prompts` 与 `providers` 共用，
避免出现第二份会漂移的映射表。

**Stardew 的 `timeOfDay` 表示法**（`Game1.timeOfDay`，本项目 `smapi/` 侧直接透传整数）：

* 取值 `600 ~ 2600`，步进 10，按 `HHMM` 读，但**小时是 24 小时制且允许 ≥ 24**；
* `600` = 6:00，`1200` = 12:00，`1800` = 18:00；
* `2400` = 午夜 0:00、`2500` = 次日 1:00、`2600` = 次日 2:00 —— **2400 之后都跨到了次日**，
  这是星露谷自身的写法（游戏内 2:00 强制昏倒），不是数据错误。

跨日时段必须显式带「次日」，否则凌晨 2:00 会被模型读成下午的 2 点。
"""

from __future__ import annotations

from collections.abc import Mapping

# 季节：英文枚举（游戏端原始值）与游戏内已中文化的取值都要能认。
SEASON_LABELS: dict[str, str] = {
    "spring": "春天",
    "summer": "夏天",
    "fall": "秋天",
    "autumn": "秋天",
    "winter": "冬天",
    "春": "春天",
    "夏": "夏天",
    "秋": "秋天",
    "冬": "冬天",
}

# 天气：`clear` 是游戏端晴天的原始值（`Game1.weather_clear`），
# `sunny` / `sun` 见其它调用方与离线用例。
WEATHER_LABELS: dict[str, str] = {
    "sunny": "晴天",
    "sun": "晴天",
    "clear": "晴天",
    "cloudy": "阴天",
    "clouds": "阴天",
    "overcast": "阴天",
    "rain": "雨天",
    "rainy": "雨天",
    "storm": "雷雨天",
    "stormy": "雷雨天",
    "lightning": "雷雨天",
    "wind": "有风的天气",
    "windy": "有风的天气",
    "snow": "雪天",
    "snowy": "雪天",
    "festival": "节日天气",
    "晴": "晴天",
    "阴": "阴天",
    "雨": "雨天",
    "雷": "雷雨天",
    "雪": "雪天",
    "风": "有风的天气",
}

# 时段切分表：`(下界含, 上界含, 标签)`，**降序**排列，取第一个满足 `time_value >= 下界` 的项。
#
# 上界只用于自我说明，判定本身只看下界——这样 600–2600 全范围**无缝覆盖**：
# `760` 这类非 10 倍数的取值会落进「清晨」，而不会掉进闭区间的缝隙里
# （星露谷的 `timeOfDay` 步进是 10，但没必要让边界外的取值丢失时段）。
_SEGMENTS: tuple[tuple[int, int, str], ...] = (
    (2400, 2600, "凌晨"),  # 次日 0:00–2:00（2400 在星露谷表示午夜 0:00）
    (2200, 2350, "深夜"),  # 22:00–23:50
    (1900, 2150, "晚上"),  # 19:00–21:50
    (1700, 1850, "傍晚"),  # 17:00–18:50
    (1300, 1650, "下午"),  # 13:00–16:50
    (1100, 1250, "中午"),  # 11:00–12:50
    (800, 1050, "上午"),  # 8:00–10:50
    (600, 750, "清晨"),  # 6:00–7:50
)

_MAX_TIME_OF_DAY = 2600
_MIN_TIME_OF_DAY = 600


def normalise_label(
    value: object,
    mapping: Mapping[str, str],
) -> str | None:
    """把游戏端原始枚举（或已中文化的取值）归一成中文标签；认不出就返回 None。

    与 `providers.py` 此前的匹配口径一致：先全词精确匹配，再退化为子串匹配
    （容忍 `Game1.weather_clear` 这类前缀写法）。**不做猜测性兜底**——
    未知值返回 None，由调用方决定是原样透传还是丢弃，免得把英文枚举当中文发出去。
    """

    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    if not normalized:
        return None
    if normalized in mapping:
        return mapping[normalized]
    for marker, label in mapping.items():
        if marker in normalized:
            return label
    return None


def season_label(value: object) -> str | None:
    """季节 → 中文标签（`spring` → `春天`）。"""

    return normalise_label(value, SEASON_LABELS)


def weather_label(value: object) -> str | None:
    """天气 → 中文标签（`clear` → `晴天`）。"""

    return normalise_label(value, WEATHER_LABELS)


def _clock_text(hour: int, minute: int) -> str:
    return f"{hour}:{minute:02d}"


def time_of_day_label(
    time_value: object,
    *,
    include_clock: bool = True,
) -> str | None:
    """`timeOfDay` 整数 → 人类可读时段（`600` → `清晨（6:00）`）。

    `include_clock=False` 只给时段词（`清晨`），用于「现在是清晨」这类行文里，
    避免在人读的演示文案中塞进括号时间。

    无法解释的输入（None / 非整数 / 超出 600–2600 / 分钟位非法如 `760`）返回 None，
    由调用方决定是否回落到原始值——**不编造时段**，也不产出 `7:60` 这种不存在的时刻。
    """

    if isinstance(time_value, bool) or not isinstance(time_value, int):
        return None
    if not _MIN_TIME_OF_DAY <= time_value <= _MAX_TIME_OF_DAY:
        return None

    hour, minute = divmod(time_value, 100)
    if minute > 59:  # `760` 之类：不是合法的 HHMM
        return None
    # 2400 起是次日：星露谷把 0:00 写成 2400、次日 2:00 写成 2600。
    next_day = hour >= 24
    hour_24 = hour - 24 if next_day else hour

    label = next(
        (segment_label for lower, _upper, segment_label in _SEGMENTS
         if time_value >= lower),
        None,
    )
    if label is None:  # 表未覆盖（低于 600 的取值）
        return None

    if include_clock:
        clock = _clock_text(hour_24, minute)
        return f"次日{label}（{clock}）" if next_day else f"{label}（{clock}）"
    return f"次日{label}" if next_day else label
