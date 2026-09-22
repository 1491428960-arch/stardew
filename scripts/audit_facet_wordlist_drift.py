"""词表漂移表：候选词加入某个面之前，先看全库判面会怎么动（**只读**）。

**为什么必须先跑**：`_facet_of_topic` 取**声明顺序里第一个命中的面**，而「工作或手艺」
排在第一位 ⇒ 任何加进工作面的词都会优先抢走别的面的句子。实测代价：

  * 「酒」救 22 条，却吃掉 **79 条「吃喝」**（酒馆 / 酒吧同族）
  * 「织」所谓"救活 10 条"**全是「组织 / 交织」**（Kent「更有组织的生活」、
    Harvey「肌肉组织」、Emily「人生道路交织」），而真实漂移 3 条是真的
  * 「塞」把「拿布塞过」这种**动作句**判成工作面
  * 「桶」是量词，与 `test_a_bare_quantifier_is_not_a_facet` 钉住的既有口径冲突

所以规矩是：**一次只加一组、逐条看漂移原文、单字先测**。

用法：

    PYTHONPATH=bridge/src;scripts python -B scripts/audit_facet_wordlist_drift.py
    ... --group sewing            # 只跑缝纫组
    ... --candidate "亚麻|棉布" --facet 工作或手艺
    ... --detail                  # 把漂移的**原文**逐条打出来（不看原文不裁决）
    ... --real8                   # 另用真机 8 轮实测回复核对判面变化
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from facet_probe_common import (  # noqa: E402
    WORK,
    corpus,
    first_hit,
    hits,
    patched,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

# ---------------------------------------------------------------------------
# 候选组。每条是 (pattern, 归到哪一面, 备注)。
# **已落地**的用 `LANDED` 标出来 —— 落地后再跑这张表会读作全 0，
# 那是"表已经生效"的意思，不是"没效果"。
# ---------------------------------------------------------------------------

WORDLIST_GROUP: tuple[tuple[str, str, str], ...] = (
    ("装瓶|封瓶", WORK, "酿酒作业；全库命中 0，价值在**模型实时回复**"),
    ("木塞|瓶塞|软木塞", WORK, "同上：全库 0 命中，防的是动作句"),
    ("封蜡|蜡", WORK, "「封蜡」；⚠「蜡」单字偏宽，实测只影响 1 条"),
    ("标签", WORK, "「贴标签」是酿酒作业"),
    ("发酵", WORK, "酿酒作业"),
    ("葡萄", WORK, "与「葡萄园」同族；「吃葡萄」会漂到工作面"),
)

SEWING_GROUP: tuple[tuple[str, str, str], ...] = (
    ("亚麻|棉布|帆布|呢绒", WORK, "布料名；全库 0 影响，价值在实时回复（真机第 3/4 轮「一整块亚麻布」）"),
    ("裁缝|裁剪", WORK, "缝纫动作；只影响 1 条，且方向是**修正**（Scarlett 的「裁剪皮夹克」）"),
    ("围裙|戏服", WORK, "成品创作物；全库 0 影响，防未来实时回复"),
)

# **实测否决项**（保留在此，防止日后有人"顺手加回来"）：
#   ("酒", WORK)            → 救 22 / **吃 79 条吃喝**
#   ("苹果酒|葡萄酒", WORK)   → Pierre 的「招牌的香料南瓜苹果酒」是吃喝面素材，
#                             收进来会让他的面覆盖从 5 面退回（已有测试钉住）
#   ("塞", WORK)            → 「拿布塞过」这种动作句被判成工作面
#   ("桶", WORK)            → 量词（"那几桶"），与既有口径冲突
#   ("织", WORK)            → 救活的 10 条**全是"组织 / 交织"**，且漂移 3 条是真的
#   ("针", WORK)            → "救活"的那条是 Shane「但不是**针对**你」
#   ("缝", WORK)            → Gunther「洞壁之间有一个小**缝隙**…线索」是探险线索
#   ("裁", WORK)            → Morris「公司的**总裁**」；改用多字形式「裁缝|裁剪」
#   ("连衣裙|裙子", WORK)     → 救活的唯一一条是 Bianka 的情感句

GROUPS = {
    "wordlist": ("酿酒作业（已落地）", WORDLIST_GROUP),
    "sewing": ("缝纫 / 布料（提案）", SEWING_GROUP),
}

# 真机 8 轮实测回复（2026-09-23 00:47，cloud provider，与游戏端 payload 同形）。
# 用途：补词前后逐轮核对判面，证明收益落在**真实生成**上而不只是语料统计上。
REAL_8 = (
    "嘿，刚把今天最后一张便签贴到酒瓶上，手还有点粘。这批新酿闻着比上一批甜一点，我不敢太早下结论。你晚上都在忙什么呀？",
    "哇，这批苹果的颜色比我记得的还亮。我本来只打算看一眼就回屋，结果又蹲下来挨个转了半圈。你看这颗，蒂上还挂着一小片叶子，我差点舍不得摘它。",
    "哦哦哦，我想起来了！艾米丽给过我一整块亚麻布，我一直没舍得动它。要不今晚先裁个样子出来……等等，秋十八了，风会软下来。先放着吧，明天早点起，脑子清醒再说。",
    "今晚这批酒液比昨天清亮多了，我盯着看了好一会儿。再放两三天就该分装，给你留一瓶尝尝。还有那块亚麻布，等这批酒弄完，我先裁一小块试试手。",
    "嘶，贴标签贴到第三排，手指上全是胶。本来只想核对一下日期，结果一下就蹲到现在。你看我手腕这儿，还印着一条没洗掉的墨。",
    "刚才去广场那边的杂货铺送酒，听见玛丽和皮埃尔隔着柜台吵。就为了一篮子放错摊位的南瓜，两个人谁也不肯先挪。我抱着箱子站在那儿，想劝又插不上嘴。最后还是克林特出来，把南瓜搬到墙角，两人就都不说了。你要是在场，会不会也觉得那南瓜无辜得很。",
    "哇，你看这批的颜色——我本来只想看看发酵罐，结果一待就待到现在。而且我今天在酒窖角落翻到了去年写的那张配方，纸上还有一小块酒渍。要不要一会儿我念给你听？",
    "刚洗完最后一个发酵罐，手还凉着呢。对了，刚才在阁楼翻箱子，翻出刚搬来那阵子的旧屋钥匙，锈得都不像钥匙了。那时候房里就一张旧床垫，晚上抱着杯子蹲在窗边看星星。先不忙着收，我再瞅它两眼。",
)


def scan(rows, base_first, base_hits, extra, facet):
    """返回 (新命中, 无面救活, 主面漂移, 去向计数, 漂移原文, 救活原文)。"""

    patterns = patched(extra)
    new = rescued = moved = 0
    where: dict[str, int] = {}
    drifted: list[tuple[str, str, str, str]] = []
    revived: list[tuple[str, str]] = []
    for (npc, text), before, before_hits in zip(rows, base_first, base_hits):
        after = first_hit(text, patterns)
        if after == before:
            if hits(text, patterns) - before_hits:
                new += 1
            continue
        if before is None:
            rescued += 1
            revived.append((npc, text))
        else:
            moved += 1
            where[before] = where.get(before, 0) + 1
            drifted.append((npc, text, before, after))
    return new, rescued, moved, where, drifted, revived


def main() -> None:
    parser = argparse.ArgumentParser(description="词表漂移表（只读）")
    parser.add_argument("--group", choices=sorted(GROUPS) + ["all"], default="all")
    parser.add_argument("--candidate", action="append", default=[], help="自定义候选（正则可含 |）")
    parser.add_argument("--facet", default=WORK, help="自定义候选归到哪一面")
    parser.add_argument("--detail", action="store_true", help="打印漂移条目原文")
    parser.add_argument("--real8", action="store_true", help="用真机 8 轮核对")
    args = parser.parse_args()

    rows = corpus()
    print(f"语料合计 {len(rows)} 条")
    base = patched({})
    base_first = [first_hit(text, base) for _, text in rows]
    base_hits = [hits(text, base) for _, text in rows]

    chosen: list[tuple[str, tuple[tuple[str, str, str], ...]]] = []
    if args.group == "all":
        chosen = list(GROUPS.values())
    else:
        chosen = [GROUPS[args.group]]

    if args.candidate:
        chosen.append(
            ("自定义候选", tuple((word, args.facet, "（命令行指定）") for word in args.candidate))
        )

    for title, group in chosen:
        print()
        print("=" * 96)
        print(f"候选组：{title}")
        print(f"{'候选':<24}{'新命中':>7}{'无面救活':>9}{'主面漂移':>9}  漂移去向 top3")
        print("-" * 96)
        for word, facet, note in group:
            new, rescued, moved, where, drifted, revived = scan(
                rows, base_first, base_hits, {facet: [word]}, facet
            )
            top = (
                "、".join(f"{k} {v}" for k, v in sorted(where.items(), key=lambda x: -x[1])[:3])
                or "（无漂移）"
            )
            print(f"{word:<24}{new:>7}{rescued:>9}{moved:>9}  {top}")
            print(f"          └ {note}")
            if args.detail and (drifted or revived):
                for npc, text, before, after in drifted:
                    print(f"          [漂移] {npc}: {before} -> {after}")
                    print(f"                 {text[:100]}")
                for npc, text in revived[:5]:
                    print(f"          [救活] {npc}: {text[:100]}")

        print()
        extra = {facet: [word for word, facet, _ in group]}
        new, rescued, moved, where, drifted, _ = scan(rows, base_first, base_hits, extra, WORK)
        print(f"整组一起加：新命中 {new} / 无面救活 {rescued} / 主面漂移 {moved}")
        for name, count in sorted(where.items(), key=lambda x: -x[1]):
            print(f"    {name:<14}{count:>5}")

        if args.real8:
            print()
            print("真机 8 轮核对该组：")
            changed = 0
            patterns = patched(extra)
            for index, text in enumerate(REAL_8, start=1):
                before = sorted(hits(text, base)) or ["（无面）"]
                after = sorted(hits(text, patterns)) or ["（无面）"]
                mark = ""
                if before != after:
                    changed += 1
                    mark = "  ← 变了"
                print(f"  第 {index} 轮　{'/'.join(before):<22}→ {'/'.join(after)}{mark}")
            print(f"  判面变化 {changed} / {len(REAL_8)} 轮")


if __name__ == "__main__":
    main()
