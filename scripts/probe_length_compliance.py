"""量化「输出落点 vs prompt 上的长度上限」——即**约束遵守率**。

**为什么单独测这个**：2026-09-28 发现，改前那批跑的**平均 50.1 字**、
Sophia **73.9 字**，而 prompt 里的上限是 **1–2 句、15–40 字**，
且已确认该上限**确实出现在 prompt 里**（旧值 `1–3 句` / `15–80 字` 出现 0 次）。

⇒「prompt 里有一个上限」**≠**「输出会落在这个上限内」。
这是一类**独立于**「指令是否互相打架」的问题 ——
此前整个「指令体检」都只查了「prompt 内部一致不一致」，
**从没查过「模型到底照不照做」**。

**做什么**：扫全部 `artifacts/character-quality-eval/*/results.jsonl`，
把每一轮的回复字数汇到一起，统计：

- 中位数与均值（比均值抗离群）；
- **超上限比例**（按 `guard._DIALOGUE_MAX_CHARS` 这条通用上限，当前 60）；
- **按时序分组**，看长度收束（2026-09-28 02:30）前后有没有变化。

**零请求、只读**。用法：

    python scripts/probe_length_compliance.py
    python scripts/probe_length_compliance.py --ceiling 40 --since 2026-09-28
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
ART = WT / "artifacts" / "character-quality-eval"

#: 长度收束落地时刻（`prompts.py` 改 `1–3 句、15–80 字` → `1–2 句、15–40 字`）。
#: ⚠ 这只是历史事实的记录 —— 那两版文案现在都不在代码里了，
#: 当前 prompt 写的是「中文通常 1–2 句」（句数）。不要拿 CUTOVER 当口径。
CUTOVER = datetime(2026, 9, 28, 2, 30)

#: 超长判据的**单一来源** —— 直接引 `guard`，不要再硬编码。
#: 2026-09-30 上限由 40 放宽到 60，判据口径必须跟着走，
#: 否则报告里的「超标率」算的是一个没人遵守的旧数字。
try:
    import sys as _sys

    _sys.path.insert(0, str(WT / "bridge" / "src"))
    from stardew_ai_bridge.guard import _DIALOGUE_MAX_CHARS as _DEFAULT_CEILING
except Exception:  # noqa: BLE001
    _DEFAULT_CEILING = 60


def iter_turns(*, metric: str = "reply"):
    """产出 (run 目录, mtime, caseId, npcId, 字数)。⚠ 按 mtime 排序，不按目录名 ——
    artifact 命名不统一（`20260928-…` vs `topic-…-20260915`），按名字排会错序。"""
    if not ART.exists():
        return
    runs = sorted(
        (p for p in ART.iterdir() if p.is_dir() and (p / "results.jsonl").exists()),
        key=lambda p: p.stat().st_mtime,
    )
    for run in runs:
        mtime = datetime.fromtimestamp(run.stat().st_mtime)
        try:
            text = (run / "results.jsonl").read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError:
                continue
            npc = str(case.get("npcId") or "?")
            for turn in case.get("turns") or []:
                if not isinstance(turn, dict):
                    continue
                raw = turn.get(metric)
                if isinstance(raw, str) and raw:
                    yield run.name, mtime, str(case.get("caseId") or "?"), npc, len(raw)


def describe(lengths: list[int], ceiling: int) -> str:
    if not lengths:
        return "（无数据）"
    lengths = sorted(lengths)
    n = len(lengths)
    med = statistics.median(lengths)
    over = sum(1 for v in lengths if v > ceiling)
    over2 = sum(1 for v in lengths if v > ceiling * 2)
    return (
        f"n={n:>4}  中位={med:>5.1f}  均值={statistics.mean(lengths):>5.1f}  "
        f"p90={lengths[int(n * 0.9)]:>4}  最大={lengths[-1]:>4}  "
        f"超{ceiling}字={over:>4}({over / n * 100:>5.1f}%)  超{ceiling * 2}字={over2:>3}({over2 / n * 100:>4.1f}%)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="量化长度约束遵守率")
    ap.add_argument(
        "--ceiling",
        type=int,
        default=_DEFAULT_CEILING,
        help="通用长度上限（字），默认取 `guard._DIALOGUE_MAX_CHARS`",
    )
    ap.add_argument("--metric", default="reply", help="取哪个字段，默认 reply")
    ap.add_argument("--since", default=None, help="只看该日期之后的 artifact（YYYY-MM-DD）")
    args = ap.parse_args()

    rows = list(iter_turns(metric=args.metric))
    if not rows:
        print("没有可用数据。")
        return 0

    print("=" * 108)
    print(f"长度约束遵守率（上限 {args.ceiling} 字；字段 `{args.metric}`）")
    print("=" * 108)
    print(f"⚠ 这里把 {args.ceiling} 字当作**通用**上限。真实上限随阶段/角色略有不同，")
    print("   所以「超限」是**近似**判据，用来看**量级**，不是逐条定罪。")
    print()

    all_lengths = [r[4] for r in rows]
    print(f"【全部】{describe(all_lengths, args.ceiling)}")
    print()

    before = [r[4] for r in rows if r[1] < CUTOVER]
    after = [r[4] for r in rows if r[1] >= CUTOVER]
    print("【按长度收束（2026-09-28 02:30）分组】")
    print(f"  收束前  {describe(before, args.ceiling)}")
    print(f"  收束后  {describe(after, args.ceiling)}")
    print()

    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d")
        recent = [r[4] for r in rows if r[1] >= since]
        print(f"【{args.since} 之后】{describe(recent, args.ceiling)}")
        print()

    # 按角色（只看收束后，避免混条件）
    print("【收束后 · 按角色】")
    by_npc: dict[str, list[int]] = {}
    for _, mtime, _, npc, n in rows:
        if mtime >= CUTOVER:
            by_npc.setdefault(npc, []).append(n)
    for npc in sorted(by_npc, key=lambda k: -statistics.mean(by_npc[k])):
        print(f"  {npc:<14}{describe(by_npc[npc], args.ceiling)}")
    print()

    print("⚠ 读法：")
    print("  - **中位数**比均值可靠 —— 均值会被少数超长回复拉高。")
    print(f"  - 「超 {args.ceiling} 字」比例高 ⇒ **约束写得进 prompt、但模型不照做**，")
    print("    那么该动的是**输出侧**（后处理截断 / 重试），而不是继续加措辞。")
    print("  - 「超 80 字」比例如果仍非零，说明**偶尔会完全无视上限**，值得单看那几条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
