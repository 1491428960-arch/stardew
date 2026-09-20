"""量化「对白证据长度窗口」与「知识事实筛选」的影响面（只读）。

背景（docs/semantic-duplication-audit-2026-09-20.md，P1 第 26、27 条）：

- 第 26 条：voiceAnchors 在生成侧是 6–80 字，群聊声线卡却把 >60 字的锚点静默丢弃，
  于是 61–80 字之间的合格锚点在群聊侧不可见。
- 第 27 条：knowledgeFacts 走 scope + confidence + 事件门控，而玩家的
  RecentMemoryFacts 只按时间取 6 条；本脚本统计索引侧 knowledgeFacts 的
  scope／confidence／requiredEventId 分布，给出「门控到底拦掉多少」的实测数字。

本脚本**只读索引**，不写任何文件、不联网。

用法：

    PYTHONPATH=bridge/src;scripts python -B scripts/audit_semantic_windows.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge" / "src"))

from stardew_ai_bridge.prompts import (  # noqa: E402
    MEMORY_FACT_CONFIDENCE_FLOOR,
    select_memory_facts,
)
from stardew_ai_bridge.speech import (  # noqa: E402
    VOICE_ANCHOR_MAX_TEXT,
    VOICE_ANCHOR_MIN_TEXT,
)

DEFAULT_INDEX = (
    ROOT
    / "data"
    / "generated"
    / "vanilla-sve-rasmodia-profile-index-zh-CN.next-event-dialogue.json"
)

# 群聊声线卡每个参与者最多采用两条锚点（prompts.build_group_voice_cards）。
GROUP_ANCHOR_LIMIT = 2
EVIDENCE_TEXT_LIMIT = 100


def _length_bucket(length: int) -> str:
    if length < VOICE_ANCHOR_MIN_TEXT:
        return f"<{VOICE_ANCHOR_MIN_TEXT}"
    if length <= 60:
        return f"{VOICE_ANCHOR_MIN_TEXT}-60"
    if length <= VOICE_ANCHOR_MAX_TEXT:
        return f"61-{VOICE_ANCHOR_MAX_TEXT}（旧群聊丢弃）"
    if length <= EVIDENCE_TEXT_LIMIT:
        return f"{VOICE_ANCHOR_MAX_TEXT + 1}-{EVIDENCE_TEXT_LIMIT}"
    return f">{EVIDENCE_TEXT_LIMIT}"


def _group_window(text: str) -> bool:
    """旧群聊判定：`len(text) > 60` 直接丢弃。"""

    return VOICE_ANCHOR_MIN_TEXT <= len(text.strip()) <= 60


def _new_window(text: str) -> bool:
    return VOICE_ANCHOR_MIN_TEXT <= len(text.strip()) <= VOICE_ANCHOR_MAX_TEXT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    args = parser.parse_args()

    path = pathlib.Path(args.index)
    if not path.is_file():
        print(f"找不到索引：{path}")
        return 2
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(f"索引：{path.name}（{path.stat().st_size / 1024 / 1024:.2f} MB）")
    print()

    # ── 第 26 条：voiceAnchors 长度分布 ────────────────────────────────
    cards = payload.get("voiceCards") or {}
    anchor_lengths: list[int] = []
    for card in cards.values():
        if not isinstance(card, dict):
            continue
        for anchor in card.get("voiceAnchors") or ():
            text = anchor.get("text") if isinstance(anchor, dict) else None
            if isinstance(text, str) and text.strip():
                anchor_lengths.append(len(text.strip()))
    print(f"voiceCards：{len(cards)} 张，voiceAnchors：{len(anchor_lengths)} 条")
    if anchor_lengths:
        buckets = Counter(_length_bucket(length) for length in anchor_lengths)
        for name, count in sorted(buckets.items()):
            print(f"  {name:<24} {count:>5} 条")
        in_new_window = sum(1 for length in anchor_lengths if VOICE_ANCHOR_MIN_TEXT <= length <= VOICE_ANCHOR_MAX_TEXT)
        in_old_window = sum(1 for length in anchor_lengths if _group_window("x" * length))
        print(
            f"  群聊可见（旧 ≤60）：{in_old_window} / {len(anchor_lengths)}"
            f"（{in_old_window / len(anchor_lengths) * 100:.1f}%）"
        )
        print(
            f"  群聊可见（新 ≤{VOICE_ANCHOR_MAX_TEXT}）：{in_new_window} / {len(anchor_lengths)}"
            f"（{in_new_window / len(anchor_lengths) * 100:.1f}%）"
        )
        print(f"  新增可见：{in_new_window - in_old_window} 条")

        # 群聊每个参与者只取前两条锚点：这两条里有多少来自新增窗口？
        adopted_old = adopted_new = 0
        affected_cards = 0
        for card in cards.values():
            if not isinstance(card, dict):
                continue
            texts = [
                str(anchor.get("text", "")).strip()
                for anchor in (card.get("voiceAnchors") or ())
                if isinstance(anchor, dict)
                and isinstance(anchor.get("text"), str)
                and str(anchor.get("text", "")).strip()
            ]
            old_pick = [t for t in texts if _group_window(t)][:GROUP_ANCHOR_LIMIT]
            new_pick = [t for t in texts if _new_window(t)][:GROUP_ANCHOR_LIMIT]
            adopted_old += len(old_pick)
            adopted_new += len(new_pick)
            if old_pick != new_pick:
                affected_cards += 1
        print(
            f"  群聊实际采用（每卡前 {GROUP_ANCHOR_LIMIT} 条）：{adopted_old} → {adopted_new} 条"
            f"（{affected_cards} / {len(cards)} 张卡的锚点集合发生变化）"
        )

    # ── 第 26 条（续）：speechEvidence 文本长度分布 ─────────────────────
    evidence = payload.get("speechEvidence") or []
    evidence_lengths = [
        len(str(item.get("text", "")).strip())
        for item in evidence
        if isinstance(item, dict) and str(item.get("text", "")).strip()
    ]
    print()
    print(f"speechEvidence：{len(evidence)} 条（非空文本 {len(evidence_lengths)} 条）")
    if evidence_lengths:
        buckets = Counter(_length_bucket(length) for length in evidence_lengths)
        for name, count in sorted(buckets.items()):
            share = count / len(evidence_lengths) * 100
            print(f"  {name:<24} {count:>6} 条（{share:5.1f}%）")
        outside_generation_window = sum(
            1 for length in evidence_lengths if length > VOICE_ANCHOR_MAX_TEXT
        )
        print(
            f"  超出生成侧 {VOICE_ANCHOR_MIN_TEXT}–{VOICE_ANCHOR_MAX_TEXT} 窗口："
            f"{outside_generation_window} 条"
            f"（{outside_generation_window / len(evidence_lengths) * 100:.1f}%）"
        )

    # ── 第 27 条：knowledgeFacts 门控分布 ──────────────────────────────
    facts = payload.get("knowledgeFacts") or []
    print()
    print(f"knowledgeFacts：{len(facts)} 条")
    scopes = Counter()
    confidences = Counter()
    with_required_event = 0
    passing: list[dict[str, object]] = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        scope = str(fact.get("knowledgeScope", "")).strip().casefold() or "(空)"
        confidence = str(fact.get("confidence", "")).strip().casefold() or "(空)"
        scopes[scope] += 1
        confidences[confidence] += 1
        required_event = fact.get("requiredEventId")
        has_event = isinstance(required_event, str) and required_event.strip()
        if has_event:
            with_required_event += 1
        if scope in {"canon_confirmed", "runtime_confirmed", "player_provided"} and confidence != "low":
            passing.append(fact)
    print("  knowledgeScope：", dict(scopes.most_common()))
    print("  confidence：", dict(confidences.most_common()))
    print(f"  带 requiredEventId：{with_required_event} 条")
    print(
        f"  通过 scope + confidence 门控：{len(passing)} / {len(facts)} 条"
        f"（{len(passing) / max(len(facts), 1) * 100:.1f}%）"
    )

    # 第 27 条：Bridge 侧统一实现的实际效果——knowledgeFacts 走同一套准入
    # 会拦掉多少？（这些字段此前只有知识事实那条通道在读。注意索引侧的
    # `confidence` 是 high/medium/low 字面量，与 SMAPI 的 0–1 数值必须换算到
    # 同一把尺子上；`select_memory_facts` 两种形态都认。）
    before = len(passing)
    after = len(select_memory_facts(passing, npc_id=""))
    print(
        f"  再过 Bridge 侧统一准入（select_memory_facts）：{before} → {after} 条"
        f"（准入下限 confidence ≥ {MEMORY_FACT_CONFIDENCE_FLOOR}）"
    )

    # ── 第 25 条：样本阶段条件的来源 ──────────────────────────────────
    print()
    conditional = 0
    inferred_only = 0
    for item in evidence:
        if not isinstance(item, dict):
            continue
        conditions = item.get("conditions")
        stage = ""
        if isinstance(conditions, dict):
            stage = str(conditions.get("relationshipStage", "")).strip()
        if stage:
            conditional += 1
        elif str(item.get("sourceKey", "")).strip():
            inferred_only += 1
    print(f"speechEvidence 中带显式 relationshipStage：{conditional} 条")
    print(f"无显式阶段但可按 sourceKey 推断：{inferred_only} 条")


if __name__ == "__main__":
    raise SystemExit(main())

