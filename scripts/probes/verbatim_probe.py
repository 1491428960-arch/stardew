"""量化「AI 回复有多少是复述角色原文样本」—— 2026-09-24。

## 为什么要这个指标

用户的核心目标是「长久的聊」：① 话题不断有新东西；② 同一话题能聊出不同感觉。
而「复述原文样本」直接损害 ① —— 如果她总在背游戏原版台词，
那聊起来就不会有新东西，只是把玩家已经看过的句子重新排一遍。

同一个场景两个模型各一次抽样的对比（2026-09-24）目视差别明显：
  DeepSeek  Robin「别跟我提开销，我上礼拜赶了两张木工单子，腰还没缓过来呢。」
  Kimi      Robin「嘿，如果你需要什么材料或者蓝图，请到我的店里来！而且，
                     你的光顾能够为本地的经济贡献一份力量。」
后者更像原版台词样本。**但单次抽样不足以定论，本探针就是把它量化。**

## 度量定义

把该角色的**全部原文样本**规范化（只留 CJK），切成 n-gram 集合（默认 n=8）。
对每条 AI 回复同样滑 n-gram，标记命中位置，合并成连续区间。

* **复述率** = 被命中覆盖的 CJK 字符数 / 回复的 CJK 总字符数
* **最长连续命中** = 最长的连续命中区间长度（最能说明「整句照搬」；
  8 刚好等于 n，说明只擦到一个 n-gram 的边；20+ 基本就是整句搬）

n=8 的取法：中文里 8 个连续字基本是一个完整的短句片段，
偶然撞车的概率极低（原文库才几千字）。

## 用法

    python -B scripts/probes/verbatim_probe.py --npc Sophia --turns 20
    python -B scripts/probes/verbatim_probe.py --all      # 三个角色各 10 轮

⚠ 2026-09-24 从 `.tmp/topic-probe/` 挪到这里：`.tmp/` 在 `.gitignore` 里，
放那儿等于这些工具不进版本控制，下次会话就没了。`parents[2]` 的层级
恰好不变，所以只改了本文档里的路径。

## 发历史必须用 `{"role": ...}`

⚠ **这条踩过一个大坑**：原先这里发的是
`{"speakerType": "player"/"npc", "content": ...}`，Bridge **不认且静默丢弃**，
于是 `conversation_history` 卡片始终是空的 `"[]"`——号称「多轮对话」，
实际每轮都是独立的初见。五轮各 300 回合的数据全部因此失真，连
「Kimi 的语气词是 DeepSeek 的 3.1 倍」这个结论都是从错数据里算出来的
（修正后是 1.6 倍）。**换任何字段名之前，先验证它真的到达了 prompt。**

## 诊断码要记下来

`--out` 的 JSON 里带 `warnings`：判断某个 guard 机制「到底有没有被激活」
只能看它。汇总密度数字**分不出「没效果」和「没跑起来」**——2026-09-24
语气词闸就是在「从未触发」的状态下被误判成「无效」的。

⚠ Command Code 上游抖动频繁（实测 30 次失败 8 次 = 27%），本探针自带重试。
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "data" / "generated" / (
    "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)
BRIDGE = "http://127.0.0.1:5678/api/dialogue/test"

_CJK = re.compile(r"[\u4e00-\u9fff]")

#: 各角色的玩家台词脚本。刻意用**新档 stranger 阶段**的口吻（用户刚开的档是
#: 春季第 1 天），从寒暄慢慢过渡到具体话题，模拟真实多轮。
PLAYER_SCRIPTS: dict[str, list[str]] = {
    "Sophia": [
        # ⚠ 刻意把「自我介绍类」问题放在最前：`speechEvidence` 的第一条就是
        # 覆盖层的 `Introduction` 原文（34 字），这是最容易泄漏的那张卡。
        # 2026-09-24 冒烟测试里正是这一问让模型照抄了整条 Introduction。
        "你叫什么名字？",
        "能跟我介绍一下你自己吗？",
        "你就是这片葡萄园的主人吗？",
        "你好，我是刚搬到那个旧农场的人。",
        "你是从哪里来的？",
        "这些葡萄藤是你自己种的吗？",
        "你平时一天都忙些什么？",
        "我看你这里好像还有酒桶。",
        "你酿的酒是自己喝还是拿去卖？",
        "一个人打理这么大一片地，累不累？",
        "你是什么时候开始做这一行的？",
        "这附近还有别的年轻人吗？",
        "我今天在镇上转了一圈。",
        "你认识一个叫刘易斯的吗？",
        "我那块地荒得厉害，草都到我腰了。",
        "你觉得我该先种点什么？",
        "说起来，你最喜欢哪个季节？",
        "你平时有空会去镇上吗？",
        "我听说这边冬天雪很大。",
        "你有没有养什么动物？",
        "我打算明天去矿洞看看。",
        "跟你聊了这么久，我该回去干活了。",
        "改天我带点自己种的东西给你。",
    ],
    "Lewis": [
        "你好，我是新来的农场主。",
        "请问您怎么称呼？",
        "能跟我说说您自己吗？",
        "听说这个镇子是你在管？",
        "那个旧农场以前是谁的？",
        "镇上最近有什么活动吗？",
        "我看公告栏上贴了不少东西。",
        "你平时都忙着做什么？",
        "我那块地荒了很久了。",
        "这里的居民都靠什么生活？",
        "你有没有什么建议给我？",
        "我今天在镇上转了一圈。",
    ],
    "Robin": [
        "你好，我是刚搬来的。",
        "你叫什么名字呀？",
        "你是做什么工作的？",
        "你这里可以买木材吗？",
        "我那栋房子破得挺厉害的。",
        "你会做家具？",
        "你家里还有别人吗？",
        "这附近的山上有什么？",
        "我打算把农场重新弄一下。",
        "盖个鸡舍大概要多少钱？",
        "你平时什么时候在店里？",
        "谢谢你，我改天再来。",
    ],
}

STAGE_HEARTS = {"stranger": 0, "acquaintance": 2, "friend": 4, "close": 6}

#: 中文显示名 —— 索引 `profiles[].displayName` 存的是英文（未汉化），
#: 而真实游戏端发的是游戏内显示名。用英文名跑会让 prompt 里混进英文，
#: 污染风格测量，所以这里按社区通用译名补齐。
DISPLAY_NAMES = {
    "Sophia": "索菲亚", "Lewis": "刘易斯", "Robin": "罗宾",
    "Wizard": "巫师", "Sebastian": "塞巴斯蒂安", "Alex": "亚历克斯",
    "Shane": "谢恩", "Elliott": "埃利奥特", "Harvey": "哈维",
    "Sam": "山姆", "Abigail": "阿比盖尔", "Leah": "莉亚",
    "Penny": "潘妮", "Emily": "艾米丽", "Marnie": "玛妮",
}

#: 通用台词脚本 —— 给 PLAYER_SCRIPTS 里没有的角色用（多角色对照时）。
#: 保持与专用脚本同样的「新档 stranger 口吻」基调，只是不针对具体角色。
DEFAULT_SCRIPT = [
    "你好，我是刚搬到镇上的人。",
    "你叫什么名字？",
    "能跟我说说你自己吗？",
    "你平时都忙些什么？",
    "你在这儿住了多久了？",
    "这附近有什么值得去的地方吗？",
    "你最喜欢哪个季节？",
    "我一个人打理农场，有时候挺累的。",
    "谢谢你跟我聊这些。",
    "改天再聊。",
]


def normalize(text: str) -> str:
    """只留 CJK 字符 —— 标点和空白不参与比对，避免「，」凑出假命中。"""
    return "".join(_CJK.findall(text))


def build_gram_set(texts: list[str], n: int) -> set[str]:
    grams: set[str] = set()
    for text in texts:
        s = normalize(text)
        for i in range(len(s) - n + 1):
            grams.add(s[i : i + n])
    return grams


def coverage(reply: str, grams: set[str], n: int) -> tuple[int, int, int]:
    """返回 (命中字符数, 最长连续命中, CJK 总字符数)。"""
    s = normalize(reply)
    if len(s) < n:
        return 0, 0, len(s)
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
    return sum(hit), best, len(s)


def post(payload: dict, retries: int = 4) -> dict | None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(
            BRIDGE, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            print(f"      HTTP {exc.code} {detail}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"      {type(exc).__name__} {exc}", flush=True)
        if attempt < retries - 1:
            time.sleep(5 * (attempt + 1))
    return None


def run_role(npc_id: str, display: str, texts: list[str], turns: int,
             grams_by_n: dict[int, set[str]], source_mods: list[str],
             repeats: int = 1) -> list[dict]:
    """跑 `repeats` 个**独立会话**，每个 `turns` 轮。

    2026-09-24：语气词是稀疏事件，单会话 10 轮的测量噪声就有 ±25%，
    盖过 prompt 改动的效果。独立会话（每次 history 从头建）比拉长单会话
    更贴近真实游戏，也让每份样本都处在同样的陌生关系阶段。
    """
    script = PLAYER_SCRIPTS.get(npc_id, DEFAULT_SCRIPT)[:turns]
    rows: list[dict] = []
    for session in range(1, repeats + 1):
        history: list[dict] = []
        rows_start = len(rows)
        if repeats > 1:
            print(f"  ── 会话 {session}/{repeats}", flush=True)
        for idx, player_line in enumerate(script, 1):
            payload = {
                "npcId": npc_id,
                "displayName": display,
                "message": player_line,
                "provider": "cloud",
                "compactPrompt": True,
                "channel": "face_to_face",
                "sourceMods": source_mods,
                "history": history,
                "recentReplies": [r["reply"] for r in rows[rows_start:]][-8:],
                "gameState": {
                    "season": "spring", "date": "1", "weather": "clear",
                    "time": 800 + idx * 20, "location": "Forest",
                    "friendshipHearts": 0,
                },
            }
            result = post(payload)
            if result is None:
                print(f"    turn {idx:>2}  ✗ 失败（已重试）", flush=True)
                continue
            reply = result.get("reply", "")
            row = {
                "session": session,
                "turn": idx,
                "player": player_line,
                "reply": reply,
                "provider": result.get("provider"),
                "fallback": result.get("fallback"),
                "latencyMs": result.get("latencyMs"),
                # 记下 guard 的诊断码：判断某个机制改动「到底有没有被激活」
                # 只能看这里，汇总密度数字分不出「没效果」和「没跑起来」。
                "warnings": result.get("warnings") or [],
            }
            for n, grams in grams_by_n.items():
                cov, longest, total = coverage(reply, grams, n)
                row[f"cov{n}"] = cov
                row[f"longest{n}"] = longest
                row[f"total{n}"] = total
            rows.append(row)
            # ⚠ 必须是 `{"role": ...}`。
            #
            # 此前这里写的是 `{"speakerType": "player"/"npc"}`，Bridge 不认，
            # **静默丢弃**——于是 2026-09-24 那五轮各 300 回合的探针里，
            # `conversation_history` 卡片始终是空的 `"[]"`，所谓「多轮对话」
            # 其实是每轮独立的初见。直到 gate 死活不触发才查出来。
            history.append({"role": "user", "content": player_line})
            history.append({"role": "assistant", "content": reply})
            cov8 = row["cov8"]
            rate = cov8 / row["total8"] * 100 if row["total8"] else 0
            print(f"    turn {idx:>2}  {rate:5.1f}% 最长{row['longest8']:>3}字 "
                  f"({result.get('latencyMs')}ms) {reply[:44]}", flush=True)
    return rows


def summarize(npc_id: str, rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("total8")]
    if not ok:
        return {"npc": npc_id, "n": 0}
    return {
        "npc": npc_id,
        "n": len(ok),
        "fallback": sum(1 for r in ok if r.get("fallback")),
        "rate8_median": statistics.median(r["cov8"] / r["total8"] * 100 for r in ok),
        "rate8_mean": statistics.mean(r["cov8"] / r["total8"] * 100 for r in ok),
        "longest8_median": statistics.median(r["longest8"] for r in ok),
        "longest8_max": max(r["longest8"] for r in ok),
        "rate6_median": statistics.median(r["cov6"] / r["total6"] * 100 for r in ok),
        "rate12_median": statistics.median(r["cov12"] / r["total12"] * 100 for r in ok),
        "len_median": statistics.median(r["total8"] for r in ok),
        "latency_median": statistics.median(
            r["latencyMs"] for r in ok if r.get("latencyMs")),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npc", default="Sophia")
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--all", action="store_true", help="三个角色各 --turns 轮")
    ap.add_argument(
        "--npcs",
        default="",
        help="逗号分隔的角色列表，各跑 --turns 轮（用于多角色风格对照）",
    )
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--repeats", type=int, default=1,
        help="每个角色跑几个独立会话（语气词这类稀疏指标需要多会话才测得准）",
    )
    args = ap.parse_args()

    print(f"载入索引 {INDEX.name} ...", flush=True)
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    samples = data["styleSamples"]
    by_npc: dict[str, list[str]] = {}
    by_mod: dict[str, set[str]] = {}
    for s in samples:
        nid = s.get("npcId")
        if not nid:
            continue
        by_npc.setdefault(nid, []).append(str(s.get("text") or ""))
        by_mod.setdefault(nid, set()).add(str(s.get("sourceMod") or ""))

    if args.npcs:
        targets = [
            (n.strip(), DISPLAY_NAMES.get(n.strip(), n.strip()), args.turns)
            for n in args.npcs.split(",")
            if n.strip()
        ]
    elif args.all:
        targets = [
            ("Sophia", "索菲亚", args.turns),
            ("Lewis", "刘易斯", args.turns),
            ("Robin", "罗宾", args.turns),
        ]
    else:
        targets = [(args.npc, DISPLAY_NAMES.get(args.npc, args.npc), args.turns)]

    all_rows: dict[str, list[dict]] = {}
    for npc_id, display, turns in targets:
        texts = by_npc.get(npc_id, [])
        if not texts:
            print(f"⚠ {npc_id} 没有原文样本，跳过")
            continue
        total_chars = sum(len(normalize(t)) for t in texts)
        grams_by_n = {n: build_gram_set(texts, n) for n in (6, 8, 12)}
        print(f"\n══ {npc_id}（{display}）原文库 {len(texts)} 条 / {total_chars} 字 "
              f"/ 8-gram {len(grams_by_n[8])} 个 ══", flush=True)
        rows = run_role(npc_id, display, texts, turns, grams_by_n,
                        sorted(by_mod.get(npc_id, set())), repeats=args.repeats)
        all_rows[npc_id] = rows

    print("\n\n══════════ 汇总 ══════════")
    header = (f"{'角色':<10}{'轮':>4}{'fb':>4}{'复述率8中位':>12}"
              f"{'均值':>8}{'最长中位':>10}{'最长max':>9}{'6-gram':>9}"
              f"{'12-gram':>9}{'字数中位':>10}{'延迟中位':>10}")
    print(header)
    print("-" * len(header))
    summary = []
    for npc_id, rows in all_rows.items():
        s = summarize(npc_id, rows)
        summary.append(s)
        if not s.get("n"):
            continue
        print(f"{s['npc']:<10}{s['n']:>4}{s['fallback']:>4}"
              f"{s['rate8_median']:>11.1f}%{s['rate8_mean']:>7.1f}%"
              f"{s['longest8_median']:>10.0f}{s['longest8_max']:>9}"
              f"{s['rate6_median']:>8.1f}%{s['rate12_median']:>8.1f}%"
              f"{s['len_median']:>10.0f}{s['latency_median']:>9.0f}ms")

    if args.out:
        Path(args.out).write_text(
            json.dumps({"summary": summary, "rows": all_rows},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n明细已写入 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
