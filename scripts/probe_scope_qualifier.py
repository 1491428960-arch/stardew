"""台账盲区第四类：**量化约束的「作用范围」是否被限定**。

**为什么查这个**：2026-09-28 测 `邀约` 时踩了坑 ——
「**初识阶段**不得反问、邀约或主动换题」只管 stranger / acquaintance 两个阶段，
但我拿全阶段 artifact 去测，**测的根本不是约束对象**（续二十六）。

⇒ 由此想到一类没查过的盲区：
**一条量化约束如果在某处生效、在别处不生效，它的作用范围有没有写清楚？**
- 写清楚了（带阶段词）⇒ 读的人知道它管哪一段；
- **没写**（看起来是全局）⇒ 读者会以为它**永远**生效，
  而实际可能只在某些上下文被注入 ⇒ **误判**。

**做什么**：把每条量化约束的片段连同**它前后窗口内是否出现阶段词**一起摊开，
按「带阶段限定 / 不带」分组。

⚠ **只摊开、不判定** —— 「该不该限定」是设计问题，`return 0`。
⚠ 实测提醒：**不带阶段词的约束未必有问题**（多数约束本就该全局）。

用法：

    python scripts/probe_scope_qualifier.py
    python scripts/probe_scope_qualifier.py --show 12
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "scripts"))
sys.path.insert(0, str(WT / "bridge" / "src"))

import check_prompt_consistency as chk  # noqa: E402

#: 阶段 / 关系词。出现在约束前后窗口里 ⇒ 认为这条约束**带范围限定**。
STAGE_WORDS = re.compile(
    r"初识|陌生|刚认识| acquaintance|stranger"
    r"|熟悉|朋友|friend"
    r"|亲密|恋人|约会|dating|爱人|伴侣|夫妻|已婚|marri"
    r"|家长|父母|孩子|parent"
    r"|本阶段|这个阶段|当前阶段|阶段|关系阶段"
)

#: 限定词（不只阶段 —— 也包括渠道、场景）。
SCOPE_WORDS = re.compile(
    r"初识|陌生|刚认识|熟悉|朋友|亲密|恋人|约会|已婚|marri|parent|家长"
    r"|本阶段|当前阶段|这个阶段|阶段"
    r"|主动搭话|群聊|多人|单人|私聊|远程|当面|渠道"
    r"|只有|仅在|只在|仅在|当[^。；]{0,12}时|如果|若|遇到"
)

SPLIT = re.compile(r"(?<=[。！？；])|\n+")


def main() -> int:
    ap = argparse.ArgumentParser(description="量化约束的作用范围限定扫描（只摊开）")
    ap.add_argument("--show", type=int, default=10, help="每组最多列几条")
    args = ap.parse_args()

    from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: PLC0415

    #: 卡名 → [(片段, 是否带限定, 命中的量)]
    per_card: dict[str, list[tuple[str, bool, str]]] = defaultdict(list)
    qualified = 0
    bare = 0

    for topic, compact in chk.PATHS:
        for stage in chk.STAGES:
            # ⚠ 正确用法：参数名是 friendshipHearts（不是 relationship/hearts）。
            # 用错名字不会报错（build 接受 **values），但会被**静默忽略**，
            # 导致 7 个阶段塌缩成同一个 prompt —— 2026-09-28 踩过。
            _hearts, _extra = chk.STAGES[stage]
            ctx = ContextBuilder().build("Wizard", friendshipHearts=_hearts, **_extra)
            if topic:
                ctx["interaction"] = {"intent": "topic"}
                cards = PromptBuilder().build(ctx, "", compact=compact)
            else:
                cards = PromptBuilder().build(ctx, "你好啊", compact=compact)
            for card in cards:
                name = card["name"]
                content = card["content"]
                frags = [s.strip() for s in SPLIT.split(content) if s and s.strip()]
                for i, frag in enumerate(frags):
                    kinds = [q for q, rx in chk.QUANTITIES.items() if re.search(rx, frag)]
                    if not kinds:
                        continue
                    # 窗口 = 本片段 + 前一片 + 后一片（限定词常写在相邻句里）
                    window = " ".join(frags[max(0, i - 1) : i + 2])
                    has_scope = bool(SCOPE_WORDS.search(window))
                    if has_scope:
                        qualified += 1
                    else:
                        bare += 1
                    per_card[name].append((frag, has_scope, ",".join(kinds)))

    print("=" * 100)
    print("量化约束的**作用范围限定**扫描")
    print("=" * 100)
    print()
    print(f"带限定词（阶段/渠道/条件）: {qualified}")
    print(f"不带限定词（看起来是全局）: {bare}")
    if qualified + bare:
        print(f"⇒ 带限定比例 {qualified / (qualified + bare) * 100:.1f}%")
    print()

    for want in (False, True):
        label = "⚠ 不带限定词（看起来全局生效）" if not want else "✅ 带限定词"
        print("=" * 100)
        print(f"{label}")
        print("=" * 100)
        for name in sorted(per_card):
            rows = [
                (f, k) for f, h, k in per_card[name] if h is want
            ]
            if not rows:
                continue
            uniq: list[tuple[str, str]] = []
            for f, k in rows:
                if all(f != u[0] for u in uniq):
                    uniq.append((f, k))
            print()
            print(f"--- [{name}]  {len(uniq)} 条 ---")
            for f, k in uniq[: args.show]:
                print(f"    ({k}) {f[:145]}")
            if len(uniq) > args.show:
                print(f"    …… 还有 {len(uniq) - args.show} 条")
        print()

    print("=" * 100)
    print("⚠ 本脚本**只摊开、不判定**。")
    print("  **不带阶段词的约束未必有问题** —— 多数约束本就该全局生效。")
    print("  它的用途是：改约束 / 测约束前，**先确认这条约束管哪一段**。")
    print("  依据：2026-09-28 测 `邀约` 时踩坑 —— 「初识阶段不得邀约」")
    print("  只管两个阶段，却拿全阶段样本去测 ⇒ **测的不是约束对象**。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
