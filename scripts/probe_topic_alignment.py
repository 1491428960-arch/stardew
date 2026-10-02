"""台账盲区第五类：**阶段对了，话题不对** —— 约束需要的话题在 case 集里不存在。

## 为什么需要这一层

前四类盲区各自回答一个问题：

| 类 | 问题 |
|---|---|
| ① 抽取端漏抓 | 约束**被登记**了吗？ |
| ② 跨量算术 | 两个量的关系**被表达**了吗？ |
| ③ 评测集阶段覆盖 | 该**阶段**有样本吗？ |
| ④ 验证工具自身 | 我的探针**真的在变化输入**吗？ |

这一层问的是**第四问**：**该阶段有样本，但样本问的是那件事吗？**

## 起因（实测）

「**初识阶段**不得反问、**邀约**或主动换题」——
要验它，需要 **`acquaintance` × `邀约`** 的样本。

而实际扫出来：

```
acquaintance 的 12 个 case，全部是 daily / coop / training / ranch
case 集里确实有邀约类（wizard-dating-invite、wizard-remote-invite…）
     —— 但**全在 friend / dating 阶段**
```

⇒ **阶段有了、邀约有了，但两者不相交** ⇒ 那条约束**仍然测不了**。

⚠ 这一层直接修正了一个过于乐观的结论：
我先前说「acquaintance 有 12 个 case ⇒ **跑全即可**验证那 12 条初识约束」——
**不对**。话题不对，跑全也没用。

## 做什么

对**每一条带阶段限定的约束片段**：

1. 从片段文本里识别它**要求/禁止的话题意图**（邀约、反问、换题、亲密、动作……）；
2. 在**云端 case 集（全部 suite 并集）**里找 **该阶段 × 该话题** 的 case；
3. 没有就标出来 —— 它们**即使把 suite 跑全也验不了**。

⚠ 只摊开、不判定，`return 0`。话题意图靠关键词近似，**是下界不是定论**。

用法：

    python scripts/probe_topic_alignment.py
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "scripts"))
sys.path.insert(0, str(WT / "bridge" / "src"))

import check_prompt_consistency as chk  # noqa: E402

SPLIT = re.compile(r"(?<=[。！？；])|\n+")

#: 阶段词 → 规范阶段名。
#:
#: ⚠⚠ **「初识」= `stranger`，不是 `acquaintance`**（2026-09-28 实测）：
#: 「初识阶段不得反问、邀约或主动换题；」只出现在 `stranger` 阶段的
#: `stage_execution_card` 里。映射错会**指错补数据的方向**。
STAGE_ALIASES = {
    "初识": "stranger",
    "陌生": "stranger",
    "刚认识": "stranger",
    "stranger": "stranger",
    "acquaintance": "acquaintance",
    "熟悉": "friend",
    "朋友": "friend",
    "friend": "friend",
    "亲密": "close",
    "close": "close",
    "恋人": "dating",
    "约会": "dating",
    "dating": "dating",
    "爱人": "married",
    "伴侣": "married",
    "夫妻": "married",
    "已婚": "married",
    "marri": "married",
    "家长": "parent",
    "父母": "parent",
    "parent": "parent",
    "孩子": "parent",
}

#: 话题意图 → 用于在**约束文本**里识别它的词。
#:
#: ⚠ **「长度」不在表里**（v1 曾把它放进来）—— 长度是**形式属性、不是话题**，
#: 没有对应的 case 话题词表 ⇒ 它的匹配数恒为 0，会打印出一整列**假的** ❌。
#: 长度约束的覆盖情况属 `probe_length_directives.py` 管，不要混进这一层。
INTENT_WORDS = {
    "邀约": ("邀约", "邀请", "约", "出门"),
    "反问": ("反问", "追问", "提问"),
    "换题": ("换题", "新话题", "开启新话题", "主动开"),
    "亲密": ("亲密", "亲近", "暧昧", "肢体"),
    "动作": ("动作", "表情", "反应"),
}

#: 话题意图 → 用于在 **case_id / topic_seed / topic_keywords** 里找它的词。
INTENT_CASE_WORDS = {
    "邀约": ("invite", "invitation", "邀", "一起", "出门", "约"),
    "反问": ("follow-up", "followup", "追问", "反问", "question"),
    "换题": ("topic-control", "topic-start", "turn", "换题"),
    "亲密": ("flirt", "intimate", "close", "pacing", "亲密"),
    "动作": ("action", "gesture", "动作"),
}

STAGES7 = ("stranger", "acquaintance", "friend", "close", "dating", "married", "parent")


def is_json_fragment(frag: str) -> bool:
    """判断片段是不是**被切碎的嵌入式 JSON**。

    ⚠ v1 没做这个过滤，结果 `close × 亲密` 报出 **72 条约束** ——
    不可能有那么多；真相是 `persona_core` / `stage_execution_card` 里嵌的
    JSON 被中文标点切分器切成大量碎片，**同一段被反复计数**。
    ⇒ 不过滤就得到一个**看起来很像结论的假数字**。
    """
    if frag.count('"') >= 2:
        return True
    if re.search(r"[{}\[\]]", frag):
        return True
    if re.search(r'":\s', frag):
        return True
    return False


def load_cases() -> list[tuple[str, str, str]]:
    """返回 ``[(case_id, stage, 可搜索文本)]``，取**全部 suite 并集**。"""
    out: list[tuple[str, str, str]] = []
    try:
        from stardew_ai_bridge.character_quality_eval import (  # noqa: PLC0415
            QUALITY_SUITE_IDS,
            quality_cases_for_suite,
        )

        seen: dict[str, object] = {}
        for suite in QUALITY_SUITE_IDS:
            for case in quality_cases_for_suite(suite):
                seen[case.case_id] = case
        for cid, case in seen.items():
            blob = " ".join(
                [
                    cid,
                    str(getattr(case, "topic_seed", "") or ""),
                    " ".join(getattr(case, "topic_keywords", ()) or ()),
                    str(getattr(case, "message", "") or ""),
                ]
            ).casefold()
            out.append((cid, str(getattr(case, "relationship_stage", "") or ""), blob))
    except Exception:  # noqa: BLE001
        return out
    return out


def collect_constraints() -> dict[tuple[str, str], list[str]]:
    """``{(stage, intent): [片段]}`` —— 只收**同时有阶段词和意图词**的片段。"""
    from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: PLC0415

    found: dict[tuple[str, str], list[str]] = defaultdict(list)
    for topic, compact in chk.PATHS:
        for stage in chk.STAGES:
            _hearts, _extra = chk.STAGES[stage]
            ctx = ContextBuilder().build("Wizard", friendshipHearts=_hearts, **_extra)
            if topic:
                ctx["interaction"] = {"intent": "topic"}
                cards = PromptBuilder().build(ctx, "", compact=compact)
            else:
                cards = PromptBuilder().build(ctx, "你好啊", compact=compact)
            for card in cards:
                frags = [
                    s.strip() for s in SPLIT.split(card["content"]) if s and s.strip()
                ]
                for frag in frags:
                    # ⚠ 先剔掉被切碎的嵌入式 JSON —— 否则同一段会被反复计数，
                    # 报出「close × 亲密 72 条约束」这种不可能的数字（v1 踩过）。
                    if is_json_fragment(frag):
                        continue
                    if len(frag) < 8:  # 太短的碎片没有判断价值
                        continue
                    # 阶段词必须出现在**这一片段**里（这才是「限定」）。
                    st = next(
                        (canon for w, canon in STAGE_ALIASES.items() if w in frag), None
                    )
                    if st is None:
                        continue
                    for intent, words in INTENT_WORDS.items():
                        if any(w in frag for w in words):
                            found[(st, intent)].append(frag)
    # **去重**：同一片段会在多条路径 × 多个阶段里重复出现。
    return {k: sorted(set(v)) for k, v in found.items()}


def main() -> int:
    cases = load_cases()
    by_stage: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for cid, stage, blob in cases:
        by_stage[stage].append((cid, blob))

    print("=" * 100)
    print("第五类盲区：**阶段对了，话题不对** —— 约束要的话题在 case 集里不存在")
    print("=" * 100)
    print()
    print(f"  case 集（全部 suite 并集）共 **{len(cases)}** 个 case")
    print(
        "  阶段分布："
        + " ".join(f"{s}={len(by_stage.get(s, []))}" for s in STAGES7)
    )
    print()

    cons = collect_constraints()
    rows = sorted(cons.items(), key=lambda kv: -len(kv[1]))

    print("## 约束 ×（阶段, 话题意图）× case 集是否有对应样本")
    print()
    print(f"  {'阶段':<14} {'话题意图':<8} {'约束条数':>8}   {'该阶段 case':>10}   {'话题匹配':>8}   判定")
    print("  " + "-" * 92)
    blind: list[tuple[str, str, int]] = []
    for (stage, intent), frags in rows:
        pool = by_stage.get(stage, [])
        words = INTENT_CASE_WORDS.get(intent, ())
        if not words:
            matched = []
        else:
            matched = [cid for cid, blob in pool if any(w in blob for w in words)]
        if not pool:
            verdict = "❌ **该阶段无 case**"
            blind.append((stage, intent, len(frags)))
        elif not matched:
            verdict = "❌ **阶段有、话题没** ⇒ 跑全也测不到"
            blind.append((stage, intent, len(frags)))
        elif len(matched) < 3:
            verdict = f"⚠ 仅 {len(matched)} 个匹配"
        else:
            verdict = "✅ 可测"
        print(
            f"  {stage:<14} {intent:<8} {len(frags):>8}   {len(pool):>10}   "
            f"{len(matched):>8}   {verdict}"
        )

    print()
    print("=" * 100)
    print("## ⚠ 即使把 suite 跑全也测不到的约束（阶段有、话题没）")
    print()
    if not blind:
        print("  （无）")
    for stage, intent, n in blind:
        print(f"  · **{stage} × {intent}** —— {n} 条约束")
        for frag in sorted(set(cons[(stage, intent)]))[:2]:
            print(f"      {frag[:104]}")
    print()
    print("=" * 100)
    print("⚠ 本脚本**只摊开、不判定**：")
    print("  · 话题意图靠**关键词近似** ⇒ 匹配数是**下界**，「话题没」可能是我的词表不够。")
    print("  · 它**不**说明约束写错了，只说明**现有 case 集测不到它**。")
    print("  ⇒ 这正是补 case 时**必须按（阶段 × 话题）配对**、而不是只补阶段的原因。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
