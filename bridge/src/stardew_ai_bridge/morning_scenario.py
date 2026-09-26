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

1. **开场白必须取自角色原话。** 2026-09-25 查出 `dailyRoutine` 里的「藤」「标签」「果霜」
   在 519 条原话里**一次都没出现**——那是我推断的农活，不是她的语言指纹。
   预设对话是**人工写死的**，所以这条比运行时更危险：写错了会永远写在那里。
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


def parse_scenario(raw: Mapping[str, Any]) -> MorningScenario:
    """把一条原始记录解析成 `MorningScenario`，不合法就抛错。"""
    scenario_id = _require_text(raw.get("id"), scenario_id="<unknown>", field_name="id")
    trigger = raw.get("trigger")
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

    def for_day(self, day_index: int) -> MorningScenario | None:
        """按绝对天数取预设。同一天有多条时**取第一条**并保持文件顺序稳定。"""
        for scenario in self._scenarios:
            if scenario.day_index == day_index:
                return scenario
        return None

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
