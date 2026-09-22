# -*- coding: utf-8 -*-
"""话题池体检：她原文里到底有多少可聊的东西，现在用了多少。

回答用户的「话题够不够丰富」「有没有足够的新惊喜驱动玩家来开新话题」。

做法：
  1. 从 Sophia 520 条中文原文里，抽出她提过的实体 —— 人物 / 地点 / 物品 / 活动 / 情绪。
  2. 从 AI 生成的 144 轮回复里，做同样的抽取。
  3. 对比：原文有、AI 从不提的 = **未使用的素材**（＝现成的新惊喜）。
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "artifacts/corpus/20260923-extra-dialogue/vanilla-sve-rasmodia-dialogue-corpus.json"
BATCHES = ROOT / ".tmp/topic-probe"

# 星露谷人物名（SVE + 原版）—— 用于抽"她认识谁"
NPCS = [
    "阿比盖尔", "艾米丽", "莉亚", "潘妮", "马鲁", "海莉", "莉亚", "卡罗琳", "乔迪", "伊芙琳",
    "玛妮", "罗宾", "克林特", "威利", "皮埃尔", "莫里斯", "冈瑟", "莱纳斯", "矮人", "科罗布斯",
    "谢恩", "山姆", "塞巴斯蒂安", "艾略特", "哈维", "亚历克斯", "德米特里厄斯", "肯特", "文森特",
    "贾斯", "乔治", "艾芙琳", "法师", "桑迪", "雷欧", "潘姆", "玛鲁", "安迪", "维克多",
    "奥利维亚", "克莱尔", "兰斯", "斯嘉丽", "苏珊", "摩根", "哈丽特", "索菲亚", "索菲娅",
    "布莱恩娜", "布洛克", "卡桑德拉", "科迪莉亚", "德雷克", "埃德蒙", "艾敏", "芙蕾雅",
    "盖尔", "格特鲁德", "索耶", "阿莱西亚", "苹果", "艾萨克", "雅各布",
]
# 地点
PLACES = [
    "蓝月亮", "葡萄园", "酒窖", "手工房", "广场", "镇上", "小镇", "农场", "矿洞", "海边",
    "码头", "森林", "山", "酒馆", "商店", "杂货铺", "铁匠铺", "诊所", "图书馆", "博物馆",
    "教堂", "沙滩", "沙漠", "火车站", "集市", "村子", "谷仓", "温室", "洞穴", "温泉",
]
# 物品 / 活动
ITEMS = [
    "葡萄", "酒", "新酿", "桶", "瓶", "杨桃", "精灵石", "爆米花", "桦树糖浆", "布", "线",
    "料子", "花", "苹果", "蓝莓", "南瓜", "甜瓜", "草莓", "奶酪", "面包", "蛋糕", "茶", "咖啡",
    "种子", "锄头", "镰刀", "鱼", "蛋", "牛奶", "蜂蜜", "果酱", "腌菜",
]
# 情绪 / 状态
EMOTIONS = [
    "紧张", "害怕", "害羞", "开心", "难过", "孤单", "担心", "高兴", "失望", "委屈",
    "温暖", "喜欢", "爱", "抱歉", "对不起", "谢谢", "累", "病", "哭", "笑", "梦",
]


def is_placeholder(t):
    return not t or t.strip().startswith("{{i18n:")


def load_sophia():
    d = json.loads(CORPUS.read_text(encoding="utf-8"))
    out = []
    for r in d["records"]:
        if str(r.get("npcId", "")).lower() != "sophia":
            continue
        t = (r.get("resolvedText") or "").strip()
        if is_placeholder(t):
            continue
        out.append(t)
    return out


def load_replies(label):
    out = []
    for p in sorted(BATCHES.glob(label + "-*")):
        sf = p / "summary.json"
        if not sf.exists():
            continue
        s = json.loads(sf.read_text(encoding="utf-8"))
        if s.get("entry") != "app._build_context" or s.get("turns") != 48:
            continue
        out += [x["reply"] for x in s["rows"] if x.get("reply")]
    return out


def count(texts, vocab):
    joined = "\n".join(texts)
    return {w: joined.count(w) for w in vocab}


def table(title, vocab, src, gen, src_label, gen_label):
    print("=" * 78)
    print(f"★ {title}")
    print("=" * 78)
    cs, cg = count(src, vocab), count(gen, vocab)
    hit_s = [w for w in vocab if cs[w]]
    hit_g = [w for w in vocab if cg[w]]
    miss = [w for w in vocab if cs[w] and not cg[w]]
    print(f"  原文提到的：{len(hit_s)} / {len(vocab)}　AI 提到的：{len(hit_g)} / {len(vocab)}")
    print()
    print(f"  {'条目':<14}{src_label:>8}{gen_label:>10}   状态")
    print("  " + "-" * 62)
    for w in sorted(vocab, key=lambda x: -cs[x]):
        if not cs[w] and not cg[w]:
            continue
        if cs[w] and not cg[w]:
            st = "❗ 原文有、AI 从不提"
        elif not cs[w] and cg[w]:
            st = "➕ AI 现编（原文没有）"
        else:
            r = cg[w] / cs[w]
            st = "✅ 双方都用" if 0.3 < r < 3 else ("⚠️ AI 用太多" if r >= 3 else "⚠️ AI 用太少")
        print(f"  {w:<14}{cs[w]:>8}{cg[w]:>10}   {st}")
    print()
    if miss:
        print(f"  ⇒ 未使用的素材（{len(miss)} 个）：{'、'.join(miss)}")
    print()
    return miss


def main():
    sop = load_sophia()
    gen = load_replies("chat-base") or load_replies("gamereal")
    print(f"★ 原文 {len(sop)} 条　AI 回复 {len(gen)} 轮")
    print()
    m1 = table("她认识谁（人物）", NPCS, sop, gen, "原文", "AI")
    m2 = table("她在哪（地点）", PLACES, sop, gen, "原文", "AI")
    m3 = table("她用什么/做什么（物品与活动）", ITEMS, sop, gen, "原文", "AI")
    m4 = table("她的情绪与状态", EMOTIONS, sop, gen, "原文", "AI")

    print("=" * 78)
    print("★ 汇总：话题池到底有多大，用了多少")
    print("=" * 78)
    allv = NPCS + PLACES + ITEMS + EMOTIONS
    cs, cg = count(sop, allv), count(gen, allv)
    used_in_src = [w for w in allv if cs[w]]
    never_in_ai = [w for w in used_in_src if not cg[w]]
    invented = [w for w in allv if cg[w] and not cs[w]]
    print(f"  原文素材条目：{len(used_in_src)}　AI 用到的：{len([w for w in allv if cg[w]])}")
    print(f"  ⇒ 原文有、AI 一次都没提：{len(never_in_ai)} 个"
          f"（占原文素材 {len(never_in_ai)/len(used_in_src)*100:.0f}%）")
    print(f"  ⇒ AI 凭空现编（原文没有）：{len(invented)} 个 —— {invented if invented else '无'}")
    print()
    print("  ⇒ 未使用清单：")
    for i in range(0, len(never_in_ai), 12):
        print("     " + "、".join(never_in_ai[i:i + 12]))


if __name__ == "__main__":
    main()
