"""对比**完整卡组**（`compact=False`，群聊走这条）与紧凑卡组（`compact=True`，单聊）的量约束。

`app.py` 里写着：

> 调用方显式传入时以它为准（`/api/dialogue/test` 传的是校验后的
> `Compact_prompt`）；不传的调用方目前只有**群聊**，它的内部 payload 不带这个键，
> 因此**固定走完整卡组** —— 与游戏端群聊一致。

而一致性检查、盲区探针、数量清点**全都用 `compact=True`**（单聊同路径）。
⇒ **群聊路径的量约束从未被任何检查覆盖。**

本探针量出差异，决定要不要把它接进 `check_prompt_consistency`。零请求、只读。
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


def quantities(cards) -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for card in cards:
        for frag in chk._SPLIT.split(card.get("content", "") or ""):
            frag = frag.strip()
            if not frag or len(frag) > chk._MAX_FRAGMENT:
                continue
            for quantity, rx in chk.QUANTITIES.items():
                if re.search(rx, frag):
                    found[(card["name"], quantity)] = chk.normalize_value(quantity, frag)
    return found


sets: dict[bool, list] = {}
for compact in (True, False):
    ctx = ContextBuilder().build("lewis", friendshipHearts=6)
    sets[compact] = PromptBuilder().build(ctx, "你好啊", compact=compact)
    print(f"compact={compact}: {len(sets[compact])} 张卡")

names_compact = {c["name"] for c in sets[True]}
names_full = {c["name"] for c in sets[False]}
print()
print("仅完整卡组有:", sorted(names_full - names_compact))
print("仅紧凑卡组有:", sorted(names_compact - names_full))

q_compact = quantities(sets[True])
q_full = quantities(sets[False])

for label, only in (
    ("只有完整卡组出现的量约束", {k: v for k, v in q_full.items() if k not in q_compact}),
    ("只有紧凑卡组出现的量约束", {k: v for k, v in q_compact.items() if k not in q_full}),
):
    print()
    print("=" * 78)
    print(label)
    print("=" * 78)
    if only:
        for (card, quantity) in sorted(only):
            print(f"  [{card}] {quantity}")
    else:
        print("  （无）")

print()
print("=" * 78)
print("共有卡上取值**不同**的 (卡, 量)")
print("=" * 78)
diff = {k: (q_compact[k], q_full[k]) for k in q_compact.keys() & q_full.keys() if q_compact[k] != q_full[k]}
if diff:
    for (card, quantity), (a, b) in sorted(diff.items()):
        print(f"  ⚠ [{card}] {quantity}: 紧凑={a!r}  完整={b!r}")
else:
    print("  （无）")
