"""跨量不自洽探针：同一片段里出现**两个以上不同的量**时，它们之间是否自洽？

**为什么需要这个**：台账（`constraint_scope.py`）按**量**分桶 ——
长度、句数、动作数各查各的，查的是**同一个量**的取值冲突。
但「**1–2 句、15–40 字**」是**两个不同的量**写在一起，
它们之间的**换算关系是否自洽**，台账**结构上看不到**。

2026-09-28 实测证实这个盲区是真的：
「1–2 句」被遵守（81.3% 的回复是 1–2 句），
但「15–40 字」被违反 43.8% —— **因为两句自然中文常超 40 字**。
⇒ 两个约束**不能同时满足**，而台账和抽取器都看不见这一层。

**做什么**：把 3 条路径 × 7 档的 prompt 正文按**细粒度**切片段
（句末标点、换行、**以及逗号顿号** —— 因为成对约束常用逗号连接），
找出同一片段里**同时命中两个不同量**的地方，全部摊开。

⚠ **只摊开、不判定** —— 「跨量是否自洽」需要理解语义
（例如「2 句、40 字」在中文里到底能不能同时满足），
本脚本**永远返回 0**，绝不把它当红灯用。

用法：

    python scripts/probe_cross_quantity.py
    python scripts/probe_cross_quantity.py --show 40
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "scripts"))
sys.path.insert(0, str(WT / "bridge" / "src"))

import check_prompt_consistency as chk  # noqa: E402

#: 切片段：**句末标点与换行**。
#: ⚠ **不要在这里切逗号或顿号** —— 第一版切了，结果「1–2 句、15–40 字」
#: 正好被顿号切成两片，扫描报告「零共现」（假阴性）。
#: 成对约束**就是用逗号/顿号连起来的**，所以必须留在同一片里。
#: 为了不漏掉跨句的写法，下面还会额外检查「本片 + 下一片」的拼接。
SPLIT = re.compile(r"(?<=[。！？；])|\n+")


def fragments(text: str) -> list[str]:
    return [s.strip() for s in SPLIT.split(text) if s and s.strip()]


def scan_windows(frags: list[str]) -> list[tuple[str, str]]:
    """产出 (片段, 来源标记)：单片段，以及相邻两片段的拼接。

    单片段抓「1–2 句、15–40 字」这种同句写法；
    拼接抓「……最多 2 句。全文不超过 40 字。」这种跨句写法。
    """
    out: list[tuple[str, str]] = [(f, "单片") for f in frags]
    for a, b in zip(frags, frags[1:]):
        out.append((a + b, "跨句"))
    return out


def hits_in(frag: str) -> dict[str, str]:
    """返回本片段里命中的 {量名: 命中的文本}。"""
    found: dict[str, str] = {}
    for name, pattern in chk.QUANTITIES.items():
        m = re.search(pattern, frag)
        if m:
            found[name] = m.group(0).strip()
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="跨量不自洽探针（只摊开、不判定）")
    ap.add_argument("--show", type=int, default=30, help="最多打印多少条样例")
    ap.add_argument("--pair", default=None, help="只看某一对量，如 句数,字数")
    args = ap.parse_args()

    from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: PLC0415

    pairs: Counter[tuple[str, str]] = Counter()
    samples: dict[tuple[str, str], list[str]] = {}
    scanned = 0

    for topic, compact in chk.PATHS:
        for stage in chk.STAGES:
            npc = "Wizard"
            # ⚠ 正确用法：参数名是 friendshipHearts（不是 relationship/hearts）。
            # 用错名字不会报错（build 接受 **values），但会被**静默忽略**，
            # 导致 7 个阶段塌缩成同一个 prompt —— 2026-09-28 踩过。
            _hearts, _extra = chk.STAGES[stage]
            ctx = ContextBuilder().build(npc, friendshipHearts=_hearts, **_extra)
            if topic:
                ctx["interaction"] = {"intent": "topic"}
                cards = PromptBuilder().build(ctx, "", compact=compact)
            else:
                cards = PromptBuilder().build(ctx, "你好啊", compact=compact)
            scanned += 1
            for card in cards:
                frags = fragments(card["content"])
                for frag, origin in scan_windows(frags):
                    found = hits_in(frag)
                    if len(found) < 2:
                        continue
                    names = sorted(found)
                    for i in range(len(names)):
                        for j in range(i + 1, len(names)):
                            key = (names[i], names[j])
                            if args.pair and ",".join(key) != args.pair:
                                continue
                            pairs[key] += 1
                            bucket = samples.setdefault(key, [])
                            if len(bucket) < 8:
                                desc = " / ".join(f"{k}={v}" for k, v in found.items())
                                bucket.append(
                                    f"[{card['name']}|{origin}] {frag[:150]}   ⟵ {desc}"
                                )

    print("=" * 100)
    print(f"跨量共现扫描（扫了 {scanned} 个 prompt 组合；量分类取自 check_prompt_consistency.QUANTITIES）")
    print("=" * 100)
    print()
    if not pairs:
        print("  没有找到同片段跨量共现。")
        return 0

    print("共现次数排行：")
    for (a, b), cnt in pairs.most_common():
        print(f"  {a:<8} + {b:<8} {cnt:>4} 次")
    print()

    for key, cnt in pairs.most_common():
        print("-" * 100)
        print(f"【{key[0]} + {key[1]}】共 {cnt} 次")
        print("-" * 100)
        # ⚠ 每个量对**各自**限量；早先用全局计数器，第一对就用完了配额，
        #   后面几对全打印成空 —— 看起来像「没有样例」，其实是打印 bug。
        for line in samples.get(key, [])[: args.show]:
            print(f"  {line}")
        print()

    print("=" * 100)
    print("⚠ 本脚本**只摊开、不判定**。")
    print("  「跨量是否自洽」要看语义 —— 例如「1–2 句、15–40 字」里，")
    print("  两句自然中文就常超 40 字 ⇒ 这两个数**不能同时满足**。")
    print("  这类判断**台账和抽取器都做不到**，必须人读。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
