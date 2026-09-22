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


def _bigrams(text: str) -> set[str]:
    """只留汉字再取二元组 —— 标点和语气词不该拉高相似度。"""

    clean = "".join(ch for ch in text if "\u4e00" <= ch <= "\u9fff")
    return {clean[i:i + 2] for i in range(len(clean) - 1)}


def topic_repetition(replies: list[str]) -> dict[str, float]:
    """轮间话题重复度。

    2026-09-23 02:3x 加：温度实验里发现**语气指标完全捕捉不到"她连着六轮说瓶塞松了"**，
    而这恰恰是低温最致命的退化。指标只量"怎么说话"，量不到"说的是不是同一件事"，
    所以补这一组 —— 它当场把 0.3 / 0.7 / default 分得干干净净
    （≥0.30 的轮对：12 / 7 / 0）。
    """

    if len(replies) < 2:
        return {"平均相似": 0.0, "最高相似": 0.0, "重复轮对": 0}
    grams = [_bigrams(reply) for reply in replies]
    sims = []
    near = 0
    for i in range(len(grams)):
        for j in range(i + 1, len(grams)):
            union = grams[i] | grams[j]
            score = len(grams[i] & grams[j]) / len(union) if union else 0.0
            sims.append(score)
            if score >= 0.30:
                near += 1
    return {
        "平均相似": sum(sims) / len(sims),
        "最高相似": max(sims),
        "重复轮对": near,
    }


def segment_stability(replies: list[str], size: int) -> dict[str, dict[str, float]]:
    """把一批切成若干段，算每段的指标 —— **段间跨度就是噪声下限**。

    2026-09-23 02:3x 加，起因是一次翻车：§19 用"同一档跑两遍取差"当噪声下限，
    据此得出"削 prompt 让感官/比喻更泛滥"；扩到 48 轮后发现**方向完全翻转** ——
    因为两次跑都在相近时段，那个差只反映短期抖动，**严重低估了真实波动**。

    正确做法是把**同一批**切成段（默认每 16 轮一段），看同档位内部能差多少。
    §21 就是这么翻案的：baseline 的感官描写三段 0.41/0.08/0.89，段内跨度 0.81，
    而当时据以下结论的档间差只有 0.40。
    """

    if size <= 0 or len(replies) < size * 2:
        return {}
    segments = [replies[i:i + size] for i in range(0, len(replies) - size + 1, size)]
    out: dict[str, dict[str, float]] = {}
    for index, segment in enumerate(segments, start=1):
        table = measure(segment)
        table.update({f"__{k}": v for k, v in topic_repetition(segment).items()})
        out[f"第{index}段"] = table
    return out


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
        "--split",
        type=int,
        default=0,
        help="按 N 轮切段并给段内跨度（噪声下限）。§21 的翻案工具，"
             "建议 16；给 0（默认）不输出这一段",
    )
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
        rows.append((who, len(replies), sum(len(r) for r in replies), table,
                     topic_repetition(replies)))
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
    header = f"{'指标':<16}" + "".join(f"{who:>{width}}" for who, *_ in rows)
    print(header)
    # 每轮字数单独列一行：§22 发现它比"平均每句字数"更能解释"啰嗦" ——
    # chat 每轮 50.5 字 / topic 75.8 字（各 48 轮），差 33%，而这个差
    # 在"每句字数"上是看不出来的（那个指标段内跨度比档间差还大）。
    print(f"{'规模':<16}" + "".join(
        f"{f'{turns} 轮 / {chars} 字':>{width}}" for _, turns, chars, *_ in rows))
    print(f"{'每轮字数':<16}" + "".join(
        f"{chars / turns:>{width}.1f}" for _, turns, chars, *_ in rows))
    print("-" * len(header))
    for metric in KEY_METRICS:
        cells = ""
        for *_, table, _repeat in rows:
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
    print("=== 轮间话题重复（指标量不到的那一半）===")
    print("  相邻两轮的汉字二元组 Jaccard；≥0.30 记为一对「在说同一件事」")
    print()
    print(f"{'':<16}" + "".join(f"{who:>{width}}" for who, *_ in rows))
    for key in ("平均相似", "最高相似", "重复轮对"):
        cells = "".join(f"{f'{repeat[key]:.3f}' if key != '重复轮对' else f'{int(repeat[key])} 组':>{width}}"
                        for *_, repeat in rows)
        print(f"{key:<16}{cells}")

    # 段内跨度：把每批切成段，看同一档位内部能差多少。这是噪声下限，
    # 档间差异不超过它就不该写成结论（§21 的翻案就是这么来的）。
    if args.split:
        print()
        print(f"=== 段内跨度（每 {args.split} 轮一段）—— 这才是噪声下限 ===")
        print("  §21 的教训：「跑两遍取差」只反映短期抖动；段间跨度还包含批次内漂移。")
        print()
        for who, path in items:
            replies = replies_of(path)
            segments = segment_stability(replies, args.split)
            if not segments:
                print(f"  {who}：轮数不足 {args.split * 2}，跳过")
                continue
            print(f"  {who}（{len(replies)} 轮，{len(segments)} 段）")
            for metric in KEY_METRICS:
                vals = [table.get(metric) for table in segments.values()]
                if any(v is None for v in vals):
                    continue
                spread = max(vals) - min(vals)
                shown = "".join(f"{v:>8.2f}" for v in vals)
                print(f"    {metric:<14}{shown}   段内跨度 {spread:>6.2f}")
            sims = [table.get("__最高相似") for table in segments.values()]
            if all(v is not None for v in sims):
                print(f"    {'最高相似':<14}" + "".join(f"{v:>8.3f}" for v in sims)
                      + f"   段内跨度 {max(sims) - min(sims):>6.3f}")
            print()

    print()
    print("判读方式（§18 的口径）：")
    print("  · 某指标**只有一个人**明显偏离、别人接近原话 ⇒ 这是他独有的，改他的卡能修；")
    print("  · 某指标**所有人**都朝同一方向偏 ⇒ 这是公共层（prompt / 模型），改单个角色无效。")
    print()
    print("⚠️ 语气指标量的是「怎么说话」，量不到「说的是不是同一件事」。")
    print("   §20/§21 的教训：温度 0.3 让她连着六轮说「瓶塞又松了」——")
    print("   那一项在语气指标上完全看不出来，只有读原文或看上面这组才暴露。")
    print()
    print("⚠️ 单批数字不要直接当结论。档间差异必须先跨过噪声下限：")
    print("   跑两遍取差只反映短期抖动（§19 因此写错过两条，§21 扩到 48 轮后方向翻转）；")
    print("   更可靠的是把同一批切成段看段内跨度 —— 用 --split 16 输出。")


if __name__ == "__main__":
    main()
