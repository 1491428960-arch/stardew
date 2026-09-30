"""长度约束的**衰减漏斗**：一条约束从"作者写下"到"模型遵守"，每道闸各漏掉多少。

## 为什么要有这个

2026-09-28 之前，关于长度约束我们**只知道最后一个数字**：输出侧超 40 字上限 **43.8%**。
那个数字被反复当成"模型不听话"的证据 —— **但它其实是整条链路的末端结果**。

当晚逐个量出了前面四道闸，于是同一个 43.8% 有了完全不同的解释：

```
① 作者写进角色数据        每个角色 4 条 responseRules
        ↓  到达率 50%     （voice_actions[:3] 截断；sentencePattern 先占 2 槽）
② 进到 prompt 的卡        2 条 —— 而长度那条往往不在这 2 条里
        ↓
③ 落在管长度的卡上       全 prompt 只有 1/6 张卡提「字数」
        ↓
④ 模型读到               字数 vs 句数 的**文本量**对比
        ↓
⑤ 输出侧被遵守           实测超 40 字上限 43.8%
```

⇒ **43.8% 不是"不听话"，是这条约束**一路衰减到了尽头**。**

## 用途

**改任何长度措辞之前/之后各跑一次** —— 能立刻看出改动影响的是哪一道闸：

- 只改 ③④（措辞/卡数）⇒ ①②⑤ 应基本不动；
- 若 ⑤ 没动而 ③④ 明显变了 ⇒ 说明**瓶颈不在措辞**。

## 诚实边界

- 每道闸的量法**不同**（条数 / 比例 / 卡数 / 字符数 / 比例），
  **不能相乘**得出一个"总通过率" —— 它们不是同一量纲。
  本脚本只做**逐闸并列**，不给合成数字。
- ① 层用关键词认"长度条目"（含「字」「句」「短」「长」），是**近似**。
- ④ 层的"文本量"按**字符数**算，不等于模型注意力权重。
- ⑤ 层依赖 `artifacts/` 是否已跑过；没跑过会显示 `n/a` 而不是 0。

用法：

    python scripts/probe_length_constraint_decay.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "scripts"))
sys.path.insert(0, str(WT / "bridge" / "src"))

import check_prompt_consistency as chk  # noqa: E402

SPLIT = re.compile(r"(?<=[。！？；])|\n+")
LENGTH_WORDS = ("字", "句", "短", "长")
DATA = WT / "data" / "personas"

#: 第 ⑤ 道闸的判据口径，与 `guard._DIALOGUE_MAX_CHARS` 同源。
#: 原先硬编码 40 —— 2026-09-30 上限放宽到 60 后，
#: 那个数字已不代表任何约束，再用它算就是算错。
try:
    from stardew_ai_bridge.guard import _DIALOGUE_MAX_CHARS as CEILING
except Exception:  # noqa: BLE001
    CEILING = 60


def gate1_data_layer() -> tuple[int, int, int]:
    """① 角色数据层：``(总条数, 含长度词的条数, 角色数)``。"""
    total = lengthish = npcs = 0
    for path in sorted(DATA.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue

        def walk(node: object, name: str = "") -> None:
            nonlocal total, lengthish, npcs
            if isinstance(node, dict):
                # ⚠ `displayName` 在 `voiceStyle` 的**父层** —— 必须向下传递。
                # （同一层级错误我在 `probe_response_rules_reach.py` 刚修过一次，
                #   写这个脚本时又犯了。已在此显式记下。）
                here = node.get("displayName") or node.get("npcId") or name
                rules = node.get("responseRules")
                if isinstance(rules, list) and rules and isinstance(here, str) and here:
                    npcs += 1
                    for r in rules:
                        if isinstance(r, str):
                            total += 1
                            if any(w in r for w in LENGTH_WORDS):
                                lengthish += 1
                for v in node.values():
                    walk(v, here if isinstance(here, str) else name)
            elif isinstance(node, list):
                for v in node[:80]:
                    walk(v, name)

        walk(doc)
    return total, lengthish, npcs


def gate2_reach() -> tuple[int, int]:
    """② 到达率：直接复用已实测的结论来源（同口径重算，避免两处不一致）。"""
    from probe_response_rules_reach import load_rules, prompt_text  # noqa: PLC0415

    rules = load_rules()
    tot = hit = 0
    for key, items in rules.items():
        fname, _, npc = key.partition("::")
        if fname != "vanilla.json":  # 其余文件是汉化名/overlay，见已知缺陷
            continue
        text = prompt_text(npc, "stranger")
        if not text.strip():
            continue
        tot += len(items)
        hit += sum(1 for r in items if r[:8] in text)
    return tot, hit


def gate3_cards() -> tuple[int, int, int]:
    """③ 卡层：``(含字数的卡数, 含句数的卡数, 卡总数)``（三条路径并集）。"""
    # ⚠⚠ 必须用 chk.QUANTITIES 的正则，不能自己写。
    # 第一版图省事写了只匹配阿拉伯数字的正则，漏掉中文数字
    # （「只说一句」），得出 1:4；而主结论用 chk.QUANTITIES（含中文数字）得 1:6。
    # ⇒ 同一件事两个口径两个答案 —— 工具必须复用权威正则。
    len_re = re.compile(chk.QUANTITIES["字数"])
    sen_re = re.compile(chk.QUANTITIES["句数"])
    seen: dict[str, tuple[bool, bool]] = {}
    for topic, compact in chk.PATHS:
        for stage in chk.STAGES:
            hearts, extra = chk.STAGES[stage]
            from stardew_ai_bridge.prompts import (  # noqa: PLC0415
                ContextBuilder,
                PromptBuilder,
            )

            ctx = ContextBuilder().build("Wizard", friendshipHearts=hearts, **extra)
            if topic:
                ctx["interaction"] = {"intent": "topic"}
                cards = PromptBuilder().build(ctx, "", compact=compact)
            else:
                cards = PromptBuilder().build(ctx, "你好啊", compact=compact)
            for card in cards:
                has_len = bool(len_re.search(card["content"]))
                has_sen = bool(sen_re.search(card["content"]))
                if has_len or has_sen:
                    prev = seen.get(card["name"], (False, False))
                    seen[card["name"]] = (prev[0] or has_len, prev[1] or has_sen)
    n_len = sum(1 for v in seen.values() if v[0])
    n_sen = sum(1 for v in seen.values() if v[1])
    return n_len, n_sen, len(seen)


def gate4_text_volume() -> tuple[int, int]:
    """④ 文本量：全 prompt 里「字数」类片段的字符数 vs「句数」类片段的字符数。"""
    len_re = re.compile(chk.QUANTITIES["字数"])
    sen_re = re.compile(chk.QUANTITIES["句数"])
    len_chars = sen_chars = 0
    for topic, compact in chk.PATHS:
        for stage in chk.STAGES:
            hearts, extra = chk.STAGES[stage]
            from stardew_ai_bridge.prompts import (  # noqa: PLC0415
                ContextBuilder,
                PromptBuilder,
            )

            ctx = ContextBuilder().build("Wizard", friendshipHearts=hearts, **extra)
            if topic:
                ctx["interaction"] = {"intent": "topic"}
                cards = PromptBuilder().build(ctx, "", compact=compact)
            else:
                cards = PromptBuilder().build(ctx, "你好啊", compact=compact)
            for card in cards:
                for frag in SPLIT.split(card["content"]):
                    frag = frag.strip()
                    if not frag:
                        continue
                    if len_re.search(frag):
                        len_chars += len(frag)
                    if sen_re.search(frag):
                        sen_chars += len(frag)
    return len_chars, sen_chars


def gate5_output() -> tuple[int, int] | None:
    """⑤ 输出侧：实测超上限的轮数 / 总轮数。

    ⚠ `iter_turns` 产出的是 **5 元组**：
    ``(run 目录, mtime, caseId, npcId, 字数)`` —— 我第一版按 4 元组解包，静默拿到 n/a。
    """
    try:
        from probe_length_compliance import iter_turns  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    total = over = 0
    try:
        for _run, _mtime, _cid, _npc, length in iter_turns():
            total += 1
            if length > CEILING:
                over += 1
    except Exception:  # noqa: BLE001
        return None
    return (over, total) if total else None


def pct(a: int, b: int) -> str:
    return f"{a / b * 100:.0f}%" if b else "n/a"


def main() -> int:
    print("=" * 100)
    print("长度约束的**衰减漏斗**：一条约束从「作者写下」到「模型遵守」")
    print("=" * 100)
    print()

    tot, lengthish, npcs = gate1_data_layer()
    print("闸 ① 角色数据层")
    print(f"     data/personas/*.json 共 {npcs} 个角色条目、{tot} 条 responseRules")
    print(f"     其中**含长度词**（字/句/短/长）的：**{lengthish}** 条（{pct(lengthish, tot)}）")
    print()

    rtot, rhit = gate2_reach()
    print("闸 ② 到达率（写进数据 → 真的进 prompt）")
    print(f"     vanilla.json 口径：写了 {rtot} 条 → 进 prompt **{rhit}** 条"
          f"（**{pct(rhit, rtot)}**）")
    print("     根因：`voice_actions[:3]` 截断；`signatureMoves` 为空时 `sentencePattern` 先占 2 槽")
    print()

    n_len, n_sen, n_card = gate3_cards()
    print("闸 ③ 卡片层（三条路径并集去重）")
    print(f"     提到**字数**的卡：**{n_len}** 张")
    print(f"     提到**句数**的卡：**{n_sen}** 张")
    print(f"     ⇒ 字数 / 句数 = **1 : {n_sen / n_len:.1f}**" if n_len else "     ⇒ n/a")
    print()

    len_chars, sen_chars = gate4_text_volume()
    print("闸 ④ 文本量（按字符数）")
    print(f"     含字数要求的片段合计 **{len_chars}** 字符")
    print(f"     含句数要求的片段合计 **{sen_chars}** 字符")
    print(f"     ⇒ 字数 / 句数 = **1 : {sen_chars / len_chars:.1f}**" if len_chars else "     ⇒ n/a")
    print()

    out = gate5_output()
    print("闸 ⑤ 输出侧遵守")
    if out is None:
        print("     n/a（`artifacts/` 未跑过或读取失败 —— **不是 0**）")
    else:
        over, total = out
        print(f"     共 **{total}** 轮；超 {CEILING} 字上限 **{over}** 轮（**{pct(over, total)}**）")
    print()

    print("=" * 100)
    print("⚠ **不要把五道闸相乘** —— 量纲不同（条数 / 比例 / 卡数 / 字符数 / 比例），")
    print("   相乘会得到一个**没有意义**的「总通过率」。本表只做**逐闸并列**。")
    print()
    print("⭐ 但它足以说明一件事：")
    print("   **43.8% 不是「模型不听话」，是这条约束一路衰减到了尽头。**")
    print()
    print("   改措辞之前/之后各跑一次：")
    print("     · 只改 ③④（措辞/卡数）⇒ ①②⑤ 应基本不动")
    print("     · 若 ⑤ 没动而 ③④ 明显变了 ⇒ **瓶颈不在措辞**，别再改措辞了")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
