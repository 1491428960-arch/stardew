"""语气量化基线：模型生成的她 vs 游戏原话里的她（**只读**）。

用户口径是「主要是要自然一点，像真实对话，也要像这个人该说的话」，而"文艺腔"是
这条线上反复被提到的抱怨。本脚本把"文艺腔"拆成**可数的指标**，拿**她自己的原话**
当基线 —— 只给数字，不下主观结论。

2026-09-23 实测（Sophia 原话 266 条 / 6914 字 vs 真机 8 轮 / 610 字）：

| 指标 | 她的原话 | 模型生成的她 |
|---|---|---|
| 平均每条字数 | 25.99 | 76.25 |
| 平均每句字数 | 8.54 | **20.33（2.4 倍）** |
| 语气词/100字 | 1.71 | 1.64（几乎一致） |
| 比喻/100字 | 0.10 | 0.16 |
| 自我感受/100字 | 0.40 | 0.33 |
| 感官描写/100字 | 0.13 | **0.66（5 倍）** |
| 问号/100字 | 1.26 | 0.33 |

⇒ **"文艺腔"不是语气词问题**（模型已经继承她的口语习惯：嘿 / 呀 / 哇 / 哦哦哦 / 嘶 / 呢），
而是**感官描写偏多 + 句长偏长**这两项。
提问偏少那一项**要打折扣**：游戏台词的功能与连续聊天不同（前者常直接对玩家发问，
机制使然），不能全归为缺陷。

⚠ **指标一律用密度（每 100 字），不用总数**：游戏台词短、生成回复长，
拿总数比只会得出"她变啰嗦了"这种没有信息量的结论。

⚠ **样本量诚实声明**：生成侧默认只有 8 轮 / 610 字（**很小**），数字只作方向参考；
要坐实需要更大批次。要用自己的样本就传 `--generated`。

用法：

    PYTHONPATH=bridge/src;scripts python -B scripts/audit_dialogue_tone.py
    ... --npc Sophia
    ... --generated .tmp/topic-probe/summary.json    # 云端探针的产物可直接用
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from facet_probe_common import corpus  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

COLLOQUIAL = "呀呢吧啊啦嘛哦嗯咦哎唉哟哇嘿嘶"
SIMILE = ("像", "好像", "仿佛", "似的")
FEELING = ("我觉得", "我想", "我猜", "我不知道", "我大概", "我似乎", "我不敢")
SENSE = ("闻着", "味道", "颜色", "声音", "感觉", "看着", "清亮")
QUESTION = ("？", "?")
SENT_END = "。！？…"

# 缺省样本：2026-09-23 00:47 云端实测 8 轮（与游戏端 payload 同形）。
# 它是**一次实测的快照**，不是"标准答案" —— 换样本请用 --generated。
DEFAULT_GENERATED = (
    "嘿，刚把今天最后一张便签贴到酒瓶上，手还有点粘。这批新酿闻着比上一批甜一点，我不敢太早下结论。你晚上都在忙什么呀？",
    "哇，这批苹果的颜色比我记得的还亮。我本来只打算看一眼就回屋，结果又蹲下来挨个转了半圈。你看这颗，蒂上还挂着一小片叶子，我差点舍不得摘它。",
    "哦哦哦，我想起来了！艾米丽给过我一整块亚麻布，我一直没舍得动它。要不今晚先裁个样子出来……等等，秋十八了，风会软下来。先放着吧，明天早点起，脑子清醒再说。",
    "今晚这批酒液比昨天清亮多了，我盯着看了好一会儿。再放两三天就该分装，给你留一瓶尝尝。还有那块亚麻布，等这批酒弄完，我先裁一小块试试手。",
    "嘶，贴标签贴到第三排，手指上全是胶。本来只想核对一下日期，结果一下就蹲到现在。你看我手腕这儿，还印着一条没洗掉的墨。",
    "刚才去广场那边的杂货铺送酒，听见玛丽和皮埃尔隔着柜台吵。就为了一篮子放错摊位的南瓜，两个人谁也不肯先挪。我抱着箱子站在那儿，想劝又插不上嘴。最后还是克林特出来，把南瓜搬到墙角，两人就都不说了。你要是在场，会不会也觉得那南瓜无辜得很。",
    "哇，你看这批的颜色——我本来只想看看发酵罐，结果一待就待到现在。而且我今天在酒窖角落翻到了去年写的那张配方，纸上还有一小块酒渍。要不要一会儿我念给你听？",
    "刚洗完最后一个发酵罐，手还凉着呢。对了，刚才在阁楼翻箱子，翻出刚搬来那阵子的旧屋钥匙，锈得都不像钥匙了。那时候房里就一张旧床垫，晚上抱着杯子蹲在窗边看星星。先不忙着收，我再瞅它两眼。",
)


def load_generated(path: Path) -> list[str]:
    """从云端探针产物里取生成文本（容错：list 或含 replies 的对象都收）。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    else:
        items = (
            payload.get("replies")
            or payload.get("turns")
            or payload.get("results")
            or []
        )
    texts: list[str] = []
    for item in items:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict):
            for key in ("reply", "text", "message", "content"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())
                    break
    if not texts:
        raise SystemExit(f"{path} 里没找到可用的生成文本（支持 list / replies / turns / results）")
    return texts


def measure(texts: list[str]) -> dict[str, float]:
    joined = "".join(texts)
    chars = len(joined)
    sentences = sum(joined.count(mark) for mark in SENT_END) or 1

    def density(needles) -> float:
        count = sum(joined.count(needle) for needle in needles)
        return count / chars * 100 if chars else 0.0

    return {
        "条数": len(texts),
        "总字数": chars,
        "平均每条字数": chars / len(texts) if texts else 0.0,
        "平均每句字数": chars / sentences,
        "语气词/100字": density(tuple(COLLOQUIAL)),
        "比喻/100字": density(SIMILE),
        "自我感受/100字": density(FEELING),
        "感官描写/100字": density(SENSE),
        "问号/100字": density(QUESTION),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="语气量化基线（只读）")
    parser.add_argument("--npc", default="Sophia", help="拿谁的原话当基线")
    parser.add_argument("--generated", type=Path, default=None, help="生成样本 JSON")
    args = parser.parse_args()

    generated = (
        load_generated(args.generated) if args.generated else list(DEFAULT_GENERATED)
    )
    original = [text for npc, text in corpus() if npc == args.npc]
    if not original:
        raise SystemExit(f"语料里没有 {args.npc} 的原话")

    print(f"{args.npc} 原话：{len(original)} 条")
    print(
        f"生成样本：{len(generated)} 条"
        + (f"（来自 {args.generated}）" if args.generated else "（内置：2026-09-23 00:47 实测 8 轮）")
    )
    print()

    left = measure(original)
    right = measure(generated)

    print(f"{'指标':<18}{'她的原话':>14}{'模型生成的她':>16}   差")
    print("-" * 66)
    for key in left:
        a, b = left[key], right[key]
        diff = "" if key in ("条数", "总字数") else f"{b - a:+.2f}"
        print(f"{key:<18}{a:>14.2f}{b:>16.2f}   {diff}")

    print()
    print("=== 逐条：生成回复里的语气词落在哪 ===")
    for index, text in enumerate(generated, start=1):
        marks = [ch for ch in text if ch in COLLOQUIAL]
        print(f"  第 {index} 条  {len(text):>3} 字  语气词 {len(marks)} 个  {''.join(marks)}")


if __name__ == "__main__":
    main()
