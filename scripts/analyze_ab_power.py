"""为 10-01 之后的云端 A/B 定样本量 —— 用**实测方差**算最小可检测效应（MDE）。

**为什么需要它**：2026-09-28 的 `responseRules[0]` 单变量 A/B 是**负结果** ——
未改角色的对照组波动比处理组还大，观察到的差异无法与噪音区分。
重跑一次如果还是同样的样本量，**依然测不出来**。
所以先回答：「要多少轮，才测得出我关心的那个差异？」

**方法**：双样本均值比较，α = 0.05（双侧）、power = 0.80。

    MDE(n) = (z_{1-α/2} + z_{power}) × σ × √(2/n)
           = (1.9599 + 0.8416) × σ × √(2/n)

σ 取自**实测**：把既有 artifact 里每一轮的回复字数汇到一起算合并标准差。
⚠ 这个 σ 含**两种**波动：① 轮与轮之间的真实差异 ② 跑与跑之间的漂移。
后者是 2026-09-28 那个负结果的直接原因，所以这里**刻意不拆开** ——
用它算出来的 MDE 是**乐观下界**，真实所需样本量只会更大。

零请求、只读。用法：

    python scripts/analyze_ab_power.py
    python scripts/analyze_ab_power.py --metric scrubbed
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
ART = WT / "artifacts" / "character-quality-eval"

Z_ALPHA = 1.9599  # 双侧 α = 0.05
Z_POWER = 0.8416  # power = 0.80


def turn_lengths(path: Path, metric: str) -> list[tuple[str, int]]:
    """返回 [(caseId, 该轮字数), ...]。"""
    out: list[tuple[str, int]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError:
            continue
        case_id = str(case.get("caseId") or "?")
        for turn in case.get("turns") or []:
            if not isinstance(turn, dict):
                continue
            raw = turn.get(metric)
            if isinstance(raw, str) and raw:
                out.append((case_id, len(raw)))
    return out


def stdev(values: list[int]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def mde(sigma: float, n_per_arm: int) -> float:
    """双样本、每臂 n 轮时的最小可检测差异（字）。"""
    return (Z_ALPHA + Z_POWER) * sigma * math.sqrt(2.0 / n_per_arm)


def main() -> int:
    metric = "reply"
    if "--metric" in sys.argv:
        idx = sys.argv.index("--metric")
        if idx + 1 < len(sys.argv):
            metric = sys.argv[idx + 1]

    #: ⚠ σ 有两种来源，**必须分开报**：
    #: - **跨版本**（全部 artifact）：含「prompt 改版造成的均值漂移」⇒ σ 大 ⇒ MDE 虚高；
    #:   但它反映的是**长期真实噪音**，判断「这次改动会不会被版本漂移淹没」要看它。
    #: - **同版本**（`--recent N`，默认 5）：只看最近 N 个跑 ⇒ σ 小 ⇒ MDE 贴近
    #:   同版本 A/B 的真实能力，是**当期实验**该用的数。
    recent = 5
    if "--recent" in sys.argv:
        idx = sys.argv.index("--recent")
        if idx + 1 < len(sys.argv):
            try:
                recent = max(1, int(sys.argv[idx + 1]))
            except ValueError:
                pass

    # ⚠ **必须按 mtime 排序，不能按目录名**：artifact 命名不统一 ——
    # 有的是 `20260928-063359`（日期在前），有的是
    # `topic-start-adaptive-natural-probe-20260915-093355`（主题在前）。
    # 按名字排序会把 09-15 的跑排到 09-28 后面 ⇒ 取「最近 N 个」会取错，
    # 实测因此把 σ 和 MDE 全套算成了另一批数据。
    runs = (
        sorted((p for p in ART.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
        if ART.exists()
        else []
    )
    runs = runs[-recent:]
    print("=" * 78)
    print(f"只看最近 {recent} 个 artifact 的每轮字数分布（字段 `{metric}`）")
    print("=" * 78)

    pooled: list[int] = []
    used: list[str] = []
    for run in runs:
        jl = run / "results.jsonl"
        if not jl.exists():
            continue
        pairs = turn_lengths(jl, metric)
        if not pairs:
            continue
        vals = [v for _, v in pairs]
        pooled.extend(vals)
        used.append(run.name)
        print(
            f"  {run.name:<46} n={len(vals):>3}  "
            f"mean={sum(vals)/len(vals):>6.1f}  sd={stdev(vals):>5.1f}  "
            f"min={min(vals):>3}  max={max(vals):>3}"
        )

    if not used:
        print("  （没有可用的 artifact）")
        return 0

    sigma = stdev(pooled)
    mean = sum(pooled) / len(pooled)
    print()
    print(f"合并：{len(used)} 个 artifact、{len(pooled)} 轮")
    print(f"  总体均值 {mean:.1f} 字，合并标准差 σ = {sigma:.1f} 字")
    print()

    print("=" * 78)
    print("要测出一个「平均字数差异」，每臂需要多少轮？")
    print("（α=0.05 双侧，power=0.80。⚠ 这是**乐观下界** —— σ 里含跑与跑之间的漂移）")
    print("=" * 78)
    print(f"  {'每臂轮数':>8} | {'可检测差异(MDE)':>16} | {'相当于均值的':>12}")
    print("  " + "-" * 46)
    for n in (12, 36, 72, 144, 288, 576):
        d = mde(sigma, n)
        print(f"  {n:>8} | {d:>13.1f} 字 | {d/mean*100:>10.0f}%")

    print()
    print("=" * 78)
    print("反过来：想测出指定大小的差异，需要多少轮？")
    print("=" * 78)
    print(f"  {'目标差异':>10} | {'每臂轮数':>10} | {'约几个 12-case 跑':>18}")
    print("  " + "-" * 50)
    for target in (3, 5, 8, 10, 15, 20):
        n = math.ceil(2 * ((Z_ALPHA + Z_POWER) * sigma / target) ** 2)
        # 一次 12-case 跑、每 case 3 轮 ⇒ 36 轮
        runs_needed = math.ceil(n / 36)
        print(f"  {target:>8} 字 | {n:>10} | {runs_needed:>15} 次")

    print()
    print("⚠ 结论怎么用：")
    print("  1. **先定「值得测的最小差异」**，再看要跑几次 —— 不是先跑再看结果。")
    print("  2. 2026-09-28 那次处理的效应量约 **+5.7 字**（37.2 → 42.9），")
    print("     而**对照组自己动了 −12.9 字** ⇒ 效应远小于噪音 ⇒ 负结果是**必然**，")
    print("     不是「改动没用」，而是**这个样本量根本没能力回答**。")
    print("  3. ⇒ 想验证同类小改动，要么大幅加样本，")
    print("     要么改用**配对设计**（同一 case 跑改前/改后，比同一角色的差值），")
    print("     后者能消掉「角色间差异」这一大块方差。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
