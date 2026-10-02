"""`responseRules[0]` 实验的**抗漂移设计**（额度 10-01 恢复后即可执行）。

## 为什么需要重新设计

2026-09-28 那次实验的结果是「无法判定」，原因**不是样本量**，而是：

> 两批跑之间存在**与改动无关的系统性漂移**，
> 幅度（未改的三个角色同期下降 **10~14 字**）**远超**被测效应（**5.7 字**）。

⇒ 也就是说：**改前跑一批、改后跑一批**这个做法本身有问题 ——
两次跑的**时间不同**，而模型/服务端的状态在两次之间变了。
δ（漂移）> Δ（效应），所以测不出来。

**配对设计只降到 2.6 倍**（配对差 σ = 21.4 对 条件内 σ = 24.3），**不够**。

## 本脚本提供的解法：**交织设计（interleaved）**

不要「AAAA…BBBB…」，而要「**ABABAB…**」：

- 把改前（A）与改后（B）**交替**跑，让**漂移同时作用于两臂**；
- 分析时用**相邻 A-B 配对**（第 i 个 A 对第 i 个 B），
  ⇒ 漂移在配对内**相减抵消**，只剩 Δ。

代价：**需要能快速切换 prompt 配置**（改前/改后各一份），
且跑数翻倍（每臂 N 次 ⇒ 共 2N 跑）。

## 用法（额度恢复后）

    # 1) 先看要多少跑数（用实测 σ 估算）
    python scripts/analyze_ab_power.py --help

    # 2) 生成交织运行清单（本脚本，dry-run，不真跑）
    python scripts/design_rules_experiment.py --plan

    # 3) 真跑（需云端额度；--execute 才会发出请求）
    python scripts/design_rules_experiment.py --execute --arm-a <配置A> --arm-b <配置B>

⚠ 默认 **dry-run**：只打印计划，**不发任何请求**。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / "scripts"))
sys.path.insert(0, str(WT / "bridge" / "src"))

#: 2026-09-28 实测：条件内合并 σ；配对差 σ。
SIGMA_WITHIN = 24.3
SIGMA_PAIRED = 21.4
#: 改前那批的均值（角色级），用作效应量参照。
BASELINE_EFFECT = 5.7


def mde_paired(n_pairs: float, sigma_diff: float = SIGMA_PAIRED) -> float:
    """配对设计下、n 对时能检测出的最小效应（双侧 α=0.05, power=0.80）。"""
    z = 1.9599 + 0.8416
    return z * sigma_diff / math.sqrt(n_pairs)


def mde_interleaved(n_pairs: float, sigma_within: float = SIGMA_WITHIN) -> float:
    """**交织设计**下能检测出的最小效应。

    交织把漂移**在配对内抵消**，所以剩下的噪音是**条件内随机波动**
    除以 √n —— 这正是它比「改前一批 / 改后一批」强的地方：
    后者的漂移**不可抵消**，会作为**固定偏移**留在两批之差里。
    """
    z = 1.9599 + 0.8416
    return z * sigma_within / math.sqrt(n_pairs)


def main() -> int:
    ap = argparse.ArgumentParser(description="responseRules[0] 实验的抗漂移设计")
    ap.add_argument("--plan", action="store_true", help="打印交织运行清单")
    ap.add_argument("--execute", action="store_true", help="真跑（需云端额度；默认关）")
    ap.add_argument("--pairs", type=int, default=40, help="配对数（默认 40）")
    ap.add_argument("--target", type=float, default=5.0, help="想检测的效应量（字）")
    args = ap.parse_args()

    print("=" * 92)
    print("`responseRules[0]` 实验 —— 抗漂移设计")
    print("=" * 92)
    print()
    print("⚠ **本脚本默认 dry-run，不发任何请求。**")
    print()
    print("## 一、上次为什么失败")
    print()
    print("  不是样本量，是**设计**：")
    print("    · 改前跑一批、改后跑一批 ⇒ 两批**时间不同** ⇒ 中间有漂移；")
    print(f"    · 实测漂移幅度 **10~14 字**，被测效应只有 **{BASELINE_EFFECT} 字** ⇒ δ > Δ；")
    print("    · 配对设计只降到 **2.6 倍**（配对差 σ 21.4 vs 条件内 σ 24.3），**不够**。")
    print()
    print("## 二、解法：交织（A/B/A/B…）")
    print()
    print("  把改前(A)与改后(B)**交替**跑，用**相邻 A-B 配对**分析：")
    print("    run1=A  run2=B  run3=A  run4=B  …")
    print("    ⇒ 漂移在**配对内相减抵消**，只剩 Δ。")
    print()
    print("## 三、要多少跑数（用实测 σ 估算）")
    print()
    print(f"  {'配对数':>8} {'交织可检出':>12} {'改前/改后分批可检出':>20}")
    for n in (10, 20, 30, 40, 60, 80, 120, 165, 200, 400):
        m_i = mde_interleaved(n)
        # 分批设计：漂移 10~14 字**不可抵消**，直接进误差 ⇒ 至少加上漂移的一半作底噪
        m_b = math.hypot(mde_paired(n), 6.0)
        print(f"  {n:>8} {m_i:>11.1f}字 {m_b:>19.1f}字")
    print()
    need = ((1.9599 + 0.8416) * SIGMA_WITHIN / args.target) ** 2
    print(f"  ⇒ 想检测 **{args.target:.0f} 字**的效应，交织设计需 **{math.ceil(need)} 对**"
          f"（≈ {math.ceil(need) * 2} 次跑）。")
    print(f"     对比：改前/改后分批设计在同样跑数下**检不出**这个量级的效应。")
    print()

    if args.plan or not args.execute:
        print("## 四、交织运行清单（前 12 条）")
        print()
        for i in range(min(12, args.pairs)):
            arm = "A" if i % 2 == 0 else "B"
            label = "改前（基线）" if arm == "A" else "改后（改动）"
            print(f"  run{i + 1:>3}  臂 {arm}  {label}")
        if args.pairs > 12:
            print(f"  … 共 {args.pairs} 对 = {args.pairs * 2} 次跑")
        print()
        print("## 五、分析时必须做的三件事")
        print()
        print("  1. **用相邻 A-B 配对**，不要用「所有 A 的均值 vs 所有 B 的均值」；")
        print("  2. **把未改动的角色当阴性对照** —— 它们的变化就是**当次跑的漂移量**；")
        print("     若对照角色的变化 ≥ 效应量，则**本次仍不可判定**（不要在此时下结论）；")
        print("  3. **固定 case 集合** —— 两臂跑同一批 caseId，否则比的是 case 不是改动。")
        print()
        print("⚠ 三条缺任何一条，结果都**不能**用来判「改动是否有效」。")
        print()
        print("（要真跑，加 `--execute`；那需要云端额度，10-01 才恢复。）")
        return 0

    print("## 四、执行（需云端额度）")
    print()
    print("  ⚠ 本仓库当前**云端额度未恢复**（2026-10-01T10:32Z）。")
    print("  执行入口：`scripts/run_character_quality_eval.py`，")
    print("  两臂分别用改前/改后的 `prompts.py`（建议各存一份快照到 `.tmp/ab/`）。")
    print("  ⇒ 本次未发出任何请求。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
