#!/usr/bin/env python3
"""导出已解包 vanilla / Content Patcher JSON 的统一对白语料。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "bridge" / "src"))

from stardew_ai_bridge.corpus import build_dialogue_corpus, write_dialogue_corpus  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vanilla-root",
        type=Path,
        help="已解包的 Content/Characters/Dialogue JSON 根目录",
    )
    parser.add_argument(
        "--mod-root",
        type=Path,
        action="append",
        default=[],
        help="Content Patcher mod 根目录，可重复传入",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="输出 JSON 路径",
    )
    parser.add_argument(
        "--locale",
        default="zh-CN",
        help="解析 Content Patcher i18n 时优先使用的语言，默认 zh-CN",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    corpus = build_dialogue_corpus(
        vanilla_root=args.vanilla_root,
        mod_roots=args.mod_root,
        locale=args.locale,
        vanilla_locale=args.locale,
    )
    write_dialogue_corpus(corpus, args.output)
    for warning in corpus["warnings"]:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(
        f"dialogue corpus written: {args.output} "
        f"records={len(corpus['records'])} warnings={len(corpus['warnings'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
