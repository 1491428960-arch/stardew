"""对比 `topic_request` 路径与普通路径的卡片构成与量约束。

背景：`check_prompt_consistency` 只 dump **默认路径**，而 `topic_request=True`
（由 `interaction.intent == "topic"` 触发，见 `prompts.py:1541`）会走**另一套卡片**：
按早期记录它加 `topic_response_contract` / `topic_trigger`、
少 `stage_execution_card` / `story_state`。

**这条路径的约束从未被一致性检查覆盖过。** 本探针先量出差异，再决定要不要把它接进工具。

零请求、只读。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "bridge" / "src"))
sys.path.insert(0, str(WT / "scripts"))

from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: E402

import check_prompt_consistency as chk  # noqa: E402

INTERACTION = {"intent": "topic"}
PLAYER_INPUT = "换个话题吧"

sets: dict[bool, list] = {}
for topic in (False, True):
    ctx = ContextBuilder().build("lewis", friendshipHearts=6)
    # ⚠ 必须**手动注入**：`ContextBuilder` 自己不设 `interaction`，
    #   它由调用方（`app.py`）在真实请求里注入，所以
    #   `ContextBuilder.build(..., interaction=...)` 传进去会被忽略（实测 context 里是 None）。
    if topic:
        ctx["interaction"] = INTERACTION
    got = ctx.get("interaction")
    cards = PromptBuilder().build(ctx, PLAYER_INPUT, compact=True)
    sets[topic] = cards
    print(f"topic={topic}: {len(cards)} 张卡   context['interaction']={got!r}")

base = {c["name"] for c in sets[False]}
topic_names = {c["name"] for c in sets[True]}
print()
print("仅 topic 路径有:", sorted(topic_names - base))
print("仅普通路径有:", sorted(base - topic_names))


def quantities(cards) -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for card in cards:
        for frag in chk._SPLIT.split(card.get("content", "") or ""):
            frag = frag.strip()
            if not frag or len(frag) > chk._MAX_FRAGMENT:
                continue
            for quantity, rx in chk.QUANTITIES.items():
                m = re.search(rx, frag)  # ⚠ QUANTITIES 的值是**正则字符串**，不是编译对象
                if m:
                    found[(card["name"], quantity)] = chk.normalize_value(quantity, m.group(0))
    return found


q_base = quantities(sets[False])
q_topic = quantities(sets[True])

print()
print("=" * 78)
print("只在 topic 路径出现的量约束（普通路径完全没有）")
print("=" * 78)
only_topic = {k: v for k, v in q_topic.items() if k not in q_base}
if only_topic:
    for (card, quantity), value in sorted(only_topic.items()):
        print(f"  [{card}] {quantity} = {value}")
else:
    print("  （无）")

print()
print("=" * 78)
print("只在普通路径出现的量约束")
print("=" * 78)
only_base = {k: v for k, v in q_base.items() if k not in q_topic}
if only_base:
    for (card, quantity), value in sorted(only_base.items()):
        print(f"  [{card}] {quantity} = {value}")
else:
    print("  （无）")

print()
print("=" * 78)
print("两条路径取值**不同**的 (卡, 量)")
print("=" * 78)
diff = {
    k: (q_base[k], q_topic[k])
    for k in q_base.keys() & q_topic.keys()
    if q_base[k] != q_topic[k]
}
if diff:
    for (card, quantity), (a, b) in sorted(diff.items()):
        print(f"  ⚠ [{card}] {quantity}: 普通={a}  topic={b}")
else:
    print("  （无 —— 共有卡上的取值一致）")
