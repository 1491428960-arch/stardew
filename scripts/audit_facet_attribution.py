"""判面归因审计：主面为什么是它 —— 宽词、多面命中、并列素材（**只读**）。

三个问题，三段输出：

  * `wide`  —— 每个面的分支里，哪些**命中多但主面占比低**（可能在吃别人的句子）
  * `multi` —— 多少条目**同时命中 ≥2 个面**（这些条目的主面完全由**声明顺序**决定）
  * `enum`  —— 哪些素材是**跨主题并列**（含并列连接词 **且** 跨面 ⇒ 模型可能一次说好几件事）

结论与背景见 `docs/report-facet-rotation-2026-09-22.md` §9、§10：

  * 全库 713 / 8717 条（**8%**）多面命中；角色素材 24 / 250 条（**10%**）
  * 最常见组合「家人朋友 + 工作或手艺」86 条 —— 工作面声明在第一位且手里全是宽词，
    所以"工作面占 58%"的机制是**声明顺序**，不是"她总在谈工作"
  * 跨主题并列素材 14 条，其中 Rasmodia 与 Wizard 的「天气和小镇见闻」**逐字相同**
    ⇒ 批量模板留下的痕迹
  * "命中 ≥30 且主面占比 <50%" 的可疑分支：**0 个** —— 问题不在单个词

用法：

    PYTHONPATH=bridge/src;scripts python -B scripts/audit_facet_attribution.py
    ... --section enum            # 只看跨主题并列
    ... --wide-threshold 20       # 调宽词抽查的命中门槛
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from facet_probe_common import corpus, first_hit, hits, patched  # noqa: E402

from stardew_ai_bridge.prompts import _preferred_topics_for_prompt  # noqa: E402
from stardew_ai_bridge.stage_policy import _LIFE_FACET_PATTERNS  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

TOP_PER_FACET = 6
ENUM_MARKERS = ("、", "和", "与")

# 未打补丁的词表，只构造一次 —— 别放进循环里重建（8717 条 × 每面分支数会拖到无法忍受）。
BASE = patched({})


def character_topics() -> dict[str, list[str]]:
    """每个角色**真正喂给 stage policy** 的那一份 preferredTopics。"""

    profiles: dict[str, list[str]] = {}
    for path in sorted((ROOT / "data" / "personas").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, profile in (payload.get("personas") or {}).items():
            if not isinstance(profile, dict):
                continue
            voice_style = profile.get("voiceStyle")
            raw = (
                voice_style.get("preferredTopics")
                if isinstance(voice_style, dict)
                else None
            )
            topics = _preferred_topics_for_prompt(raw)
            if topics:
                profiles[name] = topics
    return profiles


def section_wide(rows, threshold: int) -> list[tuple[str, str, int, int]]:
    """宽词：按面列分支的命中数 / 主面贡献，标出可疑项。"""

    suspects: list[tuple[str, str, int, int]] = []
    for name, pattern in _LIFE_FACET_PATTERNS:
        branches = [b for b in pattern.split("|") if b.strip()]
        stats: list[tuple[str, int, int]] = []
        for branch in branches:
            hit = first = 0
            for _, text in rows:
                if not re.search(branch, text):
                    continue
                hit += 1
                if first_hit(text, BASE) == name:
                    first += 1
            stats.append((branch, hit, first))
        stats.sort(key=lambda item: -item[1])

        print("=" * 96)
        print(f"面「{name}」—— 分支 {len(branches)} 个")
        print(f"{'分支':<26}{'全库命中':>9}{'主面贡献':>9}{'占比':>8}  判定")
        print("-" * 96)
        for branch, hit, first in stats[:TOP_PER_FACET]:
            ratio = f"{first / hit:.0%}" if hit else "—"
            if hit >= 30 and first / hit < 0.5:
                verdict = "⚠ 命中多但多数不是主面（可能在吃别人的句子）"
                suspects.append((name, branch, hit, first))
            elif hit >= 60:
                verdict = "宽词（继续用前建议抽查）"
            else:
                verdict = ""
            print(f"{branch:<26}{hit:>9}{first:>9}{ratio:>8}  {verdict}")

        low = [s for s in stats if s[1] >= threshold and s[2] / s[1] < 0.6]
        if low:
            branch = low[0][0]
            print()
            print(f"  ── 抽查「{branch}」（命中 {low[0][1]}，主面仅 {low[0][2]}）：")
            shown = 0
            for npc, text in rows:
                if re.search(branch, text) and first_hit(text, BASE) != name:
                    print(f"     [{npc}] {text[:88]}")
                    shown += 1
                    if shown >= 3:
                        break
    return suspects


def section_multi(rows, rows_first) -> None:
    """多面命中：主面由声明顺序决定的条目有多少。"""

    counter: Counter = Counter()
    for (_, text), before in zip(rows, rows_first):
        facets = tuple(sorted(hits(text, BASE)))
        if len(facets) >= 2:
            counter[facets] += 1
    total = sum(counter.values())

    print("=" * 96)
    print(f"全库多面命中：{total} / {len(rows)} = {total / len(rows):.0%}")
    print("（这些条目的主面**完全由声明顺序决定**，不是由内容轻重决定）")
    print()
    print("最常见的面组合：")
    for combo, count in counter.most_common(8):
        print(f"  {count:>5}  {' + '.join(combo)}")


def section_enum(profiles, rows_first_map) -> None:
    """跨主题并列素材：含并列连接词 且 跨面。"""

    print("=" * 96)
    print("跨主题并列素材（判据：含 、/和/与 **且** 命中 ≥2 个面）")
    print()
    suspects = []
    same_facet = 0
    for npc, topics in sorted(profiles.items()):
        for topic in topics:
            if not any(marker in topic for marker in ENUM_MARKERS):
                continue
            facets = hits(topic, BASE)
            if len(facets) >= 2:
                suspects.append((npc, topic, facets))
            else:
                same_facet += 1
    for index, (npc, topic, facets) in enumerate(suspects, start=1):
        main = first_hit(topic, BASE)
        print(f"  {index:>2}. {npc:<12} 「{topic}」")
        print(f"      主面={main}  还命中={sorted(facets - {main})}")
    print()
    print(f"跨主题并列：{len(suspects)} 条；含并列词但同面（可保留）：{same_facet} 条")


def main() -> None:
    parser = argparse.ArgumentParser(description="判面归因审计（只读）")
    parser.add_argument("--section", choices=["wide", "multi", "enum", "all"], default="all")
    parser.add_argument("--wide-threshold", type=int, default=20, help="宽词抽查的命中门槛")
    args = parser.parse_args()

    rows = corpus()
    rows_first = [first_hit(text, BASE) for _, text in rows]
    profiles = character_topics()

    if args.section in ("wide", "all"):
        suspects = section_wide(rows, args.wide_threshold)
        print()
        print(f"命中 ≥30 且主面占比 <50% 的可疑分支：{len(suspects)} 个")

    if args.section in ("multi", "all"):
        print()
        section_multi(rows, rows_first)

    if args.section in ("enum", "all"):
        print()
        section_enum(profiles, rows_first)


if __name__ == "__main__":
    main()
