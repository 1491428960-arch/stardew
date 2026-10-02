"""晨间预设对话：NPC 在早上主动发来的第一段话，以及这段对话该怎么发展。

## 它解决什么

日常对话在换 Kimi 之后质量已经不低，但玩家进游戏、坐下、想聊，**不知道接什么**。
`conversation_lead` 已经能让 NPC 在**回答之后**主动推进，但它解决的是「聊起来之后」；
**从 0 到 1 那一步没人管**——玩家不开口，就没有那一轮。

所以这里的定位是**点火，不是救场**：给一段有内容的开场 + 一个容易接的口子。

## 约束强度：中档（2026-09-26 与用户敲定）

- **强档**（每句写死、玩家选选项）⇒ 变成视觉小说，玩家一偏离就崩；
- **中档**（本模块）⇒ 开场写死，方向与边界写明，收尾条件写明，**中间的话交给模型**；
- **弱档**（只写开场）⇒ 等于没有约束，就是用户试下来「效果不理想」的那一档。

## 两条硬约束（都是踩过的）

1. **开场白要么逐字取自角色原话，要么是贴合其语言指纹的创作 —— 但绝不许编造具体事物。**
   2026-09-25 查出 `dailyRoutine` 里的「藤」「标签」「果霜」在 519 条原话里
   **一次都没出现**——那是我推断的农活，不是她的语言指纹。
   预设对话是**人工写死的**，所以这条比运行时更危险：写错了会永远写在那里。

   **2026-09-27 拆成两条来源**（用户问「你全是复用的现有对话当开场白的吗」）：

   | `_openingSource` 标注 | 守卫怎么查 |
   |---|---|
   | 「逐字取自原版」 | **真的去语料里追溯**每一条开场白 |
   | 「基于 persona 创作」 | 查人名白名单 + 不编造具体事物 |

   **为什么必须拆**：原约束把「不许编造语言指纹」和「开场白只能是游戏原话」
   混成了一件事，而这是两条不同的要求。混起来的后果有两个，第二个更严重：

   - **素材上限 = 游戏本体在季节键里写过的句子数。** spring 只有 27 条，
     连 28 天都填不满，「季节内不重复」这个最低要求都达不到。
   - **玩家已经在游戏里听过那些句子。** 把 Abigail 夏天第一天说的
     「夏天来了。我可不喜欢这个季节。」当晨间开场，重复感不只来自跨年，
     更来自**和游戏本体撞车**——而这是复用无法回避的。

   拆开之后，守卫守的仍然是当初真正要守的东西：**不编造**。
   它只是不再把「原创」误判成「编造」。

2. **约束必须是独立卡，不能埋进别的 JSON。** ㉛ 实测：话题深度槽位埋进
   `stage_execution_card` 的大 JSON 里**被无视**，提成独立卡才生效。

## 为什么按「节点」组织而不是按角色

「谁在哪天发」是**调度**，不是角色属性。同一个角色在不同节点要发不同内容，
而节点（第一天、节日、季节更替）是全局的。所以数据放 `data/scenarios/morning.json`，
不塞进 `personas/*.json`。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


class MorningScenarioError(ValueError):
    """预设数据不合法。**加载期报错，不留到运行期**——写错的内容会一直写在那里。"""


@dataclass(frozen=True)
class MorningScenario:
    """一条晨间预设：她说什么、这段对话往哪走。"""

    id: str
    npc_id: str
    display_name: str
    opening: str
    direction: str
    boundaries: tuple[str, ...] = ()
    closing_hook: str = ""
    allowed_kinds: tuple[str, ...] = ()
    trigger: Mapping[str, Any] = field(default_factory=dict)
    # 开场白的**原话出处**（数据文件里的 `_openingSource`）。
    # 它不参与运行，只给游戏外测试页审阅用：这句话写死在文件里，
    # 得让人一眼看出它是从哪条原话来的——见模块 docstring 硬约束第 1 条。
    opening_source: str = ""

    @property
    def day_index(self) -> int | None:
        """绝对天数触发（`kind == "absoluteDay"`）时的天数；其他触发返回 None。"""
        if str(self.trigger.get("kind") or "") != "absoluteDay":
            return None
        value = self.trigger.get("dayIndex")
        return value if isinstance(value, int) else None

    @property
    def event_id(self) -> str | None:
        """事件后触发（`kind == "event"`）对应的事件 ID；其他触发返回 None。

        ⚠ **不做 casefold**：`EventAuditRules` 的契约要求事件 ID 大小写敏感
        （`"A"` 与 `"a"` 是两个不同的事件），这与 NPC ID 忽略大小写**恰好相反** ——
        合并昵称无害，合并事件 ID 会掩盖真实差异。
        """
        if str(self.trigger.get("kind") or "") != "event":
            return None
        value = str(self.trigger.get("eventId") or "").strip()
        return value or None

    def matches_season(self, season: str, day_in_season: int) -> bool:
        """这条预设是否命中给定的「季节 + 季节内第几天」。

        `trigger` 允许三种写法，后两者可省略（省略 = 整个季节都命中）：

            {"kind": "season", "season": "spring", "dayInSeason": 3}
            {"kind": "season", "season": "winter",
             "minDayInSeason": 1, "maxDayInSeason": 7}
            {"kind": "season", "season": "fall"}

        类型判断都排除 `bool`：JSON 里的 `true` 在 Python 里是 `int` 的子类，
        不挡住的话 `dayInSeason: true` 会被当成「第 1 天」静默生效。
        """
        if str(self.trigger.get("kind") or "") != "season":
            return False
        if str(self.trigger.get("season") or "").strip().casefold() != season:
            return False
        exact = self.trigger.get("dayInSeason")
        if isinstance(exact, int) and not isinstance(exact, bool) and exact != day_in_season:
            return False
        low = self.trigger.get("minDayInSeason")
        if isinstance(low, int) and not isinstance(low, bool) and day_in_season < low:
            return False
        high = self.trigger.get("maxDayInSeason")
        if isinstance(high, int) and not isinstance(high, bool) and day_in_season > high:
            return False
        return True

    @property
    def season_specificity(self) -> int:
        """季节触发的特异性：**精确日 3 > 日期范围 2 > 整个季节 1**；非季节触发 0。

        为什么要算这个：同一天可能同时命中多条（一条「春天来了」的泛季节预设，
        一条 `spring_12` 的节日前台词）。谁写在文件前面纯属编辑偶然，
        语义上必须更具体的那条赢 —— **文件顺序不该决定行为**。
        """
        if str(self.trigger.get("kind") or "") != "season":
            return 0
        for key in ("dayInSeason", "minDayInSeason", "maxDayInSeason"):
            value = self.trigger.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return 3 if key == "dayInSeason" else 2
        return 1


def _require_text(value: object, *, scenario_id: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise MorningScenarioError(
            f"预设 {scenario_id!r} 的 {field_name} 不能为空"
        )
    return text


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(
            str(item).strip()
            for item in value
            if isinstance(item, (str, int, float)) and str(item).strip()
        )
    return ()


#: 星露谷历法：1 季 28 天、1 年 4 季。
#: **季节不需要游戏端另送字段** —— `DayStarted` 的 `dayIndex` 就够推出来。
_SEASON_LENGTH = 28
_SEASONS = ("spring", "summer", "fall", "winter")
#: 合法的触发方式。**未知 `kind` 一律在加载期报错**（见 `_validate_trigger`）：
#: 拼错 kind 的后果是「这条预设永远不触发」，且不像季节拼错那样能被察觉。
_TRIGGER_KINDS = frozenset({"absoluteDay", "season", "event"})
#: 一年 112 天（4 季 × 28 天）。`TotalDays` 是**跨年累加**的，池子轮转要靠它
#: 算出「第几年」——否则池子大小一旦整除 112，跨年就会原样重播（见 `for_day`）。
_DAYS_PER_YEAR = _SEASON_LENGTH * len(_SEASONS)


def season_of(day_index: int) -> tuple[str, int]:
    """人话天数（第 1 天 = 第 1 年春季第 1 天）→ `(季节, 季节内第几天)`。

    **为什么需要它**：`MorningPlanRequest` 刻意只有 `dayIndex` 与 `knownNpcIds`
    两个字段（`ApiModel` 是 `extra="forbid"`，游戏端多送一个字段就是 422），
    而季节完全能从天数推出来 —— 于是「季节触发」这一层能扩事件库，
    **一行 DLL 契约都不用动**。好感度 / 节日 / 事件后触发才需要另开端点。

    非正数按第 1 天处理：`dayIndex` 是 0 基计数器（`ge=0`），
    端点换算成「人话天数」时要减 1，边界上会落到 0。
    """
    offset = max(0, int(day_index) - 1)
    return (
        _SEASONS[(offset // _SEASON_LENGTH) % len(_SEASONS)],
        offset % _SEASON_LENGTH + 1,
    )


def _validate_trigger(value: object, *, scenario_id: str) -> None:
    """`trigger` 写错必须**在加载期**炸掉。

    季节名拼错（`"autumn"` 而不是 `"fall"`）在游戏里的表现是
    「这条预设永远不触发」—— 静默，而且离现场很远。加载期报错离现场只有一次重启。

    ⚠ 2026-09-27 加事件型时发现 `kind` 本身写错更隐蔽：原先的写法是
    「不等于 `season` 就 `return`」，于是 `{"kind": "even"}` 这种手误会被
    **原样放行**，然后在 `for_day` 里被所有分支忽略 —— 症状和没写这条预设
    完全一样，却连一条日志都没有。现在未知 `kind` 一律报错。
    """
    if not isinstance(value, Mapping):
        return
    kind = str(value.get("kind") or "").strip()
    if kind not in _TRIGGER_KINDS:
        raise MorningScenarioError(
            f"预设 {scenario_id!r} 的 trigger.kind 必须是 "
            f"{'/'.join(sorted(_TRIGGER_KINDS))} 之一，收到 {value.get('kind')!r}"
        )
    if kind == "season":
        season = str(value.get("season") or "").strip().casefold()
        if season not in _SEASONS:
            raise MorningScenarioError(
                f"预设 {scenario_id!r} 的 trigger.season 必须是 "
                f"{'/'.join(_SEASONS)} 之一，收到 {value.get('season')!r}"
            )
        return
    if kind == "event":
        # 缺 eventId 的事件型和拼错 kind 一样：永远不触发，且毫无提示。
        if not str(value.get("eventId") or "").strip():
            raise MorningScenarioError(
                f"预设 {scenario_id!r} 的 trigger.eventId 不能为空"
            )


def parse_scenario(raw: Mapping[str, Any]) -> MorningScenario:
    """把一条原始记录解析成 `MorningScenario`，不合法就抛错。"""
    scenario_id = _require_text(raw.get("id"), scenario_id="<unknown>", field_name="id")
    trigger = raw.get("trigger")
    _validate_trigger(trigger, scenario_id=scenario_id)
    return MorningScenario(
        id=scenario_id,
        npc_id=_require_text(raw.get("npcId"), scenario_id=scenario_id, field_name="npcId"),
        display_name=_require_text(
            raw.get("displayName"), scenario_id=scenario_id, field_name="displayName"
        ),
        opening=_require_text(raw.get("opening"), scenario_id=scenario_id, field_name="opening"),
        direction=_require_text(
            raw.get("direction"), scenario_id=scenario_id, field_name="direction"
        ),
        boundaries=_text_tuple(raw.get("boundaries")),
        closing_hook=str(raw.get("closingHook") or "").strip(),
        allowed_kinds=_text_tuple(raw.get("allowedKinds")),
        trigger=dict(trigger) if isinstance(trigger, Mapping) else {},
        opening_source=str(raw.get("_openingSource") or "").strip(),
    )


class MorningScenarioStore:
    """`data/scenarios/morning.json` 的只读视图。

    文件不存在时是**空库而不是错误**：预设是可选内容，
    没有它时整条链路应该照常工作（退化成现在的行为）。
    """

    def __init__(self, scenarios: Sequence[MorningScenario] = ()) -> None:
        self._scenarios = tuple(scenarios)

    def __len__(self) -> int:
        return len(self._scenarios)

    @property
    def scenarios(self) -> tuple[MorningScenario, ...]:
        return self._scenarios

    @classmethod
    def load(cls, path: Path | str) -> MorningScenarioStore:
        target = Path(path)
        if not target.exists():
            return cls()
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MorningScenarioError(f"无法读取预设文件 {target}：{exc}") from exc
        if not isinstance(payload, Mapping):
            raise MorningScenarioError(f"{target} 顶层必须是对象")
        raw_items = payload.get("scenarios") or []
        if not isinstance(raw_items, Sequence):
            raise MorningScenarioError(f"{target} 的 scenarios 必须是数组")
        parsed = [
            parse_scenario(item)
            for item in raw_items
            if isinstance(item, Mapping)
        ]
        seen: set[str] = set()
        for scenario in parsed:
            if scenario.id in seen:
                raise MorningScenarioError(f"预设 id 重复：{scenario.id}")
            seen.add(scenario.id)
        _reject_duplicate_openings(parsed)
        return cls(parsed)

    def for_day(
        self, day_index: int, recent_event_ids: Sequence[str] = ()
    ) -> MorningScenario | None:
        """按天数取预设：**事件后 > 绝对天数 > 有日期约束的季节 > 季节池轮转**。

        四级「越具体越优先」的理由相同：`absoluteDay` 的「第 2 天」是一次性节点、
        季节规则每年都命中，让季节抢走它那条预设就形同虚设；同理季节内部
        「第 12 天」也比「整个春季」具体。**排序只由语义决定，不由文件顺序决定** ——
        否则某天发哪条会取决于编辑时把哪段粘贴在前面。

        ## 事件后为什么排在最前面

        事件只会发生一次，日历每年都会再来。玩家昨天刚走完某段剧情，那是他眼下
        最具体的东西，比「今天几号」更该被提起来。让日历赢会**永久浪费**掉这条 ——
        它等不到下一次机会。

        `recent_event_ids` 由游戏端送来（`MorningPlanRequest.recentEventIds`），
        Bridge **推不出来**：`completedEventIds` 是**累积全集**，不含完成时间。
        默认空元组，所以不传信号的调用方（测试、离线脚本）行为与从前完全一致。

        ⚠ 这里**只做精确字符串比较**，不 casefold —— 见 `event_id` 属性。

        ## 第三级为什么是「轮转」而不是「直接返回」

        2026-09-27 用户指出：「不可能说第一年和第二年同一天触发同一个预设，
        这也太蠢了」。查下来比表面更糟 —— 原先「整个季节」型（不带日期字段）
        在 `matches_season` 里是**季节内每天都命中**，某季若只有它一条，
        就是**整个季节每天发同一句**。

        改成池子轮转：

            pool[(day_index - 1) % len(pool)]

        `day_index` 是**累计**天数（第 2 年 spring_1 = 113），所以取模天然跨年错开。
        池子越大撑得越久：313 条素材约 6 年不撞同一句。

        **按 `id` 排序**取池子，不按文件顺序 —— 否则往文件中间插一条，
        会把其后所有日期的排期整体挪位。这条与上面「文件顺序不该决定行为」
        是同一条原则。

        ⚠ 局限：这条路只保证**不撞同一天**，玩满池子容量后仍会重见。
        彻底的解法是游戏端回传「已用过的场景」，那需要改 DLL 契约，
        已定为后续升级（用户 2026-09-27 拍板）。
        """
        # 第 1 天早上玩家还压在开场动画里、根本没在镇上过夜，所以任何
        # 「早上好」都落不到实处（`data/scenarios/morning.json` 里 `day2-lewis`
        # 的 `_comment` 记着这个理由）。
        #
        # ⚠ **这条由调度自己守，不能指望数据作者记得避开。** 池子型匹配整个季节，
        # 必然包含第 1 天 —— 2026-09-27 加第一条池子型预设时就撞上了：
        # 场景数据本身没写错日期，是「整个春季」这个词覆盖了第 1 天。
        if int(day_index) <= 1:
            return None
        # 事件后触发排在最前面（理由见 docstring）。按 id 排序取第一条，
        # 保证「一天完成多个事件」时的结果与文件顺序无关。
        signals = {str(value).strip() for value in recent_event_ids if str(value).strip()}
        if signals:
            after_events = sorted(
                (
                    scenario
                    for scenario in self._scenarios
                    if scenario.event_id is not None and scenario.event_id in signals
                ),
                key=lambda scenario: scenario.id,
            )
            if after_events:
                return after_events[0]
        for scenario in self._scenarios:
            if scenario.day_index == day_index:
                return scenario
        season, day_in_season = season_of(day_index)
        matched = [
            scenario
            for scenario in self._scenarios
            if scenario.matches_season(season, day_in_season)
        ]
        if not matched:
            return None
        dated = [item for item in matched if item.season_specificity >= 2]
        if dated:
            # `max` 返回**第一个**最大值，所以同等特异性下仍按文件顺序取第一条 ——
            # 想在同一个节点固定发某一条，把候选按期望顺序写即可。
            return max(dated, key=lambda scenario: scenario.season_specificity)
        pool = sorted(matched, key=lambda scenario: scenario.id)
        offset = max(0, int(day_index)) - 1
        # ⚠ 再加上「第几年」，否则池子大小一旦整除 112（一年 112 天），
        # 跨年就会**原样重播**。2026-09-27 实测撞上：池子正好 28 条，
        # 而 112 = 4 × 28，于是第 2 年的每一天都和第 1 年同一天一模一样 ——
        # 修了半天「第二年不重复」，结果挑的池子大小恰好是最能触发它的那个。
        #
        # `+ year` 是最省事又最稳的写法：`year % size` 对任何 size 都不会恒为 0，
        # 所以无论池子多大都不会「年年同一条」。代价是第 y+1 年的第 d-1 天与
        # 第 y 年的第 d 天同号 —— 隔一年又差一天，玩家不会察觉到。
        offset += max(0, (int(day_index) - 1) // _DAYS_PER_YEAR)
        return pool[offset % len(pool)]

    def for_npc(self, npc_id: str) -> tuple[MorningScenario, ...]:
        target = str(npc_id or "").strip().casefold()
        return tuple(s for s in self._scenarios if s.npc_id.casefold() == target)


def _reject_duplicate_openings(scenarios: Sequence[MorningScenario]) -> None:
    """同一个 NPC 的多条预设不得有**一模一样**的开场白（2026-09-26 用户口径）。

    用户原话：「预设对话触发过一次之后就不要再触发了，**可以有小巧思变体，
    但是不能一模一样**」。⇒ 同一个角色给第二条、第三条是允许的，但必须是
    真的换了个由头；逐字相同的那句玩家已经见过一次，再来一遍只是噪音。

    为什么在**加载期**报错：这些内容是人工写死的，写重了在游戏里的表现是
    「她怎么又说了一遍同样的话」——那时离现场已经很远。加载期炸掉，
    离现场只有一次重启的距离。
    """
    by_npc: dict[str, dict[str, str]] = {}
    for scenario in scenarios:
        normalized = _normalize_opening(scenario.opening)
        if not normalized:
            continue
        previous = by_npc.setdefault(scenario.npc_id.casefold(), {})
        if normalized in previous:
            raise MorningScenarioError(
                f"预设 {scenario.id!r} 与 {previous[normalized]!r} 是同一个角色"
                f"（{scenario.npc_id}）逐字相同的开场白："
                "变体必须换个由头，不能只换个 id"
            )
        previous[normalized] = scenario.id


def _normalize_opening(text: str) -> str:
    """比对前**去掉所有空白**。

    游戏端把 `opening` 写进聊天记录时可能过一遍清洗（换行、首尾空格），
    而 `ChatHistoryRules.MaxContentLength = 240` 这类上限也可能截断它。
    只要截断没发生，去空白后的逐字比对就成立；真截断了也只会退化成
    「没认出这是晨间对话」（少一层方向约束），不会给出错误的方向。
    """
    return "".join(str(text or "").split())


def match_scenario_by_history(
    store: MorningScenarioStore,
    history: object,
) -> MorningScenario | None:
    """历史里出现过某条预设的 `opening` 时，认定这段对话是它的后续。

    **为什么靠 `opening` 认，而不是让游戏端在请求里带 `scenarioId`**：
    `DialogueTestRequest` 是 `extra="forbid"`，加一个字段就意味着
    「新 DLL + 旧 Bridge = 422 → 退化成兜底回复」，必须先发 Bridge 再发 DLL。
    而逐字比对写死的内容**不需要任何协议改动**，顺带还更准：
    它不关心「今天是第几天」，**玩家隔了三天才回，照样认得这是那段对话的后续**
    ——按天数判断反而会在跨天时断掉。

    只看**第一条 assistant 消息**：晨间消息永远是这段对话的开头，
    而后面所有轮次都是它的延续。
    """
    if not isinstance(history, (list, tuple)) or not history:
        return None
    first_assistant = ""
    for item in history:
        if isinstance(item, Mapping) and str(item.get("role") or "") == "assistant":
            first_assistant = str(item.get("content") or "")
            break
    if not first_assistant.strip():
        return None
    target = _normalize_opening(first_assistant)
    for scenario in store.scenarios:
        if _normalize_opening(scenario.opening) == target:
            return scenario
    return None


def render_direction_card(scenario: MorningScenario) -> dict[str, Any]:
    """把一条预设渲染成 **独立卡**（见模块 docstring 第 2 条硬约束）。

    卡里只放「这轮怎么走」，**不放开场白**：开场白已经在对话记录里了，
    再放进 system 卡会让模型以为那是它要「再确认一遍」的信息。
    """
    card: dict[str, Any] = {
        "instruction": (
            "玩家正在回应你早上的那条消息。顺着这条线聊下去，不要重新自我介绍，"
            "也不要把已经说过的事再说一遍。"
        ),
        "direction": scenario.direction,
    }
    if scenario.boundaries:
        card["boundaries"] = list(scenario.boundaries)
    if scenario.closing_hook:
        card["closing"] = scenario.closing_hook
    if scenario.allowed_kinds:
        card["allowedKinds"] = list(scenario.allowed_kinds)
    return card
