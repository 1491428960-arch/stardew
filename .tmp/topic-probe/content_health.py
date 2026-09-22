# -*- coding: utf-8 -*-
"""内容体检：回答用户的四个问题。

用户的原始表述（2026-09-23 早上）：
  「其实罗不罗嗦不是核心问题，我主要是在乎和原文角色说话方式接不接近，
    以及话题够不够丰富，聊天的变化够不够，让玩家能够长久的聊」
  追加澄清：「长久聊不是指的一轮对话一直聊，指的是每次聊天都有不一样的新东西，
    有足够的新惊喜驱动玩家来开始新话题」

四个维度：
  ① 还原度  —— AI 回复 vs Sophia 520 条原文的「说话指纹」
  ② 话题丰富 —— facet 生活面覆盖 + 话题种类数
  ③ 跨轮变化 —— 相似度 / 重复短语
  ④ 新鲜度  —— 切成"会话"后，第几次会话开始重复（＝能撑玩家来几次）

数据源：
  - 语料库   artifacts/corpus/20260923-extra-dialogue/vanilla-sve-rasmodia-dialogue-corpus.json
             → records[].resolvedText（解析后的中文原文）
  - 生成结果 .tmp/topic-probe/<batch>/summary.json
             → entry == 'app._build_context' 才是游戏端
"""
import json
import re
import statistics as st
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "artifacts/corpus/20260923-extra-dialogue/vanilla-sve-rasmodia-dialogue-corpus.json"
BATCHES = ROOT / ".tmp/topic-probe"

# ---------------------------------------------------------------- 原文指纹

# Sophia 的语言特征（从 520 条原文里可观察到的类别）
FINGERPRINT = {
    "结巴/重复字": r"(.)、\1",              # 「等、等一下」「那、那我们」
    "省略号": r"…",
    "嗯": r"嗯",
    "语气词_呀": r"呀",
    "语气词_哦": r"哦",
    "语气词_嘿": r"嘿",
    "语气词_哇": r"哇",
    "逗号": r"，",
    "感叹号": r"！",
    "问号": r"？",
    "紧张_害怕类": r"紧张|害怕|怕|不好意思|抱歉|对不起",
    "犹豫类": r"也许|大概|可能|应该|有点|好像",
    "葡萄/酿酒": r"葡萄|酒|酿|桶|瓶",
    "小镇/镇": r"镇",
}


def load_sophia_texts():
    d = json.loads(CORPUS.read_text(encoding="utf-8"))
    out = []
    for r in d["records"]:
        if str(r.get("npcId", "")).lower() != "sophia":
            continue
        t = (r.get("resolvedText") or "").strip()
        if not t or t.startswith("{{i18n:"):
            continue
        out.append(t)
    return out


def load_batches():
    """返回 {label: [batch, ...]}，只收游戏端 48 轮批次。"""
    groups = {}
    for p in sorted(BATCHES.iterdir()):
        sf = p / "summary.json"
        if not p.is_dir() or not sf.exists():
            continue
        try:
            s = json.loads(sf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if s.get("entry") != "app._build_context":
            continue
        if s.get("turns") != 48:
            continue
        label = re.sub(r"-\d{8}-\d{6}-\d+$", "", p.name)
        groups.setdefault(label, []).append(s)
    return groups


# ---------------------------------------------------------------- 工具

def fingerprint(texts):
    """一组文本的指纹：每项 = 每 100 字出现次数 或 条目占比。"""
    joined = "\n".join(texts)
    n = len(joined) or 1
    out = {}
    for name, pat in FINGERPRINT.items():
        cnt = len(re.findall(pat, joined))
        out[name] = cnt / n * 100          # 每 100 字
    return out


def sentences(text):
    return [x.strip() for x in re.split(r"[。！？…\n]+", text) if x.strip()]


def ngrams(text, n=4):
    t = re.sub(r"[\s，。！？…、—～~\"'「」『』（）()【】\[\]]", "", text)
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------- ① 还原度

def report_fidelity(sophia, replies):
    print("=" * 78)
    print("① 还原度：AI 回复 vs Sophia 520 条原文的说话指纹")
    print("=" * 78)
    fa = fingerprint(sophia)
    fb = fingerprint(replies)
    print(f"  {'特征':<14}{'原文':>9}{'AI 回复':>10}{'倍数':>9}   判断")
    print("  " + "-" * 66)
    for k in FINGERPRINT:
        a, b = fa[k], fb[k]
        ratio = (b / a) if a else float("inf")
        if a == 0 and b == 0:
            mark = "两边都没有"
        elif a == 0:
            mark = "❗原文没有、AI 却有"
        elif ratio > 2:
            mark = "❌ AI 明显更多"
        elif ratio > 1.3:
            mark = "⚠️ AI 偏多"
        elif ratio < 0.5:
            mark = "❌ AI 明显更少"
        elif ratio < 0.77:
            mark = "⚠️ AI 偏少"
        else:
            mark = "✅ 接近"
        r = f"{ratio:.2f}×" if a else "—"
        print(f"  {k:<14}{a:>9.2f}{b:>10.2f}{r:>9}   {mark}")
    print()
    print("  （单位：每 100 字出现次数）")


# ---------------------------------------------------------------- ② 话题

FACETS = {
    "农活": r"种|收|播|藤|庄稼|作物|浇水|锄|地|农场",
    "酿酒": r"酒|酿|桶|瓶|发酵|葡萄|果|甜|味道|尝|喝",
    "手工": r"布|缝|线|料子|手工|针|织|颜色",
    "镇务": r"镇|广场|市长|店|铺|皮埃尔|莫里斯|集市|码头",
    "人物": r"玛妮|罗宾|克林特|哈丽特|安迪|维克|奥利维亚|克莱尔|艾米丽|阿比盖尔|塞巴斯蒂安|莉亚|潘妮|山姆|谢恩|艾略特|哈维|马鲁|德米|卡罗琳|乔迪|肯特|文森特|贾斯|莱纳斯|威利|冈瑟|法师|矮人|科罗布斯",
    "回忆过去": r"以前|那年|当时|小时候|搬来|记得|曾经|旧|过去|那时候",
    "情绪": r"开心|难过|害怕|紧张|害羞|担心|高兴|失望|委屈|孤单|温暖|喜欢|爱",
    "天气季节": r"天气|下雨|雪|晴|风|冷|热|春|夏|秋|冬|季节",
    "身体劳作": r"累|歇|睡|醒|腰|手|脚|病|药|医生|哈丽特",
}


def report_topics(all_replies):
    print()
    print("=" * 78)
    print("② 话题丰富度")
    print("=" * 78)
    # 每轮标签
    hit_rounds = Counter()
    hit_total = Counter()
    n = len(all_replies)
    for r in all_replies:
        seen = set()
        for name, pat in FACETS.items():
            c = len(re.findall(pat, r))
            if c:
                hit_total[name] += c
                seen.add(name)
        for name in seen:
            hit_rounds[name] += 1
    print(f"  共 {n} 轮。生活面覆盖：")
    print(f"  {'生活面':<12}{'出现轮数':>9}{'占比':>8}{'提及次数':>9}   条形")
    print("  " + "-" * 62)
    for name in FACETS:
        c = hit_rounds[name]
        pct = c / n * 100 if n else 0
        bar = "█" * int(pct / 3)
        print(f"  {name:<12}{c:>9}{pct:>7.1f}%{hit_total[name]:>9}   {bar}")
    used = sum(1 for k in FACETS if hit_rounds[k])
    print()
    print(f"  ⇒ 用到的生活面：{used} / {len(FACETS)}")
    # 每轮平均覆盖几个面
    per = []
    for r in all_replies:
        per.append(sum(1 for pat in FACETS.values() if re.search(pat, r)))
    print(f"  ⇒ 每轮平均覆盖 {st.mean(per):.2f} 个生活面（中位 {st.median(per):.0f}）")


# ---------------------------------------------------------------- ③ 变化

def report_variation(label, batches):
    print()
    print("=" * 78)
    print(f"③ 跨轮变化（{label}，{len(batches)} 批 × 48 轮）")
    print("=" * 78)
    adj, allpairs, dupng = [], [], []
    for s in batches:
        reps = [x["reply"] for x in s["rows"] if x.get("reply")]
        gs = [ngrams(r) for r in reps]
        adj += [jaccard(gs[i], gs[i + 1]) for i in range(len(gs) - 1)]
        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                allpairs.append(jaccard(gs[i], gs[j]))
        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                if gs[i] and gs[j]:
                    dupng.append(len(gs[i] & gs[j]) / max(len(gs[i]), 1))
    def q(a, p):
        a = sorted(a)
        return a[min(len(a) - 1, int(len(a) * p))]
    print(f"  相邻两轮 4-gram Jaccard：中位 {st.median(adj):.3f}　均值 {st.mean(adj):.3f}　p90 {q(adj,.9):.3f}　最大 {max(adj):.3f}")
    print(f"  任意两轮 4-gram Jaccard：中位 {st.median(allpairs):.3f}　均值 {st.mean(allpairs):.3f}　p90 {q(allpairs,.9):.3f}　最大 {max(allpairs):.3f}")
    hi = sum(1 for x in allpairs if x > 0.30) / len(allpairs) * 100
    print(f"  ⇒ 相似度 > 0.30 的轮次对占比：{hi:.2f}%（{'偏高' if hi > 1 else '低'}）")
    # 高频重复短语
    allg = Counter()
    for s in batches:
        for x in s["rows"]:
            if x.get("reply"):
                t = re.sub(r"[\s，。！？…、—～~\"'「」（）()]", "", x["reply"])
                for i in range(len(t) - 5):
                    allg[t[i:i + 6]] += 1
    print(f"  ⇒ 出现最多的 6 字片段：")
    for g, c in allg.most_common(12):
        print(f"       {g}  ×{c}")


# ---------------------------------------------------------------- ④ 新鲜度

def report_freshness(label, batches, session=8):
    """把 48 轮切成若干「会话」，看第几次会话开始和之前重复。"""
    print()
    print("=" * 78)
    print(f"④ 新鲜度：把 48 轮切成 {48//session} 段「会话」，看新东西什么时候用完")
    print("=" * 78)
    curve = []
    for s in batches:
        reps = [x["reply"] for x in s["rows"] if x.get("reply")]
        nsec = len(reps) // session
        gs = [ngrams(r) for r in reps]
        seen = set()
        for k in range(nsec):
            seg = gs[k * session:(k + 1) * session]
            # 本段里，与之前所有段的最大相似度
            if seen:
                mx = [jaccard(g, seen) for g in seg]
            else:
                mx = [0.0] * len(seg)
            curve.append((k + 1, st.mean(mx), max(mx)))
            for g in seg:
                seen |= g
    # 汇总
    bysec = {}
    for k, m, x in curve:
        bysec.setdefault(k, []).append((m, x))
    print(f"  {'第几次会话':<12}{'与前文平均相似度':>18}{'最大相似度':>14}   判断")
    print("  " + "-" * 62)
    for k in sorted(bysec):
        ms = [a for a, _ in bysec[k]]
        xs = [b for _, b in bysec[k]]
        m, x = st.median(ms), max(xs)
        judge = "🌱 全新" if m < 0.10 else ("🌿 还算新" if m < 0.20 else ("⚠️ 开始重复" if m < 0.35 else "❌ 明显重复"))
        print(f"  第 {k} 次{'':<7}{m:>18.3f}{x:>14.3f}   {judge}")
    print()
    print("  ⇒ 解读：这张表就是「玩家第几次来找她，会觉得没新东西了」。")


def report_arcs(label, batches):
    """桥段（故事单元）重复 —— Jaccard 看不见的那一层。"""
    print()
    print("=" * 78)
    print(f"⑤ 桥段重复：哪些「故事」被反复讲（{label}，{len(batches)} 批 × 48 轮）")
    print("=" * 78)
    # 故事单元：手工枚举她反复讲的那几件事的特征词
    ARCS = {
        "刚搬来住的旧房子（漏风/堵缝）": r"旧房|漏风|窗框|窗户关不严|搬来那阵|刚搬来|缝堵|旧屋子",
        "酒窖那批新酿（澄清/装瓶）": r"新酿|那批酒|澄清|装瓶|发酵|开桶|酒窖里|蓝月亮",
        "桦树糖浆爆米花": r"爆米花|桦树糖浆|糖浆",
        "送酒路过广场看吵架": r"广场|吵起|争吵|为了一筐|摊位|围了一圈",
        "葡萄园/老藤": r"葡萄|老藤|藤|园子|摘|压榨|果子",
        "手工房/布料": r"布料|手工房|缝|线轴|料子|衬边",
    }
    total = sum(len([x for x in s["rows"] if x.get("reply")]) for s in batches)
    print(f"  {'桥段':<32}{'出现轮数':>9}{'占全部轮次':>12}   判断")
    print("  " + "-" * 66)
    rows = []
    for name, pat in ARCS.items():
        c = sum(len(re.findall(pat, x["reply"])) > 0
                for s in batches for x in s["rows"] if x.get("reply"))
        rows.append((name, c, c / total * 100 if total else 0))
    for name, c, pct in sorted(rows, key=lambda r: -r[1]):
        judge = "❌ 反复讲" if pct > 25 else ("⚠️ 偏多" if pct > 12 else "✅ 适量")
        print(f"  {name:<32}{c:>9}{pct:>11.1f}%   {judge}")
    # 每轮命中几个桥段
    per = [sum(1 for pat in ARCS.values() if re.search(pat, x["reply"]))
           for s in batches for x in s["rows"] if x.get("reply")]
    print()
    print(f"  ⇒ 每轮平均命中 {st.mean(per):.2f} 个已知桥段（中位 {st.median(per):.0f}）")
    print(f"  ⇒ 完全没命中任何已知桥段的轮次：{sum(1 for x in per if x == 0)} / {len(per)}"
          f"（{sum(1 for x in per if x == 0)/len(per)*100:.1f}%）")


def main():
    sophia = load_sophia_texts()
    groups = load_batches()
    print(f"★ 原文：Sophia 中文台词 {len(sophia)} 条")
    print(f"★ 生成：游戏端 48 轮批次 {sum(len(v) for v in groups.values())} 批，覆盖 {len(groups)} 种配置")
    print()

    baseline = groups.get("chat-base") or groups.get("gamereal") or []
    if not baseline:
        print("✗ 找不到基线批次"); return
    base_label = "chat-base" if "chat-base" in groups else "gamereal"
    reps48 = [x["reply"] for s in baseline for x in s["rows"] if x.get("reply")]

    report_fidelity(sophia, reps48)
    report_topics(reps48)
    report_variation(base_label, baseline)
    report_freshness(base_label, baseline)
    report_arcs(base_label, baseline)


if __name__ == "__main__":
    main()
