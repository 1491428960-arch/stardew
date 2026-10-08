#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""回复质量离线审计 —— 动作堆叠 / 泛泛反问 / 主动换题，外加量词-状态问句假阴性量化。

**零云端请求、只读**：不修改任何生产代码，判据全部复用生产常量与函数。

用法（PYTHONPATH 需三者：`<wt>;<wt>/bridge/src;<wt>/scripts`）::

    python -B scripts/audit_reply_quality.py              # 默认三批（含人读 ground truth）
    python -B scripts/audit_reply_quality.py --all        # 全库（排除 pytest 夹具）
    python -B scripts/audit_reply_quality.py --path <文件或目录>

判据分层（这是本脚本唯一的设计主张）
------------------------------------
2026-10-08 查明的教训是：`answeredCurrentTopic` 在**量词-状态问句**上结构性假阴性
（`harvey-close-gesture` 13.3% vs 同角色 `harvey-close-clinic` 93.3%，差 80pp）。
**假阴性比「没有判据」更危险** —— 它会给出一个看起来像质量证据的数字。
三类约束的可操作程度并不相同，所以本脚本**对它们区别对待**：

* **动作堆叠** —— 判据可操作（数括号块），给出**真判据**；
* **泛泛反问 / 主动换题** —— 判据依赖字面重叠，**只摊开计数并列样本，不判定**
  （判据不存在时「跑通」不等于「测到了」，见 `probe_topic_alignment.py` 的同一纪律）；
* **量词-状态问句** —— 用 **monkey-patch 常量 + 调用真函数** 量化「扩充常量」的翻转面，
  并要求**反向验证**：真没回答的样本必须仍判 False。

⚠ 刻意**不复制** `_conversation_topic_answered` 的函数体：复制出第二份实现，
两边迟早走偏（项目既有纪律）。这里改的是模块级常量，调用的是同一个函数。
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

WT = pathlib.Path(__file__).resolve().parents[1]
for _extra in (str(WT), str(WT / "bridge" / "src"), str(WT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

import stardew_ai_bridge.behavior_quality as bq  # noqa: E402
from stardew_ai_bridge import guard as guard_mod  # noqa: E402

#: 默认三批 —— 2026-10-05 那批是 `sam/elliott/harvey` 三个人读结论的来源，
#: 10-06 两批（本地 / cloud）是同名 case 的另一次采样，用来验判据的跨 provider 稳定性。
DEFAULT_RUNS = (
    ".tmp/eval-topic-alignment-20261005/results.jsonl",
    ".tmp/eval-scene-hardfact/pre-change-20261006/results.jsonl",
    ".tmp/eval-scene-hardfact/pre-change-20261006-cloud/results.jsonl",
)

#: 量词-状态问句：玩家问的是**状态里的数量/时长**（「你还要忙多久」「还剩几个」）。
#: 这类问句的正确答案天然**不含提问用词**（「快了」「两个」），
#: 于是字面 n-gram / 锚点通道必然空手而归 —— 这就是 80pp 缺口的成因。
QUANTITY_STATUS_QUESTION = re.compile(
    r"(?:多久|多长时间|几天|几个|几杯|几份|几个|几次|几回|多少|多长)[？?]?\s*$"
)

def _extend(pattern: re.Pattern[str], extra: str) -> re.Pattern[str]:
    """把 `extra` 作为新分支插进 pattern **最外层分组**，其余部分逐字不变。

    刻意不手抄一份 pattern —— 手抄出的第二份定义会与生产常量各自漂移，
    这正是项目反对的「两处各写一份，慢慢走偏」。
    """

    text = pattern.pattern
    if not text.startswith("(?:"):
        raise ValueError(f"pattern 不以 (?: 开头，无法安全扩展：{text[:40]}")
    return re.compile(text.replace("(?:", f"(?:{extra}|", 1))


#: 提案 A：只在既有 QUESTION 常量上补量词分支。
PROPOSED_QUESTION = _extend(
    bq._CONVERSATION_LEAD_STATUS_QUESTION_PATTERN,
    "多久|多长时间|几天|几个|几杯|几份|几次|几回|多少",
)

#: 提案 B：再补 REPLY 侧 —— 「快了 / 两个钟头 / 还剩三份」这类**数量或时长表述**。
#: 刻意用「数词+量词」的结构模式而不是枚举具体词：这一类答案的共同特征是
#: **答案里出现数量**，不是出现某个特定词，枚举挡不住没见过的搭配。
PROPOSED_REPLY = _extend(
    bq._CONVERSATION_LEAD_STATUS_REPLY_PATTERN,
    r"快了|马上|就好|就快|这就|还剩|剩下|只剩"
    r"|[两三四五六七八九十百]+(?:个|份|杯|天|次|分钟|小时|钟头|周|月|年|句|页|遍)"
    r"|\d+\s*(?:个|份|杯|天|次|分钟|小时|钟头|周|月|年|句|页|遍)",
)

STAGE_DIRECTION = getattr(guard_mod.ResponseGuard, "_stage_direction", None)


def iter_turns(path: pathlib.Path):
    """逐 (case, turn) 产出；夹具目录与空文件自动跳过。"""

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        for turn in case.get("turns") or []:
            yield case, turn


def collect(paths: list[pathlib.Path]):
    rows = []
    for path in paths:
        for case, turn in iter_turns(path):
            rows.append(
                {
                    "caseId": case.get("caseId"),
                    "npcId": case.get("npcId"),
                    "stage": case.get("relationshipStage"),
                    "channel": case.get("channel"),
                    "provider": case.get("provider"),
                    "src": path.parent.name,
                    "input": str(turn.get("playerInput") or ""),
                    "reply": str(turn.get("reply") or ""),
                    "answered": turn.get("answeredCurrentTopic"),
                    "caseAnswered": case.get("answeredCurrentTopic"),
                }
            )
    return rows


def simulate(question, reply, input_text: str, reply_text: str) -> bool:
    """把模块常量临时换成提案版，调用**同一个**生产函数，再还原。"""

    orig_q = bq._CONVERSATION_LEAD_STATUS_QUESTION_PATTERN
    orig_r = bq._CONVERSATION_LEAD_STATUS_REPLY_PATTERN
    bq._CONVERSATION_LEAD_STATUS_QUESTION_PATTERN = question
    if reply is not None:
        bq._CONVERSATION_LEAD_STATUS_REPLY_PATTERN = reply
    try:
        return bq._conversation_topic_answered(input_text, reply_text)
    finally:
        bq._CONVERSATION_LEAD_STATUS_QUESTION_PATTERN = orig_q
        bq._CONVERSATION_LEAD_STATUS_REPLY_PATTERN = orig_r


def clip(text: str, limit: int = 72) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", default=[], help="results.jsonl 或其目录，可重复")
    parser.add_argument("--all", action="store_true", help="扫全库（排除 .tmp/pytest）")
    parser.add_argument("--samples", type=int, default=12, help="每节列出的样本条数")
    args = parser.parse_args()

    if args.all:
        paths = [
            p
            for p in WT.rglob("results.jsonl")
            if "pytest" not in p.parts and "__pycache__" not in p.parts
        ]
    elif args.path:
        paths = []
        for raw in args.path:
            p = pathlib.Path(raw)
            if not p.is_absolute():
                p = WT / p
            paths.extend(sorted(p.rglob("results.jsonl")) if p.is_dir() else [p])
    else:
        paths = [WT / rel for rel in DEFAULT_RUNS]

    paths = [p for p in paths if p.exists()]
    if not paths:
        print("没有可读的 results.jsonl。")
        return 1

    rows = collect(paths)
    print("=== 载入 ===")
    for p in paths:
        n = sum(1 for r in rows if r["src"] == p.parent.name)
        print(f"  {p.relative_to(WT)}  →  {n} 回合")
    print(f"  合计 {len(rows)} 回合 / {len(paths)} 批")

    print("\n=== §0 这批数据能测什么（先问工具看得见多少）===")
    action_mode = getattr(guard_mod, "NPC_ACTION_MODE", None)
    print(f"  guard.NPC_ACTION_MODE（环境变量 STARDEW_AI_NPC_ACTION）= {action_mode!r}")
    print("    ⚠ 它只决定**将来新跑**的批次写不写括号动作，**不影响**读历史产物；")
    print("      下面的括号计数来自数据本身，与它无关。")
    if STAGE_DIRECTION is not None:
        in_paren = sum(1 for r in rows if STAGE_DIRECTION.search(r["input"]))
        out_paren = sum(1 for r in rows if STAGE_DIRECTION.search(r["reply"]))
        print(f"  玩家输入含括号动作：{in_paren} / {len(rows)}")
        print(f"  NPC 回复含括号动作：{out_paren} / {len(rows)}")
        if out_paren == 0:
            print("  ⚠⚠ 回复里**一个括号块都没有** ⇒ §1 在这批数据上测不了：")
            print("     0 段不等于模型不写动作，只等于当时没开这个功能。")
        else:
            print("  → 回复里有括号样本，§1 可测（够不够看 §1 的分布，别只看有没有）。")

    if STAGE_DIRECTION is None:
        print("\n⚠ 取不到 guard.ResponseGuard._stage_direction，§1 跳过。")
    else:
        print("\n=== §1 动作堆叠（判据：括号块计数）===")
        buckets = collections.Counter()
        multi = []
        by_channel = collections.Counter()
        for row in rows:
            count = len(STAGE_DIRECTION.findall(row["reply"]))
            buckets[count] += 1
            if count >= 2:
                multi.append(row)
                by_channel[row["channel"]] += 1
        dist = "  ".join(f"{k} 段: {buckets[k]}" for k in sorted(buckets))
        print(f"  分布（全部 {len(rows)} 回合）：{dist}")
        total_multi = sum(by_channel.values())
        print(f"  ≥2 段：{total_multi} 回合（{(total_multi / len(rows) * 100) if rows else 0:.1f}%）  按 channel：{dict(by_channel)}")
        print(f"  ⚠ 判据只数括号块，**不含量级的语义判断** —— 「2 段」是否算堆叠仍需人读：")
        for row in multi[: args.samples]:
            print(f"    [{row['caseId']}] {clip(row['reply'], 96)}")

    print("\n=== §2 泛泛反问（只摊开，不判定）===")
    ask_total = generic = substantive = 0
    generic_samples = []
    for row in rows:
        if not bq._CONVERSATION_LEAD_QUESTION_PATTERN.search(row["reply"]):
            continue
        ask_total += 1
        tail = row["reply"].strip()
        if bq._CONVERSATION_LEAD_GENERIC_QUESTION_PATTERN.search(tail):
            generic += 1
            generic_samples.append(row)
        else:
            substantive += 1
    print(f"  含问句回合 {ask_total}：泛泛反问 {generic} / 实质追问 {substantive}")
    print("  泛泛反问样本：")
    for row in generic_samples[: args.samples]:
        print(f"    [{row['caseId']}] 玩家「{clip(row['input'], 34)}」→ {clip(row['reply'], 72)}")

    print("\n=== §3 主动换题（只摊开，不判定）===")
    answered = sum(1 for r in rows if bq._conversation_topic_answered(r["input"], r["reply"]))
    switched = []
    for row in rows:
        if not row["input"].strip() or not row["reply"].strip():
            continue
        if not bq._conversation_topic_answered(row["input"], row["reply"]):
            continue
        anchors = bq.conversation_lead_anchors(row["input"], row["reply"])
        prior = bq._conversation_lead_anchor_candidates(row["input"])
        if bq.conversation_lead_has_new_anchor(anchors, prior, previous_skeleton=row["input"]):
            switched.append(row)
    print(f"  答上题 {answered} / {len(rows)}（重算值，用于与产物的 answeredCurrentTopic 对账）")
    print(f"  「答上题 + 引入新锚点」= 换题候选 {len(switched)}")
    for row in switched[: args.samples]:
        print(f"    [{row['caseId']}] 玩家「{clip(row['input'], 30)}」→ {clip(row['reply'], 76)}")

    print("\n=== §4 量词-状态问句：假阴性量化（核心）===")
    hits = [
        r
        for r in rows
        if r["input"].strip()
        and r["reply"].strip()
        and QUANTITY_STATUS_QUESTION.search(r["input"])
    ]
    print(f"  命中的回合：{len(hits)}")
    if not hits:
        print("  ⚠ 本批没有量词-状态问句 —— 说明这批数据**验不了**这条假阴性，别据此说「没问题」。")
        return 0

    flip_q = collections.Counter()
    flip_qr = collections.Counter()
    detail = []
    for row in hits:
        now = bq._conversation_topic_answered(row["input"], row["reply"])
        only_q = simulate(PROPOSED_QUESTION, None, row["input"], row["reply"])
        q_and_r = simulate(PROPOSED_QUESTION, PROPOSED_REPLY, row["input"], row["reply"])
        flip_q[(now, only_q)] += 1
        flip_qr[(now, q_and_r)] += 1
        detail.append((row, now, only_q, q_and_r))

    def matrix(counter: collections.Counter) -> str:
        f2t = sum(v for (a, b), v in counter.items() if not a and b)
        t2f = sum(v for (a, b), v in counter.items() if a and not b)
        same = sum(v for (a, b), v in counter.items() if a == b)
        return f"False→True {f2t} / True→False {t2f} / 不变 {same}"

    print(f"  现状判 True：{sum(1 for _, n, _, _ in detail if n)} / {len(detail)}")
    print(f"  提案 A（只扩 QUESTION）：{matrix(flip_q)}")
    print(f"  提案 B（再扩 REPLY）　：{matrix(flip_qr)}")
    print("  逐条（输入 / 回复 / 现状 / A / B）：")
    for row, now, only_q, q_and_r in detail[: max(args.samples, 20)]:
        print(f"    [{row['caseId']}@{row['src']}|{row['provider']}] 「{clip(row['input'], 40)}」")
        print(f"        答：「{clip(row['reply'], 80)}」  现状={now} A={only_q} B={q_and_r}")
    print("  ⚠ 反向验证（改判据前必做）：提案版对**真没回答**的样本必须仍判 False；")
    print("    若 True→False 或大量无关样本翻成 True，说明判据在系统性偏移，不能采纳。")

    print("\n=== §5 case 级复原（对账 2026-10-08 登记的 13.3% vs 93.3%）===")
    by_case: dict[str, list[int]] = {}
    for row in rows:
        value = row.get("caseAnswered")
        if value is None:
            continue
        slot = by_case.setdefault(str(row["caseId"]), [0, 0])
        slot[0] += 1
        if value:
            slot[1] += 1
    focus = (
        "harvey-close-gesture",
        "harvey-close-clinic",
        "elliott-close-gesture",
        "elliott-close-topic-control",
        "sam-stranger-topic-control",
    )
    for case_id in focus:
        total, hit = by_case.get(case_id, (0, 0))
        rate = f"{hit / total * 100:.1f}%" if total else "N/A（这批里没有）"
        print(f"  {case_id}: {hit}/{total} = {rate}   ← 产物里原生的 case 级 answeredCurrentTopic")
    print("  ⚠ 与 §3 的「重算值」口径不同：这里读的是**产物里已经写下的**判定。")
    print("     两者对不上 = 判据在数据与当前代码之间漂移过，别混用。")

    print("\n=== §5b 同一 case 的 **turn 级**口径（引用数字前必须先说清是哪一种）===")
    by_turn: dict[str, list[int]] = {}
    for row in rows:
        value = row.get("answered")
        if value is None:
            continue
        slot = by_turn.setdefault(str(row["caseId"]), [0, 0])
        slot[0] += 1
        if value:
            slot[1] += 1
    for case_id in focus:
        total, hit = by_turn.get(case_id, (0, 0))
        rate = f"{hit / total * 100:.1f}%" if total else "N/A（这批里没有）"
        print(f"  {case_id}: {hit}/{total} = {rate}   ← turn 级 answeredCurrentTopic")
    print("  ⚠ case 级与 turn 级**数值不一样**（一个 case 含多个 turn，且 turn 级字段可能为 null）。")
    print("     同一批数据能按两种口径读出两个都「看起来对」的百分比 —— 引用「答上题率」")
    print("     而不写口径，是 2026-10-08 那组数字对不上的最可能原因。")

    print("\n=== §6 提案 B 的影响面：全量外溢检查（这是真正的反向验证）===")
    inside, spill_f2t, spill_t2f = 0, [], []
    for row in rows:
        if not row["input"].strip() or not row["reply"].strip():
            continue
        now = bq._conversation_topic_answered(row["input"], row["reply"])
        after = simulate(PROPOSED_QUESTION, PROPOSED_REPLY, row["input"], row["reply"])
        if now == after:
            continue
        if QUANTITY_STATUS_QUESTION.search(row["input"]):
            inside += 1
        elif after:
            spill_f2t.append(row)
        else:
            spill_t2f.append(row)
    print(f"  在全部 {len(rows)} 回合上重算，翻转如下：")
    print(f"    落在量词-状态问句上的 False→True：{inside}   ← 这是**修好的**（目标内）")
    print(f"    外溢到其它输入的 False→True　　：{len(spill_f2t)}   ← 必须为 0，否则判据在放宽")
    print(f"    外溢的 True→False　　　　　　　：{len(spill_t2f)}   ← 必须为 0，否则有误伤")
    for row in (spill_f2t + spill_t2f)[:10]:
        print(f"      [{row['caseId']}@{row['src']}] 「{clip(row['input'], 36)}」→ {clip(row['reply'], 60)}")
    print("  ⚠ 影响面之所以天然受限：REPLY 侧常量**只在** L1304 那条「输入匹配 QUESTION」")
    print("     的分支里被使用 ⇒ 扩它不会碰到别的判定通道。上面的计数是这一点的实测证据。")
    print("     ⚠ 但上面的「外溢」若不为 0，逐条看：`还好吗` 类输入 + 回复里恰好出现时间词")
    print("       （「前两天」「二十分钟」）会被误判成答上题 —— 那是**假阳性**，不是修好。")

    print("\n=== §7 同批内对照（跨批比较会混入时间 / provider / 设置差异）===")
    by_src: dict[str, dict[str, list[int]]] = {}
    for row in rows:
        value = row.get("answered")
        if value is None:
            continue
        slot = by_src.setdefault(row["src"], {}).setdefault(str(row["caseId"]), [0, 0])
        slot[0] += 1
        if value:
            slot[1] += 1
    pairs = 0
    for src in sorted(by_src):
        gesture = by_src[src].get("harvey-close-gesture")
        clinic = by_src[src].get("harvey-close-clinic")
        if not gesture or not clinic:
            continue
        pairs += 1
        print(f"  [{src}]  gesture {gesture[1]}/{gesture[0]}  vs  clinic {clinic[1]}/{clinic[0]}")
    print(f"  同时含两个 case 的批：{pairs} 个")
    print("  ⚠ 只有**同一批**里同时出现两个 case 时，这个对比才排除了批次差异；")
    print("     把各批混在一起算（§5/§5b 的做法）得到的是**跨批混合值**，不能当干净对照。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
