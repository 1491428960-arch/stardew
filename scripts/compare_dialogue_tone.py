#!/usr/bin/env python
"""把多个角色的语气指标并排比出来 —— 报告 §18 那套对照方法的固化版。

## 为什么需要它

报告 §18 的结论是"一半的偏差是 Sophia 独有的，一半是共通的"。要得出那个结论，
必须把**同一套指标**同时算在**多个角色、同参数批次**上。手工做一遍要：
跑批次 → 从目录里认出谁是谁 → 逐个调 `audit_dialogue_tone.py` → 抄数字进表，
中间最容易错的就是"认目录"（§18.6 实际踩到了：我从日志重建样本，因为回复里的换行
被截断，Sophia 少算了一半字数）。

这个脚本把那一步固化：给它若干个 `summary.json`，它自己认角色、自己算指标、自己列表。

## 用法

    # 最省事：自动扫 .tmp/topic-probe/ 下最近的若干批次
    python scripts/compare_dialogue_tone.py

    # 指定批次（可加多个）
    python scripts/compare_dialogue_tone.py --batch Shane=path/to/summary.json \
                                            --batch Alex=path/to/另一份.json

    # 顺便把每个角色的逐轮回复导出，方便人工读
    python scripts/compare_dialogue_tone.py --dump

## 注意

- **只读现有数据，不调 API、不花钱**。跑批次是另一件事（§18.1 里的命令）。
- 指标口径**直接复用** `audit_dialogue_tone.measure`，本脚本不另立一套，
  避免两处口径漂移。
- 某个角色语料里没有就会明确报出来，不会静默给 0。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "bridge" / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

from audit_dialogue_tone import measure  # noqa: E402
from facet_probe_common import corpus  # noqa: E402

PROBE_DIR = ROOT / ".tmp" / "topic-probe"

# §18 用来判定"独有 / 共通"的就是这几项，顺序固定便于逐行比
KEY_METRICS = (
    "平均每句字数",
    "语气词/100字",
    "感官描写/100字",
    "比喻/100字",
    "自我感受/100字",
    "问号/100字",
)


def npc_from_summary(path: Path) -> str:
    """认这批是谁跑的。

    2026-09-23 02:1x：探针原先**不记身份**，跑完对照批次只能靠时间去猜目录，实测踩到了。
    现在探针已补 `npc` / `case` 字段，所以优先读它们；老数据没有就返回空串（跳过并说明）。
    """

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    npc = str(data.get("npc") or "").strip()
    if npc:
        return npc[:1].upper() + npc[1:]
    case = str(data.get("case") or "").strip()
    if case:
        parts = case.split("-")
        if "control" in parts:
            index = parts.index("control")
            if index + 1 < len(parts):
                word = parts[index + 1]
                return word[:1].upper() + word[1:]
    return ""


def replies_of(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [str(row.get("reply") or "") for row in data.get("rows", []) if row.get("reply")]


def originals_of(npc: str) -> list[str]:
    """角色原话基线。语料里没有就抛出来，不静默补 0。"""

    found = [text for who, text in corpus() if who == npc]
    if not found:
        raise SystemExit(f"语料里没有 {npc} 的原话，无法建立基线")
    return found


def discover(limit: int) -> list[tuple[str, Path]]:
    if not PROBE_DIR.exists():
        raise SystemExit(f"没有 {PROBE_DIR}，先跑一次批次")
    files = sorted(
        PROBE_DIR.glob("cloud-rotation-*/summary.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    found: list[tuple[str, Path]] = []
    skipped = 0
    for path in files:
        npc = npc_from_summary(path)
        if not npc:
            skipped += 1
            continue
        if any(name == npc for name, _ in found):
            continue
        found.append((npc, path))
        if len(found) >= limit:
            break
    if skipped:
        print(f"  （跳过 {skipped} 份没有身份字段的老批次 —— 那是补字段之前跑的）")
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", action="append", default=[],
                        help="标签=summary.json，可重复。标签只是显示名（消融对比时写档位名）")
    parser.add_argument("--limit", type=int, default=4, help="自动扫描时取几个角色")
    parser.add_argument("--dump", action="store_true", help="顺带导出逐轮回复")
    parser.add_argument(
        "--baseline-npc",
        default="",
        help="统一用谁的原话当基线。消融对比时标签是档位名（baseline/dedupe…），"
             "查不到语料，必须在这里指明角色",
    )
    args = parser.parse_args()

    if args.batch:
        items = []
        for spec in args.batch:
            if "=" not in spec:
                raise SystemExit(f"--batch 要写成 标签=路径：{spec}")
            who, raw = spec.split("=", 1)
            items.append((who, Path(raw)))
    else:
        items = discover(args.limit)

    if not items:
        raise SystemExit("没找到带身份信息的批次（老数据没有 npc/case 字段）")

    rows = []
    for who, path in items:
        replies = replies_of(path)
        if not replies:
            print(f"  {who}：{path} 里没有回复，跳过")
            continue
        # 标签本身若是语料里存在的角色名，就用它；否则用 --baseline-npc 指定的角色。
        # 这样既支持"多角色对比"，也支持"同角色多档位消融对比"。
        known = {name for name, _ in corpus()}
        npc = who if who in known else args.baseline_npc
        if not npc:
            raise SystemExit(
                f"标签 {who} 不是语料里的角色名，请用 --baseline-npc 指明原话基线"
            )
        table = {"original": measure(originals_of(npc)), "generated": measure(replies)}
        rows.append((who, len(replies), sum(len(r) for r in replies), table))
        if args.dump:
            out = PROBE_DIR / f"compare-{who}.json"
            out.write_text(
                json.dumps({"replies": [{"reply": r} for r in replies]},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  已导出 {out.relative_to(ROOT)}")

    if not rows:
        raise SystemExit("没有任何可用批次")

    print()
    print("=== 各角色的语气指标（她的原话 → 模型生成的她）===")
    print()
    width = 21
    header = f"{'指标':<16}" + "".join(f"{who:>{width}}" for who, _, _, _ in rows)
    print(header)
    print(f"{'':<16}" + "".join(f"{f'{turns} 轮/{chars} 字':>{width}}" for _, turns, chars, _ in rows))
    print("-" * len(header))
    for metric in KEY_METRICS:
        cells = ""
        for _, _, _, table in rows:
            left = table["original"].get(metric)
            right = table["generated"].get(metric)
            if left is None or right is None:
                cells += f"{'—':>{width}}"
                continue
            # 差异方向用箭头直接看：↑ 变多 / ↓ 变少 / · 基本不变
            delta = right - left
            mark = "·" if abs(delta) < max(0.01, abs(left) * 0.05) else ("↑" if delta > 0 else "↓")
            cells += f"{f'{left:.2f} → {right:.2f} {mark}':>{width}}"
        print(f"{metric:<16}{cells}")

    print()
    print("判读方式（§18 的口径）：")
    print("  · 某指标**只有一个人**明显偏离、别人接近原话 ⇒ 这是他独有的，改他的卡能修；")
    print("  · 某指标**所有人**都朝同一方向偏 ⇒ 这是公共层（prompt / 模型），改单个角色无效。")


if __name__ == "__main__":
    main()
