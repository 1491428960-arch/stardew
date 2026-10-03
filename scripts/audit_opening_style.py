#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""开场方式与说话指纹盘点：模型输出 vs 同角色原版语料。**零云端请求。**

用法（在 worktree 根，PYTHONPATH 需三者：`<worktree>;<worktree>/bridge/src;<worktree>/scripts`）::

    python -B scripts/audit_opening_style.py
    python -B scripts/audit_opening_style.py --run artifacts/character-quality-eval/<ts>

它读已有的评测产物（`results.jsonl` 的 `turns[].reply`），与
`facet_probe_common.corpus()` 里的原版语料对照。

**判据沿用 2026-09-26 tone 审计的同一组正则**（原脚本 `.tmp/tone-baseline.py`），
刻意不新造定义，这样不同时期的数字才可比。

⚠ **口径**：语料侧是 `styleSamples` 全部（10182 条 / 137 NPC）里与受测角色同名的子集，
**含事件与婚姻台词**，不是只有 `Characters/Dialogue/`
（`profile-index.json` 里没有该目录的 `sampleId`，窄口径取不到）。
这会让语料基线偏高，但缺口方向不受影响 —— 引用数字时请一并说明。
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys


# ---------------------------------------------------------------------------
# 判据（与 .tmp/tone-baseline.py 保持一致，勿单独改）
# ---------------------------------------------------------------------------

SELF_START = re.compile(r"^[\s，。…、—-]*我")
SECOND_PERSON_START = re.compile(r"^[\s，。…、—-]*你")
SELF_STATE = re.compile(
    r"我(?:想|觉得|感觉|怕|喜欢|不喜欢|习惯|得|要|不想|不能|总是|知道|明白|"
    r"只是|也|还|不|没|会|能|应该|宁愿|后悔|担心|舍不得)"
)
ECHO_ASK = re.compile(r"你呢|你那边|你这边|怎么样？\s*$|\?\s*$|？\s*$")
TIME_WORD = re.compile(
    r"昨天|今天|今早|今晚|昨晚|这两天|刚才|刚|早上|下午|明天|前几|每年|"
    r"春天|这一周|这周"
)
REPORT_VERB = re.compile(
    r"整理|检查|核对|清点|修|收拢|查看|翻|归档|归类|处理|布置|补|记下|盘算|"
    r"收拾|打理|走访|巡察|维护|疏通"
)

COLLOQUIAL = "呀呢吧啊啦嘛哦嗯咦哎唉哟哇嘿嘶"
SIMILE = ("像", "好像", "仿佛", "似的")
FEELING = ("我觉得", "我想", "我猜", "我不知道", "我大概", "我似乎", "我不敢")
SENSE = ("闻着", "味道", "颜色", "声音", "感觉", "看着", "清亮")

SENTENCE_SPLIT = re.compile(r"[。！？…]+")

#: 开场归类，**顺序即优先级**（只归第一类命中）。
OPENING_CATEGORIES: tuple[tuple[str, re.Pattern[str] | None], ...] = (
    ("我-自我立场", SELF_START),
    ("你-直接对话", SECOND_PERSON_START),
    (
        "时间词",
        re.compile(
            r"^[\s，。…、—-]*(?:昨天|今天|今早|今晚|昨晚|这两天|刚才|早上|"
            r"下午|明天|最近|前几天|每年|春天|这周|这一周)"
        ),
    ),
    (
        "语气词起",
        re.compile(r"^[\s，。…、—-]*(?:嗯|哦|呀|嘿|啊|唉|唔|呃|哈|咦|哎|喂|哇|嘶|噢|诶)[\s，。…、—-]"),
    ),
    (
        "名字/称谓起",
        re.compile(r"^[\s，。…、—-]*(?:嘿|喂)?\s*(?:亲爱的|孩子|年轻人|先生|小姐|老朋友)"),
    ),
    ("其他-动作环境", None),  # 兜底
)

DEFAULT_RUN = "20260930-234319"


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def _ensure_import_paths() -> pathlib.Path:
    root = _repo_root()
    for extra in (str(root), str(root / "bridge" / "src"), str(root / "scripts")):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    return root


def classify_opening(text: str) -> str | None:
    """把一条回复的第一句归到开场类别；空文本返回 None。"""

    stripped = text.replace("\n", "").strip()
    if not stripped:
        return None
    for name, pattern in OPENING_CATEGORIES:
        if pattern is None:
            return name
        if pattern.match(stripped):
            return name
    return "其他-动作环境"


def _density(text: str, needles: tuple[str, ...] | str) -> int:
    if isinstance(needles, str):
        return sum(text.count(ch) for ch in needles)
    return sum(text.count(word) for word in needles)


def load_model_replies(run_dir: pathlib.Path) -> tuple[list[str], set[str]]:
    """读 `results.jsonl`，返回（非空回复, 受测 NPC 名集合）。"""

    path = run_dir / "results.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    replies: list[str] = []
    npc_ids: set[str] = set()
    for case in cases:
        npc_id = case.get("npcId")
        if isinstance(npc_id, str) and npc_id:
            npc_ids.add(npc_id)
        for turn in case.get("turns") or []:
            reply = str(turn.get("reply") or "")
            if reply.strip():
                replies.append(reply)
    return replies, npc_ids


def load_corpus_replies(npc_ids: set[str]) -> list[str]:
    """取语料里与受测角色同名的样本。"""

    from facet_probe_common import corpus  # noqa: PLC0415  （需 scripts 在路径上）

    return [
        str(text)
        for npc, text in corpus()
        if npc in npc_ids and str(text).strip()
    ]


def report_metric(label: str, hits: int, total: int, other: int, other_total: int) -> None:
    a = hits / total * 100 if total else 0.0
    b = other / other_total * 100 if other_total else 0.0
    print(f"  {label:<12} 模型 {a:6.1f}%   语料 {b:6.1f}%   差 {a - b:+6.1f}pt")


def main() -> int:
    parser = argparse.ArgumentParser(description="开场方式与说话指纹盘点（零请求）")
    parser.add_argument(
        "--run",
        default=None,
        help=f"artifact 目录（默认 artifacts/character-quality-eval/{DEFAULT_RUN}）",
    )
    args = parser.parse_args()

    root = _ensure_import_paths()
    run_dir = pathlib.Path(args.run) if args.run else (
        root / "artifacts" / "character-quality-eval" / DEFAULT_RUN
    )
    if not (run_dir / "results.jsonl").is_file():
        print(f"找不到 {run_dir / 'results.jsonl'}", file=sys.stderr)
        return 2

    model, npc_ids = load_model_replies(run_dir)
    corpus_replies = load_corpus_replies(npc_ids)
    if not model or not corpus_replies:
        print("样本不足，无法对照", file=sys.stderr)
        return 2

    nm, nc = len(model), len(corpus_replies)
    print(f"run      : {run_dir}")
    print(f"模型侧   : {nm} 条非空回复")
    print(f"语料侧   : {nc} 条（{len(npc_ids)} 个同名角色，⚠ 含事件/婚姻台词）")

    # --- 1. 开场类型分布 ---------------------------------------------------
    print("\n== 开场类型分布（只归第一类命中）==")
    m_cnt = collections.Counter(classify_opening(t) for t in model)
    c_cnt = collections.Counter(classify_opening(t) for t in corpus_replies)
    print(f"  {'类型':<14} {'模型':>8} {'语料':>8} {'差':>9}")
    for name, _ in OPENING_CATEGORIES:
        a, b = m_cnt.get(name, 0) / nm * 100, c_cnt.get(name, 0) / nc * 100
        flag = " ⭐" if abs(a - b) >= 10 else ""
        print(f"  {name:<14} {a:7.1f}% {b:7.1f}% {a - b:+8.1f}pt{flag}")

    # --- 2. 说话指纹 -------------------------------------------------------
    print("\n== 说话指纹（首句/全句命中率）==")
    report_metric("我开头", sum(bool(SELF_START.match(t)) for t in model), nm,
                  sum(bool(SELF_START.match(t)) for t in corpus_replies), nc)
    report_metric("你开头", sum(bool(SECOND_PERSON_START.match(t)) for t in model), nm,
                  sum(bool(SECOND_PERSON_START.match(t)) for t in corpus_replies), nc)
    report_metric("自我状态", sum(bool(SELF_STATE.search(t)) for t in model), nm,
                  sum(bool(SELF_STATE.search(t)) for t in corpus_replies), nc)
    report_metric("反问", sum(bool(ECHO_ASK.search(t)) for t in model), nm,
                  sum(bool(ECHO_ASK.search(t)) for t in corpus_replies), nc)
    report_metric("时间词", sum(bool(TIME_WORD.search(t)) for t in model), nm,
                  sum(bool(TIME_WORD.search(t)) for t in corpus_replies), nc)
    report_metric("事务动词", sum(bool(REPORT_VERB.search(t)) for t in model), nm,
                  sum(bool(REPORT_VERB.search(t)) for t in corpus_replies), nc)

    # --- 3. 密度指标（每 100 字，避免被长度稀释）---------------------------
    print("\n== 密度（每 100 字）==")
    m_chars = sum(len(t) for t in model) or 1
    c_chars = sum(len(t) for t in corpus_replies) or 1
    for label, needles in (
        ("语气词", COLLOQUIAL),
        ("比喻", SIMILE),
        ("感受", FEELING),
        ("感官", SENSE),
        ("问号", ("？", "?")),
    ):
        a = _density("".join(model), needles) / m_chars * 100
        b = _density("".join(corpus_replies), needles) / c_chars * 100
        print(f"  {label:<8} 模型 {a:5.2f}   语料 {b:5.2f}   差 {a - b:+5.2f}")

    # --- 4. 长度与句数 -----------------------------------------------------
    print("\n== 长度与句数 ==")
    for label, rows in (("模型", model), ("语料", corpus_replies)):
        lengths = sorted(len(t) for t in rows)
        n = len(lengths)
        pct = lambda p: lengths[min(n - 1, int(n * p))]  # noqa: E731
        over40 = sum(1 for x in lengths if x > 40) / n * 100
        over68 = sum(1 for x in lengths if x > 68) / n * 100
        counts = [len([s for s in SENTENCE_SPLIT.split(t) if s.strip()]) for t in rows]
        many = sum(1 for c in counts if c >= 4) / n * 100
        print(
            f"  {label}: 均值 {sum(lengths) / n:5.1f}  中位 {pct(0.5):3d}  "
            f"p90 {pct(0.9):3d}  超40字 {over40:5.1f}%  超68字 {over68:5.1f}%  "
            f"4句+ {many:5.1f}%"
        )

    print("\n⚠ 单 run 不确定度约 ±10pt（见 docs/STATE.md §七末之二）：")
    print("   差值小于 10 点的指标不要当结论用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
