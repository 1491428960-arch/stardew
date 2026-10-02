"""清点 prompt 里出现的**全部「数量 + 单位」**，找没有被任何检查覆盖的量。

动机：约束台账的 8 个量（句数 / 字数 / 动作数 / 话题数 / 追问数 / 邀约 /
重复次数 / 口语颗粒频率）是**人工枚举**的。枚举法天生会漏 —— 这个探针反过来问：

> prompt 里**实际出现**的数量表述，有没有落在这些量之外的？

做法：抓「数字 + 紧邻的 1–4 个汉字」，统计搭配频次。高频搭配就是候选的新量。
零请求、只读。
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "bridge" / "src"))
sys.path.insert(0, str(WT / "scripts"))

from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: E402

import check_prompt_consistency as chk  # noqa: E402

NUM = r"[一二三四五六七八九十百两\d]+"
PAIR = re.compile(rf"({NUM})([\u4e00-\u9fff]{{1,4}})")

#: 已被台账覆盖的单位。
#: ⚠ 判据用 `in` 而非 `startswith`：数字后紧跟的汉字不一定以单位开头 ——
#: 「十**来个字**」「二十**出头**」「一**组三轮对**话」都以别的字开头，用 startswith 会误报。
COVERED = ("句", "字", "个", "项", "条", "种", "次", "轮", "遍", "步")


def covered(unit: str) -> bool:
    return any(c in unit for c in COVERED)

counter: Counter[str] = Counter()
examples: dict[str, str] = {}
card_of: dict[str, str] = {}

for stage in ("stranger", "friend", "close", "married"):
    hearts, extra = chk.STAGES[stage]
    ctx = ContextBuilder().build("lewis", friendshipHearts=hearts, **extra)
    for card in PromptBuilder().build(ctx, "你好啊", compact=True):
        body = card.get("content", "") or ""
        for frag in chk._SPLIT.split(body):
            frag = frag.strip()
            if not frag or len(frag) > chk._MAX_FRAGMENT:
                continue
            for m in PAIR.finditer(frag):
                unit = m.group(2)
                counter[unit] += 1
                examples.setdefault(unit, frag[:100])
                card_of.setdefault(unit, card["name"])

uncovered = {u: n for u, n in counter.items() if not covered(u)}

print("=" * 78)
print("全部「数字 + 汉字」搭配（按频次降序，前 45）")
print("=" * 78)
for unit, n in counter.most_common(45):
    mark = "  " if covered(unit) else "❓"
    print(f"  {mark} {n:>3}×  「{unit}」   [{card_of.get(unit,'')}]")
    print(f"          {examples.get(unit,'')}")

print()
print("=" * 78)
print("❓ = 不在台账已覆盖的单位里（可能是还没被枚举的量）")
print("=" * 78)
for unit, n in sorted(uncovered.items(), key=lambda kv: -kv[1]):
    print(f"  {n:>3}×  「{unit}」  [{card_of.get(unit,'')}]")
    print(f"        {examples.get(unit,'')}")
if not uncovered:
    print("  （无）")
