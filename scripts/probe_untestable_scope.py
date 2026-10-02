"""台账盲区第五类：**哪些约束因为「已跑评测集从未覆盖该阶段」而无法验证**。

## 起因

2026-09-28 测 `邀约` 失败（续二十六），后来量化了原因：

```
artifact 阶段覆盖： married 59 / dating 36 / friend 22 / close 9
                    acquaintance  4  /  stranger  0     ← ⚠⚠
```

而 `邀约` 的约束原文是「**初识阶段**不得反问、邀约或主动换题」——
**它要测的两个阶段，已跑的样本几乎不存在**（stranger 一个都没有）。

⇒ 由此得到一类**结构性盲区**（不是提取器漏了，也不是没有场景，而是**跑过的没覆盖**）：
**凡是限定在「初识 / 陌生」的约束，现有 artifact 一条都验不了。**

## ⚠⚠ 一个必须分清的区分（我一开始就说错过）

**「artifact 里没有」≠「没有可用的场景」。**

| | 含义 | 能否补救 |
|---|---|---|
| **artifact 覆盖** | **已经跑过并留下记录的** case | 要**重跑** |
| **场景定义** | `data/personas/behavior-quality-scenarios.json` 里**已有的**场景 | **直接可跑** |

**实测（2026-09-28）**：场景定义文件里有 **21 个场景**，
`relationshipStage` 分布是 **acquaintance 5 / friend 5 / dating 6 / married 5** ——
也就是说 `wizard-acquaintance-remote-invitation`（Wizard × 初识 × **邀约**主题）
这样的场景**本来就存在**，只是**没进过已跑的评测集**。

⇒ 所以正确的说法是「**已跑的评测集里初识阶段几乎为空**」，
**不是**「没有场景可用于验证」—— 后者会让人误以为必须先造数据。
⇒ 仍然**不能**拿现有 artifact 去测那条约束（那是我犯过的错），
但要补的只是**一次定向重跑**，不是从零构造场景。

## 做什么

把 3 条路径 × 7 档阶段里**所有带阶段限定的约束片段**找出来，
按**限定到哪个阶段**归类，并与 **artifact 的实际覆盖**对照，
标出**覆盖为 0 或极少**的那些 —— 它们就是「**用现有样本测不了**」的约束。

⚠ 只摊开、不判定，`return 0`。它不下"这些约束有问题"的结论，
只指出"**这些约束目前无法用现有样本验证**"。

用法：

    python scripts/probe_untestable_scope.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "scripts"))
sys.path.insert(0, str(WT / "bridge" / "src"))

import check_prompt_consistency as chk  # noqa: E402

ART = WT / "artifacts" / "character-quality-eval"
SCENARIOS = WT / "data" / "personas" / "behavior-quality-scenarios.json"

#: 阶段词 → 规范化阶段名。
#:
#: ⚠⚠ **「初识」必须映射到 `stranger`，不是 `acquaintance`** ——
#: 2026-09-28 实测：「初识阶段不得反问、邀约或主动换题；」这条约束
#: **只出现在 `stranger` 阶段的 `stage_execution_card` 里**
#: （卡内 `"stage": "stranger"`）。
#:
#: ⇒ 我一开始把它映射成 `stranger/acquaintance` 两可，
#:   于是把「该约束测不了」的原因说成了「acquaintance 样本少」——
#:   **真正的原因是 `stranger` 一个 case 都没有**。
#:   ⇒ 这会**指错补数据的方向**（去补 acquaintance，而约束在 stranger 生效）。
#: 台账 `constraint_scope.CURRENT` 里那条的 `cond` 也确实是 `stage: stranger`。
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

SPLIT = re.compile(r"(?<=[。！？；])|\n+")

STAGES7 = ("stranger", "acquaintance", "friend", "close", "dating", "married", "parent")


def artifact_stage_coverage() -> tuple[dict[str, int], int]:
    """扫 artifact，数每个阶段有多少个 case（按 caseId 里的阶段词，去重）。

    返回 ``(每个阶段的 case 数, caseId 总数)``。
    """
    counts: dict[str, int] = {s: 0 for s in STAGES7}
    counts["(无阶段词)"] = 0
    seen: set[str] = set()
    if not ART.exists():
        return counts, 0
    for run in ART.iterdir():
        f = run / "results.jsonl"
        if not (run.is_dir() and f.exists()):
            continue
        try:
            txt = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in txt.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                cid = str(json.loads(line).get("caseId") or "")
            except Exception:  # noqa: BLE001
                continue
            if cid in seen:
                continue
            seen.add(cid)
            hit = next((s for s in STAGES7 if s in cid), None)
            counts[hit or "(无阶段词)"] += 1
    return counts, len(seen)


def available_stage_coverage() -> Counter[str]:
    """数**云端评测 case 集**里每个阶段有多少个 case —— **取全部 suite 的并集**。

    ⚠⚠ **这里踩过两次坑，都记下来**：

    **坑一（查错源头）**：我最初以为「可跑的」是
    `data/personas/behavior-quality-scenarios.json` —— **错了**。
    那是**本地行为样本生成器**（`scripts/generate_behavior_examples.py`，
    `--provider` 只有 `local`，走 Ollama）的输入，**与云端评测无关**。
    云端 case 定义在**源码** `stardew_ai_bridge.character_quality_eval` 里。

    **坑二（只看了 default）**：`DEFAULT_CASES` 只有 **47** 个，
    但 artifact 里 married 跑过 **59** 个 —— **跑过的比 default 还多**，
    说明 artifact 的 case 来自**多个 suite**（`relationship-world`、
    `topic-start-*` 等）。⇒ 必须取**全部 suite 的并集**（去重后 **255** 个）。
    只看 `DEFAULT_CASES` 会把「可跑的」低估一半以上。

    ⇒ 用并集后结论**更硬**：**stranger / parent 在全部 255 个 case 里都是 0。**
    """
    out: Counter[str] = Counter()
    try:
        from stardew_ai_bridge.character_quality_eval import (  # noqa: PLC0415
            QUALITY_SUITE_IDS,
            quality_cases_for_suite,
        )

        seen: dict[str, str] = {}
        for suite in QUALITY_SUITE_IDS:
            for case in quality_cases_for_suite(suite):
                stage = getattr(case, "relationship_stage", None)
                if stage:
                    seen[case.case_id] = str(stage)
        out.update(seen.values())
    except Exception:  # noqa: BLE001
        return out
    return out


def main() -> int:
    from stardew_ai_bridge.prompts import ContextBuilder, PromptBuilder  # noqa: PLC0415

    #: 规范化阶段 → {卡名: [片段]}
    per_scope: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

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
                frags = [s.strip() for s in SPLIT.split(card["content"]) if s and s.strip()]
                for i, frag in enumerate(frags):
                    if not any(re.search(rx, frag) for rx in chk.QUANTITIES.values()):
                        continue
                    window = " ".join(frags[max(0, i - 1) : i + 2])
                    for word, canon in STAGE_ALIASES.items():
                        if word in window:
                            per_scope[canon][name].append(frag)
                            break

    cov, n_cases = artifact_stage_coverage()
    scen = available_stage_coverage()

    print("=" * 100)
    print("哪些约束因为「已跑评测集从未覆盖该阶段」而**用现有样本测不了**")
    print("=" * 100)
    print()
    print("## 一、两份覆盖**必须分开看**，且第二列要查**对源头**")
    print()
    print("  「**没跑过**」≠「**没有 case**」—— 前者跑一下就行，后者要**新写 case**。")
    print()
    print("  ⚠⚠ 第二列取的是**云端评测的 `DEFAULT_CASES`**（源码里），")
    print("  **不是** `data/personas/behavior-quality-scenarios.json` ——")
    print("  那个是**本地行为样本生成器**的输入，与云端评测无关。")
    print("  （我一度查错源头，把「case 集里根本没有」误读成「跑一下就行」。）")
    print()
    print(f"  {'阶段':<16} {'跑过的(artifact)':>16} {'case 集里的':>12}")
    for s in STAGES7:
        a = cov.get(s, 0)
        b = scen.get(s, 0)
        fa = "⚠⚠" if a == 0 else ("⚠" if a <= 5 else "  ")
        fb = "⚠⚠" if b == 0 else "  "
        print(f"  {s:<16} {a:>13} {fa} {b:>9} {fb}")
    print(f"  {'(无阶段词)':<16} {cov.get('(无阶段词)', 0):>13}")
    print()
    print(f"  ⇒ artifact 共 **{n_cases}** 个不同 caseId；")
    print(f"     云端 case 集共 **{sum(scen.values())}** 个 case")
    print()

    print("## 二、约束按「限定到的阶段」归类")
    print()
    rows = sorted(per_scope.items(), key=lambda kv: -sum(len(v) for v in kv[1].values()))
    for canon, cards in rows:
        total = sum(len(v) for v in cards.values())
        if canon == "stranger/acquaintance":
            n = cov.get("stranger", 0) + cov.get("acquaintance", 0)
            ns = scen.get("stranger", 0) + scen.get("acquaintance", 0)
        else:
            key = canon.split("/")[0]
            n = cov.get(key, 0)
            ns = scen.get(key, 0)
        if n == 0:
            verdict = "❌ **用现有样本测不了**（artifact 覆盖 0）"
        elif n <= 5:
            verdict = f"⚠ 样本仅 {n} ⇒ 结论不可靠"
        else:
            verdict = f"✅ 可验证（{n} 个 case）"
        if n <= 5 and ns > 0:
            verdict += f"；但**已有 {ns} 个场景** ⇒ 定向重跑即可，不必造数据"
        print(f"  ── 限定到【{canon}】的约束：{total} 条，涉及 {len(cards)} 张卡")
        print(f"     artifact 覆盖：{n} 个 case ⇒ {verdict}")
        for cname in sorted(cards, key=lambda k: -len(cards[k])):
            uniq = sorted(set(cards[cname]))
            print(f"       [{cname}]  {len(uniq)} 条")
            for f in uniq[:2]:
                print(f"          {f[:110]}")
        print()

    print("=" * 100)
    print("⚠ 本脚本**只摊开、不判定**。")
    print("  它指出的是「**现有样本无法验证**」，**不是**「这些约束写错了」，")
    print("  也**不是**「没有场景可用」—— 见第一节的两列对比。")
    print("  依据：2026-09-28 测 `邀约` 时拿全阶段样本去测一条只管初识阶段的约束，")
    print("  ⇒ **测的不是约束对象**，得到的 8.8% 无意义。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
