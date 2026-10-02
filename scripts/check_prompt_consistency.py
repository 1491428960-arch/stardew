"""跨卡数值一致性检查：同一个量有没有被规定成两个不同的值。

用法：
    python scripts/check_prompt_consistency.py
    python scripts/check_prompt_consistency.py --stage stranger

背景（2026-09-28）：长度指令曾在同一轮 prompt 的**六处**出现，其中三处取值不同
（`1–2 句` / `1–3 句` / `2–3 句`），模型**取最松的那条**，实测平均回复 70.5 字。
收束到统一取值后降到 38.8 字（云端对照见
`docs/report-instruction-conflicts-2026-09-28.md` §15）。

⚠ **判据要分清两类**，否则会删错东西：

- **同义的重复** —— 有意的**分层防御**，不同位置各防一层，且**有测试钉住**
  （如「复述玩家」4 处）。**不是问题，不要动。**
- **取值不同的重复** —— 真矛盾，模型取最松那条。**这才是本脚本要查的。**

⚠ **输出需要人工判断**：脚本只负责把「同一阶段内、同一个量的所有取值」摊开，
「这是矛盾还是兼容」由人看 —— 例如「整条 15–40 字」与「每句十来个字、最多二十出头」
看着是两个值，实际 `2×20 = 40` 正好吻合，**是兼容的**。

零请求、只读。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

_WORKTREE = Path(__file__).resolve().parent.parent
if str(_WORKTREE / "bridge" / "src") not in sys.path:
    sys.path.insert(0, str(_WORKTREE / "bridge" / "src"))

from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: E402

#: 量词主题 → 正则。命中即认为这句在给某个量定值。
#:
#: ⚠ **2026-09-28 修正**：原正则一律要求「最多/只」或「N–N」形态，而 prompt 里
#: 大量数量约束是**无限定词**的写法 —— 「**用 1 句**直接回答」「再补**第 2 句**」
#: 「断成**第二句**」「提出**一个**具体下一步」。这些全被漏掉。
#: 实测（`.tmp/length-probe/probe_extraction_blindspot.py`）：宽口径命中 90 处，
#: 原正则只抓 24 处（27%）。**漏掉就等于台账判不出冲突**，因为抽取器是台账的唯一数据源。
#: 放宽的代价是「铺开清单」变长（含少量非约束的数量词），但那是**多提示补台账**，
#: 不会造成误判 —— 比漏判安全。
QUANTITIES: dict[str, str] = {
    "句数": (
        r"[一二三四五六七八九十两\d]+\s*[–~\-—]\s*[一二三四五六七八九十两\d]+\s*句"
        r"|最多\s*[一二三四五六七八九十两\d]+\s*句"
        r"|只[说写讲][一二三四五六七八九十两\d]*句"
        r"|用\s*[一二三四五六七八九十两\d]+\s*句"
        # ⚠ 「补」必须后接「第」才算长度约束：「再补**第** 2 句」在定上限，
        #   而「补一句自我怀疑」是**动作**、不是整条句数。不区分会把后者误当长度，
        #   实测在 persona 静态扫描里造出假冲突（Caroline）。
        r"|(?:再?补|断成|接|加)\s*第\s*[一二三四五六七八九十两\d]+\s*句"
        # ⚠ 排除「同一句」「在同一句」——那是**指示词**（"让爱意落在同一句里"），
        #   不是句数上限。实测在 `affection_initiative` 与 `affection_priority_final`
        #   上各造出一个假取值「1 句」，与同卡真取值「一两句」并列，看起来像矛盾。
        #   「紧接的一句」同理（前一字是「的」）。
        # ⚠ 再排除**动词 + 一句**：「不要把回复拆成『复述一句→回答一句』的模板」
        #   说的是**两个动作**，不是整条最多两句（与「补一句自我怀疑」同类）。
        #   「补/加」+「第 N 句」由上面那条专门规则接住，这里排除它们不会丢真约束。
        r"|(?<!同)(?<!的)(?<![复述答说讲读写问聊谈提及])[一二三四五六七八九十两\d]+\s*句"
    ),
    "字数": (
        r"[一二三四五六七八九十两\d]+\s*[–~\-—]\s*\d+\s*字"
        r"|最多\s*\d+\s*字|十来个字|二十出头|\d+\s*字"
    ),
    "动作数": (
        r"最多[^。；]{0,10}?[一个两三四\d]+[^。；]{0,6}?(动作|细节|追问|选择|安排)"
        r"|[一个两三四\d]+\s*(?:个|项|条)?\s*(?:具体)?\s*"
        r"(?:动作|细节|追问|选择|安排|下一步|小行动|事实)"
    ),
    # 口语颗粒（嗯/唔/啊）的使用频率上限 —— 与长度无关，但同属数值上限约束。
    "口语颗粒频率": (
        r"一组\s*[一二三四五六七八九十两\d]+\s*轮[^。；]{0,12}?最多[^。；]{0,6}?一次"
    ),
    "话题数": (
        r"(只能|最多|只|提出|开启|换)[^。；]{0,8}?(一个|一项|一条|一种)"
        r"[^。；]{0,6}?(话题|问题|事)"
    ),
    "追问数": (
        r"(最多|只|允许|可以)[^。；]{0,8}?(一次|一句|一个)[^。；]{0,6}?(追问|反问|提问)"
        r"|再\s*反问\s*[一二三四五六七八九十两\d]*\s*句"
    ),
    "邀约": r"(不|别|不要)[^。；]{0,8}?(邀约|约定|预约|排期|承诺)",
}

#: 阶段 → (心数, 额外字段)。`relationship` 会**覆盖**心数（见 report 附注）。
STAGES: dict[str, tuple[int, dict[str, object]]] = {
    # ⚠ 必须覆盖 `_SHARED_POLICIES` 的**全部**档位。原先只有 4 档，
    #   少了 acquaintance / dating / parent —— 于是 `--against-scope`
    #   **从来没检查过这三档**（包括 2026-09-28 改的 dating 与 parent，
    #   等于那次改动没被这个工具验证过）。2026-09-28 补齐。
    "stranger": (0, {}),
    "acquaintance": (4, {}),
    "friend": (6, {}),
    "close": (8, {}),
    "dating": (10, {"relationship": "dating"}),
    "married": (12, {"relationship": "married", "marriageStatus": "married"}),
    # parent 判定看 `childrenCount`（`prompts._relationship_stage`）。
    "parent": (12, {"relationship": "married", "marriageStatus": "married", "childrenCount": 2}),
}

_SPLIT = re.compile(r"(?<=[。；])|\n+")
#: 超过这个长度就跳过。原为 120，2026-09-28 提到 300 ——
#: `stage_execution_card` 的 JSON 片段常在 128–156 字、`persona_core` 达 225 字，
#: 而它们**恰恰含 responseShape / signatureMoves 这类数量约束**，
#: 原上限把最该查的卡片直接排除了。仍保留一个上限，避免超大段文本里搜到无关数字。
_MAX_FRAGMENT = 300

#: 中文数字（含「二十」这类常见复合），用于把取值归一化成数值。
_CN_NUM = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "二十": 20, "三十": 30, "四十": 40, "五十": 50,
}

_UNIT_OF = {
    "句数": "句", "字数": "字",
    "动作数": "个", "话题数": "个", "追问数": "次",
}


def _to_int(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        return int(token)
    return _CN_NUM.get(token)


def normalize_value(quantity: str, matched: str) -> str:
    """把匹配到的**文本**归一化成**数值取值**。

    ⚠ 必须归一化。同一段话里「用一句」与「一句」是两个不同 match，
    但说的是**同一个取值 1**；「再补一句」同理。
    不归一化就会把同一条约束报成「多种取值」—— 在 50 个 persona 上
    实测产生 **20 处假冲突**（`probe_persona_static_conflicts.py`）。
    归一化后只剩真冲突。
    """
    unit = _UNIT_OF.get(quantity)
    if unit is None:
        return matched
    nums = [n for n in (_to_int(t) for t in re.findall(r"[一二三四五六七八九十两\d]+", matched)) if n is not None]
    if not nums:
        return matched
    lo, hi = min(nums), max(nums)
    return f"{lo}–{hi} {unit}" if lo != hi else f"{lo} {unit}"


#: 真实存在的 prompt 路径：(topic, compact)。
#: - `(False, True)`  单聊普通回复 —— 游戏里绝大多数回合；
#: - `(True,  True)`  单聊 topic（玩家说「换个话题」）—— 15 张卡；
#: - `(False, False)` **群聊** —— `app.py` 写明群聊不传 `compactPrompt`，走**完整卡组**（14 张卡）。
#: ⚠ 三条都不查会整张卡地漏：topic 路径多 `topic_response_contract`，
#:    群聊路径多 `voice_variation`。
PATHS: tuple[tuple[bool, bool], ...] = ((False, True), (True, True), (False, False))


def collect(
    stage: str, *, topic: bool = False, compact: bool = True
) -> list[tuple[str, str, str]]:
    """返回 [(量, 取值, 卡名), ...] —— 只取该阶段实际进 prompt 的卡。

    `topic=True` 走**另一条真实存在的路径**：`app.py` 在 `payload["intent"] == "topic"`
    时注入 `context["interaction"]`，prompt 变成 **15 张卡**（加
    `topic_response_contract` / `topic_trigger` / `interaction`，少 `player_input`）。

    ⚠ 必须**手动注入** `interaction` —— `ContextBuilder` 自己不设这个键
    （实测 `ContextBuilder.build(..., interaction=...)` 会被忽略、`context["interaction"]`
    仍是 `None`）。这正是这条路径长期没被检查到的原因。
    """
    hearts, extra = STAGES[stage]
    context = ContextBuilder().build("lewis", friendshipHearts=hearts, **extra)
    if topic:
        context["interaction"] = {"intent": "topic"}
    cards = PromptBuilder().build(context, "" if topic else "你好啊", compact=compact)
    found: list[tuple[str, str, str]] = []
    for quantity, pattern in QUANTITIES.items():
        rx = re.compile(pattern)
        for card in cards:
            body = card.get("content", "") or ""
            for fragment in _SPLIT.split(body):
                fragment = fragment.strip()
                if not fragment or len(fragment) > _MAX_FRAGMENT:
                    continue
                match = rx.search(fragment)
                if match:
                    found.append(
                        (quantity, normalize_value(quantity, match.group(0)), card["name"])
                    )
    return found


def report(stage: str, *, topic: bool = False, compact: bool = True) -> bool:
    """打印一个阶段的检查结果；有「同一阶段内取值多于一种」时返回 True。"""
    by_quantity: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for quantity, value, card in collect(stage, topic=topic, compact=compact):
        by_quantity[quantity][value].append((card, ""))

    label = stage
    if topic or not compact:
        tag = "topic 路径" if topic else "群聊（完整卡组）"
        label = f"{stage}（{tag}）"
    print("=" * 78)
    print(f"阶段 {label}")
    print("=" * 78)
    suspicious = False
    for quantity in QUANTITIES:
        values = by_quantity.get(quantity)
        if not values:
            continue
        if len(values) > 1:
            suspicious = True
        flag = "  ⚠ 同一阶段内取值多于一种" if len(values) > 1 else ""
        cards = sorted({card for hits in values.values() for card, _ in hits})
        print(f"\n  【{quantity}】{len(values)} 种取值 / 出现在 {len(cards)} 张卡{flag}")
        for value, hits in values.items():
            print(f"     「{value}」  ←  {'、'.join(sorted({c for c, _ in hits}))}")
    print()
    return suspicious


def diff_against_scope(stages: list[str]) -> int:
    """把实际渲染的 prompt 抽到的量约束，与台账对照，报出**台账没覆盖的 (卡, 量)**。

    ⚠ 台账的致命局限：**漏一条就判不出冲突** —— 2026-09-28 建表时实际漏过一条，
    而那一条正是唯一能判出冲突的（见 `docs/constraint-scope.md` §五）。
    本函数用来抓这种漏，同时输出「**铺开清单**」：台账还没覆盖的量与卡。

    返回台账未覆盖的组合数。
    """
    sys.path.insert(0, str(_WORKTREE / "scripts"))
    from constraint_scope import CURRENT, resolve_quantity  # noqa: PLC0415

    known = {(item.card, item.quantity) for item in CURRENT}
    uncovered: dict[tuple[str, str], set[str]] = defaultdict(set)
    # ⚠ 三条真实路径都要查 —— 卡组不同，只查一条会整张卡地漏：
    #    topic 路径多 `topic_response_contract` / `topic_trigger`，少 `player_input`；
    #    群聊（完整卡组）多 `voice_variation`。
    for stage in stages:
        for topic_path, compact_path in PATHS:
            for raw_quantity, value, card in collect(
                stage, topic=topic_path, compact=compact_path
            ):
                # ⚠ 抽取端用中文量名、台账用英文规范名 —— 必须先归一化。
                #    不归一化会把「台账里明明有」的条目录成缺口。
                quantity = resolve_quantity(card, raw_quantity)
                if (card, quantity) not in known:
                    uncovered[(card, quantity)].add(value)

    print("=" * 78)
    print("台账未覆盖的 (卡, 量) —— 这就是「铺开清单」")
    print("=" * 78)
    if not uncovered:
        print("  台账已覆盖实际 prompt 里出现的全部量约束。")
    for (card, quantity), values in sorted(uncovered.items()):
        print(f"\n  {card}  ×  {quantity}")
        for value in sorted(values):
            print(f"     「{value}」")
    print(f"\n  合计 {len(uncovered)} 组待铺开。")
    print(
        "\n  ⚠ 未覆盖 ≠ 有冲突：本清单只说明台账还缺这些条目，"
        "在补齐之前它不能用来宣布「没有别的冲突」。"
    )
    return len(uncovered)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--stage",
        choices=sorted(STAGES),
        action="append",
        help="只检查指定阶段，可重复；默认四个阶段全查",
    )
    parser.add_argument(
        "--against-scope",
        action="store_true",
        help="与约束作用域台账对照，输出铺开清单（不改判断，只列缺口）",
    )
    parser.add_argument(
        "--topic",
        action="store_true",
        help="只查 topic 路径（15 张卡）；不加则默认三条真实路径都查",
    )
    args = parser.parse_args()
    stages = args.stage or list(STAGES)

    if args.against_scope:
        return 0 if diff_against_scope(stages) >= 0 else 1

    # 默认三条真实路径都查（单聊普通 / 单聊 topic / 群聊完整卡组）——
    # 卡组互不相同，只查一条会整张卡地漏。
    paths = ((True, True),) if args.topic else PATHS
    any_suspicious = any(
        report(stage, topic=t, compact=c) for stage in stages for t, c in paths
    )
    if any_suspicious:
        print(
            "提示：取值多于一种**不一定**是矛盾 —— 例如「整条 15–40 字」与\n"
            "      「每句十来个字、最多二十出头」是兼容的（2×20 = 40）。\n"
            "      请读原句判断：**方向一致且层层更严** ⇒ 兼容；**互相抵消** ⇒ 真矛盾。"
        )
    else:
        print("四个阶段内都没有发现「同一个量取值多于一种」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
