"""把 `voiceCards[*].voiceAnchors` 里的事件锚点补上 `eventId`（离线回填）。

## 为什么需要它

`speech._voice_anchor_candidates` 在 2026-09-29 之前**没有**把 `eventId` 放进锚点
（只放 `sampleId`/`sourceMod`/`text`/`sourceKey`/`evidenceKind`），于是运行时
`ProfileIndexStore.voice_card` 无法对这些锚点做事件门控：
**60 个角色的锚点全部无法门控**，其中 34 个角色的锚点会全空、31 个只有事件语料。
实测见 `.scratch/probe-voice-card-gate.py`。

构建期已经补上该字段，但**重建 16MB 索引要先复原整套构建输入**（persona-dir、
多个 corpus、vanilla 三套解包根、mod 根，缺一个直接 return 2）。
而锚点自带 `sampleId`，`speechEvidence` / `styleSamples` 里有同 id 的完整记录
（含 `eventId`）—— 实测 **237/237 命中且都带 id** ⇒ 离线回填即可。

## 用法

    python -B scripts/backfill_voice_anchor_event_ids.py \
        --index  data/generated/xxx.json \
        --output data/generated/xxx.with-anchor-eventids.json

不覆盖 `--index`：输出必须是另一个路径。
只补**缺**的字段，已有 `eventId` 的锚点原样保留；其余内容逐字节不变。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="给语气锚点的事件对白回填 eventId（不重建索引）"
    )
    parser.add_argument("--index", required=True, type=Path, help="源索引 JSON")
    parser.add_argument("--output", required=True, type=Path, help="输出索引 JSON")
    return parser


def _sample_index(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for field in ("speechEvidence", "styleSamples"):
        records = payload.get(field)
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, Mapping):
                continue
            sample_id = record.get("sampleId")
            if isinstance(sample_id, str) and sample_id.strip():
                by_id.setdefault(sample_id.strip(), record)
    return by_id


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.index.resolve() == args.output.resolve():
        print("refusing to overwrite the source index; pass a different --output", file=sys.stderr)
        return 2
    if not args.index.is_file():
        print(f"index not found: {args.index}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(args.index.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"cannot read index: {error}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("index root is not an object", file=sys.stderr)
        return 2

    by_id = _sample_index(payload)
    cards = payload.get("voiceCards")
    if not isinstance(cards, Mapping):
        print("index has no voiceCards mapping", file=sys.stderr)
        return 2

    filled = 0
    already = 0
    missing = 0
    other = 0
    touched_cards: set[str] = set()
    missing_samples: list[str] = []

    for npc_id, card in cards.items():
        if not isinstance(card, Mapping):
            continue
        anchors = card.get("voiceAnchors")
        if not isinstance(anchors, list):
            continue
        for anchor in anchors:
            if not isinstance(anchor, dict):
                continue
            if str(anchor.get("evidenceKind", "")).strip().casefold() != "event_dialogue":
                other += 1
                continue
            if isinstance(anchor.get("eventId"), str) and anchor["eventId"].strip():
                already += 1
                continue
            sample_id = str(anchor.get("sampleId", "")).strip()
            record = by_id.get(sample_id)
            event_id = record.get("eventId") if isinstance(record, Mapping) else None
            if isinstance(event_id, str) and event_id.strip():
                anchor["eventId"] = event_id.strip()
                filled += 1
                touched_cards.add(str(npc_id))
            else:
                missing += 1
                if len(missing_samples) < 5:
                    missing_samples.append(sample_id)

    # 保持与构建器一致的写法（非 ASCII 直出），便于和源文件逐字段比对。
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"written: {args.output}")
    print(
        f"event_dialogue 锚点：补上 eventId {filled} 条（涉及 {len(touched_cards)} 个角色）；"
        f"原本就有 {already}；查不到样本 {missing}；非事件锚点 {other}"
    )
    if missing_samples:
        print("  查不到样本的样例：" + "、".join(missing_samples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
