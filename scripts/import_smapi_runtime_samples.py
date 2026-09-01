#!/usr/bin/env python3
"""把 SMAPI 运行时对白标记导入为幂等 JSONL 样本。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "bridge" / "src"))

from stardew_ai_bridge.runtime_samples import (  # noqa: E402
    append_runtime_sample,
    attribute_runtime_sample,
)


MARKER = "[StardewAI.RuntimeDialogueSample]"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--corpus",
        type=Path,
        help="可选的 dialogue corpus；仅唯一命中时补回静态来源",
    )
    return parser


def _load_corpus_records(path: Path | None) -> list[dict[str, object]]:
    if path is None:
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 corpus：{path}：{exc}") from exc
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError(f"corpus 缺少 records 列表：{path}")
    return [item for item in records if isinstance(item, dict)]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        corpus_records = _load_corpus_records(args.corpus)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    captured = 0
    invalid = 0
    for log_path in args.log:
        if not log_path.is_file():
            print(f"log not found: {log_path}", file=sys.stderr)
            return 2
        for line_number, line in enumerate(
            log_path.read_text(encoding="utf-8", errors="replace").splitlines(),
            start=1,
        ):
            marker_index = line.find(MARKER)
            if marker_index < 0:
                continue
            raw_json = line[marker_index + len(MARKER) :].strip()
            try:
                payload = json.loads(raw_json)
                if corpus_records:
                    payload = attribute_runtime_sample(payload, corpus_records)
                append_runtime_sample(args.output, payload)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                invalid += 1
                print(
                    f"invalid runtime sample {log_path.name}:{line_number}: {exc}",
                    file=sys.stderr,
                )
                continue
            captured += 1
    print(f"runtime samples imported: {captured} invalid={invalid} output={args.output}")
    return 0 if invalid == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
