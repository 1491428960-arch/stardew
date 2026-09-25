"""Kimi vs DeepSeek：角色风格模仿度对照 —— 2026-09-24。

## 回答的问题

用户问「kimi 和 ds 哪个对角色风格的模仿效果更好」。

## 两组数据的来源与⚠ 不对称

| | Kimi | DeepSeek |
|---|---|---|
| 来源 | 本轮实跑 `.tmp/topic-probe/verbatim-*.json` | `artifacts/character-quality-eval/` 09-11~09-17 历史批次 |
| 路径 | `/api/dialogue/test`（**游戏端**，compactPrompt=true） | 评测路径（naturalMode=true，多 4 张评测卡） |
| 阶段 | **stranger**（hearts=0） | dating / married / friend / acquaintance / close |
| 轮数 | 单角色连续多轮 | 每 case 3 轮 |

**⚠ 两条路径与两个阶段都不同，所以这不是严格 A/B。**
本脚本的产出只能当作「同角色、不同模型」的**倾向性证据**，不是判决。

## 三个指标

1. **原文复述率** —— 8-gram 命中角色原文库的比例（越低越好，说明不是背台词）
2. **风格指纹距离** —— 6 维风格特征与角色原文特征的距离（越低越像）
3. **指纹逐维对照** —— 看差距具体在哪一维

### 风格指纹的 6 个维度

| 维度 | 含义 |
|---|---|
| `len_mean` | 平均句长（CJK 字数）—— 说话的节奏 |
| `ellipsis_rate` | 每 100 字省略号数 —— 犹豫/停顿特征 |
| `filler_rate` | 每 100 字语气词数（嗯呃哦啊唉呀） |
| `question_rate` | 疑问句占比 |
| `excl_rate` | 每 100 字感叹号数 |
| `comma_per_sent` | 平均每句逗号数 —— 长句/短句倾向 |

**距离** = 各维「相对差」的均方根（相对差 = |a-b| / max(|原文|, 一个小常数)），
这样量纲不同的维度可以放在一起。距离 0 = 完全一致。

用法：
    python -B .tmp/topic-probe/style_compare.py
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / ".tmp" / "topic-probe"
ARTIFACTS = ROOT / "artifacts" / "character-quality-eval"
INDEX = ROOT / "data" / "generated" / (
    "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)

DS_BATCHES = [
    "20260915-topic-start-adaptive-vanilla-voice-v2",
    "20260917-topic-start-adaptive-full-promotion-gate-v8",
    "20260914-deepseek-chat-default-full-echo-fix",
    "20260911-181107883-deepseek-chat-default-full",
]

CJK = re.compile(r"[\u4e00-\u9fff]")
FILLERS = "嗯呃哦啊唉呀哎诶嘿哈唔嘛呢吧"
SENT_SPLIT = re.compile(r"[。！？…]+")
ELLIPSIS = re.compile(r"…|\.\.\.")
EXCL = re.compile(r"！")
QUESTION = re.compile(r"[？?]")


def cjk(s: str) -> str:
    return "".join(CJK.findall(s))


def sentences(text: str) -> list[str]:
    return [s for s in SENT_SPLIT.split(text) if cjk(s)]


def fingerprint(texts: list[str]) -> dict[str, float] | None:
    """6 维风格指纹。输入是一组文本（同一角色的多条发言）。"""
    joined = "\n".join(texts)
    body = cjk(joined)
    if not body:
        return None
    sents = [s for t in texts for s in sentences(t)]
    sents_cjk = [cjk(s) for s in sents]
    sents_cjk = [s for s in sents_cjk if s]
    per100 = lambda n: n / len(body) * 100
    return {
        "len_mean": statistics.mean(len(s) for s in sents_cjk) if sents_cjk else 0.0,
        "ellipsis_rate": per100(len(ELLIPSIS.findall(joined))),
        "filler_rate": per100(sum(1 for ch in body if ch in FILLERS)),
        "question_rate": (
            len(QUESTION.findall(joined)) / len(sents) if sents else 0.0
        ),
        "excl_rate": per100(len(EXCL.findall(joined))),
        "comma_per_sent": (
            joined.count("，") / len(sents) if sents else 0.0
        ),
    }


def distance(a: dict[str, float], b: dict[str, float]) -> float:
    """各维相对差的均方根。"""
    total = 0.0
    for k in a:
        base = max(abs(b[k]), 0.5)  # 小常数防止除零放大噪声
        total += ((a[k] - b[k]) / base) ** 2
    return math.sqrt(total / len(a))


def build_gram_set(texts: list[str], n: int = 8) -> set[str]:
    grams: set[str] = set()
    for t in texts:
        s = cjk(t)
        for i in range(len(s) - n + 1):
            grams.add(s[i : i + n])
    return grams


def verbatim_rate(reply: str, grams: set[str], n: int = 8) -> tuple[float, int]:
    s = cjk(reply)
    if len(s) < n:
        return 0.0, 0
    hit = [False] * len(s)
    for i in range(len(s) - n + 1):
        if s[i : i + n] in grams:
            for j in range(i, i + n):
                hit[j] = True
    best = cur = 0
    for h in hit:
        cur = cur + 1 if h else 0
        if cur > best:
            best = cur
    return sum(hit) / len(s) * 100, best


def load_kimi() -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for fname in ("verbatim-all.json", "verbatim-v2.json", "verbatim-multi.json"):
        p = PROBE / fname
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for npc, rows in d["rows"].items():
            for r in rows:
                if r.get("reply"):
                    out[npc].append(r["reply"])
    return out


def load_deepseek() -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for batch in DS_BATCHES:
        p = ARTIFACTS / batch / "results.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            d = json.loads(line)
            npc = d.get("npcId")
            if not npc:
                continue
            for t in d.get("turns", []):
                if t.get("reply"):
                    out[npc].append(t["reply"])
    return out


def main() -> None:
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    by_npc: dict[str, list[str]] = defaultdict(list)
    for s in data["styleSamples"]:
        if s.get("npcId"):
            by_npc[s["npcId"]].append(str(s.get("text") or ""))

    kimi = load_kimi()
    deepseek = load_deepseek()

    print(f"Kimi 角色: {sorted(kimi)}")
    print(f"DeepSeek 角色数: {len(deepseek)}")
    shared = sorted(set(kimi) & set(deepseek))
    print(f"共同角色: {shared}\n")

    rows = []
    for npc in shared:
        src = by_npc.get(npc, [])
        if not src:
            continue
        grams = build_gram_set(src, 8)
        fp_src = fingerprint(src)
        rec = {"npc": npc, "src_fp": fp_src, "n_src": len(src)}
        for label, pool in (("kimi", kimi[npc]), ("ds", deepseek[npc])):
            rates, longs = [], []
            for r in pool:
                rate, longest = verbatim_rate(r, grams, 8)
                rates.append(rate)
                longs.append(longest)
            rec[label] = {
                "n": len(pool),
                "fp": fingerprint(pool),
                "rate_median": statistics.median(rates) if rates else 0.0,
                "rate_mean": statistics.mean(rates) if rates else 0.0,
                "longest_max": max(longs) if longs else 0,
                "len_median": statistics.median(
                    len(cjk(r)) for r in pool
                ) if pool else 0,
            }
        rec["dist_kimi"] = distance(rec["kimi"]["fp"], fp_src)
        rec["dist_ds"] = distance(rec["ds"]["fp"], fp_src)
        rows.append(rec)

    # ── 复述率 ──
    print("═══ 1. 原文复述率（8-gram，越低越好）═══")
    print(f"{'角色':<11}{'原文条':>6}{'Kimi n':>7}{'Kimi 中位':>11}{'DS n':>6}{'DS 中位':>9}{'Kimi max':>10}{'DS max':>8}")
    print("-" * 70)
    for r in sorted(rows, key=lambda x: x["npc"]):
        print(f"{r['npc']:<11}{r['n_src']:>6}{r['kimi']['n']:>7}"
              f"{r['kimi']['rate_median']:>10.2f}%{r['ds']['n']:>6}"
              f"{r['ds']['rate_median']:>8.2f}%{r['kimi']['longest_max']:>10}"
              f"{r['ds']['longest_max']:>8}")

    # ── 风格指纹距离 ──
    print("\n═══ 2. 风格指纹距离（6 维相对差均方根，越低越像原角色）═══")
    print(f"{'角色':<11}{'Kimi 距离':>11}{'DS 距离':>10}{'更接近':>10}")
    print("-" * 44)
    kw = dw = 0
    for r in sorted(rows, key=lambda x: x["npc"]):
        who = "Kimi" if r["dist_kimi"] < r["dist_ds"] else "DeepSeek"
        if r["dist_kimi"] < r["dist_ds"]:
            kw += 1
        else:
            dw += 1
        print(f"{r['npc']:<11}{r['dist_kimi']:>11.3f}{r['dist_ds']:>10.3f}{who:>10}")
    print(f"\n  Kimi 更接近 {kw} 个角色 / DeepSeek 更接近 {dw} 个角色")
    if rows:
        print(f"  平均距离：Kimi {statistics.mean(r['dist_kimi'] for r in rows):.3f}  "
              f"DeepSeek {statistics.mean(r['dist_ds'] for r in rows):.3f}")

    # ── 逐维对照 ──
    print("\n═══ 3. 逐维对照（原文 → Kimi / DeepSeek）═══")
    dims = ["len_mean", "ellipsis_rate", "filler_rate", "question_rate",
            "excl_rate", "comma_per_sent"]
    for r in sorted(rows, key=lambda x: x["npc"]):
        print(f"\n  {r['npc']}（原文 {r['n_src']} 条）")
        print(f"    {'维度':<18}{'原文':>9}{'Kimi':>9}{'DS':>9}   {'谁更近':>7}")
        for d in dims:
            sv, kv, dv = r["src_fp"][d], r["kimi"]["fp"][d], r["ds"]["fp"][d]
            who = "Kimi" if abs(kv - sv) < abs(dv - sv) else "DS"
            print(f"    {d:<18}{sv:>9.3f}{kv:>9.3f}{dv:>9.3f}   {who:>7}")

    # ── 输出 JSON ──
    out = PROBE / "style-compare.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n明细已写入 {out}")


if __name__ == "__main__":
    main()
