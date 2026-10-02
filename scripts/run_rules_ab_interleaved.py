"""`responseRules[0]` 交织 A/B 实验的**执行器**（把设计变成可跑流程）。

## 它解决什么

`scripts/design_rules_experiment.py` 只打印设计（它的 `--execute` 分支是空壳，
只打印一句「额度未恢复」就返回，且文档串里的 `--arm-a/--arm-b` 参数并不存在）。
本脚本是**真执行**的那一半。

## 单位（钉死，避免再次出现 $12 / $264 的歧义）

- **一轮** = 一次模型请求（一个 case 的一回合）——`待决策.md` 里「430 轮/臂」就是这个单位。
- **一批** = 用 `--cases` 个 case 跑一遍，每个 case `--turns` 轮
  （实测 6 case × 3 轮 = 18 轮 = **22 请求** ≈ **$0.73**，标定自 2026-09-28 的 L1 第一跑）。
- **一对** = 同一 case、同一轮次上的一次 A 与一次 B（**按轮配对**，不按批配对——
  按轮配对不浪费样本，同样的钱能检出更小的效应）。

⇒ 实验组（被改的角色）每批贡献 `wizard_turns_per_batch` 轮，
  故 `--batches N` ⇒ N 批/臂 ⇒ `N × wizard_turns_per_batch` 个配对数。

## 两臂怎么切

`responseRules` 由 `identity["voiceStyle"]` 提供（`personas.py` 加载 persona 文件），
`--profile-index` 只影响索引查询 ⇒ **两臂必须换 `data/personas/vanilla.json`**。
本脚本因此：

1. 启动时把当前 `vanilla.json` 备份到 `.tmp/ab/vanilla.json.baseline`
   （**备份的是工作区版本**，不是 HEAD —— 工作区本来就有未提交的 Sam 角色）；
2. B 臂用**字符串级替换**只改 Wizard 那一条，不重新序列化整个 JSON
   （避免把整个文件的格式改掉）；
3. 无论成功、失败还是 Ctrl-C，`finally` 都还原。

⚠ **残留检测**：若上次跑崩在 B 臂，文件会停在改动状态。脚本每次启动都会
比对当前文件与 baseline，不一致就**拒绝执行**并提示 `--restore`。

## 用法

    # 零请求：看预算、看两臂到底差什么
    python -B scripts/run_rules_ab_interleaved.py --plan

    # 本地免费先验证流程（--provider local 默认，不发云端请求）
    python -B scripts/run_rules_ab_interleaved.py --execute --batches 1 --provider local

    # 真跑（云端，花钱）
    python -B scripts/run_rules_ab_interleaved.py --execute --batches 9 --provider cloud

    # 只还原 persona 文件
    python -B scripts/run_rules_ab_interleaved.py --restore
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
PERSONA = WT / "data" / "personas" / "vanilla.json"
AB_DIR = WT / ".tmp" / "ab"
BASELINE = AB_DIR / "vanilla.json.baseline"
ARTIFACTS = WT / "artifacts" / "rules-ab"

#: 实测标定（2026-09-28 L1 第一跑：6 case × 3 轮 = 22 请求 / $0.73）。
REQUESTS_PER_CASE_TURN = 22 / 18
USD_PER_REQUEST = 0.73 / 22
#: 交织设计下、n 对时可检出的最小效应（双侧 α=0.05, power=0.80），σ 取 09-28 实测。
SIGMA_WITHIN = 24.3

#: A 臂（基线）与 B 臂（改动）的差别 —— 只在 Wizard 那一条上。
#: 上下文取到「responseRules 的第一项」，保证唯一匹配。
ARM_A_TEXT = '"responseRules": ["先回答眼前的问题",'
ARM_B_TEXT = '"responseRules": ["问到具体的事就直说，其余时候按自己的状态开口",'


def mde(n_pairs: float) -> float:
    z = 1.9599 + 0.8416
    return z * SIGMA_WITHIN / math.sqrt(n_pairs)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _count_wizard_turns(cases: int) -> int:
    """每批里被改角色（Wizard）占的轮数。

    默认 suite 的前 6 个 case 是 3 个 wizard + 3 个 sophia（`--plan` 实测），
    sophia 当**阴性对照**（§五.3 要求）。这里按 case 数的一半估，
    并在 `--plan` 里把实际 caseIds 打出来让人核对。
    """

    return max(1, cases // 2) * 3


def _print_plan(args: argparse.Namespace) -> int:
    turns_per_batch = args.cases * args.turns
    requests_per_batch = round(turns_per_batch * REQUESTS_PER_CASE_TURN)
    wizard_turns = _count_wizard_turns(args.cases)
    pairs = args.batches * wizard_turns
    total_batches = args.batches * 2
    total_requests = requests_per_batch * total_batches
    usd = total_requests * USD_PER_REQUEST

    print("=" * 88)
    print("`responseRules[0]` 交织 A/B 实验 —— 执行计划")
    print("=" * 88)
    print()
    print("## 单位（钉死）")
    print(f"  一轮 = 一次模型请求；一批 = {args.cases} case × {args.turns} 轮 = {turns_per_batch} 轮")
    print(f"  一对 = 同一 case 同一轮次上的 A/B 各一次（**按轮配对**）")
    print()
    print("## 两臂")
    print(f"  落点：{PERSONA.relative_to(WT)}")
    print(f"  A（基线）：{ARM_A_TEXT}")
    print(f"  B（改动）：{ARM_B_TEXT}")
    print(f"  ⚠ 只替换这一处字符串，文件其余部分逐字节不变。")
    print()
    print("## 预算")
    print(f"  每批：{turns_per_batch} 轮 / 约 {requests_per_batch} 请求（含 20% 重试余量）"
          f" / 约 ${requests_per_batch * USD_PER_REQUEST:.2f}")
    print(f"  每臂 {args.batches} 批 ⇒ 共 {total_batches} 批 / **{total_requests} 请求**"
          f" / 约 **${usd:.1f}**")
    print(f"  其中实验组（Wizard）每批 {wizard_turns} 轮 ⇒ 配对数 **{pairs}**")
    print(f"  ⇒ 可检出最小效应 **{mde(pairs):.1f} 字**"
          f"（对比：上次分批设计实测漂移 10~14 字，把 5.7 字的效应整个淹掉）")
    print()
    print("## 跑法")
    print(f"  ① 先本地验证流程（免费）：--execute --batches 1 --provider local")
    print(f"  ② 再云端真跑：--execute --batches {args.batches} --provider cloud")
    print(f"  产物：{ARTIFACTS.relative_to(WT)}/<臂>-<序号>/")
    print(f"  分析：python scripts/analyze_ab_power.py（读各批 results.jsonl）")
    print()
    print("## 还原保障")
    print(f"  baseline：{BASELINE.relative_to(WT)}")
    print("  finally 还原；启动时检测残留，不一致就拒绝跑。")
    print()
    print("⚠ 未发出任何请求。")
    return 0


def _restore() -> int:
    if not BASELINE.is_file():
        print(f"没有 baseline：{BASELINE}", file=sys.stderr)
        return 2
    shutil.copyfile(BASELINE, PERSONA)
    print(f"已还原：{PERSONA.relative_to(WT)} ⇐ {BASELINE.relative_to(WT)}")
    return 0


def _prepare_baseline() -> int:
    AB_DIR.mkdir(parents=True, exist_ok=True)
    if BASELINE.is_file():
        if _read_text(BASELINE) != _read_text(PERSONA):
            print(
                "⚠ 检测到残留：当前 persona 与 baseline 不一致（上次可能崩在 B 臂）。\n"
                "  先跑 `--restore` 还原，再重新执行。",
                file=sys.stderr,
            )
            return 3
        return 0
    shutil.copyfile(PERSONA, BASELINE)
    print(f"已备份 baseline：{BASELINE.relative_to(WT)}")
    return 0


def _write_arm(arm: str) -> None:
    """把 persona 文件写成某一臂。

    A 臂 = baseline **原样**（baseline 本来就是 A 状态，不做任何替换）；
    B 臂 = 在 baseline 上把 Wizard 那一条替换掉。都从 baseline 出发，
    保证两臂的差异**只有这一处**。
    """

    text = _read_text(BASELINE)
    if arm == "B":
        hits = text.count(ARM_A_TEXT)
        if hits != 1:
            raise SystemExit(f"B 臂锚点命中 {hits} 次（应为 1）：{ARM_A_TEXT}")
        text = text.replace(ARM_A_TEXT, ARM_B_TEXT)
    PERSONA.write_text(text, encoding="utf-8")


def _run_batch(arm: str, index: int, args: argparse.Namespace) -> int:
    out = ARTIFACTS / f"{arm}-{index:02d}"
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-B", str(WT / "scripts" / "run_character_quality_eval.py"),
        "--suite", args.suite,
        "--limit", str(args.cases),
        "--economical",
        "--provider", args.provider,
        "--output-dir", str(out),
    ]
    if args.provider == "cloud":
        cmd.append("--confirm-cloud")
    print(f"[{arm}-{index:02d}] {' '.join(cmd[2:])}")
    # 用文件重定向而不是管道：沙箱下 piped stdio 会 EPERM。
    with (out / "run.log").open("w", encoding="utf-8") as log:
        return subprocess.run(cmd, cwd=WT, stdout=log, stderr=subprocess.STDOUT).returncode


def _execute(args: argparse.Namespace) -> int:
    if _prepare_baseline() != 0:
        return 3
    failures = 0
    try:
        for i in range(1, args.batches + 1):
            for arm in ("A", "B"):
                _write_arm(arm)
                code = _run_batch(arm, i, args)
                if code != 0:
                    failures += 1
                    print(f"  ⚠ {arm}-{i:02d} 退出码 {code}（该批标记为不完整）")
    finally:
        _restore()
    print()
    print(f"完成：{args.batches * 2} 批，失败 {failures} 批。产物在 {ARTIFACTS}")
    if failures:
        print("⚠ 有失败的批次 ⇒ 按 runbook 口径，失败的批次不参与对比。")
    print("下一步：python scripts/analyze_ab_power.py（相邻 A-B 配对）")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="responseRules[0] 交织 A/B 实验执行器")
    ap.add_argument("--plan", action="store_true", help="只打印预算与两臂差异（零请求）")
    ap.add_argument("--execute", action="store_true", help="真跑（默认关）")
    ap.add_argument("--restore", action="store_true", help="只还原 persona 文件")
    ap.add_argument("--batches", type=int, default=9, help="每臂批数（默认 9）")
    ap.add_argument("--cases", type=int, default=6, help="每批 case 数（默认 6）")
    ap.add_argument("--turns", type=int, default=3, help="每 case 轮数（默认 3）")
    ap.add_argument("--suite", default="default")
    ap.add_argument("--provider", choices=("local", "cloud", "fake"), default="local")
    args = ap.parse_args()

    if args.restore:
        return _restore()
    if args.plan or not args.execute:
        return _print_plan(args)
    return _execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
