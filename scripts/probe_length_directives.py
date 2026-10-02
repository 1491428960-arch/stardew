"""清点 prompt 里**所有**长度指令（句数 / 字数），供「同向改多处」使用。

**为什么需要它**：`test_prompts.py:9249` 那条守卫的注释里记着一个**实测结论** ——

> 同一轮 prompt 里曾有**六处**长度指令，而只有 `stage_execution_card`
> 那条给硬数字，模型于是**取最宽的那条**。

⇒ 所以**只改一处等于没改**：模型会取剩下那条更宽的。
⇒ 要动长度措辞，必须先知道**一共有几处、分别在哪张卡**。

**做什么**：扫 3 条路径 × 7 档关系阶段，把每个含「句数」或「字数」的片段
连同**卡名**一起列出来，按卡归类，并给出**每张卡在几条路径/几档里出现**。

加 `--all` 时，改为清点**所有**量化约束的「话语权」（出现在几张卡里）——
用于找出**低话语权**的约束，它们是「容易被无视」的候选。

零请求、只读。`return 0` —— 它只清点，不判定对错。

## ⚠ 两个已踩过的坑（改这个文件前先读）

1. **`ContextBuilder.build` 的参数名是 `friendshipHearts`**，不是 `relationship`
   也不是 `hearts`。`build` 接受 `**values` ⇒ **拼错的参数名被静默忽略、永不报错**，
   会让 7 个阶段**塌缩成同一个 prompt**。⇒ 因此本文件**带阶段指纹自检**。
2. **不要用 PowerShell `.Replace()` 改本文件的代码块** ——
   锚点若出现多次会**全部替换**，2026-09-28 曾因此把文件结构改坏。

用法：

    python scripts/probe_length_directives.py
    python scripts/probe_length_directives.py --all
    python scripts/probe_length_directives.py --show 6
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "scripts"))
sys.path.insert(0, str(WT / "bridge" / "src"))

import check_prompt_consistency as chk  # noqa: E402

#: 句数 / 字数两类的**只读**匹配（与台账的 QUANTITIES 同源，但更宽松：
#: 这里是为了**清点**，宁可多列不可漏 —— 漏掉一处就会「改了一处、留了一处更宽的」）。
LEN_PATTERNS = {
    "句数": re.compile(
        r"[一二三四五六七八九十两\d]+\s*[–~\-—至]\s*[一二三四五六七八九十两\d]+\s*句"
        r"|最多\s*[一二三四五六七八九十两\d]+\s*句"
        r"|只[说写讲]\s*[一二三四五六七八九十两\d]+\s*句"
        r"|(?:再?补|断成|接|加|留|用)\s*第?\s*[一二三四五六七八九十两\d]+\s*句"
        r"|(?<!同)(?<!的)(?<![复述答说讲读写问聊谈提及])[一二三四五六七八九十两\d]+\s*句"
    ),
    "字数": re.compile(
        r"[一二三四五六七八九十两\d]+\s*[–~\-—至]\s*\d+\s*字"
        r"|最多\s*\d+\s*字|\d+\s*字以内|约?\s*\d+\s*字|十来个字|二十出头"
    ),
}

SPLIT = re.compile(r"(?<=[。！？；])|\n+")


def main() -> int:
    ap = argparse.ArgumentParser(description="清点全部长度指令（只清点、不判定）")
    ap.add_argument("--show", type=int, default=4, help="每张卡最多列几条原文")
    ap.add_argument(
        "--all",
        action="store_true",
        dest="allq",
        help="不只长度 —— 清点 **所有**量化约束的「话语权」（出现于几张卡）",
    )
    args = ap.parse_args()

    from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: PLC0415

    #: 卡名 → [(片段, 命中类型, 路径标记, 阶段)]
    per_card: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    card_paths: dict[str, set[str]] = defaultdict(set)
    card_stages: dict[str, set[str]] = defaultdict(set)

    #: --all 模式：量名 → 出现过的卡集合 / 命中次数
    qty_cards: dict[str, set[str]] = defaultdict(set)
    qty_hits: dict[str, int] = defaultdict(int)

    combos = 0
    stage_sigs: dict[str, str] = {}

    for topic, compact in chk.PATHS:
        tag = f"topic={int(topic)},compact={int(compact)}"
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
            combos += 1
            # 一致性自检：记录每个阶段产生的 prompt 指纹（见下方打印）。
            stage_sigs[stage] = hashlib.sha1(
                "".join(c["content"] for c in cards).encode("utf-8")
            ).hexdigest()[:8]

            for card in cards:
                name = card["name"]
                for frag in SPLIT.split(card["content"]):
                    frag = frag.strip()
                    if not frag:
                        continue
                    for kind, rx in LEN_PATTERNS.items():
                        if rx.search(frag):
                            per_card[name].append((frag, kind, tag, stage))
                            card_paths[name].add(tag)
                            card_stages[name].add(stage)
                            break
                    if args.allq:
                        for qname, qrx in chk.QUANTITIES.items():
                            if re.search(qrx, frag):
                                qty_cards[qname].add(name)
                                qty_hits[qname] += 1

    # ⭐ 一致性自检：**一个从不失败的检查等于没有检查。**
    # 2026-09-28 曾因参数名写错让 7 个阶段**静默塌缩成同一个 prompt**，
    # 而输出看起来完全正常 —— 这个自检就是为那次事故加的。
    print("【阶段自检】7 个阶段是否真的产生了不同的 prompt：")
    for _s, _sig in stage_sigs.items():
        print(f"    {_s:<14} {_sig}")
    _n = len(set(stage_sigs.values()))
    if _n == len(stage_sigs):
        print(f"  ✅ {_n}/{len(stage_sigs)} 个阶段各不相同 —— 阶段维度有效")
    else:
        print(f"  ⚠⚠ 只有 {_n}/{len(stage_sigs)} 种不同！阶段**塌缩**了 ——")
        print("      检查 ContextBuilder.build 的参数名（应为 friendshipHearts）。")
        print("      下面所有「阶段 N/7」的数字都**不可信**。")
    print()

    if args.allq:
        print("=" * 100)
        print(f"⭐ 各量化约束的『话语权』（{combos} 个 prompt 组合）")
        print("=" * 100)
        print()
        print("  依据：`test_prompts.py:9249` 的实测结论 ——")
        print("  「同一轮有多处同类指令时，模型取最宽的那条」。")
        print("  ⇒ **只出现在 1 张卡里的约束，话语权最低，最可能被无视。**")
        print()
        print(f"  {'量':<10} {'卡数':>5} {'命中次数':>8}   出现在哪些卡")
        for qname in sorted(qty_cards, key=lambda k: (len(qty_cards[k]), -qty_hits[k])):
            cards_of = sorted(qty_cards[qname])
            flag = "  ⚠⚠ 话语权最低" if len(cards_of) == 1 else ""
            print(
                f"  {qname:<10} {len(cards_of):>5} {qty_hits[qname]:>8}   "
                f"{', '.join(cards_of)}{flag}"
            )
        print()
        print("  ⚠ 这是**结构性指标**，不是违规率 —— 它预测「哪些约束容易被无视」，")
        print("     但不等于「已经被无视」。要确认还须像长度那样**分开算违规率**。")
        print("  ⚠ 已实测的反例：`追问数` 同样只在 1 张卡，违规率却仅 ~1%（被严守）")
        print("     ⇒ **是否被遵守还取决于「模型自然倾向」是否与该约束同向**。")
        print()
        return 0

    print("=" * 100)
    print(f"长度指令清点（{combos} 个 prompt 组合 = {len(chk.PATHS)} 路径 × {len(chk.STAGES)} 阶段）")
    print("=" * 100)
    print()
    print(f"共 **{len(per_card)} 张卡**含长度指令：")
    print()
    for name in sorted(per_card, key=lambda k: -len(per_card[k])):
        items = per_card[name]
        kinds = sorted({k for _, k, _, _ in items})
        uniq = sorted({f for f, _, _, _ in items})
        print(
            f"  {name:<34} 命中 {len(items):>3} 次 / 唯一片段 {len(uniq):>2} 条"
            f"  路径 {len(card_paths[name])}/{len(chk.PATHS)}"
            f"  阶段 {len(card_stages[name])}/{len(chk.STAGES)}  [{','.join(kinds)}]"
        )
    print()

    print("=" * 100)
    print("逐卡原文（『同向改多处』要照这份清单改）")
    print("=" * 100)
    for name in sorted(per_card, key=lambda k: -len(per_card[k])):
        uniq: list[str] = []
        for frag, kind, _, _ in per_card[name]:
            if frag not in uniq:
                uniq.append(frag)
        print()
        print(f"--- [{name}]  {len(uniq)} 条唯一片段 ---")
        for frag in uniq[: args.show]:
            print(f"    {frag[:150]}")
        if len(uniq) > args.show:
            print(f"    …… 还有 {len(uniq) - args.show} 条")
    print()
    print("=" * 100)
    print("⚠ 本脚本**只清点、不判定**。")
    print("  用途：改长度措辞前确认**一共要改几处**。")
    print("  依据 `test_prompts.py:9249` 的实测结论 —— 只改一处等于没改，")
    print("  模型会取剩下那条**更宽**的。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
