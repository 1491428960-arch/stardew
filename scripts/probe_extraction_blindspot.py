"""量化 `check_prompt_consistency.py` 的抽取盲区。

做法：用**独立于抽取器**的宽口径正则，找出 prompt 里所有含「数量 + 单位」的片段，
再与抽取器实际抓到的对照，列出漏掉的。

不修改抽取器，只测量它 —— 因为「台账漏一条就判不出冲突」，
而抽取器是台账的数据来源，它的盲区就是台账的盲区。

用法：python probe_extraction_blindspot.py
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

NUM = r"[一二三四五六七八九十两\d]+"
UNIT = r"句|字|次|个|项|条|种|轮|遍|回合"
# 宽口径：任何「数量词 (+ 修饰) + 单位」，不要求「最多/只」
BROAD = re.compile(rf"{NUM}\s*[–~\-—]?\s*(?:{NUM})?\s*(?:{UNIT})")

stats: dict[str, int] = {"total": 0, "caught": 0, "missed": 0, "long_skipped": 0}

for stage in ("stranger", "friend", "close", "married"):
    print("=" * 78)
    print(f"阶段 {stage}")
    print("=" * 78)
    hearts, extra = chk.STAGES[stage]
    ctx = ContextBuilder().build("lewis", friendshipHearts=hearts, **extra)
    cards = PromptBuilder().build(ctx, "你好啊", compact=True)
    extracted = chk.collect(stage)
    missed: list[tuple[str, int, str, list[str]]] = []
    long_skipped: list[tuple[str, int, str]] = []

    for card in cards:
        body = card.get("content", "") or ""
        caught_values = {v for _, v, c in extracted if c == card["name"]}
        for frag in chk._SPLIT.split(body):
            frag = frag.strip()
            if not frag:
                continue
            hits = BROAD.findall(frag)
            if not hits:
                continue
            stats["total"] += 1
            if len(frag) > chk._MAX_FRAGMENT:
                # 抽取器会因长度直接跳过 —— 这是纯结构性盲区
                stats["long_skipped"] += 1
                long_skipped.append((card["name"], len(frag), frag[:90]))
                continue
            if any(v in frag for v in caught_values) or any(
                chk.normalize_value(raw, m.group(0)) in caught_values
                for raw, pattern in chk.QUANTITIES.items()
                for m in re.finditer(pattern, frag)
            ):
                stats["caught"] += 1
            else:
                stats["missed"] += 1
                missed.append((card["name"], len(frag), frag[:110], hits[:4]))

    print(f"  含数量的片段 {stats['total']} 个（累计）")
    print(f"  ├─ 抽取器抓到          : {stats['caught']}")
    print(f"  ├─ **漏掉（长度不超限）**: {stats['missed']}")
    print(f"  └─ **因 >120 字被跳过** : {stats['long_skipped']}")
    if missed:
        print("\n  ---- 漏掉且非长度原因（前 10）----")
        for name, ln, text, hits in missed[:10]:
            print(f"    [{name}] {hits}")
            print(f"        {text}")
    if long_skipped:
        print("\n  ---- 因长度 >120 被跳过（前 5）----")
        for name, ln, text in long_skipped[:5]:
            print(f"    [{name}] 长 {ln} 字")
            print(f"        {text}")
    print()

print("=" * 78)
print("汇总")
print("=" * 78)
tot = stats["total"] or 1
print(f"  含数量片段总数      : {stats['total']}")
print(f"  抓到                : {stats['caught']}  ({stats['caught']/tot:.0%})")
print(f"  漏（非长度原因）    : {stats['missed']}  ({stats['missed']/tot:.0%})")
print(f"  漏（长度原因）      : {stats['long_skipped']}  ({stats['long_skipped']/tot:.0%})")
